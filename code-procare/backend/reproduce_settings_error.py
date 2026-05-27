
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.append(str(backend_dir))

try:
    from app.core.settings_manager import SettingsManager
    
    print("Initializing SettingsManager...")
    manager = SettingsManager()
    print("SettingsManager initialized.")
    
    print("Getting settings...")
    settings = manager.get_settings()
    print("Settings retrieved successfully.")
    print(settings)

except Exception as e:
    print(f"Caught exception: {e}")
    import traceback
    traceback.print_exc()
