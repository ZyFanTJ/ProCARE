import os
import sys
import shutil
import json
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from app.core.opencode_runner import OpenCodeRunner

def test_opencode_job():
    print("\n[Test] Starting OpenCode Execution with real job context...")
    
    # Source job directory
    source_job_dir = BASE_DIR / "output" / "jobs" / "job_1774932471_7deadd09"
    if not source_job_dir.exists():
        print(f"[Error] Source job directory not found: {source_job_dir}")
        return

    # Target test directory
    test_dir = Path(__file__).parent / "output" / "job_opencode_real"
    if test_dir.exists():
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            print(f"Failed to remove existing test dir: {e}")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    plots_dir = test_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Create dummy .git
    (test_dir / ".git").mkdir()

    # Load inputs from source job
    plan_path = source_job_dir / "plan.json"
    excel_info_path = source_job_dir / "excel_info.json"
    
    if not plan_path.exists() or not excel_info_path.exists():
        print("[Error] Missing plan.json or excel_info.json in source job directory.")
        return

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    with open(excel_info_path, "r", encoding="utf-8") as f:
        excel_info = json.load(f)
        
    # In excel_info, the path might be absolute to some original file. We just use it as is if it exists.
    # Check if the excel file exists
    excel_path = Path(excel_info.get("path", ""))
    if not excel_path.exists():
        print(f"[Warning] Original excel file not found at: {excel_path}")
        # Try to find a test data file if original is missing
        fallback_excel = Path(__file__).parent / "test_data.xlsx"
        if fallback_excel.exists():
            print(f"[Info] Using fallback test_data.xlsx: {fallback_excel}")
            excel_info["path"] = str(fallback_excel.resolve())
            excel_path = fallback_excel
        else:
            print("[Warning] No fallback excel file found either. OpenCode might fail to read data.")

    # Copy plan and excel_info to test_dir just for completeness
    with open(test_dir / "plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    with open(test_dir / "excel_info.json", "w", encoding="utf-8") as f:
        json.dump(excel_info, f, indent=2, ensure_ascii=False)

    # Initialize OpenCodeRunner
    print("[Test] Initializing OpenCodeRunner...")
    runner = OpenCodeRunner(work_dir=str(test_dir))

    # Generate Instruction
    print("[Test] Generating instruction markdown...")
    md_path = runner.generate_instruction_markdown(plan, excel_info)
    print(f"[Test] Instruction generated at: {md_path}")
    print("-" * 50)
    print(md_path.read_text(encoding="utf-8")[:500] + "\n... [truncated]")
    print("-" * 50)

    # Run OpenCode stream
    print("[Test] Starting OpenCode execution...")
    # Using the same prompt logic as in execute_opencode_stream
    prompt = (
        "Read the instructions in `implementation_plan.md` carefully. "
        "You must ONLY work within the current directory. "
        "Write the final data analysis code to `analysis.py`. "
        "Any plots generated must be saved into the `plots/` subdirectory. "
        "Make sure the code is complete, correct, and runnable."
    )
    
    logs = []
    for event in runner.stream_run(prompt):
        event_type = event.get("type")
        if event_type == "log":
            content = event.get("content", "")
            print(content, end="", flush=True)
            logs.append(content)
        elif event_type == "error":
            print(f"\n[Error] OpenCode error: {event.get('content')}")
        elif event_type == "done":
            print(f"\n[Test] OpenCode execution completed.")
            
    # Check output
    analysis_py = test_dir / "analysis.py"
    if analysis_py.exists():
        print(f"\n[Success] analysis.py was generated! Size: {analysis_py.stat().st_size} bytes")
    else:
        print("\n[Failure] analysis.py was NOT generated.")
        
    print(f"[Test] Done. Check {test_dir} for results.")

if __name__ == "__main__":
    test_opencode_job()
