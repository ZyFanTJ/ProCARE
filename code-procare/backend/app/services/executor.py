import subprocess
import tempfile
import textwrap
import sys
from pathlib import Path
from typing import Dict, Optional


class CodeExecutor:
    def __init__(self, work_dir: Optional[str] = None, use_monty: bool = False):
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.use_monty = use_monty
        self.monty_runner = Path(__file__).parent / "monty_runner.py"

    def _get_cmd(self, script_path: str):
        if self.use_monty:
            # Use Monty sandbox runner
            return [sys.executable, str(self.monty_runner), str(script_path)]
        else:
            # Use standard Python interpreter
            # 增加 -W ignore 参数以屏蔽不影响运行的 Warning 信息
            return [sys.executable, "-W", "ignore", str(script_path)]

    def run(self, code: str) -> Dict:
        # 将代码写入临时文件并以子进程运行
        temp_py = tempfile.NamedTemporaryFile(delete=False, suffix=".py", dir=self.work_dir)
        temp_path = Path(temp_py.name)
        temp_py.write(textwrap.dedent(code).encode("utf-8"))
        temp_py.close()

        # 使用与后端同一解释器，避免依赖环境不一致（如未安装pandas）
        cmd = self._get_cmd(str(temp_path))
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.work_dir),
            text=True,
        )
        stdout, stderr = proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "script_path": str(temp_path),
        }

    def run_script_path(self, script_path: str) -> Dict:
        """直接运行指定脚本路径（位于work_dir或其子目录）。"""
        path = Path(script_path)
        # 若路径非绝对，则基于work_dir解析
        if not path.is_absolute():
            path = self.work_dir / path
            
        cmd = self._get_cmd(str(path))
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.work_dir),
            text=True,
        )
        stdout, stderr = proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "script_path": str(path),
        }

    def run_script_path_stream(self, script_path: str):
        path = Path(script_path)
        if not path.is_absolute():
            path = self.work_dir / path
            
        cmd = self._get_cmd(str(path))
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.work_dir),
            text=True,
            bufsize=1,
        )
        if proc.stdout is not None:
            for line in proc.stdout:
                yield line
        rc = proc.wait()
        yield f"PROCESS_EXIT:{rc}\n"

    def execute_command(self, command: str) -> Dict:
        """Execute a shell command in the work directory."""
        try:
            # Use shell=True to support pipes, redirects, etc.
            # But be careful with security if input is untrusted.
            # Here we assume the command comes from the LLM which is "trusted" in this context.
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.work_dir),
                text=True,
            )
            stdout, stderr = proc.communicate()
            return {
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "command": command,
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "command": command,
            }