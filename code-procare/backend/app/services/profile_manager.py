import json
import os
from pathlib import Path
from typing import Dict, Optional, List
import datetime

class ProfileManager:
    """
    Manages persistent storage of Excel profiles (excel_info) keyed by file MD5.
    Allows sharing and reuse of data structure and profile information across jobs.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            # Default to output/knowledge_base/profiles
            base_dir = Path(__file__).resolve().parents[3] / "output" / "knowledge_base" / "profiles"
            self.storage_dir = base_dir
        else:
            self.storage_dir = storage_dir
            
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def get_profile_path(self, md5: str) -> Path:
        return self.storage_dir / f"{md5}.json"

    def list_profiles(self) -> List[Dict]:
        """
        List all cached profiles summary.
        """
        res = []
        for p in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                st = p.stat()
                res.append({
                    "md5": p.stem,
                    "path": data.get("path"),
                    "description": data.get("description"),
                    "sheet_count": len(data.get("sheets", [])),
                    "profile_count": len(data.get("profile", {})),
                    "updated_at": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "size": st.st_size
                })
            except Exception:
                continue
        # Sort by updated_at desc
        res.sort(key=lambda x: x["updated_at"], reverse=True)
        return res


    def get_profile(self, md5: str) -> Optional[Dict]:
        """
        Retrieve cached profile for a given MD5.
        """
        p = self.get_profile_path(md5)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[ProfileManager] Failed to load profile for {md5}: {e}")
                return None
        return None

    def save_profile(self, md5: str, excel_info: Dict):
        """
        Save or update profile for a given MD5.
        Merges with existing profile to ensure we don't lose information from other sheets
        if the new excel_info is partial.
        """
        p = self.get_profile_path(md5)
        existing = self.get_profile(md5)
        
        if existing:
            # Merge logic:
            # 1. Update basic info if missing (path, description)
            # 2. Merge 'profile' dictionary (sheet-level profiles)
            merged = dict(existing)
            
            # Update top-level fields if they are more recent/complete?
            # Actually, path might change (upload location), but MD5 is same.
            # We should probably keep the latest path or just rely on MD5.
            # But let's respect the new excel_info's updates.
            
            # Merge profiles
            existing_profiles = existing.get("profile", {}) or {}
            new_profiles = excel_info.get("profile", {}) or {}
            
            for sheet, sheet_profile in new_profiles.items():
                # If new profile has data, overwrite/update existing
                if sheet_profile:
                     existing_profiles[sheet] = sheet_profile
            
            merged["profile"] = existing_profiles
            
            # Update other fields
            for k, v in excel_info.items():
                if k != "profile":
                    merged[k] = v
            
            to_save = merged
        else:
            to_save = excel_info

        try:
            p.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[ProfileManager] Failed to save profile for {md5}: {e}")

    def delete_profile(self, md5: str) -> bool:
        """
        Delete cached profile for a given MD5.
        """
        p = self.get_profile_path(md5)
        if p.exists():
            try:
                os.remove(p)
                return True
            except Exception as e:
                print(f"[ProfileManager] Failed to delete profile for {md5}: {e}")
                return False
        return False
