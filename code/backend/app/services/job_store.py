import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class JobNotFoundError(FileNotFoundError):
    """Raised when a task id does not exist on disk."""


class FileJobStore:
    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create_job(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = self._utc_now()
        job = {
            "task_id": task_id,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "summary": None,
            "error": None,
            "output_file": None,
            **payload,
        }
        self._write_job(task_id, job)
        return job

    def get_job(self, task_id: str) -> dict[str, Any] | None:
        job_file = self._job_file(task_id)
        if not job_file.exists():
            return None
        return self._read_job(job_file)

    def require_job(self, task_id: str) -> dict[str, Any]:
        job = self.get_job(task_id)
        if job is None:
            raise JobNotFoundError(task_id)
        return job

    def update_job(self, task_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            job = self.require_job(task_id)
            job.update(changes)
            job["updated_at"] = self._utc_now()
            self._write_job(task_id, job)
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = [self._read_job(path) for path in self.jobs_dir.glob("*.json")]
        return sorted(jobs, key=lambda item: item["created_at"], reverse=True)

    def latest_job(self) -> dict[str, Any] | None:
        jobs = self.list_jobs()
        if not jobs:
            return None
        return jobs[0]

    def _job_file(self, task_id: str) -> Path:
        return self.jobs_dir / f"{task_id}.json"

    def _read_job(self, job_file: Path) -> dict[str, Any]:
        return json.loads(job_file.read_text(encoding="utf-8"))

    def _write_job(self, task_id: str, payload: dict[str, Any]) -> None:
        job_file = self._job_file(task_id)
        job_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
