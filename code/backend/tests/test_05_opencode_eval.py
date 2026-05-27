import os
import sys
import shutil
import json
import time
import subprocess
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from app.core.opencode_runner import OpenCodeRunner

def evaluate_opencode():
    print("\n[Eval] Starting OpenCode Evaluation...")
    
    # Source test directory provided by the user
    source_test_dir = BASE_DIR / "tests" / "test_job_opencode"
    if not source_test_dir.exists():
        print(f"[Error] Source test directory not found: {source_test_dir}")
        return

    # Target execution directory
    test_dir = BASE_DIR / "tests" / "output" / "job_opencode_eval"
    if test_dir.exists():
        try:
            shutil.rmtree(test_dir)
        except Exception as e:
            print(f"Failed to remove existing test dir: {e}")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    plots_dir = test_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Create dummy .git to prevent opencode from looking upwards
    (test_dir / ".git").mkdir()

    print(f"[Eval] Copying test data from {source_test_dir} to {test_dir}...")
    for item in source_test_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, test_dir / item.name)

    # Validate inputs
    plan_path = test_dir / "plan.json"
    excel_info_path = test_dir / "excel_info.json"
    md_path = test_dir / "implementation_plan.md"
    
    if not plan_path.exists() or not excel_info_path.exists() or not md_path.exists():
        print("[Error] Missing required files (plan.json, excel_info.json, or implementation_plan.md).")
        return
        
    # Update excel_info.json to point to the local dataset file to ensure it runs correctly locally
    dataset_file = test_dir / "03-数据集-截至202509.xlsx"
    if dataset_file.exists():
        with open(excel_info_path, "r", encoding="utf-8") as f:
            excel_info = json.load(f)
        old_path = excel_info.get("path", "")
        new_path = str(dataset_file.resolve())
        excel_info["path"] = new_path
        with open(excel_info_path, "w", encoding="utf-8") as f:
            json.dump(excel_info, f, ensure_ascii=False, indent=2)
            
        # Also replace path in implementation_plan.md
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        md_content = md_content.replace(old_path, new_path)
        # Fix possible escaped backslashes issue in md
        md_content = md_content.replace(old_path.replace("\\", "\\\\"), new_path)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    # Initialize OpenCodeRunner
    print("\n[Eval] Initializing OpenCodeRunner...")
    runner = OpenCodeRunner(work_dir=str(test_dir))

    # Run OpenCode stream
    print("[Eval] Starting OpenCode execution...")
    # Using the exact same prompt as the actual route
    prompt = (
        "Read the instructions in `implementation_plan.md` carefully. "
        "Check `excel_info.json` for exact sheet names and columns. "
        "You must ONLY work within the current directory. "
        "Write the final data analysis code to `analysis.py` (or `main.py` if modular). "
        "Any plots generated must be saved into the `plots/` subdirectory. "
        "Make sure the code is complete, correct, and runnable."
    )
    
    # Get active model to maintain consistency with the system
    active_model = "openai/gpt-5.4" # default to a known opencode model
    try:
        from app.core.settings_manager import SettingsManager
        settings = SettingsManager().get_settings()
        if settings and settings.get("llm") and settings["llm"].get("active_model"):
            active_model = settings["llm"]["active_model"]
    except Exception as e:
        print(f"[Eval] Failed to get active model from settings, using default: {e}")


    t0 = time.time()
    logs = []
    success = False
    
    for event in runner.stream_run(prompt, model=active_model):
        event_type = event.get("type")
        if event_type == "log":
            content = event.get("content", "")
            print(content, end="", flush=True)
            logs.append(content)
        elif event_type == "error":
            print(f"\n[Error] OpenCode error: {event.get('content')}")
        elif event_type == "done":
            success = True
            print(f"\n[Eval] OpenCode execution completed stream.")
            
    elapsed = time.time() - t0
    print(f"\n[Eval] OpenCode run took {elapsed:.2f} seconds.")

    # Check output
    analysis_py = test_dir / "analysis.py"
    main_py = test_dir / "main.py"
    
    script_to_run = main_py if main_py.exists() else analysis_py
    
    if script_to_run.exists():
        print(f"\n[Success] {script_to_run.name} was generated! Size: {script_to_run.stat().st_size} bytes")
        
        # Verify if it's executable
        print(f"[Eval] Validating generated code execution ({script_to_run.name})...")
        try:
            proc = subprocess.run(
                        [sys.executable, str(script_to_run)],
                        cwd=str(test_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=300, # wait at most 300s
                    )
            if proc.returncode == 0:
                print(f"[Eval] Code execution SUCCESS! Output preview:\n{proc.stdout[:500]}")
                # Check plots
                generated_plots = list(plots_dir.glob("*.png"))
                if generated_plots:
                    print(f"[Eval] Generated {len(generated_plots)} plots: {[p.name for p in generated_plots]}")
                else:
                    print("[Eval] No plots were generated.")
            else:
                print(f"[Eval] Code execution FAILED! Error preview:\n{proc.stderr[:500]}")
        except subprocess.TimeoutExpired:
            print("[Eval] Code execution TIMED OUT (30s).")
        except Exception as e:
            print(f"[Eval] Failed to run code: {e}")
            
    else:
        print("\n[Failure] analysis.py was NOT generated.")
        
    print(f"\n[Eval] Done. Please inspect {test_dir} for full results.")

if __name__ == "__main__":
    evaluate_opencode()
