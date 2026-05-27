
import sys
import json
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from app.agents.report_agent import ReportAgent

def test_report_generation():
    print("\n[Test] Starting Report Generation...")
    
    # Load inputs
    plan_path = Path(__file__).parent / "output" / "plan.json"
    excel_info_path = Path(__file__).parent / "output" / "excel_info.json"
    exec_result_path = Path(__file__).parent / "output" / "exec_result.json"
    
    # Use the job directory from test_03
    job_dir = Path(__file__).parent / "output" / "job_sandbox"
    
    if not plan_path.exists() or not excel_info_path.exists() or not exec_result_path.exists():
        print("[Error] Missing input files. Run previous tests first.")
        return
        
    if not job_dir.exists():
         print("[Error] Job directory missing. Run test_03_sandbox.py first.")
         return

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    with open(excel_info_path, "r", encoding="utf-8") as f:
        excel_info = json.load(f)
    with open(exec_result_path, "r", encoding="utf-8") as f:
        exec_result = json.load(f)
        
    topic = plan.get("topic", "Test Topic")
    
    agent = ReportAgent()
    
    try:
        report_path = agent.build_report_modular(
            job_dir=str(job_dir),
            topic=topic,
            plan=plan,
            exec_result=exec_result,
            excel_info=excel_info,
            job_id="test_job_id"
        )
        print(f"[Test] Report generated at: {report_path}")
        
        # Verify
        if Path(report_path).exists():
             print("[Test] SUCCESS: Report file exists.")
        else:
             print("[Test] FAILURE: Report file returned but not found on disk.")
             
    except Exception as e:
        print(f"[Test] Report generation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_report_generation()
