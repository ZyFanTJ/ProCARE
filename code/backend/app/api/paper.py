import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile

from app.core.settings_manager import SettingsManager
from app.services.job_store import FileJobStore, JobNotFoundError
from app.services.report_pipeline import run_report_generation


router = APIRouter(prefix="/paper", tags=["paper"])

BASE_DIR = Path(__file__).resolve().parents[2]
JOBS_DIR = BASE_DIR / "output" / "jobs"


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _paper_dir(job_id: str) -> Path:
    return _job_dir(job_id) / "paper"


def _store_for(job_id: str) -> FileJobStore:
    return FileJobStore(_paper_dir(job_id) / "_state")


def _paper_payload(job_id: str, job: dict[str, Any] | None) -> dict[str, Any]:
    paper_dir = _paper_dir(job_id)
    output_file = Path(str(job.get("output_file") or paper_dir / "paper.pdf")) if job else paper_dir / "paper.pdf"
    latex_file = Path(str(job.get("latex_file") or paper_dir / "paper.tex")) if job else paper_dir / "paper.tex"
    figure_dir = Path(str(job.get("figure_dir") or paper_dir / "figures")) if job else paper_dir / "figures"
    latex_project_dir = (
        Path(str(job.get("latex_project_dir") or paper_dir / "latex_project"))
        if job
        else paper_dir / "latex_project"
    )
    latex_zip = Path(str(job.get("latex_zip") or paper_dir / "latex_project.zip")) if job else paper_dir / "latex_project.zip"
    bibliography_file = (
        Path(str(job.get("bibliography_file") or latex_project_dir / "references.bib"))
        if job
        else latex_project_dir / "references.bib"
    )
    status = str(job.get("status") or "not_started") if job else "not_started"
    if job is None and output_file.exists() and latex_file.exists():
        status = "completed"

    return {
        "job_id": job_id,
        "task_id": "paper",
        "status": status,
        "error": job.get("error") if job else None,
        "output_file": str(output_file) if output_file.exists() else None,
        "latex_file": str(latex_file) if latex_file.exists() else None,
        "figure_dir": str(figure_dir) if figure_dir.exists() else None,
        "latex_project_dir": str(latex_project_dir) if latex_project_dir.exists() else None,
        "latex_zip": str(latex_zip) if latex_zip.exists() else None,
        "bibliography_file": str(bibliography_file) if bibliography_file.exists() else None,
        "pdf_url": f"/static/jobs/{job_id}/paper/{output_file.name}" if output_file.exists() else None,
        "tex_url": f"/static/jobs/{job_id}/paper/{latex_file.name}" if latex_file.exists() else None,
        "figures_url": f"/static/jobs/{job_id}/paper/figures" if figure_dir.exists() else None,
        "latex_project_url": f"/static/jobs/{job_id}/paper/latex_project" if latex_project_dir.exists() else None,
        "latex_zip_url": f"/static/jobs/{job_id}/paper/{latex_zip.name}" if latex_zip.exists() else None,
        "bib_url": f"/static/jobs/{job_id}/paper/latex_project/{bibliography_file.name}" if bibliography_file.exists() else None,
        "compile_engine": job.get("compile_engine") if job else None,
        "llm_model": job.get("llm_model") if job else None,
        "updated_at": job.get("updated_at") if job else None,
    }


