import re
import json
import time
from pathlib import Path
from typing import Dict, Optional, Generator, Any, List

# Avoid circular imports if possible, otherwise use local import
try:
    from .llm import LLMClient
    from .skill_manager import SkillManager
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from llm import LLMClient
    from core.skill_manager import SkillManager

class SandboxLoop:
    """
    Advanced Sandbox Loop for complex research tasks.
    Supports shell commands, file operations, and multi-step reasoning.
    """

    def __init__(self, max_iters: int = 15):
        self.max_iters = max_iters
        self.llm = LLMClient()
        self.skill_manager = SkillManager()

    def stream_run(self, executor, context: Optional[Dict] = None) -> Generator[Dict[str, Any], None, None]:
        history = [] # List of strings for Prompt
        structured_logs = [] # List of dicts for Result
        job_dir = Path(context.get("job_dir")) if context and context.get("job_dir") else executor.work_dir
        
        # Initial context extraction
        plan = context.get("plan", {})
        excel_info = context.get("excel_info", {})
        
        yield {"type": "phase", "phase": "sandbox_init"}

        for step in range(self.max_iters):
            # 1. Prepare Prompt
            # List files in current directory
            try:
                files = [f.name for f in job_dir.iterdir()]
            except Exception:
                files = []

            prompt = self.skill_manager.get_skill("sandbox_research").render(
                    plan_objective=plan.get("objective", ""),
                    plan_steps="\n".join([f"- {s}" for s in plan.get("steps", [])]),
                    excel_info=json.dumps(excel_info, indent=2, ensure_ascii=False),
                    cwd=str(job_dir),
                    files=json.dumps(files),
                    history="\n".join(history)
                )

            yield {"type": "step_start", "step": step}
            
            # 2. Call LLM
            response_text = ""
            for chunk in self.llm.stream_iter(prompt):
                response_text += chunk
                yield {"type": "llm_chunk", "chunk": chunk, "step": step}
            
            # 3. Parse Action
            action = self._parse_action(response_text)
            if not action:
                error_msg = "No valid action found in response."
                history.append(f"[Step {step+1}]\nResponse: {response_text}\nSystem Error: {error_msg}\n")
                structured_logs.append({"step": step, "error": error_msg, "response": response_text})
                yield {"type": "error", "error": error_msg}
                continue

            action_type = action["type"]
            action_content = action["content"]
            action_path = action.get("path")

            yield {"type": "action", "action": action, "step": step}

            # 4. Execute Action
            result_output = ""
            success = True
            
            try:
                if action_type == "run_command":
                    cmd_res = executor.execute_command(action_content.strip())
                    result_output = f"Stdout:\n{cmd_res['stdout']}\nStderr:\n{cmd_res['stderr']}\nReturnCode: {cmd_res['returncode']}"
                    if cmd_res['returncode'] != 0:
                        success = False
                
                elif action_type == "write_file":
                    if not action_path:
                        result_output = "Error: write_file requires 'path' attribute."
                        success = False
                    else:
                        file_path = job_dir / action_path
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(action_content, encoding="utf-8")
                        result_output = f"File {action_path} written successfully."
                
                elif action_type == "read_file":
                    file_path = job_dir / action_content.strip()
                    if file_path.exists():
                        content = file_path.read_text(encoding="utf-8")
                        # Truncate if too long?
                        if len(content) > 5000:
                            content = content[:5000] + "\n...[Truncated]..."
                        result_output = f"Content of {action_content}:\n{content}"
                    else:
                        result_output = f"Error: File {action_content} not found."
                        success = False

                elif action_type == "run_python_script":
                    script_res = executor.run_script_path(action_content.strip())
                    result_output = f"Stdout:\n{script_res['stdout']}\nStderr:\n{script_res['stderr']}\nReturnCode: {script_res['returncode']}"
                    if script_res['returncode'] != 0:
                        success = False
                
                elif action_type == "finish":
                    structured_logs.append({"step": step, "action": action, "result": action_content, "success": True})
                    yield {"type": "done", "success": True, "summary": action_content, "logs": structured_logs}
                    return

                else:
                    result_output = f"Error: Unknown action type '{action_type}'"
                    success = False

            except Exception as e:
                result_output = f"Execution Error: {str(e)}"
                success = False

            yield {"type": "exec_result", "output": result_output, "success": success, "step": step}

            # 5. Update History
            history_entry = f"[Step {step+1}]\nAction: {action_type} {action_path if action_path else ''}\nResult:\n{result_output}\n"
            history.append(history_entry)
            structured_logs.append({"step": step, "action": action, "result": result_output, "success": success})
            
            # Save status
            self._save_status(job_dir, step, history)

        yield {"type": "done", "success": False, "message": "Max iterations reached", "logs": structured_logs}

    def _parse_action(self, text: str) -> Optional[Dict[str, str]]:
        # Regex to match <action type="...">content</action>
        # Handling potential newlines and attributes
        pattern = re.compile(r'<action\s+type="([^"]+)"(?:\s+path="([^"]+)")?>(.*?)</action>', re.DOTALL | re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return {
                "type": match.group(1),
                "path": match.group(2),
                "content": match.group(3).strip()
            }
        return None

    def _save_status(self, job_dir: Path, step: int, history: List[str]):
        try:
            status_path = job_dir / "exec_status.json"
            # Read existing status if possible to preserve other fields
            current_status = {}
            if status_path.exists():
                try:
                    current_status = json.loads(status_path.read_text(encoding="utf-8"))
                except:
                    pass
            
            current_status.update({
                "current_step": step,
                "sandbox_history_len": len(history),
                # Maybe store last few history items?
                "last_action_result": history[-1] if history else ""
            })
            
            status_path.write_text(json.dumps(current_status, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
