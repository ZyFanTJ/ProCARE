from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="AI4Research Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    # 静态文件挂载：用于前端预览生成的图表等产物
    # 将 output/jobs 目录映射到 /static/jobs
    from pathlib import Path
    # 与routes中保持一致：定位到backend目录，再使用backend/output/jobs
    base_backend_dir = Path(__file__).resolve().parents[1]
    jobs_dir = base_backend_dir / "output" / "jobs"
    app.mount("/static/jobs", StaticFiles(directory=str(jobs_dir), html=False), name="static-jobs")
    # 同步挂载上传目录，便于文件管理页预览与下载
    uploads_dir = base_backend_dir / "output" / "uploads"
    app.mount("/static/uploads", StaticFiles(directory=str(uploads_dir), html=False), name="static-uploads")
    return app


app = create_app()