import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger(__name__)


class ViolationLogger:
    """
    Manages structured persistence of proctoring violations to disk (JSON format).
    Supports per-student isolated logs to guarantee multi-student isolation.
    Ensures safe reading, writing, and recovery from malformed files.
    """

    def __init__(self, log_path: Optional[Path] = None, test_id: Optional[str] = None, student_id: Optional[str] = None):
        if log_path is not None:
            self.log_path = Path(log_path)
        elif student_id:
            clean_test = (test_id or "test").replace("/", "_").replace("\\", "_")
            clean_stu = str(student_id).replace("/", "_").replace("\\", "_")
            logs_dir = config.VIOLATIONS_DIR / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = logs_dir / f"{clean_test}_{clean_stu}_violations.json"
        else:
            self.log_path = Path(config.VIOLATION_LOG_FILE)

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_log_file_exists()

    def _ensure_log_file_exists(self):
        """Initializes JSON log file if missing or recovers if malformed."""
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            self._write_records([])
            return

        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("JSON log root is not a list")
        except Exception as e:
            logger.warning(f"Malformed violation log detected at '{self.log_path}': {e}. Backing up and resetting.")
            backup_path = self.log_path.with_suffix(f".corrupted_{int(time.time())}.json")
            try:
                self.log_path.rename(backup_path)
            except Exception:
                pass
            self._write_records([])

    def _write_records(self, records: List[Dict[str, Any]]):
        """Atomically writes violation records array to JSON file with Windows lock fallback."""
        tmp_path = self.log_path.with_suffix(".tmp")
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
            
            if self.log_path.exists():
                try:
                    self.log_path.unlink()
                except Exception:
                    pass
            tmp_path.replace(self.log_path)
        except Exception:
            try:
                with open(self.log_path, 'w', encoding='utf-8') as f:
                    json.dump(records, f, indent=2, ensure_ascii=False)
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception as e:
                logger.error(f"Failed writing violation log: {e}")

    def log_violation(self, record: Dict[str, Any]):
        """Appends a new violation record to persistent JSON log."""
        records = self.get_records()
        records.append(record)
        self._write_records(records)

    def update_violation(self, episode_id: str, updated_fields: Dict[str, Any]):
        """Updates an existing violation record with duration and close times."""
        records = self.get_records()
        found = False
        for rec in records:
            if rec.get("id") == episode_id:
                rec.update(updated_fields)
                found = True
                break
        if found:
            self._write_records(records)

    def get_records(self) -> List[Dict[str, Any]]:
        """Returns all persistent records from disk."""
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def get_all_violations(self) -> List[Dict[str, Any]]:
        """Alias for backwards compatibility with ViolationManager."""
        return self.get_records()
