from functools import lru_cache
from pathlib import Path


PROFILE_DIR = Path(__file__).resolve().parents[1] / "prompt_profiles"


@lru_cache(maxsize=None)
def load_prompt_profile(profile_name: str) -> str:
    profile_path = PROFILE_DIR / f"{profile_name}.md"
    if not profile_path.exists():
        return ""
    return profile_path.read_text(encoding="utf-8").strip()


def compose_system_prompt(task_instructions: str, *, profile_name: str | None = None) -> str:
    profile_text = load_prompt_profile(profile_name) if profile_name else ""
    if not profile_text:
        return task_instructions.strip()
    return f"{profile_text}\n\nTask instructions:\n{task_instructions.strip()}".strip()
