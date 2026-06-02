import json
import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_SETTINGS = {
    "systemName": "RWS研究系统",
    "footerText": "2026 AI4RWS System",
    "logoDataUrl": "/logo.png",
    "faviconDataUrl": "/favicon.ico",
    "carouselSlides": [
        { "title": "AI4Research", "desc": "智能研究助手，让数据分析更高效。", "image": "/bg.png", "link": "/dashboard" },
        { "title": "AI4Research", "desc": "立即开始新的 RWS 研究项目。", "image": "/bg2.png", "link": "/" },
        { "title": "RWS 专业报告精修", "desc": "一键组合报告章节，快速导出 Markdown/PDF。", "image": "/bg_report.png", "link": "/reports" },
    ],
    "model_costs": {
        "default": { "input_price": 5, "output_price": 20 }
    },
    "active_model": "gemini-3-pro-preview",
    "api_keys": {},
    "api_base_url": "",
    "language": "zh",
    "theme": "dark",
    "userProfile": {
        "name": "研究员",
        "role": "高级分析师",
        "email": "researcher@example.com",
        "bio": "致力于通过数据驱动的研究发现洞见。",
        "avatar": ""
    }
}

class SettingsManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.settings_file = self._resolve_settings_file()
        self._last_mtime = 0
        self._load_settings()
        self._initialized = True

    def _resolve_settings_file(self) -> Path:
        env_path = os.getenv("RWS_SETTINGS_FILE")
        if env_path:
            return Path(env_path)

        container_path = Path("/app/config/system_settings.json")
        if os.name != "nt" and Path("/app").exists():
            return container_path

        backend_dir = Path(__file__).resolve().parents[2]
        return backend_dir / "config" / "system_settings.json"

    def _load_settings(self):
        if self.settings_file.exists():
            try:
                # Update mtime
                current_mtime = self.settings_file.stat().st_mtime
                self._last_mtime = current_mtime
                
                content = self.settings_file.read_text(encoding="utf-8")
                self.settings = json.loads(content)
                # Merge with defaults to ensure all keys exist
                self._merge_defaults(self.settings, DEFAULT_SETTINGS)
            except Exception as e:
                print(f"Error loading settings: {e}")
                self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        else:
            self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
            self._save_settings()

    def _check_reload(self):
        """Check if file has been modified and reload if necessary."""
        if self.settings_file.exists():
            try:
                # Defensive check for hot-reload state
                if not hasattr(self, '_last_mtime'):
                    self._last_mtime = 0
                    
                current_mtime = self.settings_file.stat().st_mtime
                if current_mtime > self._last_mtime:
                    print(f"[SettingsManager] Detected file change, reloading settings...")
                    self._load_settings()
            except Exception:
                pass

    def _merge_defaults(self, target: Dict, defaults: Dict):
        for k, v in defaults.items():
            if k not in target:
                target[k] = v
            elif isinstance(v, dict) and isinstance(target[k], dict):
                self._merge_defaults(target[k], v)

    def _save_settings(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False), encoding="utf-8")
            self._last_mtime = self.settings_file.stat().st_mtime
        except Exception as e:
            print(f"Error saving settings: {e}")
            raise

    def get_settings(self) -> Dict[str, Any]:
        # Check for updates before returning
        self._check_reload()
        # Defensive check: if settings were never loaded
        if not hasattr(self, 'settings'):
            self._load_settings()
        return self.settings

    def update_settings(self, new_settings: Dict[str, Any]):
        if not hasattr(self, 'settings'):
            self._load_settings()
        # Update logic: can be partial update
        # For top-level keys, direct replacement
        for k, v in new_settings.items():
            self.settings[k] = v
        self._save_settings()

    def reset_settings(self) -> Dict[str, Any]:
        """Reset settings to system defaults."""
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS)) # Deep copy
        self._save_settings()
        return self.settings

    def get_model_cost_config(self, model_name: str) -> Dict[str, float]:
        self._check_reload()
        costs = self.settings.get("model_costs", {})
        
        # Exact match
        if model_name in costs:
            return costs[model_name]
        
        # Prefix match (e.g. gpt-4-0613 -> gpt-4)
        # Sort keys by length desc to match longest prefix first
        sorted_keys = sorted(costs.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in model_name and key != "default":
                return costs[key]
                
        return costs.get("default", DEFAULT_SETTINGS["model_costs"]["default"])

