import json
import os
import time
import uuid
import hashlib
from pathlib import Path
import shutil
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi import BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.responses import StreamingResponse
from fastapi import Request

from ..agents.excel_agent import ExcelAgent
from ..agents.plan_agent import PlanAgent
from ..agents.code_agent import CodeAgent
from ..agents.report_agent import ReportAgent
from ..core.llm import LLMClient
from ..models.schemas import (
    ResearchRequest, ResearchResponse,
    PlanRequest, PlanResponse,
    ExecuteRequest, ExecuteResponse,
    PlanUpdateRequest, PlanUpdateResponse,
    PlanRefineRequest, PlanRefineResponse,
    ReportRegenRequest, ReportRegenResponse,
)


router = APIRouter()


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
JOBS_DIR = OUTPUT_DIR / "jobs"
ROOT_DIR = BASE_DIR.parents[1] if len(BASE_DIR.parents) >= 2 else BASE_DIR

for d in [OUTPUT_DIR, UPLOAD_DIR, JOBS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


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
    index_path = UPLOAD_DIR / "md5_index.json"
    index: dict = {}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            index = {}

    # 若MD5已存在且文件仍在，直接复用之前的路径（兼容现有重命名策略）
    existing_path = index.get(md5)
    if existing_path and Path(existing_path).exists():
        excel_agent = ExcelAgent()
        excel_info = excel_agent.analyze_excel(str(existing_path), user_description=description)
        # 创建job目录并保存excel_info.json，保证分步流程的前置可用性
        job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        job_dir = JOBS_DIR / job_id
        plots_dir = job_dir / "plots"
        job_dir.mkdir(parents=True, exist_ok=True)
        plots_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "excel_path": str(existing_path),
            "excel_info": excel_info,
            "duplicate": True,
            "md5": md5,
            "job_id": job_id,
        }

    # 保存上传文件（沿用时间戳+uuid+原文件名的兼容命名策略）
    ts = int(time.time())
    save_name = f"{ts}_{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = UPLOAD_DIR / save_name
    save_path.write_bytes(content)
    # 更新MD5索引
    try:
        index[md5] = str(save_path)
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # 索引写入失败不影响主流程
        pass

    # 分析结构并创建job目录，保存excel_info.json
    excel_agent = ExcelAgent()
    excel_info = excel_agent.analyze_excel(str(save_path), user_description=description)
    job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    plots_dir = job_dir / "plots"
    job_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "excel_path": str(save_path),
        "excel_info": excel_info,
        "duplicate": False,
        "md5": md5,
        "job_id": job_id,
    }


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
    excel_info = excel_agent.refine_profile(excel_path, excel_info=excel_info, plan=plan)
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    refined_plan = plan_agent.generate_refined_plan(topic=req.topic, excel_info=excel_info, base_plan=plan)
    plan = _merge_plan(plan, refined_plan)
    (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) 代码生成与ReAct执行
    code_agent = CodeAgent(job_dir=str(job_dir))
    exec_result = code_agent.generate_and_execute(plan=plan, excel_info=excel_info, excel_path=excel_path)
    (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")

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
    return ResearchResponse(
        job_id=job_id,
        success=exec_result.get("success", False),
        report_path=report_path,
    )


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
            if plan_path.exists():
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
    except Exception:
        pass
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
        "files": "查看上传的文件列表与基本信息。",
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
        try:
            plan_path = job_dir / "plan_refined.json"
            if not plan_path.exists():
                plan_path = job_dir / "plan.json"
            if plan_path.exists():
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                topic = plan.get("topic") or plan.get("objective")
                if topic:
                    parts.append(f"主题:{topic}")
        except Exception:
            pass
        try:
            status_path = job_dir / "report_status.json"
            if status_path.exists():
                st = json.loads(status_path.read_text(encoding="utf-8"))
                state = st.get("state")
                prog = st.get("progress")
                parts.append(f"报告状态:{state} 进度:{prog}")
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

@router.post("/assistant/chat")
async def assistant_chat(
    page_key: str = Body(...),
    pathname: str = Body(...),
    job_id: Optional[str] = Body(None),
    messages: list = Body([]),
):
    llm = LLMClient()
    prompt = _build_prompt(page_key, pathname, job_id, messages)
    reply = llm.generate(prompt)
    return {"reply": reply}

@router.post("/assistant/chat_stream")
async def assistant_chat_stream(
    page_key: str = Body(...),
    pathname: str = Body(...),
    job_id: Optional[str] = Body(None),
    messages: list = Body([]),
):
    llm = LLMClient()
    def gen():
        if job_id:
            yield f"JOB_ID:{job_id}\n"
        prompt = _build_prompt(page_key, pathname, job_id, messages)
        for chunk in llm.stream_iter(prompt):
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
        plan = plan_agent.generate_plan(topic=req.topic, excel_info=excel_info)
        (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
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

            for chunk in plan_agent.stream_plan_iter(topic=req.topic, excel_info=excel_info):
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

    if not want_stream:
        excel_info = excel_agent.refine_profile(excel_path, excel_info=excel_info, plan=base_plan)
        excel_info_path.write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
        refined_plan = plan_agent.generate_refined_plan(topic=base_plan.get("topic", ""), excel_info=excel_info, base_plan=base_plan)
        merged = _merge_plan(base_plan, refined_plan)
        (job_dir / "plan.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
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
            for s_event in excel_agent.refine_profile_stream(excel_path, excel_info=excel_info, plan=base_plan):
                try:
                    excel_info_path.write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                yield s_event + "\n"
                if await disconnected():
                    return
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
    excel_path = excel_info.get("path")
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    code_agent = CodeAgent(job_dir=str(job_dir))
    exec_result = code_agent.generate_and_execute(plan=plan, excel_info=excel_info, excel_path=excel_path)
    (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")

    report_builder = ReportBuilder()
    report_path = report_builder.build_report(
        job_dir=str(job_dir), topic=plan.get("topic", ""), plan=plan, exec_result=exec_result, excel_info=excel_info,
        job_id=req.job_id,  # Pass job_id
    )
    # 收集图表文件列表
    plot_files = []
    if plots_dir.exists():
        for p in sorted(plots_dir.glob("*.png")):
            plot_files.append(p.name)

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
            m_code = code_agent._extract_code_block(text)  # type: ignore[attr-defined]
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
    code_agent = CodeAgent(job_dir=str(job_dir))
    exec_result = code_agent.generate_and_execute(plan=plan, excel_info=excel_info, excel_path=excel_path)
    (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_builder = ReportBuilder()
    report_path = report_builder.build_report(
        job_dir=str(job_dir), topic=plan.get("topic", ""), plan=plan, exec_result=exec_result, excel_info=excel_info,
        job_id=job_dir.name,
    )
    # 报告生成后更新状态文件，便于前端立即显示报告
    try:
        status_path = job_dir / "exec_status.json"
        status = {}
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
        status.update({
            "report_ready": True,
            "report_path": report_path,
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


# 代码执行流式
@router.post("/execute_stream")
async def execute_stream(job_id: str = Body(...)):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job不存在")
    plan_path = job_dir / "plan.json"
    excel_info_path = job_dir / "excel_info.json"
    code_path = job_dir / "analysis.py"
    if not plan_path.exists() or not excel_info_path.exists() or not code_path.exists():
        raise HTTPException(status_code=400, detail="缺少计划/Excel结构/代码文件")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    excel_info = json.loads(excel_info_path.read_text(encoding="utf-8"))
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    executor = CodeExecutor(work_dir=str(job_dir))

    status_path = job_dir / "exec_status.json"

    def gen():
        logs = []
        yield f"JOB_ID:{job_id}\n"
        yield "PHASE:EXEC_START\n"
        try:
            for line in executor.run_script_path_stream(str(code_path)):
                logs.append({"line": line})
                try:
                    plots = [p.name for p in sorted(plots_dir.glob("*.png"))]
                except Exception:
                    plots = []
                payload = {
                    "running": True,
                    "success": False,
                    "logs": logs,
                    "plots": plots,
                    "current_step": 0,
                    "max_iters": 1,
                }
                try:
                    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                yield line
        finally:
            try:
                plots = [p.name for p in sorted(plots_dir.glob("*.png"))]
            except Exception:
                plots = []
            end_payload = {
                "running": False,
                "success": any("TASK_DONE" in (l.get("line") or "") for l in logs),
                "logs": logs,
                "plots": plots,
                "current_step": 0,
                "max_iters": 1,
            }
            try:
                status_path.write_text(json.dumps(end_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

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

    return PlanUpdateResponse(ok=True, job_id=req.job_id)
from ..services.chapters import SectionContext, REGISTRY