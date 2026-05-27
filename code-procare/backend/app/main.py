from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api.routes import router
from .api.dataprep import router as dataprep_router
from .api.sandbox import router as sandbox_router
from .api.settings import router as settings_router
from .api.paper import router as paper_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI4Research Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        # allow_origins=["*"],  # 由于 allow_credentials=True，不能使用通配符 "*"
        # 使用正则匹配所有 HTTP/HTTPS 来源，使得 Access-Control-Allow-Origin 返回具体 Origin
        allow_origin_regex=r"https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(dataprep_router, prefix="/api/dataprep", tags=["dataprep"])
    app.include_router(sandbox_router, prefix="/api/sandbox", tags=["sandbox"])
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(paper_router, prefix="/api")
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
