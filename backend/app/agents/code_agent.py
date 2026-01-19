from typing import Dict
from pathlib import Path
import re
import json

from ..core.react_loop import ReActLoop
from ..services.executor import CodeExecutor
from ..core.llm import LLMClient


class CodeAgent:
    def __init__(self, job_dir: str):
        self.job_dir = Path(job_dir)
        self.plots_dir = self.job_dir / "plots"
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        self.llm = LLMClient()

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
        guidance = (
            "【角色定位】\n"
            "- 你是ProCARE框架下的 Constrained Code Synthesizer。\n"
            "- 任务：基于详细计划(Pd)和数据画像(Phi)，生成满足静态和运行时约束的Python代码。\n\n"

            "【约束条件(Constraints)】\n"
            "1. 静态约束(Static): 代码必须符合Excel的物理结构(Sheet名, 列名)。\n"
            "   - 必须使用 excel_info.normalized_columns 进行列名匹配。\n"
            "   - 必须检查列是否存在，不存在则打印警告并跳过，禁止报错退出。\n"
            "2. 运行时约束(Runtime): 代码必须符合统计方法的假设。\n"
            "   - 使用 'knowledge' 画像中的 variable_roles 确定 Exposure/Outcome。\n"
            "   - 确保数据类型正确(如: 数值型变量不能含非数字字符，需清洗)。\n\n"

            "【核心原则】\n"
            "- 严格遵循研究计划 objective/steps，但在科学合理范围内允许主动扩展分析（附加验证、灵敏度分析、补充图表）。\n"
            "- 保持代码可维护性：模块化、函数名稳定、便于后续补丁最小化修改。\n"
            "- 所有分析必须可解释、可追踪：打印步骤、字段匹配过程、跳过原因。\n"
            "- 错误要明确打印，不因异常 silently fail。\n\n"

            "【字段匹配策略（极重要）】\n"
            "- 筛选数据时，确保对字段的鲁棒性匹配，能够处理大小写、空格、同义词、中英文等差异。\n"
            "- 每一次字段解析都必须打印：concept、found/not found、候选列名。\n"
            "- 所有字段解析逻辑必须与后续补丁兼容（保持最少耦合）。\n\n"

            "【分析策略（允许主动扩展）】\n"
            "- 逐步解析 plan.steps，并按步骤自动选择合理的数据分析方法，例如：\n"
            "  * 若检测到生存分析 → 绘制 K-M 曲线、风险表、分组比较。\n"
            "  * 若检测到治疗方案差异 → 生成分布图、分组统计、箱线图、风险比估计。\n"
            "  * 若检测到基线差异 → 生成描述性统计、热力图、相关矩阵。\n"
            "- 在不违背计划的前提下，可自动添加扩展分析：\n"
            "  * 数据质量评估（缺失值、异常值、稀疏度）。\n"
            "  * 字段一致性检查与补充日志。\n"
            "  * 附加的探索性图表（直方图、散点）。\n\n"

            "【输出日志要求】\n"
            "- 每个 Sheet 开始前打印：Sheet=<name> shape=<rows, cols>\n"
            "- 打印关键字段样例（来自 excel_info.profile.samples）。\n"
            "- 图表保存必须打印：Saved plot: <path>\n"
            "- 若完成至少一个有效分析输出图 → 打印 TASK_DONE\n"
            "- 若无任何图输出或发生致命错误 → TASK_FAILED\n\n"

            "【代码结构要求】\n"
            "- 使用 pandas/matplotlib 作为主要数据处理与可视化工具。\n"
            "- 必须包含可保持稳定的函数：\n"
            "  resolve_column(df, concepts)\n"
            "  analyze_sheet(df, sheet_name, info)\n"
            "  main()\n"
            "- 允许创建辅助函数（如 plot_km、plot_distribution），但主函数结构保持稳定。\n"
            "- 忽略 UserWarning，仅输出关键错误。\n\n"

            "【扩展能力】\n"
            "- 鼓励生成中间结果 CSV 文件，以便后续循环调试。\n"
            "- 允许根据计划推断额外必要的分析，而非机械照抄 steps。\n"
            "- 具有自恢复能力：遇到无效字段自动跳过，不影响整体执行。\n"
        )

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
        prompt = (
            "你是参与 ReAct 循环的代码生成 Agent。你的目标是："
            "结合 Excel 路径、结构画像 excel_info、研究计划（objective + steps），"
            "自动生成一段可以直接运行、稳健、易扩展、可维护的 Python 分析脚本。\n\n"

            f"{guidance}\n"

            "【输出要求】\n"
            "- 仅输出最终 Python 代码，不要添加解释、说明或 markdown 围栏。\n"
            "- 输出的代码必须可以直接运行。\n\n"

            "【算法于代码计划信息】\n"
            f"excel_path: {excel_path}\n"
            f"excel_info: {excel_info}\n"
            f"output_dir: {self.plots_dir}\n"
            f"plan: {plan}\n"
        )


        buf: list[str] = []
        code_result = self.llm.generate_stream(prompt, on_chunk=lambda c: buf.append(c or ""))
        full_text = code_result if code_result is not None else "" + "".join(buf)
        code = self._extract_code_block(full_text) or full_text
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
        guidance = (
            "- 阅读研究计划的objective与steps，提炼可执行的数据分析任务；\n"
            "- 遵循ProCARE框架的Constrained Code Synthesis原则，生成满足静态和运行时约束的代码；\n"
            "- 静态约束：严格按照 excel_info.normalized_columns 匹配列名，禁止幻觉；\n"
            "- 运行时约束：确保数据类型符合统计方法假设（如KM分析需数值型时间）；\n"
            "- 使用pandas/matplotlib完成数据处理和图表绘制；\n"
            "- 鼓励对筛选出的数据保存为CSV文件，方便后续分析；\n"
            "- 采用模块化结构并保持函数名稳定：resolve_column(df, concepts)、analyze_sheet(df, sheet_name, info)、main()；\n"
            "- 输出信息充分且可追踪的日志：\n"
            "  - 每个sheet开始打印：Sheet=<name> shape=<rows, cols>；\n"
            "  - 图表保存统一打印：Saved plot: <path>；\n"
            "  - 成功完成至少一个有效图表或任务达成时打印 'TASK_DONE'；失败或跳过打印 'TASK_FAILED'；\n"
            "- 图表保存到指定目录 /plots；\n"
            "- 字段处理必须稳健：\n"
            "  1) 基于 excel_info.normalized_columns 与 excel_info.synonyms_hint 构造 resolve_column(df, concepts) 函数；\n"
            "  2) 先尝试精确匹配列名，其次匹配标准化列名与别名；\n"
            "  3) 匹配失败时不要猜测，打印可用列并跳过该分析步骤；\n"
            "  4) 在stdout打印字段映射日志：Found/NotFound、候选concept、命中列名；\n"
            "- 在开始每个Sheet的分析前，打印Sheet名、形状、关键字段的示例值（来自 excel_info.profile.samples）；\n"
            "- 忽略UserWarning等非关键警告，仅保留关键错误；\n"
            "- 保持代码风格稳定，以便后续以小补丁进行增量修复；\n"
        )
        prompt = (
            "你是参与ReAct循环的代码生成Agent。请根据Excel路径、结构画像与研究计划，生成一段可直接运行且字段匹配稳健的Python脚本：\n"
            f"{guidance}"
            "- 仅输出代码，不要包含解释或markdown围栏。\n"
            f"excel_path: {excel_path}\n"
            f"output_dir: {self.plots_dir}\n"
            f"plan.objective: {objective}\n"
            f"plan.steps: {steps}\n"
            f"plan.context: {context}\n"
        )
        for chunk in self.llm.stream_iter(prompt):
            yield chunk

    def _extract_code_block(self, text: str) -> str | None:
        if not text:
            return None
        m = re.search(r"```python\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"```\s*(.*?)```", text, flags=re.DOTALL)
        if m:
            return m.group(1).strip()
        return None

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