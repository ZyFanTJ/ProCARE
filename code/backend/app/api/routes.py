import json
import os
import sys
import time
import uuid
import hashlib
import pandas as pd
import subprocess
from pathlib import Path
import shutil
from typing import Optional
import datetime 
import json
import asyncio

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi import BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.responses import StreamingResponse
from fastapi import Request

from ..agents.excel_agent import ExcelAgent
from ..agents.data_profile_agent import DataProfileAgent
from ..agents.plan_agent import PlanAgent
from ..agents.code_agent import CodeAgent
from ..agents.report_agent import ReportAgent
from ..skills.code_generation.utils import extract_code_block
from ..core.llm import LLMClient
from ..core.skill_manager import SkillManager
from ..core.settings_manager import SettingsManager
from ..core.opencode_runner import OpenCodeRunner
from ..core.audit import AuditLogger
from ..services.executor import CodeExecutor
from ..services.profile_manager import ProfileManager
from ..services.knowledge_graph_service import KnowledgeGraphService
from ..services.evidence_contract import (
    CONTRACT_TRACE_FILE,
    CONTRACT_VALIDATION_FILE,
    EVIDENCE_CERTIFICATES_FILE,
    PROFILE_CONTRACT_FILE,
    RWS_IR_FILE,
    read_contract_bundle,
    write_contract_bundle,
)
from ..models.schemas import (
    ResearchRequest, ResearchResponse,
    PlanRequest, PlanResponse,
    ExecuteRequest, ExecuteResponse,
    PlanUpdateRequest, PlanUpdateResponse,
    PlanRefineRequest, PlanRefineResponse,
    ReportRegenRequest, ReportRegenResponse,
    BrainstormRequest, BrainstormResponse,
)


router = APIRouter()


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
JOBS_DIR = OUTPUT_DIR / "jobs"
KNOWLEDGE_BASE_DIR = OUTPUT_DIR / "knowledge_base"
ROOT_DIR = BASE_DIR.parents[1] if len(BASE_DIR.parents) >= 2 else BASE_DIR

