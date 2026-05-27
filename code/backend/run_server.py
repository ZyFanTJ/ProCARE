import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv


def main() -> None:
    """启动命令：uv run uvicorn app.main:app（带常用调试参数）。

    - 工作目录设置为 backend，确保模块路径为 `app.*`
    - 默认启用 `--reload`，日志级别为 `debug`
    - 可通过环境变量覆盖：
      - UVICORN_HOST（默认 0.0.0.0）
      - UVICORN_PORT（默认 8000）
      - UVICORN_LOG_LEVEL（默认 debug）
      - UVICORN_RELOAD（默认 1，设置为 0/false 关闭）
    - 额外的命令行参数会直接透传给 uvicorn
    """

    backend_dir = Path(__file__).parent
    load_dotenv(backend_dir / ".env")

    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    port = os.getenv("UVICORN_PORT", "8000")
    log_level = os.getenv("UVICORN_LOG_LEVEL", "debug")
    reload_enabled = os.getenv("UVICORN_RELOAD", "1").lower() not in {"0", "false"}

    cmd = [
        "uv",
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        str(host),
        "--port",
        str(port),
        "--log-level",
        str(log_level),
    ]

    if reload_enabled:
        cmd.append("--reload")

    # 透传额外命令行参数，例如 --workers 1
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])

    print("Running:", " ".join(cmd))

    try:
        subprocess.run(cmd, cwd=str(backend_dir), check=True)
    except KeyboardInterrupt:
        # 友好退出
        pass


if __name__ == "__main__":
    main()