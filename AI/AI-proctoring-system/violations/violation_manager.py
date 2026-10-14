import cv2
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable
from collections import deque
import numpy as np

import config
from detectors.base_detector import DetectorResult
from violations.logger import ViolationLogger

logger = logging.getLogger(__name__)


class ViolationEpisode:
    """Represents an active or historical continuous violation episode."""

    def __init__(self, episode_id: str, vtype: str, timestamp_str: str, start_time: float,
                 message: str, similarity: float, screenshot_path: str,
                 extra_metadata: Optional[Dict[str, Any]] = None):
        self.id = episode_id
        self.vtype = vtype
        self.timestamp_str = timestamp_str
        self.start_time = start_time
        self.end_time: Optional[float] = None
        self.duration_seconds: Optional[float] = None
        self.message = message
        self.similarity = similarity
        self.screenshot_path = screenshot_path
        self.extra_metadata = extra_metadata or {}

    def close(self, end_time: float):
        self.end_time = end_time
        self.duration_seconds = round(end_time - self.start_time, 1)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "type": self.vtype,
            "timestamp": self.timestamp_str,
            "message": self.message,
            "similarity": self.similarity,
            "screenshot": self.screenshot_path,
            "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%dT%H:%M:%S") if self.end_time else None,
            "duration_seconds": self.duration_seconds
        }
        for k, v in self.extra_metadata.items():
            if k not in data:
                data[k] = v
        return data