for d in [OUTPUT_DIR, UPLOAD_DIR, JOBS_DIR, KNOWLEDGE_BASE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


DEFAULT_OPENCODE_MODEL = "blt/gpt-5.3-codex"
OPENCODE_MODEL_ALIASES = {
    "bltcy/gpt-5.4": DEFAULT_OPENCODE_MODEL,
    "gpt-5.4": DEFAULT_OPENCODE_MODEL,
    "gpt-5.3-codex": "blt/gpt-5.3-codex",
    "gemini-3-pro-preview": "blt/gemini-3-pro-preview",
    "deepseek-chat": "deepseek/deepseek-chat",
    "deepseek-reasoner": "deepseek/deepseek-reasoner",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
}


def _normalize_opencode_model(model: object) -> str | None:
    raw_model = str(model or "").strip()
    if not raw_model:
        return None
    if raw_model in OPENCODE_MODEL_ALIASES:
        return OPENCODE_MODEL_ALIASES[raw_model]
    if raw_model.startswith("bltcy/"):
        model_id = raw_model.split("/", 1)[1]
        return OPENCODE_MODEL_ALIASES.get(model_id, f"blt/{model_id}")
    return raw_model


def _get_active_opencode_model(model: Optional[str] = None) -> str:
    explicit_model = _normalize_opencode_model(model)
    if explicit_model:
        return explicit_model
    env_model = _normalize_opencode_model(os.getenv("OPENCODE_MODEL"))
    if env_model:
        return env_model
    try:
        settings = SettingsManager().get_settings()
        llm_settings = (settings or {}).get("llm") or {}
        configured_model = (
            _normalize_opencode_model(llm_settings.get("opencode_model"))
            or _normalize_opencode_model((settings or {}).get("opencode_model"))
            or _normalize_opencode_model(llm_settings.get("active_model"))
            or _normalize_opencode_model((settings or {}).get("active_model"))
        )
        if configured_model:
            return configured_model
    except Exception as exc:
        print(f"Failed to get active model for OpenCode: {exc}")
    return DEFAULT_OPENCODE_MODEL


def _read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _write_contract_artifacts(
    job_dir: Path,
    *,
    plan: Optional[dict] = None,
    excel_info: Optional[dict] = None,
    exec_result: Optional[dict] = None,
    report_text: Optional[str] = None,
) -> Optional[dict]:
    """Best-effort ProCARE contract/RWS-IR artifact writer."""
    try:
        plan = plan if plan is not None else _read_json_if_exists(job_dir / "plan.json")
        excel_info = excel_info if excel_info is not None else _read_json_if_exists(job_dir / "excel_info.json")
        if exec_result is None and (job_dir / "exec_logs.json").exists():
            exec_result = _read_json_if_exists(job_dir / "exec_logs.json")
        if report_text is None:
            report_text = _read_text_if_exists(job_dir / "report.md")
        if not plan or not excel_info:
            return None
        return write_contract_bundle(
            job_dir=job_dir,
            plan=plan,
            excel_info=excel_info,
            exec_result=exec_result,
            report_text=report_text,
        )
    except Exception as exc:
        print(f"[EvidenceContract] Failed to write contract artifacts for {job_dir}: {exc}")
        return None


def _contract_payload_for_response(job_dir: Path, *, include_artifacts: bool = False) -> dict:
    bundle = read_contract_bundle(job_dir)
    trace = bundle.get("contract_trace") or {}
    payload = {
        "job_id": job_dir.name,
        "exists": bool(bundle),
        "trace": trace,
        "files": {
            "profile_contract": PROFILE_CONTRACT_FILE if (job_dir / PROFILE_CONTRACT_FILE).exists() else None,
            "rws_ir": RWS_IR_FILE if (job_dir / RWS_IR_FILE).exists() else None,
            "contract_validation": CONTRACT_VALIDATION_FILE if (job_dir / CONTRACT_VALIDATION_FILE).exists() else None,
            "evidence_certificates": EVIDENCE_CERTIFICATES_FILE if (job_dir / EVIDENCE_CERTIFICATES_FILE).exists() else None,
            "contract_trace": CONTRACT_TRACE_FILE if (job_dir / CONTRACT_TRACE_FILE).exists() else None,
        },
    }
    if include_artifacts:
        payload["artifacts"] = bundle
    return payload


def _collect_plot_files(plots_dir: Path) -> list[str]:
    if not plots_dir.exists():
        return []
    return [p.name for p in sorted(plots_dir.glob("*.png")) if p.is_file()]


def _select_generated_script(job_dir: Path) -> Path:
    main_py = job_dir / "main.py"
    analysis_py = job_dir / "analysis.py"
    return main_py if main_py.exists() else analysis_py


def _validate_publication_outputs(job_dir: Path) -> tuple[bool, list[str]]:
    plots_dir = job_dir / "plots"
    manifest_path = plots_dir / "figure_manifest.json"
    errors: list[str] = []
    if not manifest_path.exists():
        return False, ["Missing plots/figure_manifest.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"Invalid figure_manifest.json: {exc}"]
    if not isinstance(manifest, list) or not manifest:
        return False, ["figure_manifest.json must contain at least one figure"]
    for item in manifest:
        if not isinstance(item, dict):
            errors.append("A figure manifest entry is not an object")
            continue
        file_stem = str(item.get("file_stem") or "").strip()
        if not file_stem:
            errors.append("A figure manifest entry is missing file_stem")
            continue
        for suffix in ("png", "pdf", "svg"):
            figure_path = plots_dir / f"{file_stem}.{suffix}"
            if not figure_path.exists():
                errors.append(f"Missing {figure_path.name}")
            elif figure_path.stat().st_size < 2048:
                errors.append(f"{figure_path.name} is too small to be a valid publication figure")
    return not errors, errors


def _validate_generated_script(job_dir: Path, script_path: Path, timeout: int = 300) -> tuple[bool, str, str]:
    if not script_path.exists():
        return False, "", f"Generated script not found: {script_path.name}"
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(job_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"Validation timed out after {timeout}s"
    except Exception as exc:
        return False, "", f"Validation failed with exception: {exc}"

    ok = proc.returncode == 0 and "TASK_FAILED" not in (proc.stdout or "")
    return ok, proc.stdout or "", proc.stderr or ""


def _run_opencode_analysis(job_dir: Path, plan: dict, excel_info: dict, model: Optional[str] = None) -> dict:
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    runner = OpenCodeRunner(work_dir=str(job_dir))
    prepared = runner.prepare_workspace(plan, excel_info)
    active_model = _get_active_opencode_model(model)
    live_log_path = job_dir / "opencode_live.log"

    opencode_logs: list[str] = []
    opencode_success = False
    for event in runner.stream_run(
        prepared["prompt"],
        model=active_model,
        attach_files=prepared["attach_files"],
    ):
        if event.get("type") == "log":
            opencode_logs.append(str(event.get("content") or ""))
        elif event.get("type") == "done":
            opencode_success = bool(event.get("success"))

    script_to_run = _select_generated_script(job_dir)
    exec_log_stdout = "OpenCode execution finished.\n" + "".join(opencode_logs[-20:])
    exec_log_stderr = ""
    exec_success = opencode_success

    if exec_success:
        validation_ok, validation_stdout, validation_stderr = _validate_generated_script(job_dir, script_to_run)
        exec_log_stdout += f"\nValidation stdout:\n{validation_stdout[-4000:]}"
        exec_log_stderr += validation_stderr[-4000:]
        exec_success = validation_ok

    figure_ok, figure_errors = _validate_publication_outputs(job_dir)
    if not figure_ok:
        exec_success = False
        exec_log_stderr += "\nFigure validation failed:\n" + "\n".join(figure_errors)

    exec_result = {
        "success": exec_success,
        "logs": [
            {
                "step": 0,
                "stdout": exec_log_stdout,
                "stderr": exec_log_stderr,
                "code": f"See {script_to_run.name}",
            }
        ],
        "code_path": str(script_to_run),
        "plots_dir": str(plots_dir),
        "runner": "opencode",
        "workspace_dir": str(job_dir),
        "opencode_live_log": str(live_log_path),
        "figure_validation": {"ok": figure_ok, "errors": figure_errors},
    }
    (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_contract_artifacts(job_dir, plan=plan, excel_info=excel_info, exec_result=exec_result)
    return exec_result


def _stream_opencode_analysis_lines(
    *,
    job_id: str,
    job_dir: Path,
    plan: dict,
    excel_info: dict,
    model: Optional[str] = None,
):
    total_start_time = time.time()
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    live_log_path = job_dir / "opencode_live.log"

    init_status = {
        "running": True,
        "success": False,
        "logs": [],
        "plots": [],
        "current_step": 0,
        "max_iters": 1,
        "report_ready": False,
        "workspace_dir": str(job_dir),
        "opencode_live_log": str(live_log_path),
    }
    (job_dir / "exec_status.json").write_text(json.dumps(init_status, ensure_ascii=False, indent=2), encoding="utf-8")

    exec_success = False
    exec_log_stdout = ""
    exec_log_stderr = ""
    plot_files = []
    script_to_run = None

    try:
        yield json.dumps({"type": "meta", "job_id": job_id}) + "\n"
        yield json.dumps(
            {
                "type": "workspace",
                "workspace_dir": str(job_dir),
                "opencode_live_log": str(live_log_path),
            },
            ensure_ascii=False,
        ) + "\n"
        yield json.dumps(
            {
                "type": "code_chunk",
                "content": f"Workspace: {job_dir}\nOpenCode live log: {live_log_path}\n",
            },
            ensure_ascii=False,
        ) + "\n"
        yield json.dumps({"type": "phase", "phase": "execution"}) + "\n"

        runner = OpenCodeRunner(work_dir=str(job_dir))
        prepared = runner.prepare_workspace(plan, excel_info)
        active_model = _get_active_opencode_model(model)

        opencode_logs: list[str] = []
        for event in runner.stream_run(
            prepared["prompt"],
            model=active_model,
            attach_files=prepared["attach_files"],
        ):
            if event.get("type") == "log":
                content = str(event.get("content") or "")
                opencode_logs.append(content)
                yield json.dumps({"type": "code_chunk", "content": content}, ensure_ascii=False) + "\n"
            elif event.get("type") == "done":
                exec_success = bool(event.get("success"))
                if not exec_success:
                    yield json.dumps({"type": "error", "error": "OpenCode 执行失败"}, ensure_ascii=False) + "\n"
            elif event.get("type") in {"phase", "step_start"}:
                yield json.dumps(event, ensure_ascii=False) + "\n"

        script_to_run = _select_generated_script(job_dir)
        exec_log_stdout = "OpenCode execution finished.\n" + "".join(opencode_logs[-20:])

        if exec_success:
            yield json.dumps(
                {
                    "type": "phase",
                    "phase": "validation",
                    "content": f"Validating generated code execution ({script_to_run.name})...",
                },
                ensure_ascii=False,
            ) + "\n"
            validation_ok, validation_stdout, validation_stderr = _validate_generated_script(job_dir, script_to_run)
            exec_log_stdout += f"\nValidation stdout:\n{validation_stdout[-4000:]}"
            exec_log_stderr += validation_stderr[-4000:]
            if not validation_ok:
                exec_success = False
                yield json.dumps(
                    {"type": "error", "error": f"Generated code validation failed:\n{exec_log_stderr[-800:]}"},
                    ensure_ascii=False,
                ) + "\n"

        figure_ok, figure_errors = _validate_publication_outputs(job_dir)
        if not figure_ok:
            exec_success = False
            exec_log_stderr += "\nFigure validation failed:\n" + "\n".join(figure_errors)
            yield json.dumps(
                {"type": "error", "error": "Figure validation failed: " + "; ".join(figure_errors[:5])},
                ensure_ascii=False,
            ) + "\n"

        plot_files = _collect_plot_files(plots_dir)
        if plot_files:
            yield json.dumps({"type": "plots", "plots": plot_files}, ensure_ascii=False) + "\n"

    except Exception as exc:
        exec_success = False
        exec_log_stderr += f"\n[Error] Stream generator exception: {exc}"
        yield json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n"

    finally:
        if script_to_run is None:
            script_to_run = job_dir / "main.py"
        exec_result = {
            "success": exec_success,
            "logs": [
                {
                    "step": 0,
                    "stdout": exec_log_stdout,
                    "stderr": exec_log_stderr,
                    "code": f"See {script_to_run.name}",
                }
            ],
            "code_path": str(script_to_run),
            "plots_dir": str(plots_dir),
            "runner": "opencode",
            "workspace_dir": str(job_dir),
            "opencode_live_log": str(live_log_path),
        }
        (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_contract_artifacts(job_dir, plan=plan, excel_info=excel_info, exec_result=exec_result)

        final_status = {
            "running": False,
            "success": exec_success,
            "logs": exec_result["logs"],
            "plots": plot_files,
            "current_step": 1,
            "max_iters": 1,
            "report_ready": False,
            "workspace_dir": str(job_dir),
            "opencode_live_log": str(live_log_path),
        }
        (job_dir / "exec_status.json").write_text(json.dumps(final_status, ensure_ascii=False, indent=2), encoding="utf-8")

    if exec_success:
        yield json.dumps({"type": "success"}, ensure_ascii=False) + "\n"
    yield json.dumps(
        {"type": "exec_done", "success": exec_success, "message": "Execution finished. Waiting for manual report generation."},
        ensure_ascii=False,
    ) + "\n"
    yield json.dumps({"type": "log", "content": f"\nTotal Time: {time.time() - total_start_time:.2f}s\n"}) + "\n"


def _merge_plan(a: dict, b: dict) -> dict:
    r = dict(a or {})
    bs = b.get("steps") if isinstance(b.get("steps"), list) else []
    as_ = r.get("steps") if isinstance(r.get("steps"), list) else []
    if bs:
        merged_steps = list(as_)
        for s in bs:
            if s not in merged_steps:
                merged_steps.append(s)
        r["steps"] = merged_steps
    for k in ("objective", "topic"):
        if k not in r and k in b:
            r[k] = b[k]
    ba = r.get("artifacts") if isinstance(r.get("artifacts"), dict) else {}
    bb = b.get("artifacts") if isinstance(b.get("artifacts"), dict) else {}
    if ba or bb:
        m = dict(ba)
        for k, v in bb.items():
            if k not in m:
                m[k] = v
        r["artifacts"] = m
    if "target_sheets" in b:
        r["target_sheets"] = b["target_sheets"]
    if "required_fields" in b:
        rf_a = r.get("required_fields") if isinstance(r.get("required_fields"), dict) else {}
        rf_b = b.get("required_fields") if isinstance(b.get("required_fields"), dict) else {}
        mrf = dict(rf_a)
        for k, v in rf_b.items():
            mrf[k] = v
        r["required_fields"] = mrf
    for k, v in b.items():
        if k in ("steps", "objective", "artifacts", "target_sheets", "required_fields", "topic"):
            continue
        if k not in r:
            r[k] = v
    return r

@router.post("/upload_excel")
async def upload_excel(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="只支持Excel文件（.xlsx/.xls）")

    # 读取内容并计算MD5，用于去重
    content = await file.read()
    md5 = hashlib.md5(content).hexdigest()
    
    # 尝试从画像管理器获取缓存
    pm = ProfileManager()
    cached_profile = pm.get_profile(md5)
    
    index_path = UPLOAD_DIR / "md5_index.json"
    index: dict = {}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            index = {}

    # 确定文件存储路径
    final_path = None
    existing_path = index.get(md5)
    is_duplicate_file = False
    
    if existing_path and Path(existing_path).exists():
        final_path = Path(existing_path)
        is_duplicate_file = True
    else:
        # 保存新文件
        ts = int(time.time())
        save_name = f"{ts}_{uuid.uuid4().hex[:8]}_{file.filename}"
        final_path = UPLOAD_DIR / save_name
        final_path.write_bytes(content)
        # 更新MD5索引
        try:
            index[md5] = str(final_path)
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # 准备 excel_info
    if cached_profile:
        excel_info = cached_profile
        # 更新路径和描述（如果用户提供了新描述，或者路径变更）
        excel_info["path"] = str(final_path)
        if description:
            excel_info["description"] = description
        # 确保md5字段存在
        excel_info["md5"] = md5
        # 更新缓存中的路径信息
        pm.save_profile(md5, excel_info)
    else:
        # 新分析
        excel_agent = ExcelAgent()
        excel_info = excel_agent.analyze_excel(str(final_path), user_description=description)
        
        # 自动执行非LLM的结构化画像
        try:
            dp_agent = DataProfileAgent()
            # 空计划将触发默认策略（前N张表）
            dummy_plan = {"steps": [], "objective": "Initial Structural Profiling"}
            excel_info = dp_agent.refine_profile(str(final_path), excel_info, dummy_plan, use_llm=False)
        except Exception as e:
            print(f"[Upload] Auto-profiling failed: {e}")

        excel_info["md5"] = md5
        pm.save_profile(md5, excel_info)

    # 创建job目录并保存excel_info.json
    job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    plots_dir = job_dir / "plots"
    job_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "excel_path": str(final_path),
        "excel_info": excel_info,
        "duplicate": is_duplicate_file, # 文件本身是否重复
        "profile_reused": bool(cached_profile), # 画像是否复用
        "md5": md5,
        "job_id": job_id,
    }


@router.delete("/profile/{md5}")
async def delete_profile(md5: str):
    pm = ProfileManager()
    success = pm.delete_profile(md5)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found or failed to delete")
    return {"ok": True}


@router.get("/profiles")
async def list_profiles():
    pm = ProfileManager()
    return pm.list_profiles()


@router.get("/profile/{md5}")
async def get_profile(md5: str):
    pm = ProfileManager()
    profile = pm.get_profile(md5)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/profile/{md5}/analyze")
async def analyze_profile(md5: str):
    """
    手动触发LLM画像分析 (Streamed response via SSE)
    """
    pm = ProfileManager()
    profile = pm.get_profile(md5)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    path = profile.get("path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Excel file not found on disk")
        
    async def event_generator():
        try:
            dp_agent = DataProfileAgent()
            # 空计划将触发默认策略（前N张表）
            dummy_plan = {"steps": [], "objective": "Deep Knowledge Profiling"}
            
            # 使用 refine_profile_stream 进行流式处理
            # 注意: refine_profile_stream 是同步生成器，我们需要将其包装在异步生成器中或直接迭代
            # 但由于它是CPU密集型任务，最好在线程池中运行，不过这里为了简单先直接迭代，
            # 并在每次迭代时 yield SSE 格式的数据
            
            # 由于 DataProfileAgent.refine_profile_stream 是同步的 generator
            # 我们无法直接 await 它。为了不阻塞 Event Loop，我们应该把它放在线程中运行吗？
            # 这里的 refine_profile_stream 内部有并发处理 (concurrent.futures)，所以它本身是会阻塞的。
            # 为了支持 SSE 流式输出，我们需要修改 refine_profile_stream 或者在这里进行适配。
            # 鉴于 refine_profile_stream 是 yield 字符串消息，我们可以直接迭代它。
            # 但为了避免阻塞 fastapi 的 loop，我们需要小心。
            # 简单的做法是直接迭代，因为 fastAPI 对于 async def 函数会在主线程执行。
            # 如果耗时太长会阻塞其他请求。
            # 更好的做法是重构 DataProfileAgent 支持异步，或者容忍一定的阻塞。
            # 这里为了快速实现，我们假设 refine_profile_stream 的 yield 间隔足够短，
            # 或者我们接受在此连接期间的阻塞（影响并发）。
            # 实际上，DataProfileAgent 内部用了 ThreadPoolExecutor，所以大部分 IO/LLM 等待是在线程中，
            # 主线程主要是在等待 future 完成并 yield。
            
            iterator = dp_agent.refine_profile_stream(path, profile, dummy_plan, use_llm=True)
            
            for msg in iterator:
                # 构建 SSE 消息
                # data: {"status": "processing", "message": "正在分析 sheet1..."}
                yield f"data: {json.dumps({'status': 'processing', 'message': msg}, ensure_ascii=False)}\n\n"
                # 给 event loop 一点喘息时间
                await asyncio.sleep(0.01)
            
            # 完成后保存
            pm.save_profile(md5, profile)
            
            # 发送完成消息和新的 profile
            yield f"data: {json.dumps({'status': 'completed', 'profile': profile}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/profile/{md5}/data")
async def preview_data(md5: str, sheet: str, limit: int = 20):
    """
    Preview data from a specific sheet using openpyxl read-only mode for speed.
    Non-blocking implementation.
    """
    from starlette.concurrency import run_in_threadpool
    from openpyxl import load_workbook

    pm = ProfileManager()
    profile = pm.get_profile(md5)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    path = profile.get("path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Excel file not found on disk")
        
    def _read_preview():
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            if sheet not in wb.sheetnames:
                raise ValueError(f"Sheet {sheet} not found")
            
            ws = wb[sheet]
            # Use iter_rows to stream data
            rows_iter = ws.iter_rows(min_row=1, max_row=limit+1, values_only=True)
            
            header = next(rows_iter, None)
            if not header:
                return [], []
            
            # Clean header (handle None or non-string)
            header_clean = [str(h) if h is not None else f"Unnamed:{i}" for i, h in enumerate(header)]
            
            data = []
            for row in rows_iter:
                # Pad row if shorter than header
                row_list = list(row)
                if len(row_list) < len(header_clean):
                    row_list.extend([None] * (len(header_clean) - len(row_list)))
                # Truncate if longer
                row_list = row_list[:len(header_clean)]
                
                record = {}
                for k, v in zip(header_clean, row_list):
                    if isinstance(v, (pd.Timestamp, datetime.datetime, datetime.date)):
                        record[k] = str(v)
                    else:
                        record[k] = v
                data.append(record)
            
            return header_clean, data
        finally:
            wb.close()

    try:
        # Run in threadpool to avoid blocking event loop
        columns, data = await run_in_threadpool(_read_preview)
        
        return {
            "columns": columns,
            "data": data,
            "total_preview_rows": len(data)
        }
    except Exception as e:
        # Check for specific errors
        if "Sheet" in str(e) and "not found" in str(e):
             raise HTTPException(status_code=404, detail=str(e))
        print(f"Preview error: {e}")
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")




@router.post("/research", response_model=ResearchResponse)
async def research(req: ResearchRequest):
    excel_path = req.excel_path
    if not excel_path or not os.path.exists(excel_path):
        raise HTTPException(status_code=400, detail="excel_path不存在或未提供")

    job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    plots_dir = job_dir / "plots"
    job_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    # 1) Excel结构与上下文
    excel_agent = ExcelAgent()
    excel_info = excel_agent.analyze_excel(excel_path, user_description=req.excel_description)
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    plan_agent = PlanAgent()
    plan = plan_agent.generate_plan(topic=req.topic, excel_info=excel_info)
    (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2.5) 按计划细化画像（只针对相关sheet），减少无关采样与提升字段匹配质量
    profile_agent = DataProfileAgent()
    excel_info = profile_agent.refine_profile(excel_path, excel_info=excel_info, plan=plan)
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    refined_plan = plan_agent.generate_refined_plan(topic=req.topic, excel_info=excel_info, base_plan=plan)
    plan = _merge_plan(plan, refined_plan)
    (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_contract_artifacts(job_dir, plan=plan, excel_info=excel_info)

    # 3) 代码生成与ReAct执行
    exec_result = _run_opencode_analysis(job_dir=job_dir, plan=plan, excel_info=excel_info)

    # In research function
    # 4) 生成报告
    report_agent = ReportAgent()
    report_path = report_agent.build_report_modular(
        job_dir=str(job_dir),
        topic=req.topic,
        plan=plan,
        exec_result=exec_result,
        excel_info=excel_info,
        job_id=job_id,  # Pass job_id
    )
    _write_contract_artifacts(
        job_dir,
        plan=plan,
        excel_info=excel_info,
        exec_result=exec_result,
        report_text=_read_text_if_exists(Path(report_path)),
    )
    return ResearchResponse(
        job_id=job_id,
        success=exec_result.get("success", False),
        report_path=report_path,
    )


@router.post("/brainstorm", response_model=BrainstormResponse)
async def brainstorm(req: BrainstormRequest):
    job_dir = JOBS_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    
    excel_info_path = job_dir / "excel_info.json"
    if not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="Excel结构信息不存在")
        
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    
    plan_agent = PlanAgent()
    # 异步生成假设
    hypotheses = plan_agent.generate_hypotheses(excel_info, topic=req.topic)
    
    return BrainstormResponse(hypotheses=hypotheses)


@router.get("/report/{job_id}", response_class=PlainTextResponse)
async def get_report(job_id: str):
    path = JOBS_DIR / job_id / "report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    return path.read_text(encoding="utf-8")

@router.get("/jobs")
async def list_jobs():
    jobs = []
    for d in sorted(JOBS_DIR.glob("job_*")):
        if not d.is_dir():
            continue
        job_id = d.name
        plan_path = d / "plan.json"
        
        # 优化：跳过没有plan.json的job（仅上传了文件但未开始研究的临时job）
        if not plan_path.exists():
            continue
            
        exec_path = d / "exec_logs.json"
        report_path = d / "report.md"
        plots_dir = d / "plots"
        item = {
            "job_id": job_id,
            "topic": None,
            "success": None,
            "report_exists": report_path.exists(),
            "plots": [],
            "created_ts": int(d.stat().st_ctime),
        }
        try:
            # plan_path must exist due to check above
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            item["topic"] = plan.get("topic") or plan.get("objective")
            
            if exec_path.exists():
                exec_result = json.loads(exec_path.read_text(encoding="utf-8"))
                item["success"] = exec_result.get("success", None)
            if plots_dir.exists():
                item["plots"] = [p.name for p in sorted(plots_dir.glob("*.png"))]
        except Exception:
            pass
        jobs.append(item)
    return {"jobs": jobs}

@router.get("/job/{job_id}/plan")
async def get_job_plan(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / "plan.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="计划不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="读取计划失败")
    return data

@router.get("/job/{job_id}/excel_info")
async def get_job_excel_info(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / "excel_info.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Excel结构信息不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="读取Excel结构失败")
    return data

@router.get("/job/{job_id}/exec_logs")
async def get_job_exec_logs(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / "exec_logs.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="执行日志不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="读取执行日志失败")
    return data

@router.get("/job/{job_id}/analysis_code", response_class=PlainTextResponse)
async def get_job_analysis_code(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / "analysis.py"
    if not path.exists():
        raise HTTPException(status_code=404, detail="分析代码不存在")
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=500, detail="读取分析代码失败")


@router.post("/contract/{job_id}/compile")
async def compile_contract(job_id: str):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    bundle = _write_contract_artifacts(job_dir)
    if bundle is None:
        raise HTTPException(status_code=400, detail="缺少计划或Excel结构，无法生成contract")
    return _contract_payload_for_response(job_dir, include_artifacts=False)


@router.get("/contract/{job_id}")
async def get_contract(job_id: str, include_artifacts: bool = False):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    if not (job_dir / CONTRACT_TRACE_FILE).exists():
        _write_contract_artifacts(job_dir)
    return _contract_payload_for_response(job_dir, include_artifacts=include_artifacts)


@router.get("/contract/{job_id}/profile")
async def get_profile_contract(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / PROFILE_CONTRACT_FILE
    if not path.exists():
        _write_contract_artifacts(job_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail="profile contract不存在")
    return _read_json_if_exists(path)


@router.get("/contract/{job_id}/rws_ir")
async def get_rws_ir(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / RWS_IR_FILE
    if not path.exists():
        _write_contract_artifacts(job_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail="RWS-IR不存在")
    return _read_json_if_exists(path)


@router.get("/contract/{job_id}/validation")
async def get_contract_validation(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / CONTRACT_VALIDATION_FILE
    if not path.exists():
        _write_contract_artifacts(job_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail="contract validation不存在")
    return _read_json_if_exists(path)


@router.get("/contract/{job_id}/certificates")
async def get_evidence_certificates(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / EVIDENCE_CERTIFICATES_FILE
    if not path.exists():
        _write_contract_artifacts(job_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail="evidence certificates不存在")
    return _read_json_if_exists(path)


@router.get("/uploads")
async def list_uploads():
    files = []
    for p in sorted(UPLOAD_DIR.glob("*")):
        if p.is_file():
            try:
                files.append({
                    "name": p.name,
                    "size": p.stat().st_size,
                    "created_ts": int(p.stat().st_ctime),
                    "url": f"/static/uploads/{p.name}",
                })
            except Exception:
                files.append({"name": p.name})
    return {"files": files}

@router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job不存在")
    try:
        shutil.rmtree(job_dir)
    except Exception:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"ok": True}

@router.post("/plan/update", response_model=PlanUpdateResponse)
async def plan_update(req: PlanUpdateRequest):
    job_dir = JOBS_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    
    # Write to plan.json
    # If plan_refined.json exists, we might want to update that too, or just plan.json
    # Usually plan.json is the base.
    plan_path = job_dir / "plan.json"
    
    # Merge or Overwrite? The request has 'plan' dict.
    # Assuming full replacement or merge. Let's do merge if not full structure.
    # But usually the frontend sends the full plan.
    # For safety, let's read existing and update.
    try:
        current_plan = {}
        if plan_path.exists():
            current_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        
        # Recursive update or simple update? Simple update for now.
        current_plan.update(req.plan)
        
        plan_path.write_text(json.dumps(current_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # If refined plan exists, we might need to invalidate it or update it. 
        # For now, let's delete refined plan to force re-refinement if needed, or update it too if provided.
        # But simple approach: just update plan.json.
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update plan: {e}")

    _write_contract_artifacts(job_dir, plan=current_plan)
    return PlanUpdateResponse(ok=True, job_id=req.job_id)


@router.get("/reports")
async def list_reports():
    items = []
    for d in sorted(JOBS_DIR.glob("job_*")):
        if not d.is_dir():
            continue
        job_id = d.name
        print(job_id)
        report_path = d / "report.md"
        if report_path.exists():
            items.append({
                "job_id": job_id,
                "report_url": f"/api/report/{job_id}",
                "static_url": f"/static/jobs/{job_id}/report.md",
                "created_ts": int(report_path.stat().st_ctime),
            })
    return {"reports": items}


# 仅重新生成报告（基于已有执行日志与计划）
@router.post("/report_regen", response_model=ReportRegenResponse)
async def report_regen(req: ReportRegenRequest):
    job_dir = JOBS_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    exec_logs_path = job_dir / "exec_logs.json"
    if not plan_path.exists() or not excel_info_path.exists() or not exec_logs_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划/Excel结构或执行日志，无法重新生成报告")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    exec_result = json.loads(exec_logs_path.read_text(encoding="utf-8"))

    report_agent = ReportAgent()
    report_path = report_agent.build_report_modular(
        job_dir=str(job_dir),
        topic=plan.get("topic", ""),
        plan=plan,
        exec_result=exec_result,
        excel_info=excel_info,
        job_id=req.job_id,
    )
    _write_contract_artifacts(
        job_dir,
        plan=plan,
        excel_info=excel_info,
        exec_result=exec_result,
        report_text=_read_text_if_exists(Path(report_path)),
    )

    # 重新生成报告后，也更新执行状态为成功（因为用户已获得报告）
    try:
        status_path = job_dir / "exec_status.json"
        status = {}
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
        status.update({
            "report_ready": True,
            "report_path": report_path,
            "success": True,
            "running": False,
            "message": "报告已重新生成",
        })
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return ReportRegenResponse(ok=True, report_path=report_path)

# 生成单个报告章节
@router.post("/generate_section")
async def generate_section(
    job_id: str = Body(...),
    section_id: str = Body(...),
    human_note: Optional[str] = Body(None),
    guidelines: Optional[str] = Body(None),
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    # 优先使用细化计划；若不存在则回退到plan.json
    plan_path = job_dir / "plan_refined.json"
    if not plan_path.exists():
        plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    exec_logs_path = job_dir / "exec_logs.json"
    if not plan_path.exists() or not excel_info_path.exists() or not exec_logs_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划/Excel结构或执行日志，无法生成章节")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    exec_result = json.loads(exec_logs_path.read_text(encoding="utf-8"))

    report_agent = ReportAgent()
    try:
        section_content = report_agent.generate_section_modular(
            job_dir=str(job_dir),
            topic=plan.get("topic", ""),
            plan=plan,
            exec_result=exec_result,
            excel_info=excel_info,
            section_id=section_id,
            job_id=job_id,
            human_note=human_note,
            guidelines=guidelines,
        )
        return {"section_id": section_id, "content": section_content}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate section")

# 流式生成单个报告章节（StreamingResponse）
@router.post("/generate_section_stream")
async def generate_section_stream(
    job_id: str = Body(...),
    section_id: str = Body(...),
    human_note: Optional[str] = Body(None),
    guidelines: Optional[str] = Body(None),
    request: Request = None,
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan_refined.json"
    if not plan_path.exists():
        plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    exec_logs_path = job_dir / "exec_logs.json"
    if not plan_path.exists() or not excel_info_path.exists() or not exec_logs_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划/Excel结构或执行日志，无法生成章节")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    exec_result = json.loads(exec_logs_path.read_text(encoding="utf-8"))

    ctx = SectionContext(job_dir=str(job_dir), topic=plan.get("topic", ""), plan=plan, exec_result=exec_result, excel_info=excel_info, job_id=job_id)
    chapter = REGISTRY._items.get(section_id)  # type: ignore[attr-defined]
    if chapter is None:
        raise HTTPException(status_code=400, detail="Unknown section")

    sections_dir = job_dir / 'sections'
    sections_dir.mkdir(exist_ok=True)
    out_path = sections_dir / f"{section_id}.md"

    async def gen():
        buf = []
        yield f"JOB_ID:{job_id}\n"
        try:
            async def disconnected():
                try:
                    return await request.is_disconnected() if request is not None else False
                except Exception:
                    return False
            for chunk in chapter.render_stream_iter(ctx, human_note=human_note, guidelines=guidelines):
                buf.append(chunk)
                yield chunk
                if await disconnected():
                    try:
                        out_path.write_text("".join(buf), encoding='utf-8')
                    except Exception:
                        pass
                    return
        finally:
            try:
                content = "".join(buf)
                out_path.write_text(content, encoding='utf-8')
            except Exception:
                pass
            # 移除尾部JSON元数据，以避免污染章节文本内容

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/knowledge_base")
async def list_knowledge_base_files():
    files = []
    if KNOWLEDGE_BASE_DIR.exists():
        for p in sorted(KNOWLEDGE_BASE_DIR.glob("*")):
            if p.is_file() and p.name != "knowledge_graph.json":
                files.append({
                    "name": p.name,
                    "size": p.stat().st_size,
                    "created_ts": int(p.stat().st_ctime),
                    "modified_ts": int(p.stat().st_mtime),
                })
    return {"files": files}


@router.get("/knowledge_graph")
async def get_knowledge_graph():
    kgs = KnowledgeGraphService(KNOWLEDGE_BASE_DIR)
    # If graph is empty or missing, refresh it
    graph = kgs.load_graph()
    if not graph.get("nodes"):
        graph = kgs.refresh_graph_from_files()
    return graph


@router.post("/knowledge_base/upload")
async def upload_knowledge_base_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    # 允许的文件类型: txt, md, pdf, docx, json, yaml, yml, csv, xlsx, xls
    allowed_exts = {".txt", ".md", ".pdf", ".docx", ".json", ".yaml", ".yml", ".csv", ".xlsx", ".xls"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    save_path = KNOWLEDGE_BASE_DIR / file.filename
    # 如果文件已存在，可以选择覆盖或重命名。这里简单起见，覆盖。
    content = await file.read()
    save_path.write_bytes(content)
    
    # Update Knowledge Graph
    try:
        kgs = KnowledgeGraphService(KNOWLEDGE_BASE_DIR)
        kgs.add_file_node(file.filename)
    except Exception as e:
        print(f"Failed to update knowledge graph: {e}")

    return {
        "name": file.filename,
        "size": len(content),
        "status": "uploaded"
    }


@router.delete("/knowledge_base/{filename}")
async def delete_knowledge_base_file(filename: str):
    # 安全检查：防止路径遍历
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    file_path = KNOWLEDGE_BASE_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        os.remove(file_path)
        # Update Knowledge Graph
        kgs = KnowledgeGraphService(KNOWLEDGE_BASE_DIR)
        kgs.remove_file_node(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
        
    return {"ok": True}

@router.post("/run_code_stream")
async def run_code_stream(
    job_id: str = Body(..., embed=True),
    request: Request = None,
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    
    script_path = job_dir / "analysis.py"
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="分析代码不存在")

    use_monty = os.getenv("USE_MONTY_SANDBOX", "false").lower() == "true"
    executor = CodeExecutor(work_dir=str(job_dir), use_monty=use_monty)

    async def gen():
        try:
            async def disconnected():
                try:
                    return await request.is_disconnected() if request is not None else False
                except Exception:
                    return False
            
            # 由于executor是同步生成器，这里简单包装一下
            # 如果需要完全异步，可能需要将executor改为异步或使用run_in_threadpool
            # 但这里为了简单，我们假设subprocess流式输出足够快或接受少量阻塞
            for line in executor.run_script_path_stream(str(script_path)):
                yield line
                if await disconnected():
                    # 这里无法轻易kill subprocess，但在executor中如果pipe断了可能会报错退出
                    return
        except Exception as e:
            yield f"[SYSTEM_ERROR] {str(e)}\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


@router.post("/compose_report")
async def compose_report(
    job_id: str = Body(...),
    sections: list = Body(...),
    overrides: Optional[dict] = Body(None),
    save: Optional[bool] = Body(False),
    use_existing: Optional[bool] = Body(True),
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan_refined.json"
    if not plan_path.exists():
        plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    exec_logs_path = job_dir / "exec_logs.json"
    if not plan_path.exists() or not excel_info_path.exists() or not exec_logs_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划/Excel结构或执行日志，无法组合报告")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    exec_result = json.loads(exec_logs_path.read_text(encoding="utf-8"))

    rb = ReportAgent()
    md_parts = []
    status_path = job_dir / "report_status.json"
    report_path = job_dir / "report.md"
    try:
        status_path.write_text(json.dumps({
            "state": "running",
            "step": "init",
            "progress": 0,
            "total": len(sections or []),
            "completed": 0,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    sections_dir = job_dir / 'sections'
    for sid in sections or []:
        ov = (overrides or {}).get(sid) or {}
        use_cache = bool(use_existing) and not (ov.get('human_note') or ov.get('guidelines'))
        content = None
        if use_cache and (sections_dir / f"{sid}.md").exists():
            try:
                content = (sections_dir / f"{sid}.md").read_text(encoding='utf-8')
            except Exception:
                content = None
        if not content:
            content = rb.generate_section_modular(
                job_dir=str(job_dir),
                topic=plan.get("topic", ""),
                plan=plan,
                exec_result=exec_result,
                excel_info=excel_info,
                section_id=sid,
                job_id=job_id,
                human_note=ov.get("human_note"),
                guidelines=ov.get("guidelines"),
            )
        md_parts.append(content)
        try:
            st = {}
            if status_path.exists():
                st = json.loads(status_path.read_text(encoding="utf-8"))
            st.update({
                "state": "running",
                "step": sid,
                "completed": int(st.get("completed", 0)) + 1,
            })
            total = int(st.get("total", len(sections or []))) or 1
            st["progress"] = int(100 * st["completed"] / total)
            status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
            report_path.write_text("\n".join(md_parts), encoding="utf-8")
        except Exception:
            pass

    final_md = "\n".join(md_parts)
    # 始终写入最终结果到 report.md，保持系统一致性
    try:
        report_path.write_text(final_md, encoding="utf-8")
    except Exception:
        pass
    try:
        st = {}
        if status_path.exists():
            st = json.loads(status_path.read_text(encoding="utf-8"))
        st.update({"state": "done", "step": "done", "progress": 100})
        status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

        # 同步更新 exec_status.json，确保项目列表状态正确
        exec_status_path = job_dir / "exec_status.json"
        est = {}
        if exec_status_path.exists():
            est = json.loads(exec_status_path.read_text(encoding="utf-8"))
        est.update({
            "report_ready": True,
            "report_path": str(report_path),
            "success": True,
            "message": "报告已生成（组合模式）"
        })
        exec_status_path.write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    _write_contract_artifacts(
        job_dir,
        plan=plan,
        excel_info=excel_info,
        exec_result=exec_result,
        report_text=final_md,
    )
    return {"ok": True, "content": final_md, "saved": bool(save), "report_path": str(report_path) if save else None}


@router.get("/sections_meta")
async def sections_meta():
    from ..services.chapters import SECTIONS_META
    items = []
    for s in SECTIONS_META:
        items.append({
            'id': s.get('id'),
            'title': s.get('title'),
            'desc': s.get('desc'),
            'default': s.get('default'),
            'category': s.get('parent'),
        })
    return {"sections": items}

@router.get("/assistant/guide")
async def assistant_guide(page: str):
    text = _read_guide(page)
    return {"text": text}

@router.get("/audit/logs")
async def get_audit_logs(limit: int = 100, offset: int = 0):
    try:
        logger = AuditLogger()
        return logger.get_logs(limit, offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {e}")

@router.get("/audit/stats")
async def get_audit_stats():
    try:
        logger = AuditLogger()
        return logger.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {e}")

def _read_guide(page_key: str) -> str:
    try:
        p = ROOT_DIR / "docs" / "assistant" / f"{page_key}.md"
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    fallback = {
        "dashboard": "查看研究项目与报告概览，支持快速跳转与统计汇总。",
        "wizard": "按步骤完成：上传Excel→生成计划→生成并执行代码，可中断与重试。",
        "projects": "浏览与管理研究项目，支持重新执行与删除。",
        "data-manager": "管理数据资产与原始文件，支持上传、画像预览与AI分析。",
        "templates": "选择报告章节模板并调整顺序，用于后续组合。",
        "report-composer": "按章节流式生成与调整报告，支持覆盖与组合预览。",
        "report-viewer": "查看Markdown报告与图片资源，支持导出PDF与目录跳转。",
        "settings": "配置系统名称、Logo、Favicon与首页轮播。",
    }
    return fallback.get(page_key, "")

def _build_page_context(page_key: str, pathname: str, job_id: Optional[str]) -> str:
    parts: list[str] = []
    if job_id:
        job_dir = JOBS_DIR / job_id
        # 1. Plan Info
        try:
            plan_path = job_dir / "plan_refined.json"
            if not plan_path.exists():
                plan_path = job_dir / "plan.json"
            if plan_path.exists():
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                topic = plan.get("topic") or plan.get("objective")
                if topic:
                    parts.append(f"主题:{topic}")
                # Add steps summary
                steps = plan.get("steps", [])
                if steps:
                    parts.append(f"计划步骤: {', '.join(steps)}")
        except Exception:
            pass

        # 2. Execution Status
        try:
            exec_status_path = job_dir / "exec_status.json"
            if exec_status_path.exists():
                est = json.loads(exec_status_path.read_text(encoding="utf-8"))
                parts.append(f"执行状态: {'Running' if est.get('running') else 'Stopped'}")
                parts.append(f"当前步骤: {est.get('current_step')}")
                parts.append(f"是否成功: {est.get('success')}")
                if est.get('logs'):
                    # Get last 2 logs
                    last_logs = est.get('logs')[-2:]
                    log_str = json.dumps(last_logs, ensure_ascii=False)
                    parts.append(f"最近日志: {log_str}")
        except Exception:
            pass

        # 3. Report Status
        try:
            status_path = job_dir / "report_status.json"
            if status_path.exists():
                st = json.loads(status_path.read_text(encoding="utf-8"))
                state = st.get("state")
                prog = st.get("progress")
                parts.append(f"报告生成状态:{state} 进度:{prog}%")
        except Exception:
            pass
    parts.append(f"页面:{page_key}")
    parts.append(f"路径:{pathname}")
    return "\n".join([p for p in parts if p])

def _build_prompt(page_key: str, pathname: str, job_id: Optional[str], messages: list) -> str:
    guide = _read_guide(page_key)
    ctx = _build_page_context(page_key, pathname, job_id)
    hist = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in (messages or [])][-8:])
    head = "你是RWS系统副驾驶。基于页面上下文与操作指引，用简洁要点回答，并给出可执行建议。"
    return "\n".join([head, "操作指引:", guide, "上下文:", ctx, "对话:", hist, "答复:"])

def _build_messages(page_key: str, pathname: str, job_id: Optional[str], messages: list, context: Optional[dict] = None) -> list:
    guide = _read_guide(page_key)
    ctx = _build_page_context(page_key, pathname, job_id)
    
    # Build detailed job context (Data Profile & Report)
    job_context_str = ""
    if job_id:
        try:
            job_dir = JOBS_DIR / job_id
            
            # 1. Data Profile
            profile_path = job_dir / "excel_info.json"
            if profile_path.exists():
                profile_content = profile_path.read_text(encoding="utf-8")
                # Limit size to avoid token overflow
                if len(profile_content) > 3000:
                    profile_content = profile_content[:3000] + "...(truncated)"
                job_context_str += f"\n[Data Profile]\n{profile_content}\n"
                
            # 2. Report Draft
            report_path = job_dir / "report.md"
            if report_path.exists():
                report_content = report_path.read_text(encoding="utf-8")
                if len(report_content) > 5000:
                    report_content = report_content[-5000:]
                job_context_str += f"\n[Current Report Draft]\n...{report_content}\n"
        except Exception as e:
            print(f"Error loading job context: {e}")

    # Process dynamic context (e.g. from Notebook)
    extra_context = ""
    if context and context.get("type") == "notebook":
        code_content = context.get("content", "")
        if code_content:
             extra_context = f"\n\n当前正在编辑的代码:\n```python\n{code_content}\n```\n"
    
    # Load Skills
    skill_prompts = []
    sm = SkillManager()
    
    try:
        # 0. System Information (Global Context)
        settings_manager = SettingsManager()
        settings = settings_manager.get_settings()
        sys_info_skill = sm.get_skill("copilot_system_info")
        skill_prompts.append(sys_info_skill.render(
            system_name=settings.get("systemName", "RWS研究系统"),
            active_model=settings.get("active_model", "gemini-3-pro-preview"),
            language=settings.get("language", "zh"),
            theme=settings.get("theme", "dark")
        ))

        # 1. Page Understanding (Base Context)
        page_skill = sm.get_skill("copilot_page_understanding")
        skill_prompts.append(page_skill.render(
            page_name=page_key,
            guide=guide,
            context=ctx
        ))
        
        # 2. Domain Knowledge (Data & Report)
        domain_skill = sm.get_skill("copilot_domain_knowledge")
        skill_prompts.append(domain_skill.render(
            job_context=job_context_str,
            extra_context=extra_context
        ))

        # 3. System Operations (Actions)
        ops_skill = sm.get_skill("copilot_system_operations")
        skill_prompts.append(ops_skill.render())

        # 4. Navigation (Frontend Actions)
        nav_skill = sm.get_skill("frontend_navigation")
        skill_prompts.append(nav_skill.render())
        
    except Exception as e:
        print(f"Warning: Failed to load skills: {e}")
        # Fallback to basic context if skills fail
        skill_prompts.append(f"Guide: {guide}\nContext: {ctx}\n{job_context_str}\n{extra_context}")

    skills_content = "\n\n".join(skill_prompts)
    
    system_content = f"""你是RWS系统副驾驶。基于页面上下文与操作指引，用简洁要点回答，并给出可执行建议。

{skills_content}"""
    
    msgs = [{"role": "system", "content": system_content}]
    
    # Process history messages (last 10 to keep context, assuming reasonable size)
    # Filter out empty messages or invalid roles if necessary
    for m in (messages or [])[-10:]:
        role = m.get('role')
        if role not in ('user', 'assistant', 'system'):
            role = 'user'
            
        content = m.get('content') or ""
        images = m.get('images') or []
        
        if not images:
            msgs.append({"role": role, "content": content})
        else:
            # Construct multimodal content
            content_parts = [{"type": "text", "text": content}]
            for img_b64 in images:
                # OpenAI expects data URI or URL
                content_parts.append({
                    "type": "image_url", 
                    "image_url": {"url": img_b64}
                })
            msgs.append({"role": role, "content": content_parts})
            
    return msgs

@router.post("/assistant/chat")
async def assistant_chat(
    page_key: str = Body(...),
    pathname: str = Body(...),
    job_id: Optional[str] = Body(None),
    messages: list = Body([]),
    context: Optional[dict] = Body(None),
):
    llm = LLMClient()
    # prompt = _build_prompt(page_key, pathname, job_id, messages)
    msgs = _build_messages(page_key, pathname, job_id, messages, context)
    reply = llm.generate(messages=msgs)
    return {"reply": reply}

@router.post("/assistant/chat_stream")
async def assistant_chat_stream(
    page_key: str = Body(...),
    pathname: str = Body(...),
    job_id: Optional[str] = Body(None),
    messages: list = Body([]),
    context: Optional[dict] = Body(None),
):
    llm = LLMClient()
    def gen():
        if job_id:
            yield f"JOB_ID:{job_id}\n"
        # prompt = _build_prompt(page_key, pathname, job_id, messages)
        msgs = _build_messages(page_key, pathname, job_id, messages, context)
        for chunk in llm.stream_iter(messages=msgs):
            yield chunk
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


def _run_compose_report(job_dir: Path, plan: dict, excel_info: dict, exec_result: dict, sections: list, overrides: dict, job_id: str, use_existing: bool = True):
    rb = ReportAgent()
    status_path = job_dir / "report_status.json"
    report_path = job_dir / "report.md"
    try:
        status_path.write_text(json.dumps({
            "state": "running",
            "step": "init",
            "progress": 0,
            "total": len(sections or []),
            "completed": 0,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    md_parts = []
    sections_dir = job_dir / 'sections'
    for sid in sections or []:
        ov = (overrides or {}).get(sid) or {}
        use_cache = bool(use_existing) and not (ov.get('human_note') or ov.get('guidelines'))
        content = None
        if use_cache and (sections_dir / f"{sid}.md").exists():
            try:
                content = (sections_dir / f"{sid}.md").read_text(encoding='utf-8')
            except Exception:
                content = None
        if not content:
            try:
                content = rb.generate_section_modular(
                    job_dir=str(job_dir),
                    topic=plan.get("topic", ""),
                    plan=plan,
                    exec_result=exec_result,
                    excel_info=excel_info,
                    section_id=sid,
                    job_id=job_id,
                    human_note=ov.get("human_note"),
                    guidelines=ov.get("guidelines"),
                )
            except Exception:
                content = ""
        md_parts.append(content)
        try:
            st = {}
            if status_path.exists():
                st = json.loads(status_path.read_text(encoding="utf-8"))
            st.update({
                "state": "running",
                "step": sid,
                "completed": int(st.get("completed", 0)) + 1,
            })
            total = int(st.get("total", len(sections or []))) or 1
            st["progress"] = int(100 * st["completed"] / total)
            status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
            report_path.write_text("\n".join(md_parts), encoding="utf-8")
        except Exception:
            pass
    try:
        st = {}
        if status_path.exists():
            st = json.loads(status_path.read_text(encoding="utf-8"))
        st.update({"state": "done", "step": "done", "progress": 100})
        status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

        # 同步更新 exec_status.json，确保项目列表状态正确
        exec_status_path = job_dir / "exec_status.json"
        est = {}
        if exec_status_path.exists():
            est = json.loads(exec_status_path.read_text(encoding="utf-8"))
        est.update({
            "report_ready": True,
            "report_path": str(report_path),
            "success": True,
            "message": "报告已生成（后台组合模式）"
        })
        exec_status_path.write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_contract_artifacts(
            job_dir,
            plan=plan,
            excel_info=excel_info,
            exec_result=exec_result,
            report_text="\n".join(md_parts),
        )
    except Exception:
        pass


@router.post("/compose_report_async")
async def compose_report_async(
    job_id: str = Body(...),
    sections: list = Body(...),
    overrides: Optional[dict] = Body(None),
    use_existing: Optional[bool] = Body(True),
    background_tasks: BackgroundTasks = None,
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan_refined.json"
    if not plan_path.exists():
        plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    exec_logs_path = job_dir / "exec_logs.json"
    if not plan_path.exists() or not excel_info_path.exists() or not exec_logs_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划/Excel结构或执行日志，无法组合报告")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    exec_result = json.loads(exec_logs_path.read_text(encoding="utf-8"))

    if background_tasks is None:
        background_tasks = BackgroundTasks()
    background_tasks.add_task(_run_compose_report, job_dir, plan, excel_info, exec_result, sections, overrides or {}, job_id, bool(use_existing))
    return {"started": True}


@router.get("/report_status/{job_id}")
async def report_status(job_id: str):
    job_dir = JOBS_DIR / job_id
    path = job_dir / "report_status.json"
    if not path.exists():
        return {"state": "unknown"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"state": "unknown"}
    return data


@router.get("/report_preview/{job_id}", response_class=PlainTextResponse)
async def report_preview(job_id: str):
    job_dir = JOBS_DIR / job_id
    # 为保持一致性，预览接口返回 report.md 内容；若不存在再回退到章节拼接。
    path = job_dir / "report.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    secs_dir = job_dir / 'sections'
    if secs_dir.exists():
        parts = []
        for p in sorted(secs_dir.glob('*.md')):
            try:
                parts.append(p.read_text(encoding='utf-8'))
            except Exception:
                pass
        if parts:
            return "\n".join(parts)
    raise HTTPException(status_code=404, detail="预览不存在")


@router.get("/report_sections/{job_id}")
async def report_sections(job_id: str):
    job_dir = JOBS_DIR / job_id
    secs_dir = job_dir / 'sections'
    items = []
    if secs_dir.exists():
        for p in sorted(secs_dir.glob('*.md')):
            try:
                items.append({
                    'id': p.stem,
                    'path': f'sections/{p.name}',
                    'size': p.stat().st_size,
                    'mtime': int(p.stat().st_mtime),
                })
            except Exception:
                pass
    return { 'sections': items }


@router.post("/save_report")
async def save_report(job_id: str = Body(...), content: str = Body(...)):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    path = job_dir / 'report.md'
    try:
        path.write_text(content or "", encoding='utf-8')
    except Exception:
        raise HTTPException(status_code=500, detail="保存失败")
    return { 'ok': True, 'report_path': str(path), 'url': f"/static/jobs/{job_id}/report.md" }


# 分步：生成计划（可重试）
@router.post("/plan", response_model=PlanResponse)
async def generate_plan(req: PlanRequest, request: Request):
    excel_path = req.excel_path
    if not excel_path or not os.path.exists(excel_path):
        raise HTTPException(status_code=400, detail="excel_path不存在或未提供")

    job_id = req.job_id or f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    plots_dir = job_dir / "plots"
    job_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    excel_info_path = job_dir / "excel_info.json"
    if excel_info_path.exists():
        excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    else:
        excel_agent = ExcelAgent()
        excel_info = excel_agent.analyze_excel(excel_path, user_description=req.excel_description)
        excel_info_path.write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    plan_agent = PlanAgent()

    want_stream = False
    try:
        q = request.query_params
        want_stream = q.get("stream") in ("1", "true", "True") or request.headers.get("X-Stream") in ("1", "true", "True")
    except Exception:
        want_stream = False

    if not want_stream:
        plan = plan_agent.generate_plan(topic=req.topic, excel_info=excel_info, mode=req.mode)
        (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_contract_artifacts(job_dir, plan=plan, excel_info=excel_info)
        return PlanResponse(job_id=job_id, plan=plan)

    async def gen():
        yield f"JOB_ID:{job_id}\n"
        buf = []
        try:
            async def disconnected():
                try:
                    return await request.is_disconnected()
                except Exception:
                    return False

            for chunk in plan_agent.stream_plan_iter(topic=req.topic, excel_info=excel_info, mode=req.mode):
                buf.append(chunk)
                yield chunk
                if await disconnected():
                    try:
                        (job_dir / "plan_stream_partial.txt").write_text("".join(buf), encoding="utf-8")
                    except Exception:
                        pass
                    return
        finally:
            full_text = "".join(buf)
            import re
            plan = None
            try:
                m = re.search(r"\{[\s\S]*\}", full_text)
                if m:
                    plan = json.loads(m.group(0))
            except Exception:
                plan = None
            if plan is None:
                plan = {
                    "objective": f"围绕主题『{req.topic}』进行数据探索与基础统计分析",
                    "steps": [
                        "加载Excel并读取所有Sheet",
                        "对每个Sheet进行描述性统计（行数、字段数、示例数据）",
                        "尝试针对关键字段生成简单的图表（柱状/折线）",
                    ],
                    "artifacts": {"report": "report.md", "plots": "plots/"},
                }
            plan["topic"] = req.topic
            try:
                (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
                _write_contract_artifacts(job_dir, plan=plan, excel_info=excel_info)
            except Exception:
                pass
            try:
                yield "\n" + json.dumps(plan, ensure_ascii=False, indent=2)
            except Exception:
                pass

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


# 分步：细化计划（可重试）
@router.post("/plan_refine", response_model=PlanRefineResponse)
async def refine_plan(req: PlanRefineRequest, request: Request):
    job_dir = JOBS_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在，请先生成计划")

    excel_info_path = job_dir / "excel_info.json"
    plan_path = job_dir / "plan.json"
    if not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="缺少Excel结构，请先上传或生成计划")

    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    excel_path = excel_info.get("path")
    if not plan_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划，请先调用/plan")
    base_plan = json.loads(plan_path.read_text(encoding="utf-8"))

    plan_agent = PlanAgent()
    want_stream = False
    try:
        q = request.query_params
        want_stream = q.get("stream") in ("1", "true", "True") or request.headers.get("X-Stream") in ("1", "true", "True")
    except Exception:
        want_stream = False
    excel_agent = ExcelAgent()
    profile_agent = DataProfileAgent()

    if not want_stream:
        excel_info = profile_agent.refine_profile(excel_path, excel_info=excel_info, plan=base_plan)
        excel_info_path.write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # Sync to ProfileManager
        md5 = excel_info.get("md5")
        if not md5 and Path(excel_path).exists():
            try:
                md5 = hashlib.md5(Path(excel_path).read_bytes()).hexdigest()
                excel_info["md5"] = md5
            except Exception:
                pass
        if md5:
            ProfileManager().save_profile(md5, excel_info)

        refined_plan = plan_agent.generate_refined_plan(topic=base_plan.get("topic", ""), excel_info=excel_info, base_plan=base_plan)
        merged = _merge_plan(base_plan, refined_plan)
        (job_dir / "plan.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_contract_artifacts(job_dir, plan=merged, excel_info=excel_info)
        return PlanRefineResponse(job_id=req.job_id, plan_initial=base_plan, plan_refined=merged)

    async def gen():
        yield f"JOB_ID:{req.job_id}\n"
        buf = []
        try:
            async def disconnected():
                try:
                    return await request.is_disconnected()
                except Exception:
                    return False
            for s_event in profile_agent.refine_profile_stream(excel_path, excel_info=excel_info, plan=base_plan):
                try:
                    excel_info_path.write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                yield s_event + "\n"
                if await disconnected():
                    return
            
            # Sync to ProfileManager after profiling
            md5 = excel_info.get("md5")
            if not md5 and Path(excel_path).exists():
                try:
                    md5 = hashlib.md5(Path(excel_path).read_bytes()).hexdigest()
                    excel_info["md5"] = md5
                except Exception:
                    pass
            if md5:
                ProfileManager().save_profile(md5, excel_info)

            for chunk in plan_agent.stream_refined_plan_iter(topic=base_plan.get("topic", ""), excel_info=excel_info, base_plan=base_plan):
                buf.append(chunk)
                yield chunk
                if await disconnected():
                    try:
                        (job_dir / "plan_refine_stream_partial.txt").write_text("".join(buf), encoding="utf-8")
                    except Exception:
                        pass
                    return
        finally:
            full_text = "".join(buf)
            import re
            refined = None
            try:
                m = re.search(r"\{[\s\S]*\}", full_text)
                if m:
                    refined = json.loads(m.group(0))
            except Exception:
                refined = None
            if refined is None:
                refined = dict(base_plan)
            merged = _merge_plan(base_plan, refined)
            try:
                (job_dir / "plan.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
                _write_contract_artifacts(job_dir, plan=merged, excel_info=excel_info)
            except Exception:
                pass
            try:
                yield "\n" + json.dumps({"job_id": req.job_id, "plan_refined": merged, "plan_initial": base_plan}, ensure_ascii=False, indent=2)
            except Exception:
                pass

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


# 分步：执行代码（可重试）
@router.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    job_dir = JOBS_DIR / req.job_id
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    if not plan_path.exists() or not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划或Excel结构，请先调用/plan")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    exec_result = _run_opencode_analysis(job_dir=job_dir, plan=plan, excel_info=excel_info)
    
    report_agent = ReportAgent()
    report_path = report_agent.build_report_modular(
        job_dir=str(job_dir), topic=plan.get("topic", ""), plan=plan, exec_result=exec_result, excel_info=excel_info,
        job_id=req.job_id,  # Pass job_id
    )
    _write_contract_artifacts(
        job_dir,
        plan=plan,
        excel_info=excel_info,
        exec_result=exec_result,
        report_text=_read_text_if_exists(Path(report_path)),
    )
    # 收集图表文件列表
    plot_files = _collect_plot_files(plots_dir)

    return ExecuteResponse(
        success=exec_result.get("success", False),
        report_path=report_path,
        logs=exec_result.get("logs"),
        plots=plot_files,
    )


# 初始代码流式生成
@router.post("/generate_code_stream")
async def generate_code_stream(job_id: str = Body(...)):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    if not plan_path.exists() or not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划或Excel结构，请先调用/plan")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    excel_path = excel_info.get("path")
    code_agent = CodeAgent(job_dir=str(job_dir))

    out_path = job_dir / "analysis.py"

    def gen():
        buf = []
        yield f"JOB_ID:{job_id}\n"
        yield "```python\n"
        for chunk in code_agent.stream_initial_code_iter(excel_path=excel_path, excel_info=excel_info, plan=plan):
            buf.append(chunk)
            yield chunk
        try:
            text = "".join(buf)
            m_code = extract_code_block(text)
            final_code = (m_code or text).replace("```python", "").replace("```", "").strip()
            if not final_code:
                final_code = code_agent._initial_code(excel_path=excel_path, excel_info=excel_info, plan=plan)
            out_path.write_text(final_code, encoding="utf-8")
        except Exception:
            pass
        yield "\n```"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


# 异步执行接口：返回立即，后台持续写入状态（exec_status.json）
def _run_execute_job(job_dir: Path, plan: dict, excel_info: dict, excel_path: str):
    exec_result = _run_opencode_analysis(job_dir=job_dir, plan=plan, excel_info=excel_info)
    report_agent = ReportAgent()
    report_path = report_agent.build_report_modular(
        job_dir=str(job_dir), topic=plan.get("topic", ""), plan=plan, exec_result=exec_result, excel_info=excel_info,
        job_id=job_dir.name,
    )
    _write_contract_artifacts(
        job_dir,
        plan=plan,
        excel_info=excel_info,
        exec_result=exec_result,
        report_text=_read_text_if_exists(Path(report_path)),
    )
    # 报告生成后更新状态文件，便于前端立即显示报告
    try:
        status_path = job_dir / "exec_status.json"
        status = {}
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
        status.update({
            "report_ready": bool(exec_result.get("success")),
            "report_path": report_path,
            "success": bool(exec_result.get("success")),
            "running": False,
            "message": "执行完成（报告已生成）" if exec_result.get("success") else "执行失败",
        })
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


@router.post("/execute_async")
async def execute_async(req: ExecuteRequest, background_tasks: BackgroundTasks):
    job_dir = JOBS_DIR / req.job_id
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    if not plan_path.exists() or not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划或Excel结构，请先调用/plan")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    excel_path = excel_info.get("path")
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # 初始化状态文件
    init_status = {
        "running": True,
        "success": False,
        "logs": [],
        "plots": [],
        "current_step": 0,
        "max_iters": 5,
        "report_ready": False,
        "report_path": None,
    }
    (job_dir / "exec_status.json").write_text(json.dumps(init_status, ensure_ascii=False, indent=2), encoding="utf-8")

    # 后台任务开始执行
    background_tasks.add_task(_run_execute_job, job_dir, plan, excel_info, excel_path)
    return {"started": True, "job_id": req.job_id}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    job_dir = JOBS_DIR / job_id
    status_path = job_dir / "exec_status.json"
    if not status_path.exists():
        return {
            "running": False,
            "success": False,
            "logs": [],
            "plots": [],
            "current_step": 0,
            "max_iters": 0,
        }
    data = json.loads(status_path.read_text(encoding="utf-8"))
    return data


# OpenCode 执行流式

@router.post("/execute_opencode_stream")
async def execute_opencode_stream(
    job_id: str = Body(..., embed=True),
    model: Optional[str] = Body(None, embed=True),
    request: Request = None,
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    if not plan_path.exists() or not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划或Excel结构，请先调用/plan")
    
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        _stream_opencode_analysis_lines(
            job_id=job_id,
            job_dir=job_dir,
            plan=plan,
            excel_info=excel_info,
            model=model,
        ),
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )

# 代码执行流式
from ..core.react_loop import ReActLoop
from ..core.sandbox_loop import SandboxLoop

@router.post("/execute_stream_v2")
async def execute_stream_v2(
    job_id: str = Body(..., embed=True),
    request: Request = None,
):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    if not plan_path.exists() or not excel_info_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划或Excel结构，请先调用/plan")
    
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        _stream_opencode_analysis_lines(
            job_id=job_id,
            job_dir=job_dir,
            plan=plan,
            excel_info=excel_info,
        ),
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )
    excel_path = excel_info.get("path")
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    code_agent = CodeAgent(job_dir=str(job_dir))
    out_path = job_dir / "analysis.py"
    init_duration = time.time() - start_time
    print(f"Init Time: {init_duration:.4f}s")

    # Reset status
    init_status = {
        "running": True,
        "success": False,
        "logs": [],
        "plots": [],
        "current_step": 0,
        "max_iters": 5,
        "report_ready": False,
    }
    (job_dir / "exec_status.json").write_text(json.dumps(init_status, ensure_ascii=False, indent=2), encoding="utf-8")

    async def gen():
        total_start_time = time.time()
        yield json.dumps({"type": "meta", "job_id": job_id}) + "\n"
        
        # 1. Initial Code Generation
        phase_start = time.time()
        yield json.dumps({"type": "phase", "phase": "code_generation"}) + "\n"
        
        full_code_buf = []
        try:
            for chunk in code_agent.stream_initial_code_iter(excel_path=excel_path, excel_info=excel_info, plan=plan):
                print(chunk)
                yield json.dumps({"type": "code_chunk", "content": chunk}) + "\n"
                full_code_buf.append(chunk)
                if request and await request.is_disconnected():
                    return
        except Exception as e:
            yield json.dumps({"type": "error", "error": f"Code generation failed: {str(e)}"}) + "\n"
            return

        full_text = "".join(full_code_buf)
        # Extract code
        m_code = extract_code_block(full_text)
        final_code = (m_code or full_text).replace("```python", "").replace("```", "").strip()
        if not final_code:
            final_code = code_agent._initial_code(excel_path=excel_path, excel_info=excel_info, plan=plan)
        
        out_path.write_text(final_code, encoding="utf-8")
        yield json.dumps({"type": "code_saved", "path": str(out_path)}) + "\n"

        code_gen_duration = time.time() - phase_start
        print(f"[Timing] Code Generation took {code_gen_duration:.2f}s")
        yield json.dumps({"type": "log", "content": f"Code Generation took {code_gen_duration:.2f}s"}) + "\n"

        # 2. Execution Loop
        phase_start = time.time()
        yield json.dumps({"type": "phase", "phase": "execution"}) + "\n"
        
        use_monty = os.getenv("USE_MONTY_SANDBOX", "false").lower() == "true"
        executor = CodeExecutor(work_dir=str(job_dir), use_monty=use_monty)
        
        # Determine max_iters
        sheets = excel_info.get("sheets", []) or []
        sheet_count = len(sheets)
        if sheet_count >= 12: max_iters = 12
        elif sheet_count >= 6: max_iters = 8
        else: max_iters = 5
        
        # Use SandboxLoop for advanced execution
        sandbox = SandboxLoop(max_iters=max_iters)
        
        ctx = {
            "excel_info": excel_info,
            "plan": plan,
            "excel_path": excel_path,
            "plots_dir": str(plots_dir),
            "job_dir": str(job_dir),
        }
        
        exec_success = False
        exec_result_logs = []
        
        for event in sandbox.stream_run(executor=executor, context=ctx):
            yield json.dumps(event, ensure_ascii=False) + "\n"
            if event.get("type") == "done":
                exec_success = event.get("success", False)
                exec_result_logs = event.get("logs", [])
            if request and await request.is_disconnected():
                return
        
        # Save exec_logs
        exec_result = {"success": exec_success, "logs": exec_result_logs, "code_path": str(out_path), "plots_dir": str(plots_dir)}
        (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")

        exec_duration = time.time() - phase_start
        print(f"[Timing] Execution took {exec_duration:.2f}s")
        yield json.dumps({"type": "log", "content": f"Execution took {exec_duration:.2f}s"}) + "\n"

        # 3. Report Generation (SKIPPED - Manual Trigger)
        # We stop here to let user confirm execution results before generating report.
        
        # Update status to success (report_ready=False)
        status_path = job_dir / "exec_status.json"
        if status_path.exists():
            st = json.loads(status_path.read_text(encoding="utf-8"))
            st.update({
                "report_ready": False,
                "success": exec_success,
                "running": False,
                "message": "执行完成（等待生成报告）" if exec_success else "执行失败"
            })
            status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        
        yield json.dumps({"type": "exec_done", "success": exec_success, "message": "Execution finished. Waiting for manual report generation."}) + "\n"

        """
        # 3. Report Generation
        phase_start = time.time()
        yield json.dumps({"type": "phase", "phase": "report"}) + "\n"
        
        try:
            report_agent = ReportAgent()
            report_path = report_agent.build_report_modular(
                job_dir=str(job_dir),
                topic=plan.get("topic", ""),
                plan=plan,
                exec_result=exec_result,
                excel_info=excel_info,
                job_id=job_id,
            )
            report_duration = time.time() - phase_start
            print(f"[Timing] Report Generation took {report_duration:.2f}s")
            yield json.dumps({"type": "log", "content": f"Report Generation took {report_duration:.2f}s"}) + "\n"

            yield json.dumps({"type": "report_ready", "report_path": report_path}) + "\n"
            
            # Update status to success
            status_path = job_dir / "exec_status.json"
            if status_path.exists():
                st = json.loads(status_path.read_text(encoding="utf-8"))
                st.update({
                    "report_ready": True,
                    "report_path": report_path,
                    "success": True,
                    "running": False,
                    "message": "执行完成（报告已生成）"
                })
                status_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
                
        except Exception as e:
            yield json.dumps({"type": "error", "error": f"Report generation failed: {str(e)}"}) + "\n"
        """
        
        total_duration = time.time() - total_start_time
        print(f"[Timing] Total Process took {total_duration:.2f}s")
        yield json.dumps({"type": "log", "content": f"Total Process took {total_duration:.2f}s"}) + "\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


# 更新计划（保存用户编辑的计划）
@router.post("/plan_update", response_model=PlanUpdateResponse)
async def plan_update(req: PlanUpdateRequest):
    job_dir = JOBS_DIR / req.job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在，请先生成计划")
    plan_json_path = job_dir / "plan.json"
    plan_text = json.dumps(req.plan, ensure_ascii=False, indent=2)
    plan_json_path.write_text(plan_text, encoding="utf-8")
    _write_contract_artifacts(job_dir, plan=req.plan)

    return PlanUpdateResponse(ok=True, job_id=req.job_id)
from ..services.chapters import SectionContext, REGISTRY
