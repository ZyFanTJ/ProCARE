import httpx
import json
import shutil
from pathlib import Path
import sys

def main():
    base_url = "http://localhost:8000"
    
    # 1. First make sure the dummy job exists in backend/output/jobs
    backend_dir = Path(__file__).resolve().parents[1]
    jobs_dir = backend_dir / "output" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    
    job_id = "test_opencode_job_123"
    job_dir = jobs_dir / job_id
    
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a dummy excel_info.json
    excel_info = {
        "path": str(job_dir / "dummy_data.csv"),
        "columns": ["age", "income", "score"]
    }
    (job_dir / "excel_info.json").write_text(json.dumps(excel_info), encoding="utf-8")
    
    # Create a dummy dummy_data.csv
    (job_dir / "dummy_data.csv").write_text("age,income,score\n25,50000,80\n30,60000,85\n", encoding="utf-8")
    
    # Create a plan
    plan = {
        "objective": "Analyze the dummy data and create a scatter plot.",
        "steps": [
            "Load the dummy_data.csv",
            "Print summary statistics",
            "Plot age vs income and save to plots/scatter.png"
        ]
    }
    (job_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    
    print(f"Created test job: {job_id}")
    print(f"Sending request to {base_url}/api/execute_opencode_stream...")
    
    try:
        with httpx.stream("POST", f"{base_url}/api/execute_opencode_stream", json={"job_id": job_id}, timeout=300.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "log":
                            print(data.get("content", ""), end="")
                        else:
                            print(f"\n[Event]: {data}\n")
                    except json.JSONDecodeError:
                        print(line)
    except Exception as e:
        print(f"Error calling API: {e}")
        print("Make sure the backend server is running (uvicorn app.main:app).")

if __name__ == "__main__":
    main()
