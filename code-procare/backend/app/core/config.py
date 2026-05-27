from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_name: str
    base_dir: Path
    app_data_dir: Path
    output_archive_dir: Path
    uploads_dir: Path
    outputs_dir: Path
    intermediates_dir: Path
    jobs_dir: Path
    default_template_path: Path | None

    def ensure_directories(self) -> None:
        for path in (
            self.app_data_dir,
            self.output_archive_dir,
            self.uploads_dir,
            self.outputs_dir,
            self.intermediates_dir,
            self.jobs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[2]
    settings = Settings(
        project_name="RWS Report Generator API",
        base_dir=base_dir,
        app_data_dir=base_dir / "app_data",
        output_archive_dir=base_dir / "output",
        uploads_dir=base_dir / "app_data" / "uploads",
        outputs_dir=base_dir / "app_data" / "outputs",
        intermediates_dir=base_dir / "app_data" / "intermediates",
        jobs_dir=base_dir / "app_data" / "jobs",
        default_template_path=base_dir / "app" / "builtin_templates" / "arxiv_default",
    )
    settings.ensure_directories()
    return settings