@router.post("/{job_id}/generate")
async def generate_paper(
    job_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict[str, Any]:
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job not found")

    markdown_path = job_dir / "report.md"
    if not markdown_path.exists():
        raise HTTPException(status_code=404, detail="report.md not found")

    paper_dir = _paper_dir(job_id)
    state_dir = paper_dir / "_state"
    work_dir = paper_dir / "_work"
    plots_dir = job_dir / "plots"
    paper_dir.mkdir(parents=True, exist_ok=True)
    options = await _parse_generation_options(request)

    store = FileJobStore(state_dir)
    current = store.get_job("paper")
    if current and current.get("status") in {"pending", "running"}:
        return _paper_payload(job_id, current)

    if work_dir.exists():
        shutil.rmtree(work_dir)
    uploads_dir = work_dir / "uploads"
    outputs_dir = paper_dir
    intermediates_dir = work_dir / "intermediates"
    references_dir = work_dir / "reference_assets"
    for path in (uploads_dir, outputs_dir, intermediates_dir, references_dir):
        path.mkdir(parents=True, exist_ok=True)

    reference_asset_names = await _save_reference_uploads(references_dir, options["reference_files"])
    asset_names = []
    if plots_dir.exists():
        asset_names = [
            p.name
            for p in sorted(plots_dir.iterdir())
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".svg"}
        ]

    plan_path = job_dir / "plan.json"
    report_name = str(options.get("report_name") or "").strip()

    llm_settings = _resolve_rws_llm_settings(bool(options["llm_enabled"]))

    store.create_job(
        "paper",
        {
            "report_name": report_name,
            "markdown_name": markdown_path.name,
            "report_language": options["report_language"],
            "asset_names": asset_names,
            "reference_asset_names": reference_asset_names,
            "template_path": options["template_path"],
            "markdown_path": str(markdown_path),
            "assets_dir": str(plots_dir),
            "reference_assets_dir": str(references_dir),
            "intermediate_dir": str(intermediates_dir),
            "planned_output_path": str(outputs_dir / "paper.pdf"),
            "output_type": "pdf",
            "compile_engine": None,
            "llm_enabled": bool(options["llm_enabled"]),
            "llm_provider": llm_settings["provider"],
            "llm_base_url": llm_settings["base_url"],
            "llm_api_key": llm_settings["api_key"],
            "llm_model": llm_settings["model"],
            "llm_timeout_seconds": options["llm_timeout_seconds"],
            "use_last_input": False,
            "source_job_id": job_id,
            "writing_requirements": options["writing_requirements"],
            "intermediate_files": [],
            "skip_archive": True,
        },
    )
    background_tasks.add_task(_run_and_prune_paper_artifacts, job_id)
    return _paper_payload(job_id, store.require_job("paper"))


@router.get("/{job_id}")
async def get_paper_status(job_id: str) -> dict[str, Any]:
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job not found")
    try:
        job = _store_for(job_id).require_job("paper")
    except JobNotFoundError:
        return _paper_payload(job_id, None)
    return _paper_payload(job_id, job)


def _run_and_prune_paper_artifacts(job_id: str) -> None:
    paper_dir = _paper_dir(job_id)
    work_dir = paper_dir / "_work"
    store = _store_for(job_id)
    run_report_generation("paper", store)

    job = store.require_job("paper")
    if job.get("status") == "completed":
        tex_target = paper_dir / "paper.tex"
        source_tex = Path(str(job.get("latex_file") or ""))
        if source_tex.exists():
            shutil.copy2(source_tex, tex_target)

        source_figures = Path(str(job.get("figure_dir") or ""))
        figures_target = paper_dir / "figures"
        if figures_target.exists():
            shutil.rmtree(figures_target)
        if source_figures.exists():
            shutil.copytree(source_figures, figures_target)

        project_target = paper_dir / "latex_project"
        if project_target.exists():
            shutil.rmtree(project_target)
        source_project = Path(str(job.get("latex_project_dir") or ""))
        if source_project.exists():
            shutil.copytree(source_project, project_target)
        else:
            project_target.mkdir(parents=True, exist_ok=True)
            if tex_target.exists():
                shutil.copy2(tex_target, project_target / "main.tex")
            if figures_target.exists():
                shutil.copytree(figures_target, project_target / "assets", dirs_exist_ok=True)

        _ensure_overleaf_project_files(project_target)
        latex_zip = paper_dir / "latex_project.zip"
        if latex_zip.exists():
            latex_zip.unlink()
        shutil.make_archive(str(latex_zip.with_suffix("")), "zip", project_target)

        store.update_job(
            "paper",
            latex_file=str(tex_target),
            figure_dir=str(figures_target) if figures_target.exists() else None,
            latex_project_dir=str(project_target),
            latex_zip=str(latex_zip),
            bibliography_file=str(project_target / "references.bib"),
            intermediate_files=[],
            final_markdown_file=None,
        )
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


