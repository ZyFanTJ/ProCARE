from typing import Dict, Optional
from pathlib import Path
import json
import re
# 支持作为脚本直接运行的导入回退逻辑
try:
    from .llm import LLMClient
    from ..services.diff_apply import (
        apply_patch_text,
        is_apply_patch_text,
        apply_replace_in_file_text,
        is_replace_in_file_text,
    )
except Exception:
    import sys
    from pathlib import Path as _Path
    sys.path.append(str(_Path(__file__).resolve().parents[1]))  # 将 app 目录加入路径
    from llm import LLMClient
    from services.diff_apply import (
        apply_patch_text,
        is_apply_patch_text,
        apply_replace_in_file_text,
        is_replace_in_file_text,
    )


class ReActLoop:
    """
    简化版ReAct循环框架：
    - 尝试运行初始代码；失败则通过LLM生成修复思路（占位），并可迭代若干次。
    - 为了示例可运行，默认最大迭代=1，且不进行自动修复（防止无LLM出错）。
    """

    def __init__(self, max_iters: int = 1):
        self.max_iters = max_iters
        self.llm = LLMClient()

    def run(self, initial_code: str, executor, context: Optional[Dict] = None) -> Dict:
        logs = []
        events = []
        code = initial_code
        success = False
        job_dir = None
        plots_dir = None
        if context:
            job_dir = (context or {}).get("job_dir")
            plots_dir = (context or {}).get("plots_dir")

        for step in range(self.max_iters):
            # 若存在analysis.py则直接运行文件，避免重复生成临时脚本
            analysis_path = None
            if job_dir:
                p = Path(job_dir) / "analysis.py"
                if p.exists():
                    analysis_path = p

            if analysis_path:
                result = executor.run_script_path(str(analysis_path))
            else:
                result = executor.run(code)
            step_log = {
                "step": step,
                "stdout": result.get("stdout"),
                "stderr": result.get("stderr"),
                "returncode": result.get("returncode"),
            }
            # 仅在没有文件路径时记录code文本，以减少日志体积
            if analysis_path:
                step_log["script_path"] = str(analysis_path)
            else:
                step_log["code"] = code
            logs.append(step_log)
            # 每步写入状态文件，便于前端实时轮询
            try:
                if job_dir:
                    status_path = Path(job_dir) / "exec_status.json"
                    plots = []
                    if plots_dir:
                        try:
                            plots = [p.name for p in sorted(Path(plots_dir).glob("*.png"))]
                        except Exception:
                            plots = []
                    payload = {
                        "running": True,
                        "success": False,
                        "logs": logs,
                        "events": events,
                        "plots": plots,
                        "current_step": step,
                        "max_iters": self.max_iters,
                    }
                    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                # 状态写入失败不影响主流程
                pass
            # 使用任务完成标准而非仅以returncode为准
            if self._is_task_completed(result, context):
                success = True
                # 完成时写入最终状态
                try:
                    if job_dir:
                        status_path = Path(job_dir) / "exec_status.json"
                        plots = []
                        if plots_dir:
                            try:
                                plots = [p.name for p in sorted(Path(plots_dir).glob("*.png"))]
                            except Exception:
                                plots = []
                        payload = {
                            "running": False,
                            "success": True,
                            "logs": logs,
                            "events": events,
                            "plots": plots,
                            "current_step": step,
                            "max_iters": self.max_iters,
                        }
                        status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                break
            else:
                # 构造包含原始/当前代码、错误信息、Excel结构与计划的上下文
                excel_info = (context or {}).get("excel_info")
                plan = (context or {}).get("plan")
                excel_path = (context or {}).get("excel_path")

                # 构建修复历史作为多轮对话
                history_parts = []
                if step > 0:
                    history_parts.append("\n[修复历史]\n")
                    for prev_log in logs[:-1]:  # 排除当前步骤
                        prev_step = prev_log["step"]
                        history_parts.append(f"尝试 {prev_step + 1}:\n")
                        # history_parts.append(f"代码:\n{prev_log['code']}\n")
                        # history_parts.append(f"标准输出:\n{prev_log['stdout']}\n")
                        # history_parts.append(f"错误输出:\n{prev_log['stderr']}\n")
                        if "llm_suggestion" in prev_log:
                            history_parts.append(f"LLM建议:\n{prev_log['llm_suggestion']}\n")
                        history_parts.append("\n")

                prompt_parts = [
                    "你是参与ReAct循环的代码修复助手。",
                    "请基于历史、当前脚本与错误信息、Excel结构画像（含normalized_columns/profile/synonyms_hint）和研究计划，生成最小修改的修复补丁。也可通过补充打印日志信息帮助定位问题和后续循环的修复。",
                    """严格使用 replace_in_file 工具语法生成修改，禁止任何解释、Markdown 或代码围栏。
                    使用如下 XML 包装：
                    <replace_in_file>
                      <path>目标文件相对路径（相对于当前任务目录 job_dir）</path>
                      <diff>
                    ------- SEARCH
                      [exact content to find]
                    =======
                      [new content to replace with]
                    +++++++ REPLACE
                      </diff>
                      <task_progress>可选：任务进度清单</task_progress>
                    </replace_in_file>

                    关键规则：
                    1) SEARCH 必须与文件内容逐字符精确匹配（包含空白、缩进、注释、行结尾）。
                    2) 每个区块仅替换第一次匹配；如需多处修改，按文件出现顺序提供多个区块。
                    3) 保持区块精简：每块只包含必要变更行和少量唯一上下文，不要包含长串未变更行；每行必须完整，不得截断。
                    4) 特殊操作：
                       - 移动代码：使用两个区块（原位置删除 + 新位置插入）
                       - 删除代码：REPLACE 为空

                    路径要求：
                    - <path> 必须是相对于当前任务目录 job_dir 的相对路径（例如 analysis.py 或 utils/colmap.py）。

                    调试与稳健性要求：
                    - 字段匹配必须稳健：实现并使用 resolve_column(df, concepts)，优先精确匹配，其次匹配标准化名与别名；匹配失败时打印可用列并跳过该分析。
                    - 为调试效率，在字段解析与关键中间变量处添加打印（例如 `print('[INFO] mapping:', ...)`、`print('[INFO] samples:', ...)`）。
                    - 保持函数名稳定：resolve_column(df, concepts)、analyze_sheet(df, sheet, info)、main()，便于增量补丁定位。
                    """,
                ] + history_parts + [
                    "\n[当前脚本]\n",
                    code,
                    "\n[当前输出信息]\n",
                    f"标准输出: {result.get('stdout')}",
                    f"错误输出: {result.get('stderr')}",
                ]
                if excel_path:
                    prompt_parts.extend(["\n[Excel路径]\n", str(excel_path)])
                if excel_info:
                    prompt_parts.extend([
                        "\n[Excel结构]\n",
                        json.dumps(excel_info, ensure_ascii=False),
                    ])
                if plan:
                    prompt_parts.extend([
                        "\n[研究计划]\n",
                        f"objective: {plan.get('objective', '')}",
                        f"steps: {plan.get('steps', [])}",
                    ])

                # 流式生成补丁建议，边输出到控制台
                suggestion = self.llm.generate_stream("".join(prompt_parts))
                logs.append({"step": step, "llm_suggestion": suggestion})
                events.append({"type": "llm_suggestion", "step": step})

                # 优先识别并应用 replace_in_file，其次识别 git diff，最后回退代码块
                if is_replace_in_file_text(suggestion) and job_dir:
                    print(f"找到 replace_in_file 请求，原始建议: {suggestion}")
                    try:
                        apply_result = apply_replace_in_file_text(suggestion, job_dir)
                        logs.append({"step": step, "replace_apply": apply_result})
                        events.append({"type": "apply_replace", "step": step, "applied": bool(apply_result.get("applied")), "changes": bool(apply_result.get("changes"))})
                        applied_ok = bool(apply_result.get("applied"))
                        changed = bool(apply_result.get("changes"))
                        if applied_ok and changed:
                            # 若 analysis.py 有变更则读取最新代码
                            analysis_path = Path(job_dir) / "analysis.py"
                            if analysis_path.exists():
                                try:
                                    code = analysis_path.read_text(encoding="utf-8")
                                except Exception:
                                    pass
                            print("应用 replace_in_file 成功，进入下一轮执行")
                        else:
                            print(apply_result)
                            err_list = apply_result.get("errors") or []
                            print(f"replace_in_file 未产生变更或失败，errors={err_list}")
                            clean = self._extract_code_block(suggestion)
                            if clean:
                                code = clean
                            elif "import pandas" in suggestion or "import matplotlib" in suggestion:
                                code = suggestion
                    except Exception as e:
                        logs.append({"step": step, "replace_error": str(e)})
                        clean = self._extract_code_block(suggestion)
                        if clean:
                            code = clean
                        elif "import pandas" in suggestion or "import matplotlib" in suggestion:
                            code = suggestion
                        print(f"应用 replace_in_file 异常: {e}")
                elif is_apply_patch_text(suggestion) and job_dir:
                    print(f"找到有效diff，原始建议: {suggestion}")
                    try:
                        apply_result = apply_patch_text(suggestion, job_dir)
                        logs.append({"step": step, "patch_apply": apply_result})
                        events.append({"type": "apply_patch", "step": step, "applied": bool(apply_result.get("applied")), "changes": bool(apply_result.get("changes"))})
                        # 检查应用是否成功且有实际变更
                        applied_ok = bool(apply_result.get("applied"))
                        changed = bool(apply_result.get("changes"))
                        if applied_ok and changed:
                            # 从更新后的analysis.py读取下一步执行代码
                            analysis_path = Path(job_dir) / "analysis.py"
                            if analysis_path.exists():
                                code = analysis_path.read_text(encoding="utf-8")
                            print("应用补丁成功，进入下一轮执行")
                        else:
                            # 补丁未成功应用或未产生变更，打印错误并回退到代码块策略
                            print(apply_result)
                            err_list = apply_result.get("errors") or []
                            print(f"应用补丁未产生变更或失败，errors={err_list}")
                            clean = self._extract_code_block(suggestion)
                            if clean:
                                code = clean
                            elif "import pandas" in suggestion or "import matplotlib" in suggestion:
                                code = suggestion
                    except Exception as e:
                        logs.append({"step": step, "patch_error": str(e)})
                        # 回退到代码块提取策略
                        clean = self._extract_code_block(suggestion)
                        if clean:
                            code = clean
                        elif "import pandas" in suggestion or "import matplotlib" in suggestion:
                            code = suggestion
                        print(f"应用补丁异常: {e}")
                else:
                    # 提取建议中的代码块（若返回含markdown代码围栏）
                    print(f"未找到有效diff，原始建议: {suggestion}")
                    clean = self._extract_code_block(suggestion)
                    if clean:
                        code = clean
                    elif "import pandas" in suggestion or "import matplotlib" in suggestion:
                        # 作为退化处理，直接使用纯文本（可能仍含杂质，但比空好）
                        code = suggestion

            # 每步结束后刷新一次状态
            try:
                if job_dir:
                    status_path = Path(job_dir) / "exec_status.json"
                    plots = []
                    if plots_dir:
                        try:
                            plots = [p.name for p in sorted(Path(plots_dir).glob("*.png"))]
                        except Exception:
                            plots = []
                    payload = {
                        "running": True,
                        "success": False,
                        "logs": logs,
                        "events": events,
                        "plots": plots,
                        "current_step": step,
                        "max_iters": self.max_iters,
                    }
                    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        # 循环结束：若未成功，写入最终状态，通知前端退出轮询
        try:
            if job_dir:
                status_path = Path(job_dir) / "exec_status.json"
                plots = []
                if plots_dir:
                    try:
                        plots = [p.name for p in sorted(Path(plots_dir).glob("*.png"))]
                    except Exception:
                        plots = []
                payload = {
                    "running": False,
                    "success": success,
                    "logs": logs,
                    "events": events,
                    "plots": plots,
                    "current_step": min(len(logs) - 1, self.max_iters - 1) if logs else 0,
                    "max_iters": self.max_iters,
                }
                if not success:
                    payload.update({
                        "max_iters_reached": True,
                        "message": "已达到最大重试次数，执行未成功",
                    })
                status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return {
            "success": success,
            "logs": logs,
            "events": events,
        }

    def _is_task_completed(self, result: Dict, context: Optional[Dict]) -> bool:
        """
        任务完成判定策略：
        - returncode==0 且满足以下之一：
          1) stdout包含'TASK_DONE'标记；
          2) stdout中存在至少一次图表保存日志（'Saved plot:'），并且处理了至少一个sheet；
          3) 若提供plots_dir，则该目录下存在至少一个png图表文件。
        可根据需要在后续迭代中提高覆盖率要求（如所有sheet均生成图表）。
        """
        if result.get("returncode", 1) != 0:
            return False

        stdout = (result.get("stdout") or "")
        stderr = (result.get("stderr") or "")

        # 显式错误或失败标记，视为未完成
        if "[ERROR]" in stdout or "TASK_FAILED" in stdout:
            return False
        import re as _re
        if _re.search(r"(error|exception|traceback)", stderr, flags=_re.IGNORECASE):
            return False

        if "TASK_DONE" in stdout:
            return True

        # Heuristic: 日志包含图表保存与sheet处理痕迹
        saved_plot_logs = stdout.count("Saved plot:")
        processed_sheet_logs = len(re.findall(r"Sheet=.*?shape=", stdout))
        if saved_plot_logs >= 1 and processed_sheet_logs >= 1:
            return True

        # 文件系统检查：是否已有图表输出
        try:
            plots_dir = (context or {}).get("plots_dir")
            if plots_dir:
                import os
                pngs = [f for f in os.listdir(plots_dir) if f.lower().endswith('.png')]
                if len(pngs) >= 1:
                    return True
        except Exception:
            pass

        return False

    def _extract_code_block(self, text: str) -> str | None:
        # 优先提取 ```python ... ```
        m = re.search(r"```python\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # 其次提取 ``` ... ```
        m = re.search(r"```\s*(.*?)```", text, flags=re.DOTALL)
        if m:
            return m.group(1).strip()
        return None