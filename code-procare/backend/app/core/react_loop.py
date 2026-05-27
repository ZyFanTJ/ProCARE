from typing import Dict, Optional
from pathlib import Path
import json
import re
# 支持作为脚本直接运行的导入回退逻辑
try:
    from .llm import LLMClient
    from .skill_manager import SkillManager
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
    from core.skill_manager import SkillManager
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
        self.skill_manager = SkillManager()

    def stream_run(self, initial_code: str, executor, context: Optional[Dict] = None):
        logs = []
        events = []
        code = initial_code
        success = False
        job_dir = None
        plots_dir = None
        if context:
            job_dir = (context or {}).get("job_dir")
            plots_dir = (context or {}).get("plots_dir")

        try:
            for step in range(self.max_iters):
                # 若存在analysis.py则直接运行文件，避免重复生成临时脚本
                analysis_path = None
                if job_dir:
                    p = Path(job_dir) / "analysis.py"
                    if p.exists():
                        analysis_path = p

                if analysis_path:
                    # yield status before running
                    yield {"type": "step_start", "step": step, "script": str(analysis_path)}
                    # support streaming execution logs if executor supports it, otherwise block
                    # For now, let's assume blocking execution but yield result immediately
                    result = executor.run_script_path(str(analysis_path))
                else:
                    yield {"type": "step_start", "step": step, "code_len": len(code)}
                    result = executor.run(code)
                
                step_log = {
                    "step": step,
                    "stdout": result.get("stdout"),
                    "stderr": result.get("stderr"),
                    "returncode": result.get("returncode"),
                }
                if analysis_path:
                    step_log["script_path"] = str(analysis_path)
                else:
                    step_log["code"] = code
                
                logs.append(step_log)
                yield {"type": "exec_result", "step": step, "log": step_log}

                # Update status file
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
                        yield {"type": "plots", "plots": plots}
                except Exception:
                    pass

                if self._is_task_completed(result, context):
                    success = True
                    yield {"type": "success", "step": step}
                    break
                else:
                    # Prepare context for fix
                    excel_info = (context or {}).get("excel_info")
                    plan = (context or {}).get("plan")
                    excel_path = (context or {}).get("excel_path")

                    history_parts = []
                    if step > 0:
                        history_parts.append("\n[修复历史]\n")
                        for prev_log in logs[:-1]:
                            prev_step = prev_log["step"]
                            history_parts.append(f"尝试 {prev_step + 1}:\n")
                            if "llm_suggestion" in prev_log:
                                history_parts.append(f"LLM建议:\n{prev_log['llm_suggestion']}\n")
                            history_parts.append("\n")

                    excel_path_info = ""
                    if excel_path:
                        excel_path_info = f"[Excel路径]\n{excel_path}"
                    
                    excel_structure_info = ""
                    if excel_info:
                        excel_structure_info = f"[Excel结构]\n{json.dumps(excel_info, ensure_ascii=False)}"
                    
                    plan_info = ""
                    if plan:
                        plan_info = f"[研究计划]\nobjective: {plan.get('objective', '')}\nsteps: {plan.get('steps', [])}"

                    snippet_info = ""
                    try:
                        from ..skills.code_generation.utils import get_palette
                        snippet_info = f"\n[Available Snippets Info]\nget_palette signature: {get_palette.__doc__}\n"
                    except Exception:
                        pass

                    prompt = self.skill_manager.get_skill("code_repair").render(
                        history_parts="".join(history_parts),
                        current_code=code,
                        stdout=result.get('stdout'),
                        stderr=result.get('stderr'),
                        excel_path_info=excel_path_info,
                        excel_structure_info=excel_structure_info,
                        plan_info=plan_info,
                        snippet_info=snippet_info
                    )

                    yield {"type": "llm_fix_start", "step": step}
                    
                    suggestion_buf = []
                    for chunk in self.llm.stream_iter(prompt):
                        suggestion_buf.append(chunk)
                        yield {"type": "llm_fix_chunk", "chunk": chunk, "step": step}
                    
                    suggestion = "".join(suggestion_buf)
                    logs[-1]["llm_suggestion"] = suggestion # Update current step log with suggestion
                    events.append({"type": "llm_suggestion", "step": step})
                    yield {"type": "llm_suggestion", "step": step, "suggestion": suggestion}
                    
                    # Apply fix logic (same as run method)
                    # ... (Duplicate logic or refactor? Let's copy for safety and independence)
                    if is_replace_in_file_text(suggestion) and job_dir:
                        try:
                            apply_result = apply_replace_in_file_text(suggestion, job_dir)
                            logs[-1]["replace_apply"] = apply_result
                            events.append({"type": "apply_replace", "step": step, "applied": bool(apply_result.get("applied")), "changes": bool(apply_result.get("changes"))})
                            yield {"type": "apply_replace", "result": apply_result}
                            
                            if bool(apply_result.get("applied")) and bool(apply_result.get("changes")):
                                analysis_path = Path(job_dir) / "analysis.py"
                                if analysis_path.exists():
                                    try:
                                        code = analysis_path.read_text(encoding="utf-8")
                                    except Exception:
                                        pass
                            else:
                                clean = self._extract_code_block(suggestion)
                                if clean: code = clean
                                elif "import pandas" in suggestion: code = suggestion
                        except Exception as e:
                            logs[-1]["replace_error"] = str(e)
                            clean = self._extract_code_block(suggestion)
                            if clean: code = clean
                            elif "import pandas" in suggestion: code = suggestion
                    elif is_apply_patch_text(suggestion) and job_dir:
                        try:
                            apply_result = apply_patch_text(suggestion, job_dir)
                            logs[-1]["patch_apply"] = apply_result
                            events.append({"type": "apply_patch", "step": step, "applied": bool(apply_result.get("applied")), "changes": bool(apply_result.get("changes"))})
                            yield {"type": "apply_patch", "result": apply_result}

                            if bool(apply_result.get("applied")) and bool(apply_result.get("changes")):
                                analysis_path = Path(job_dir) / "analysis.py"
                                if analysis_path.exists():
                                    code = analysis_path.read_text(encoding="utf-8")
                            else:
                                clean = self._extract_code_block(suggestion)
                                if clean: code = clean
                                elif "import pandas" in suggestion: code = suggestion
                        except Exception as e:
                            logs[-1]["patch_error"] = str(e)
                            clean = self._extract_code_block(suggestion)
                            if clean: code = clean
                            elif "import pandas" in suggestion: code = suggestion
                    else:
                        clean = self._extract_code_block(suggestion)
                        if clean: code = clean
                        elif "import pandas" in suggestion: code = suggestion

                    # If code changed manually (not via file), write it?
                    # Actually generate_and_execute writes initial code.
                    # Here if we fallback to `code = clean`, we should update the file if job_dir exists.
                    if job_dir and (isinstance(code, str) and len(code) > 0):
                        try:
                            (Path(job_dir) / "analysis.py").write_text(code, encoding="utf-8")
                        except Exception:
                            pass
            
            # Final status update
            try:
                if job_dir:
                    status_path = Path(job_dir) / "exec_status.json"
                    plots = []
                    if plots_dir:
                         plots = [p.name for p in sorted(Path(plots_dir).glob("*.png"))]
                    
                    payload = {
                        "running": False,
                        "success": success,
                        "logs": logs,
                        "events": events,
                        "plots": plots,
                        "current_step": step,
                        "max_iters": self.max_iters,
                    }
                    if not success:
                        payload["message"] = "执行未成功（已终止）"
                    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        except Exception as e:
            logs.append({"step": -1, "error": f"ReActLoop Critical Error: {str(e)}"})
            success = False
            yield {"type": "error", "error": str(e)}
        
        yield {"type": "done", "success": success, "logs": logs}

    def run(self, initial_code: str, executor, context: Optional[Dict] = None) -> Dict:
        """
        Synchronous wrapper for stream_run.
        Consumes the generator and returns the final result.
        """
        final_result = {"success": False, "logs": []}
        for event in self.stream_run(initial_code, executor, context):
            if event.get("type") == "done":
                final_result = event
        return final_result

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