async def _parse_generation_options(request: Request) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "llm_enabled": True,
        "report_language": "zh",
        "report_name": "",
        "template_path": None,
        "writing_requirements": "",
        "llm_timeout_seconds": None,
        "reference_files": [],
    }
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        defaults.update(
            {
                "llm_enabled": _as_bool(form.get("llm_enabled"), default=True),
                "report_language": _normalize_language(form.get("report_language")),
                "report_name": str(form.get("report_name") or "").strip(),
                "template_path": _clean_optional_text(form.get("template_path")),
                "writing_requirements": str(form.get("writing_requirements") or "").strip(),
                "llm_timeout_seconds": _clean_optional_text(form.get("llm_timeout_seconds")),
                "reference_files": [
                    item
                    for item in form.getlist("reference_files")
                    if hasattr(item, "filename") and hasattr(item, "read")
                ],
            }
        )
        return defaults

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    defaults.update(
        {
            "llm_enabled": _as_bool(payload.get("llm_enabled"), default=True),
            "report_language": _normalize_language(payload.get("report_language")),
            "report_name": str(payload.get("report_name") or "").strip(),
            "template_path": _clean_optional_text(payload.get("template_path")),
            "writing_requirements": str(payload.get("writing_requirements") or "").strip(),
            "llm_timeout_seconds": _clean_optional_text(payload.get("llm_timeout_seconds")),
        }
    )
    return defaults


async def _save_reference_uploads(reference_dir: Path, files: list[UploadFile]) -> list[str]:
    saved_names: list[str] = []
    for index, file in enumerate(files, start=1):
        if not file.filename:
            continue
        name = _safe_filename(file.filename, fallback=f"reference_{index}.pdf")
        target = reference_dir / name
        suffix = target.suffix
        stem = target.stem
        counter = 2
        while target.exists():
            target = reference_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        content = await file.read()
        if not content:
            continue
        target.write_bytes(content)
        saved_names.append(target.name)
    return saved_names


def _resolve_rws_llm_settings(enabled: bool) -> dict[str, str | None]:
    if not enabled:
        return {"provider": None, "base_url": None, "api_key": None, "model": None}

    settings = SettingsManager().get_settings()
    llm_settings = settings.get("llm") if isinstance(settings.get("llm"), dict) else {}
    model = str(
        settings.get("active_model")
        or (llm_settings or {}).get("active_model")
        or os.getenv("OPENAI_API_MODEL")
        or os.getenv("LLM_MODEL")
        or ""
    ).strip()
    base_url = str(
        settings.get("api_base_url")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or _default_base_url_for_model(model)
        or ""
    ).strip()
    api_keys = settings.get("api_keys") if isinstance(settings.get("api_keys"), dict) else {}
    key_name = _infer_api_key_name(model)
    api_key = str(
        api_keys.get(key_name)
        or api_keys.get("openai")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    provider = "deepseek" if "deepseek" in model.casefold() else "openai_compatible"
    return {"provider": provider, "base_url": base_url or None, "api_key": api_key or None, "model": model or None}


def _infer_api_key_name(model: str) -> str:
    normalized = model.casefold()
    if "deepseek" in normalized:
        return "deepseek"
    if "claude" in normalized or "anthropic" in normalized:
        return "anthropic"
    if "gemini" in normalized or "google" in normalized:
        return "google"
    if "qwen" in normalized:
        return "qwen"
    if "minimax" in normalized:
        return "minimax"
    return "openai"


def _default_base_url_for_model(model: str) -> str | None:
    if "minimax" in (model or "").casefold():
        return "https://api.minimax.io/v1"
    return None


def _ensure_overleaf_project_files(project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    tex_files = sorted(project_dir.glob("*.tex"))
    main_tex = project_dir / "main.tex"
    if not main_tex.exists() and tex_files:
        shutil.copy2(tex_files[0], main_tex)
    references_bib = project_dir / "references.bib"
    if not references_bib.exists():
        references_bib.write_text("% References for the generated RWS paper.\n", encoding="utf-8")
    readme = project_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# RWS generated LaTeX project\n\n"
            "Upload this folder or `latex_project.zip` to Overleaf. "
            "Use `main.tex` as the entry file.\n",
            encoding="utf-8",
        )


def _safe_filename(filename: str, *, fallback: str) -> str:
    candidate = Path(filename).name.strip() or fallback
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", candidate)
    candidate = candidate.strip(". ") or fallback
    return candidate[:160]


def _clean_optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_language(value: object) -> str:
    text = str(value or "zh").strip().lower()
    return text if text in {"zh", "en"} else "zh"


def _as_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
