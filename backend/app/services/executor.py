import subprocess
import tempfile
import textwrap
import sys
from pathlib import Path
from typing import Dict, Optional


class CodeExecutor:
    def __init__(self, work_dir: Optional[str] = None):
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def run(self, code: str) -> Dict:
        # 将代码写入临时文件并以子进程运行
        temp_py = tempfile.NamedTemporaryFile(delete=False, suffix=".py", dir=self.work_dir)
        temp_path = Path(temp_py.name)
        temp_py.write(textwrap.dedent(code).encode("utf-8"))
        temp_py.close()

        # 使用与后端同一解释器，避免依赖环境不一致（如未安装pandas）
        proc = subprocess.Popen(
            [sys.executable, str(temp_path)],
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
        proc = subprocess.Popen(
            [sys.executable, str(path)],
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
        proc = subprocess.Popen(
            [sys.executable, str(path)],
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