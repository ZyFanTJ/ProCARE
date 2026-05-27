from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import StreamingResponse
from pathlib import Path
import json
import os
import time
import asyncio
from ..services.executor import CodeExecutor
from ..models.schemas import ExecuteRequest

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
JOBS_DIR = OUTPUT_DIR / "jobs"

@router.post("/run")
async def run_sandbox_code(
    job_id: str = Body(..., embed=True),
    code: str = Body(..., embed=True),
    request: Request = None,
):
    """
    Run arbitrary python code in the context of a job.
    Streams stdout/stderr back to the client.
    """
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        # Create a temporary job if not exists? Or require valid job_id?
        # For sandbox, maybe we can create a temporary job or use a "sandbox" job.
        # But usually user is in a project context.
        raise HTTPException(status_code=404, detail="Job context not found")
    
    # Write code to a temporary file
    # We use a unique filename to avoid conflicts, or just 'sandbox_exec.py'
    # 'sandbox_exec.py' is better for simplicity and overwriting previous runs
    script_path = job_dir / "sandbox_exec.py"
    try:
        script_path.write_text(code, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write code: {str(e)}")

    use_monty = os.getenv("USE_MONTY_SANDBOX", "false").lower() == "true"
    executor = CodeExecutor(work_dir=str(job_dir), use_monty=use_monty)

    async def gen():
        try:
            async def disconnected():
                try:
                    return await request.is_disconnected() if request is not None else False
                except Exception:
                    return False
            
            # Stream output
            # We wrap the synchronous generator
            for line in executor.run_script_path_stream(str(script_path)):
                yield line
                if await disconnected():
                    return
        except Exception as e:
            yield f"[SYSTEM_ERROR] {str(e)}\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)
