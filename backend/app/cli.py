import argparse
import json
import time
import uuid
from pathlib import Path

from .agents.excel_agent import ExcelAgent
from .agents.plan_agent import PlanAgent
from .agents.code_agent import CodeAgent
from .agents.report_agent import ReportAgent


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"
JOBS_DIR = OUTPUT_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="AI4Research CLI")
    parser.add_argument("--excel", required=True, help="Excel文件路径")
    parser.add_argument("--topic", required=True, help="研究主题")
    parser.add_argument("--desc", default=None, help="Excel补充描述")
    parser.add_argument("--refine", action="store_true", help="是否在生成初步计划后执行细化计划")
    args = parser.parse_args()

    excel_path = args.excel
    topic = args.topic
    desc = args.desc

    job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Job: {job_id}")

    excel_agent = ExcelAgent()
    excel_info = excel_agent.analyze_excel(excel_path, user_description=desc)
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")

    plan_agent = PlanAgent()
    plan = plan_agent.generate_plan(topic=topic, excel_info=excel_info)
    (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    # 如指定 --refine，则执行按计划细化画像与细化计划生成
    if args.refine:
        excel_info = excel_agent.refine_profile(path=excel_path, excel_info=excel_info, plan=plan)
        (job_dir / "excel_info.json").write_text(json.dumps(excel_info, ensure_ascii=False, indent=2), encoding="utf-8")
        refined = plan_agent.generate_refined_plan(topic=topic, excel_info=excel_info, base_plan=plan)
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
        plan = _merge_plan(plan, refined)
        (job_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    code_agent = CodeAgent(job_dir=str(job_dir))
    exec_result = code_agent.generate_and_execute(plan=plan, excel_info=excel_info, excel_path=excel_path)
    (job_dir / "exec_logs.json").write_text(json.dumps(exec_result, ensure_ascii=False, indent=2), encoding="utf-8")

    report_agent = ReportAgent()
    report_path = report_agent.build_report_modular(
        job_dir=str(job_dir), topic=topic, plan=plan, exec_result=exec_result, excel_info=excel_info,
        job_id=job_id,
    )
    print(f"[INFO] Report: {report_path}")


if __name__ == "__main__":
    main()