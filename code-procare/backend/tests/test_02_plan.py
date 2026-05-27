
import sys
import json
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from app.agents.plan_agent import PlanAgent

def test_plan_generation():
    print("\n[Test] Starting Plan Generation...")
    
    # Load input
    input_path = Path(__file__).parent / "output" / "excel_info.json"
    if not input_path.exists():
        print(f"[Error] Input file {input_path} not found. Run test_01_profile.py first.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        excel_info = json.load(f)
        
    topic = "Analyze the impact of Age and Gender on Outcome_Score"
    print(f"[Test] Topic: {topic}")
    
    agent = PlanAgent()
    
    # Generate plan
    plan = agent.generate_plan(topic, excel_info)
    
    # Save result
    output_path = Path(__file__).parent / "output" / "plan.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
        
    print(f"[Test] Plan generation complete. Saved to {output_path}")
    return plan

if __name__ == "__main__":
    test_plan_generation()
