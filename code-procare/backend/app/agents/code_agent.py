from typing import Dict
from pathlib import Path
import re
import json

from ..core.react_loop import ReActLoop
from ..services.executor import CodeExecutor
from ..core.llm import LLMClient
from ..core.skill_manager import SkillManager
from ..skills.code_generation.utils import extract_code_block


class CodeAgent:
    def __init__(self, job_dir: str):
        self.job_dir = Path(job_dir)
        self.plots_dir = self.job_dir / "plots"
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        self.llm = LLMClient()
        self.skill_manager = SkillManager()

    def _initial_code(self, excel_path: str, excel_info: Dict, plan: Dict) -> str:
        # 回退模板：通用EDA，不进行任务特定的硬编码分析，保证可运行与输出基础图表
        code = f"""
        import pandas as pd
        import matplotlib.pyplot as plt
        import os

        excel_path = r"{excel_path}"
        out_dir = r"{self.plots_dir}"
        os.makedirs(out_dir, exist_ok=True)

        print("[INFO] Loading excel:", excel_path)
        xls = pd.ExcelFile(excel_path)
        print("[INFO] Sheets:", xls.sheet_names)
        success_count = 0

        for s in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=s)
            print(f"[INFO] Sheet={{s}} shape=", df.shape)
            print("[INFO] Describe:\n", df.describe(include='all'))

            # 基础非空计数柱状图
            non_null_counts = df.notnull().sum()
            fig = plt.figure(figsize=(8, 3))
            non_null_counts.plot(kind='bar', title=f'Non-null counts: {{s}}')
            plt.tight_layout()
            plot_path = os.path.join(out_dir, f"{{s}}_non_null_counts.png")
            plt.savefig(plot_path)
            plt.close(fig)
            print("[INFO] Saved plot:", plot_path)
            success_count += 1

            # 对数值列画直方图（最多前4个）
            num_cols = df.select_dtypes(include=['number']).columns.tolist()[:4]
            for c in num_cols:
                plt.figure(figsize=(6, 4))
                df[c].dropna().plot(kind='hist', bins=30, title=f'{s} - {c} Distribution')
                plt.tight_layout()
                plot_path = os.path.join(out_dir, f"{{s}}_{{c}}_hist.png")
                plt.savefig(plot_path)
                plt.close()
                print("[INFO] Saved plot:", plot_path)
                success_count += 1
        if success_count > 0:
            print("TASK_DONE")
        else:
            print("TASK_FAILED")
        """
        return code

    def _llm_generate_code(self, excel_path: str, excel_info: Dict, plan: Dict) -> str:
        # 根据研究计划的objective与steps动态生成指令；强调模块化与稳定函数名，便于后续以补丁增量修复
        objective = str(plan.get("objective", "")).strip()
        steps = plan.get("steps", [])
        context = plan.get("context", {})
        # 检查steps是否为空
        if not steps:
            steps = ["基础EDA"]
            print(f"计划未指定steps，默认添加基础EDA步骤: {steps}")
        else: 
            print(f"计划指定steps: {steps}")
        
        # 统计各个变量的字符串长度
        vars_to_check = {
            "excel_path": excel_path,
            "output_dir": str(self.plots_dir),
            "plan.objective": objective,
            "plan.steps": steps,
            "plan.context": context
        }

        print("\n[DEBUG] --- Variable Length Statistics ---")
        for name, value in vars_to_check.items():
            try:
                value_str = str(value)
                print(f"{name}: length={len(value_str)} | value={value_str}")
            except Exception as e:
                print(f"{name}: <ERROR converting to string> ({e})")
        print("--------------------------------------------------\n")
        
        prompt = self.skill_manager.get_skill("code_generation").render(
            excel_path=excel_path,
            output_dir=str(self.plots_dir),
            plan_objective=objective,
            plan_steps=steps,
            plan_context=context,
            excel_info=excel_info
        )

        buf: list[str] = []
        code_result = self.llm.generate_stream(prompt, on_chunk=lambda c: buf.append(c or ""))
        full_text = code_result if code_result is not None else "" + "".join(buf)
        code = extract_code_block(full_text) or full_text
        # 去除可能残留的markdown围栏
        code = code.replace("```python", "").replace("```", "").strip()
        print(f"LLM生成代码: {code}")
        # 简单校验，如果LLM未返回代码，则回退模板
        if not code:
            print(f"LLM生成代码失败，回退初始代码: {code}")
            code = self._initial_code(excel_path=excel_path, excel_info=excel_info, plan=plan)
        return code

    def stream_initial_code_iter(self, excel_path: str, excel_info: Dict, plan: Dict):
        objective = str(plan.get("objective", "")).strip()
        steps = plan.get("steps", [])
        context = plan.get("context", {})
        if not steps:
            steps = ["基础EDA"]
        
        prompt = self.skill_manager.get_skill("code_generation").render(
            excel_path=excel_path,
            output_dir=str(self.plots_dir),
            plan_objective=objective,
            plan_steps=steps,
            plan_context=context,
            excel_info=excel_info
        )
        
        for chunk in self.llm.stream_iter(prompt):
            yield chunk



    def generate_and_execute(self, plan: Dict, excel_info: Dict, excel_path: str) -> Dict:
        # 生成初始代码（优先LLM）
        initial_code = self._llm_generate_code(excel_path=excel_path, excel_info=excel_info, plan=plan)
        # 保存初始代码
        code_path = self.job_dir / "analysis.py"
        code_path.write_text(initial_code, encoding="utf-8")

        # ReAct循环执行
        executor = CodeExecutor(work_dir=str(self.job_dir))
        # 根据sheet数量调整最大迭代次数，避免耗时过长
        sheets = excel_info.get("sheets", []) or []
        sheet_count = len(sheets)
        if sheet_count >= 12:
            max_iters = 8
        elif sheet_count >= 6:
            max_iters = 5
        else:
            max_iters = 3
        print(f"根据sheet数量({sheet_count})调整最大迭代次数为: {max_iters}")
        react = ReActLoop(max_iters=max_iters)
        result = react.run(
            initial_code=initial_code,
            executor=executor,
            context={
                "excel_info": excel_info,
                "plan": plan,
                "excel_path": excel_path,
                "plots_dir": str(self.plots_dir),
                "job_dir": str(self.job_dir),
            },
        )
        result.update({
            "code_path": str(code_path),
            "plots_dir": str(self.plots_dir),
        })
        return result