class ViolationManager:
    """
    Stateful Violation Manager supporting temporal confirmation, intermittent detection grace periods,
    and episode tracking for Stage 1, 2, 3, 4, & 5 proctoring detectors.
    """

    def __init__(self, logger_instance: Optional[ViolationLogger] = None,
                 on_violation_start: Optional[Callable] = None,
                 on_violation_close: Optional[Callable] = None):
        self.logger = logger_instance or ViolationLogger()
        self.on_violation_start = on_violation_start
        self.on_violation_close = on_violation_close

        # Configured time thresholds for violation activation
        self.thresholds = {
            config.STATE_FACE_MISSING: config.FACE_MISSING_THRESHOLD_SEC,
            config.STATE_IDENTITY_MISMATCH: config.IDENTITY_MISMATCH_THRESHOLD_SEC,
            config.STATE_MULTIPLE_PEOPLE: config.MULTIPLE_PERSON_CONFIRM_SECONDS,
            config.STATE_PHONE_DETECTED: config.PHONE_CONFIRM_SECONDS,
            config.STATE_BOOK_DETECTED: config.BOOK_CONFIRM_SECONDS,
            config.STATE_LOOKING_AWAY: config.HEAD_POSE_CONFIRM_SECONDS,
            config.STATE_MULTIPLE_SPEAKERS: config.MULTIPLE_SPEAKER_CONFIRM_SECONDS,
        }

        # Pending state trackers: {vtype: start_timestamp}
        self.pending_states: Dict[str, float] = {}

        # Last seen timestamps for intermittent grace periods: {vtype: last_seen_timestamp}
        self.last_seen_times: Dict[str, float] = {}

        # Active triggered episodes: {vtype: ViolationEpisode}
        self.active_episodes: Dict[str, ViolationEpisode] = {}

        # Rolling Window History Deques: {vtype: deque([1, 0, 1, 1...], maxlen=N)}
        self.rolling_windows: Dict[str, deque] = {
            config.STATE_PHONE_DETECTED: deque(maxlen=config.TEMPORAL_WINDOW_SIZE),
            config.STATE_BOOK_DETECTED: deque(maxlen=config.TEMPORAL_WINDOW_SIZE),
            config.STATE_MULTIPLE_PEOPLE: deque(maxlen=config.TEMPORAL_WINDOW_SIZE),
            config.STATE_LOOKING_AWAY: deque(maxlen=config.TEMPORAL_WINDOW_SIZE),
            config.STATE_MULTIPLE_SPEAKERS: deque(maxlen=config.TEMPORAL_WINDOW_SIZE),
        }

        # Pending raw states for UI feedback
        self.pending_ui_states: Dict[str, Dict[str, Any]] = {}

        # History log for UI display
        self.violation_history: List[Dict[str, Any]] = []
        self._load_existing_history()

    def _load_existing_history(self):
        """Loads historical records from disk on startup."""
        records = self.logger.get_all_violations()
        self.violation_history = records[-20:]

    def update(self, results: Union[DetectorResult, List[DetectorResult], Dict[str, DetectorResult]], frame: np.ndarray):
        """
        Evaluates detection results against temporal confirmation & grace period thresholds.
        """
        if isinstance(results, dict):
            results_list = list(results.values())
        elif isinstance(results, DetectorResult):
            results_list = [results]
        else:
            results_list = results

        current_time = time.time()
        
        # Collect active violation states present in current frame
        active_states_in_frame: Dict[str, DetectorResult] = {}
        for res in results_list:
            if res and res.state in self.thresholds:
                active_states_in_frame[res.state] = res

        monitored_types = list(self.thresholds.keys())

        # Check if face detector specifically reported STATE_VERIFIED
        face_verified_in_frame = any(res and res.detector_name == "FaceVerifier" and res.state == config.STATE_VERIFIED for res in results_list)

        for vtype in monitored_types:
            is_present = vtype in active_states_in_frame
            res = active_states_in_frame.get(vtype)

            # Update rolling window history
            if vtype in self.rolling_windows:
                self.rolling_windows[vtype].append(1 if is_present else 0)

            rolling_ratio_qualified = False
            ratio_str = ""
            if vtype in self.rolling_windows:
                win = self.rolling_windows[vtype]
                pos_count = sum(win)
                win_len = len(win)
                ratio_str = f"{pos_count}/{win_len}"
                min_req = config.PHONE_WINDOW_MIN_DETECTIONS if vtype == config.STATE_PHONE_DETECTED else 4
                if pos_count >= min_req:
                    rolling_ratio_qualified = True

            state_active = is_present or rolling_ratio_qualified

            if state_active:
                self.last_seen_times[vtype] = current_time

                if vtype not in self.pending_states:
                    self.pending_states[vtype] = current_time

                elapsed = current_time - self.pending_states[vtype]
                threshold = self.thresholds.get(vtype, 2.5)

                is_episode_active = vtype in self.active_episodes
                self.pending_ui_states[vtype] = {
                    "pending": not is_episode_active,
                    "active": is_episode_active,
                    "conf": res.similarity_score if res else 0.0,
                    "elapsed": round(elapsed, 1),
                    "ratio_str": ratio_str,
                    "direction": res.raw_data.get("direction", "CENTER") if (res and res.raw_data) else "CENTER"
                }

                if is_episode_active and res and res.raw_data:
                    cur_dir = res.raw_data.get("direction")
                    if cur_dir and cur_dir != "CENTER":
                        self.active_episodes[vtype].extra_metadata["direction"] = cur_dir
                    if res.message:
                        self.active_episodes[vtype].message = res.message

                if elapsed >= threshold and vtype not in self.active_episodes:
                    sample_res = res or DetectorResult(detector_name="SpeakerDetector", state=vtype, similarity_score=0.0, message=f"Confirmed {vtype}")
                    self._start_violation_episode(vtype, sample_res, frame, current_time)

            else:
                time_since_last = current_time - self.last_seen_times.get(vtype, 0.0)
                if vtype == config.STATE_MULTIPLE_SPEAKERS:
                    grace_period = config.MULTIPLE_SPEAKER_CLEAR_GRACE_SECONDS
                elif vtype in [config.STATE_PHONE_DETECTED, config.STATE_BOOK_DETECTED, config.STATE_MULTIPLE_PEOPLE]:
                    grace_period = getattr(config, 'OBJECT_CLEAR_GRACE_SECONDS', 1.2)
                else:
                    grace_period = config.HEAD_POSE_CLEAR_GRACE_SECONDS

                if face_verified_in_frame and vtype in [config.STATE_FACE_MISSING, config.STATE_IDENTITY_MISMATCH]:
                    grace_period = 0.0

                if time_since_last < grace_period and (vtype in self.pending_states or vtype in self.active_episodes):
                    if vtype in self.active_episodes:
                        self.pending_ui_states[vtype] = {"pending": False, "active": True, "conf": 0.0, "elapsed": 0.0, "ratio_str": ratio_str}
                    else:
                        elapsed = current_time - self.pending_states.get(vtype, current_time)
                        self.pending_ui_states[vtype] = {"pending": True, "active": False, "conf": 0.0, "elapsed": round(elapsed, 1), "ratio_str": ratio_str}
                else:
                    if vtype in self.pending_states:
                        del self.pending_states[vtype]

                    if vtype in self.active_episodes:
                        self._close_violation_episode(vtype, current_time)

    def _start_violation_episode(self, vtype: str, result: DetectorResult, frame: np.ndarray, start_time: float):
        """Triggers a new violation episode, captures ONE screenshot, and logs to JSON."""
        now_dt = datetime.fromtimestamp(start_time)
        timestamp_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
        file_timestamp = now_dt.strftime("%Y-%m-%d_%H-%M-%S")
        episode_id = f"viol_{int(start_time)}_{vtype}"

        extra_metadata = {}
        if result and result.raw_data:
            for field in [
                "person_count", "max_confidence", "confidence", "count",
                "direction", "yaw", "pitch", "relative_yaw",
                "yaw_diff", "pitch_diff", "yaw_threshold", "pitch_threshold", "dist_cm",
                "estimated_speakers", "credible_speaker_count", "speaker_durations", "confirmed_windows", "segment_count"
            ]:
                if field in result.raw_data:
                    extra_metadata[field] = result.raw_data[field]

        # 1. Determine whether to save screenshot evidence
        # Audio violations (MULTIPLE_SPEAKERS) and Looking Away do not capture/attach screenshots.
        # Looking Away is logged strictly as a count without screenshot evidence.
        is_audio_violation = (vtype == config.STATE_MULTIPLE_SPEAKERS)
        is_looking_away = (vtype == config.STATE_LOOKING_AWAY)
        allow_screenshot = False if (is_audio_violation or is_looking_away) else True

        screenshot_full_path = None
        relative_screenshot_path = None

        if allow_screenshot:
            screenshot_filename = f"{file_timestamp}_{vtype}.jpg"
            screenshot_full_path = config.SCREENSHOTS_DIR / screenshot_filename
            relative_screenshot_path = f"violations/screenshots/{screenshot_filename}"

            if frame is not None and frame.size > 0:
                evidence_frame = frame.copy()
                eh, ew = evidence_frame.shape[:2]

                # Draw high-contrast top evidence banner
                cv2.rectangle(evidence_frame, (0, 0), (ew, 45), (30, 30, 46), -1)
                cv2.rectangle(evidence_frame, (0, 0), (ew, 45), (65, 65, 230), 2)
                
                banner_txt = f"PROCTORING VIOLATION: {vtype} | Time: {timestamp_str}"
                cv2.putText(evidence_frame, banner_txt, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

                if result.message:
                    cv2.putText(evidence_frame, result.message, (15, eh - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

                cv2.imwrite(str(screenshot_full_path), evidence_frame)
                logger.info(f"Violation screenshot evidence saved: {screenshot_full_path}")
            else:
                logger.warning("Attempted to save screenshot but frame was empty.")
        else:
            if is_looking_away:
                logger.info(f"Screenshot capture skipped for Looking Away (count-only requirement): [{vtype}]")
            else:
                logger.info(f"Screenshot capture skipped for audio violation: [{vtype}]")

        # 2. Construct episode
        episode = ViolationEpisode(
            episode_id=episode_id,
            vtype=vtype,
            timestamp_str=timestamp_str,
            start_time=start_time,
            message=result.message or f"Confirmed {vtype} violation",
            similarity=round(result.similarity_score, 2),
            screenshot_path=relative_screenshot_path,
            extra_metadata=extra_metadata
        )

        self.active_episodes[vtype] = episode

        # 3. Save initial record to logger and UI history
        rec_dict = episode.to_dict()
        self.logger.log_violation(rec_dict)

        ui_time = now_dt.strftime("%H:%M:%S")
        labels = {
            config.STATE_FACE_MISSING: "Face missing",
            config.STATE_IDENTITY_MISMATCH: "Face Mismatch",
            config.STATE_MULTIPLE_PEOPLE: "Multiple people",
            config.STATE_PHONE_DETECTED: "Phone detected",
            config.STATE_BOOK_DETECTED: "Book detected",
            config.STATE_LOOKING_AWAY: "Looking away",
            config.STATE_MULTIPLE_SPEAKERS: f"Multiple speakers ({extra_metadata.get('estimated_speakers', 2)})"
        }
        vtype_label = labels.get(vtype, vtype)

        display_record = {
            "ui_str": f"{ui_time} — {vtype_label}",
            "type": vtype,
            "timestamp": timestamp_str,
            "message": episode.message,
            "similarity": episode.similarity
        }
        self.violation_history.append(display_record)
        logger.warning(f"CONFIRMED VIOLATION TRIGGERED: [{vtype}] {episode.message}")

        if self.on_violation_start:
            try:
                self.on_violation_start(episode, str(screenshot_full_path) if screenshot_full_path else None)
            except Exception as cb_err:
                logger.error(f"Error in on_violation_start callback: {cb_err}")

    def _close_violation_episode(self, vtype: str, end_time: float):
        """Closes an active violation episode and records total duration."""
        if vtype not in self.active_episodes:
            return

        episode = self.active_episodes[vtype]
        episode.close(end_time)

        self.logger.update_violation(
            episode.id,
            {
                "end_time": episode.to_dict()["end_time"],
                "duration_seconds": episode.duration_seconds
            }
        )

        logger.info(f"Violation episode resolved: [{vtype}] Duration: {episode.duration_seconds}s")

        if self.on_violation_close:
            try:
                self.on_violation_close(episode)
            except Exception as cb_err:
                logger.error(f"Error in on_violation_close callback: {cb_err}")

        del self.active_episodes[vtype]

    def get_active_violations(self) -> List[Dict[str, Any]]:
        """Returns list of currently active violation episodes."""
        active_list = []
        now = time.time()
        for episode in self.active_episodes.values():
            active_list.append({
                "type": episode.vtype,
                "message": episode.message,
                "duration": round(now - episode.start_time, 1),
                "similarity": episode.similarity,
                "direction": episode.extra_metadata.get("direction", "")
            })
        return active_list

    def get_violation_history(self) -> List[Dict[str, Any]]:
        """Returns historical violation records for UI log display."""
        return self.violation_history

    def get_pending_status(self, vtype: str) -> Dict[str, Any]:
        """Returns raw detection vs confirmed violation state for UI debugging."""
        return self.pending_ui_states.get(vtype, {"pending": False, "active": False, "conf": 0.0, "elapsed": 0.0, "ratio_str": ""})

    def get_post_test_summary(self) -> Dict[str, Any]:
        """
        Generates structured post-test violation logs:
        - If Face Mismatch is detected, logs violation with corresponding screenshot.
        - For other screenshot-based violations, logs violation with captured screenshot.
        - Looking Away is the only exception: no screenshot attached, only count format 'Looking Away: X times'.
        """
        records = self.logger.get_all_violations()
        looking_away_count = sum(1 for r in records if r.get("type") == config.STATE_LOOKING_AWAY)
        other_records = [r for r in records if r.get("type") != config.STATE_LOOKING_AWAY]

        formatted_logs = []
        if looking_away_count > 0:
            formatted_logs.append({
                "type": "LOOKING_AWAY",
                "display": f"Looking Away: {looking_away_count} times",
                "count": looking_away_count,
                "screenshot": None
            })

        for r in other_records:
            vtype = r.get("type", "")
            is_face_mismatch = (vtype == config.STATE_IDENTITY_MISMATCH)
            label = "Face Mismatch" if is_face_mismatch else vtype
            formatted_logs.append({
                "type": vtype,
                "label": label,
                "display": f"{label}: {r.get('message', '')} ({r.get('timestamp', '')})",
                "screenshot": r.get("screenshot"),
                "similarity": r.get("similarity"),
                "timestamp": r.get("timestamp"),
                "message": r.get("message")
            })

        return {
            "total_violations": len(records),
            "looking_away_count": looking_away_count,
            "looking_away_formatted": f"Looking Away: {looking_away_count} times" if looking_away_count > 0 else None,
            "logs": formatted_logs
        }

    def print_post_test_logs(self):
        """Prints post-test violation logs to console / logger."""
        summary = self.get_post_test_summary()
        logger.info("=" * 65)
        logger.info("                 POST-TEST VIOLATION LOGS")
        logger.info("=" * 65)
        if summary["total_violations"] == 0:
            logger.info("No proctoring violations recorded during examination.")
        else:
            if summary["looking_away_count"] > 0:
                logger.info(f"* {summary['looking_away_formatted']}")
            for log_item in summary["logs"]:
                if log_item["type"] == "LOOKING_AWAY":
                    continue
                sc = log_item.get("screenshot")
                sc_info = f" [Attached Screenshot: {sc}]" if sc else " [No screenshot]"
                logger.info(f"* {log_item['display']}{sc_info}")
        logger.info("=" * 65)
