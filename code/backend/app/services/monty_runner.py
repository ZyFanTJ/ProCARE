
import sys
import asyncio
import traceback
from pathlib import Path
import pydantic_monty

async def run_monty_script(script_path: str):
    try:
        path = Path(script_path)
        if not path.exists():
            print(f"Error: Script not found at {script_path}", file=sys.stderr)
            sys.exit(1)
            
        code = path.read_text(encoding="utf-8")
        
        # Configure Monty
        # Using minimal configuration for secure sandbox execution
        m = pydantic_monty.Monty(
            code,
            script_name=path.name,
            # external_functions=[], # Add allowed functions here if needed
        )
        
        # Run Monty
        if hasattr(pydantic_monty, 'run_monty_async'):
            await pydantic_monty.run_monty_async(m)
        else:
            # Fallback for sync version if async is not available
            pydantic_monty.run_monty(m)
            
    except Exception as e:
        # Monty errors might be complex objects, ensure we print a string
        print(f"Monty Execution Error: {str(e)}", file=sys.stderr)
        # Optional: Print stack trace if it's a python exception
        # traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python monty_runner.py <script_path>", file=sys.stderr)
        sys.exit(1)
        
    script_path = sys.argv[1]
    
    # Run the async main function
    try:
        asyncio.run(run_monty_script(script_path))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Runner Error: {e}", file=sys.stderr)
        sys.exit(1)
