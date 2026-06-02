from fastapi import APIRouter, Body, HTTPException
from app.core.settings_manager import SettingsManager
from typing import Dict, Any

router = APIRouter()

@router.get("")
async def get_settings():
    try:
        manager = SettingsManager()
        return manager.get_settings()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def update_settings(settings: Dict[str, Any] = Body(...)):
    try:
        manager = SettingsManager()
        manager.update_settings(settings)
        return {"status": "success", "settings": manager.get_settings()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_settings():
    try:
        manager = SettingsManager()
        defaults = manager.reset_settings()
        return {"status": "success", "settings": defaults}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
