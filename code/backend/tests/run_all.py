
import subprocess
import sys
import os
from pathlib import Path

def run_script(script_name):
    script_path = Path(__file__).parent / script_name
    print(f"\n{'='*50}")
    print(f"Running {script_name}...")
    print(f"{'='*50}")
    
    env = os.environ.copy()
    # Add project root to PYTHONPATH
    project_root = str(Path(__file__).resolve().parents[1])
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] += os.pathsep + project_root
    else:
        env["PYTHONPATH"] = project_root
        
    # Ensure OPENAI_API_MODEL is set
    if "OPENAI_API_MODEL" not in env:
        env["OPENAI_API_MODEL"] = "gemini-3-pro-preview"
        
    result = subprocess.run([sys.executable, str(script_path)], env=env, capture_output=False)
    
    if result.returncode != 0:
        print(f"\n[FAIL] {script_name} failed with exit code {result.returncode}")
        return False
    else:
        print(f"\n[PASS] {script_name} completed successfully.")
        return True

def main():
    scripts = [
        "create_dummy_data.py",
        "test_01_profile.py",
        "test_02_plan.py",
        "test_03_sandbox.py",
        "test_04_report.py"
    ]
    
    for script in scripts:
        if not run_script(script):
            print("\nStopping due to failure.")
            sys.exit(1)
            
    print("\nAll tests passed successfully!")

if __name__ == "__main__":
    main()
