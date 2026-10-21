"""Checkpoint Store — persists execution state for crash recovery and pause/resume."""

from __future__ import annotations

from pathlib import Path

from praxis_agent_runtime.types import RunRecord


class CheckpointStore:
    """File-backed checkpoint store for execution runs."""

    def __init__(self, storage_dir: str | Path) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, run_id: str) -> Path:
        return self._dir / f"{run_id}.json"

    def save(self, run: RunRecord) -> None:
        """Persist a run record to disk."""
        data = run.model_dump_json(indent=2)
        self._path_for(run.run_id).write_text(data, encoding="utf-8")

    def load(self, run_id: str) -> RunRecord | None:
        """Load a run record from disk. Returns None if not found."""
        path = self._path_for(run_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return RunRecord.model_validate_json(raw)

    def list_runs(self) -> list[str]:
        """List all stored run IDs."""
        return [p.stem for p in self._dir.glob("*.json")]

    def delete(self, run_id: str) -> None:
        """Remove a checkpoint."""
        path = self._path_for(run_id)
        if path.exists():
            path.unlink()
