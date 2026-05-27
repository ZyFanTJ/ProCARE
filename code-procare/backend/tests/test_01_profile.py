
import sys
import json
import pandas as pd
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from app.agents.data_profile_agent import DataProfileAgent

def test_data_profile(excel_path):
    print(f"\n[Test] Starting Data Profiling on {excel_path}...")
    
    agent = DataProfileAgent()
    
    # 1. Prepare initial info
    xls = pd.ExcelFile(excel_path)
    sheets = xls.sheet_names
    excel_info = {
        "sheets": sheets,
        "profile": {}
    }
    
    # 2. Prepare dummy plan
    # If plan is empty, we need to ensure _get_target_sheets works.
    # Assuming it defaults to all sheets if plan doesn't specify.
    plan = {
        "objective": "Test Profiling",
        "steps": ["Analyze Sheet1"]
    }
    
    # Run profiling (Synchronous)
    print("[Test] Running refine_profile...")
    profile_result = agent.refine_profile(excel_path, excel_info, plan)
    
    # Save result
    output_path = Path(__file__).parent / "output" / "excel_info.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile_result, f, indent=2, ensure_ascii=False)
        
    print(f"[Test] Profiling complete. Saved to {output_path}")
    return profile_result

if __name__ == "__main__":
    test_file = Path(__file__).parent / "test_data.xlsx"
    if not test_file.exists():
        # Generate data if not exists
        try:
            from create_dummy_data import create_dummy_excel
            create_dummy_excel(str(test_file))
        except ImportError:
            # If running independently, try to import from current dir
            sys.path.append(str(Path(__file__).parent))
            from create_dummy_data import create_dummy_excel
            create_dummy_excel(str(test_file))
        
    test_data_profile(str(test_file))
