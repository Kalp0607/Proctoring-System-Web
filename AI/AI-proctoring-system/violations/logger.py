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
    Ensures safe reading, writing, and recovery from malformed files.
    """

    def __init__(self, log_path: Path = config.VIOLATION_LOG_FILE):
        self.log_path = Path(log_path)
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
            except Exception as e2:
                logger.error(f"Failed to write violation records to disk: {e2}")

    def log_violation(self, violation_data: Dict[str, Any]):
        """
        Appends a new violation record to the log file.
        """
        records = self.get_all_violations()
        records.append(violation_data)
        self._write_records(records)
        logger.info(f"Violation logged: {violation_data.get('type')} at {violation_data.get('timestamp')}")

    def update_violation(self, violation_id: str, updates: Dict[str, Any]):
        """
        Updates an existing violation record (e.g. adding end_time and duration when episode closes).
        """
        records = self.get_all_violations()
        updated = False
        for rec in records:
            if rec.get("id") == violation_id:
                rec.update(updates)
                updated = True
                break

        if updated:
            self._write_records(records)

    def get_all_violations(self) -> List[Dict[str, Any]]:
        """Reads and returns all logged violations."""
        if not self.log_path.exists():
            return []
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading violation log: {e}")
            return []
