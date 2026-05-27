import os
import sys
import shutil
import json
from pathlib import Path

# Add backend to sys.path to allow imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.opencode_runner import OpenCodeRunner

def main():
    test_dir = Path(__file__).parent / "test_job_opencode"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a dummy .git to prevent opencode from climbing up
    (test_dir / ".git").mkdir()

    # 1. Create a dummy excel_info.json
    excel_info = {
        "path": "test_data.csv",
        "columns": ["age", "income", "score"]
    }
    (test_dir / "excel_info.json").write_text(json.dumps(excel_info), encoding="utf-8")

    # 2. Create a dummy dummy_data.csv
    (test_dir / "dummy_data.csv").write_text("age,income,score\n25,50000,80\n30,60000,85\n", encoding="utf-8")

    # 3. Create a plan
    plan = {
        "objective": "Analyze the dummy data and create a scatter plot.",
        "steps": [
            "Load the dummy_data.csv",
            "Print summary statistics",
            "Plot age vs income and save to plots/scatter.png"
        ]
    }

    # 4. Initialize runner
    runner = OpenCodeRunner(work_dir=str(test_dir))

    # 5. Generate instruction
    md_path = runner.generate_instruction_markdown(plan, excel_info)
    print(f"Generated instruction at: {md_path}")
    print(md_path.read_text(encoding="utf-8"))
    print("-" * 50)

    # 6. Run the stream
    prompt = "Read the instructions in ./implementation_plan.md. You must only work within the current directory. Write the final code to ./analysis.py and save plots to ./plots/"
    
    print("Starting OpenCode execution...")
    for event in runner.stream_run(prompt):
        if event.get("type") == "log":
            # Print without extra newline as it usually contains them
            print(event.get("content", ""), end="")
        else:
            print(f"\n[Event]: {event}\n")

if __name__ == "__main__":
    main()
