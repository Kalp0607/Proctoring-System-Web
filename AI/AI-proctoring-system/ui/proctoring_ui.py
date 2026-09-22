import cv2
import numpy as np
import time
from typing import Dict, List, Optional, Any, Union

import config
from detectors.base_detector import DetectorResult
from violations.violation_manager import ViolationManager


class ProctoringUI:
    """
    Renders the split-screen Proctoring Dashboard:
    Left: Live webcam feed with 1:1 pixel aligned diagnostic bounding boxes, 3D nose rays, and evidence labels.
    Right: Real-time side panel displaying proctoring status cards, head pose telemetry, audio telemetry, active violations, and log.
    """

    def __init__(self, main_width: int = config.UI_CANVAS_WIDTH, height: int = config.UI_CANVAS_HEIGHT):
        self.main_width = main_width
        self.height = height

        # State for popup notifications
        self.active_popups = []
        self.last_history_len = -1

        # Color Palette (BGR)
        self.COLOR_BG = (24, 24, 37)           # Dark Slate (#181825)
        self.COLOR_PANEL = (30, 30, 46)        # Card Background
        self.COLOR_PANEL_BORDER = (50, 50, 75)
        self.COLOR_TEXT_MAIN = (240, 240, 245)
        self.COLOR_TEXT_MUTED = (160, 160, 180)

        # Status Colors
        self.COLOR_GREEN = (85, 195, 60)       # Verified / Normal (BGR)
        self.COLOR_RED = (65, 65, 230)         # Violation Red
        self.COLOR_AMBER = (30, 165, 240)      # Warning Amber / Pending
        
        # Object Bounding Box Colors
        self.COLOR_CYAN = (230, 180, 50)       # Person Box (Cyan/Blue)
        self.COLOR_MAGENTA = (200, 50, 220)    # Cell Phone Box (Magenta)
        self.COLOR_YELLOW = (40, 200, 240)     # Book Box (Yellow/Orange)
        self.COLOR_POSE_LINE = (0, 255, 255)    # 3D Head Orientation Line (Bright Yellow)

        self.font = cv2.FONT_HERSHEY_SIMPLEX

    def render(self, frame: np.ndarray, face_result: DetectorResult,
               obj_results: Optional[Dict[str, DetectorResult]],
               head_result: Optional[DetectorResult],
               audio_result: Optional[DetectorResult],
               violation_mgr: ViolationManager, fps: float = 0.0) -> np.ndarray:
        """
        Renders complete UI canvas with webcam feed and popup notifications.
        """
        if frame is not None and frame.size > 0:
            annotated_frame = frame.copy()
            
            # Diagnostics are hidden by default based on previous request, 
            # but can be toggled via the 'D' key for debugging.
            if config.SHOW_DIAGNOSTICS:
                annotated_frame = self._draw_diagnostics(annotated_frame, face_result, obj_results, head_result)

            if annotated_frame.shape[:2] != (self.height, self.main_width):
                resized_display = cv2.resize(annotated_frame, (self.main_width, self.height))
            else:
                resized_display = annotated_frame
            
            # A. Display Persistent Active Violation Banners across top of video feed
            active_violations = violation_mgr.get_active_violations()
            banner_y = 45
            for viol in active_violations:
                vtype = viol.get("type", "")
                direction = viol.get("direction", "")

                if vtype == config.STATE_LOOKING_AWAY:
                    dir_str = f" ({direction})" if direction and direction != "CENTER" else ""
                    viol_msg = f"VIOLATION: LOOKING AWAY{dir_str}"
                elif vtype == config.STATE_PHONE_DETECTED:
                    viol_msg = "VIOLATION: MOBILE PHONE DETECTED"
                elif vtype == config.STATE_BOOK_DETECTED:
                    viol_msg = "VIOLATION: BOOK DETECTED"
                elif vtype == config.STATE_MULTIPLE_PEOPLE:
                    viol_msg = "VIOLATION: MULTIPLE PEOPLE DETECTED"
                elif vtype == config.STATE_FACE_MISSING:
                    viol_msg = "VIOLATION: FACE NOT DETECTED"
                elif vtype == config.STATE_IDENTITY_MISMATCH:
                    viol_msg = "VIOLATION: IDENTITY MISMATCH DETECTED"
                elif vtype == config.STATE_MULTIPLE_SPEAKERS:
                    viol_msg = "VIOLATION: MULTIPLE VOICES DETECTED"
                else:
                    viol_msg = f"VIOLATION: {vtype}"

                txt_sz, _ = cv2.getTextSize(viol_msg, self.font, 0.82, 2)
                cx = (self.main_width - txt_sz[0]) // 2

                # High-contrast bold Red box with White border
                pad_x = 24
                pad_y = 12
                cv2.rectangle(
                    resized_display,
                    (cx - pad_x, banner_y - txt_sz[1] - pad_y),
                    (cx + txt_sz[0] + pad_x, banner_y + pad_y),
                    (35, 25, 210),
                    -1
                )
                cv2.rectangle(
                    resized_display,
                    (cx - pad_x, banner_y - txt_sz[1] - pad_y),
                    (cx + txt_sz[0] + pad_x, banner_y + pad_y),
                    (255, 255, 255),
                    2
                )
                cv2.putText(
                    resized_display,
                    viol_msg,
                    (cx, banner_y),
                    self.font,
                    0.82,
                    (255, 255, 255),
                    2
                )
                banner_y += (txt_sz[1] + pad_y * 2 + 16)

            # B. Calibration Status Indicator
            if not active_violations and head_result and head_result.raw_data and not head_result.raw_data.get("calibrated", True):
                calib_msg = "Calibrating baseline... Please look naturally at center of screen"
                txt_sz, _ = cv2.getTextSize(calib_msg, self.font, 0.65, 2)
                cx = (self.main_width - txt_sz[0]) // 2
                cv2.rectangle(resized_display, (cx - 18, 14), (cx + txt_sz[0] + 18, 52), (50, 40, 25), -1)
                cv2.rectangle(resized_display, (cx - 18, 14), (cx + txt_sz[0] + 18, 52), (0, 210, 255), 2)
                cv2.putText(resized_display, calib_msg, (cx, 40), self.font, 0.65, (0, 230, 255), 2)

            # C. Check for new historical violations (trigger temporary popups)
            history = violation_mgr.get_violation_history()
            current_len = len(history)
            
            if self.last_history_len == -1:
                self.last_history_len = current_len
                
            if current_len > self.last_history_len:
                new_records = history[self.last_history_len:current_len]
                for rec in new_records:
                    msg = rec.get("ui_str") or rec.get("type", "Violation")
                    if " — " in msg:
                        msg = msg.split(" — ")[-1]
                    self.active_popups.append({"message": f"VIOLATION: {msg}", "timestamp": time.time()})
                self.last_history_len = current_len

            # Remove old popups (older than 2 seconds)
            now = time.time()
            self.active_popups = [p for p in self.active_popups if now - p["timestamp"] < 2.0]

            # Draw popups if not already covered by active banner
            if not active_violations:
                y_offset = 50
                for popup in self.active_popups:
                    text = popup["message"]
                    txt_sz, _ = cv2.getTextSize(text, self.font, 0.8, 2)
                    cx = (self.main_width - txt_sz[0]) // 2
                    
                    # Draw background box (Red with White border)
                    cv2.rectangle(resized_display, (cx - 15, y_offset - 30), (cx + txt_sz[0] + 15, y_offset + 10), (46, 30, 200), -1)
                    cv2.rectangle(resized_display, (cx - 15, y_offset - 30), (cx + txt_sz[0] + 15, y_offset + 10), (255, 255, 255), 2)
                    
                    # Draw text
                    cv2.putText(resized_display, text, (cx, y_offset - 5), self.font, 0.8, (255, 255, 255), 2)
                    y_offset += 60

            canvas = resized_display
        else:
            canvas = np.zeros((self.height, self.main_width, 3), dtype=np.uint8)
            cv2.putText(canvas, "CAMERA FEED UNAVAILABLE", (self.main_width // 4, self.height // 2),
                        self.font, 1.0, self.COLOR_RED, 2)

        return canvas

    def _draw_diagnostics(self, frame: np.ndarray, face_result: DetectorResult,
                          obj_results: Optional[Dict[str, DetectorResult]],
                          head_result: Optional[DetectorResult]) -> np.ndarray:
        """
        Draws person, phone, book, face identity, 3D head pose orientation vectors,
        Person ROI inspection boundary, and real-time pipeline latency telemetry.
        """
        fh, fw = frame.shape[:2]

        # A. Draw YOLO Object Bounding Boxes (Person, Phone, Book)
        if obj_results:
            # 1. Persons (Cyan)
            person_res = obj_results.get("person")
            if person_res and person_res.raw_data and "detections" in person_res.raw_data:
                for det in person_res.raw_data["detections"]:
                    rx, ry, rw, rh = det["bbox"]
                    conf = det["confidence"]
                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), self.COLOR_CYAN, 2)
                    p_label = f"Person {conf:.2f}"
                    lbl_sz, _ = cv2.getTextSize(p_label, self.font, 0.52, 1)
                    cv2.rectangle(frame, (rx, max(0, ry - 22)), (rx + lbl_sz[0] + 8, ry), self.COLOR_CYAN, -1)
                    cv2.putText(frame, p_label, (rx + 4, ry - 6), self.font, 0.52, (0, 0, 0), 1)

            # 2. Person High-Res ROI Boundary (Dashed/Translucent Green)
            phone_res = obj_results.get("cell_phone")
            if phone_res and phone_res.raw_data:
                roi_box = phone_res.raw_data.get("roi_box")
                if roi_box:
                    roix, roiy, roiw, roih = roi_box
                    cv2.rectangle(frame, (roix, roiy), (roix + roiw, roiy + roih), (85, 195, 60), 1)
                    cv2.putText(frame, "PERSON ROI (High-Res)", (roix + 5, roiy + 15), self.font, 0.42, (85, 195, 60), 1)

            # 3. Cell Phone Multi-Frame Tracks & Candidates (Magenta/Amber)
            if phone_res and phone_res.raw_data and "detections" in phone_res.raw_data:
                for det in phone_res.raw_data["detections"]:
                    rx, ry, rw, rh = det["bbox"]
                    conf = det["confidence"]
                    track_id = det.get("track_id", "")
                    source = det.get("source", "FULL")
                    hand_prox = det.get("hand_proximity", 0.0)
                    state = det.get("state", "SUSPECTED")
                    hits = det.get("positive_count", 1)

                    is_confirmed = (state == "PHONE_CONFIRMED" or phone_res.state == config.STATE_PHONE_DETECTED)
                    box_color = self.COLOR_RED if is_confirmed else self.COLOR_AMBER
                    box_thick = 3 if is_confirmed else 2

                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), box_color, box_thick)
                    
                    id_str = f" [ID:{track_id}]" if track_id else ""
                    src_str = f" ({source})"
                    prox_str = f" [Hand:{hand_prox:.2f}]" if hand_prox > 0.0 else ""
                    ph_label = f"PHONE {conf:.2f}{id_str}{src_str}{prox_str}"
                    
                    lbl_sz, _ = cv2.getTextSize(ph_label, self.font, 0.48, 1)
                    cv2.rectangle(frame, (rx, max(0, ry - 22)), (rx + lbl_sz[0] + 8, ry), box_color, -1)
                    cv2.putText(frame, ph_label, (rx + 4, ry - 6), self.font, 0.48, (255, 255, 255), 1)

                    # Sub-label showing temporal persistence
                    sub_label = f"State: {state} (Hits: {hits})"
                    cv2.putText(frame, sub_label, (rx + 4, ry + rh + 14), self.font, 0.40, box_color, 1)

            # 4. Pipeline Performance & Latency Telemetry HUD (Top-Left)
            if phone_res and phone_res.raw_data and "telemetry" in phone_res.raw_data:
                tel = phone_res.raw_data["telemetry"]
                if tel:
                    t_full = tel.get("full_frame_ms", 0)
                    t_roi = tel.get("roi_ms", 0)
                    t_sahi = tel.get("sahi_ms", 0)
                    t_track = tel.get("tracking_ms", 0)
                    t_tot = tel.get("total_ms", 0)
                    t_fps = tel.get("fps", 0)
                    sahi_on = "YES" if tel.get("sahi_triggered", False) else "NO"

                    hud_lines = [
                        f"PHONE PIPELINE TELEMETRY | FPS: {t_fps}",
                        f"Full-Frame: {t_full}ms | Person-ROI: {t_roi}ms | SAHI ({sahi_on}): {t_sahi}ms",
                        f"Tracking: {t_track}ms | Total Pipeline: {t_tot}ms"
                    ]

                    hud_y = 20
                    cv2.rectangle(frame, (10, 8), (470, 72), (24, 24, 37), -1)
                    cv2.rectangle(frame, (10, 8), (470, 72), (85, 195, 60), 1)
                    for line in hud_lines:
                        cv2.putText(frame, line, (18, hud_y + 4), self.font, 0.40, (240, 240, 245), 1)
                        hud_y += 18

            # 5. Books (Yellow)
            book_res = obj_results.get("book")
            if book_res and book_res.raw_data and "detections" in book_res.raw_data:
                for det in book_res.raw_data["detections"]:
                    rx, ry, rw, rh = det["bbox"]
                    conf = det["confidence"]
                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), self.COLOR_YELLOW, 2)
                    bk_label = f"BOOK {conf:.2f}"
                    lbl_sz, _ = cv2.getTextSize(bk_label, self.font, 0.52, 1)
                    cv2.rectangle(frame, (rx, max(0, ry - 22)), (rx + lbl_sz[0] + 8, ry), self.COLOR_YELLOW, -1)
                    cv2.putText(frame, bk_label, (rx + 4, ry - 6), self.font, 0.52, (0, 0, 0), 1)

        # B. Draw Stage 1 Face Identity Bounding Box
        if face_result and face_result.face_detected and face_result.bounding_box:
            rx, ry, rw, rh = face_result.bounding_box
            color = self.COLOR_GREEN if face_result.verified else self.COLOR_RED
            label = f"VERIFIED ({face_result.similarity_score:.2f})" if face_result.verified else f"MISMATCH ({face_result.similarity_score:.2f})"
            cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), color, 2)
            label_size, _ = cv2.getTextSize(label, self.font, 0.55, 2)
            cv2.rectangle(frame, (rx, max(0, ry - 26)), (rx + label_size[0] + 10, ry), color, -1)
            cv2.putText(frame, label, (rx + 5, ry - 7), self.font, 0.55, (255, 255, 255), 2)

        # C. Draw Stage 4 3D Nose Orientation Vector (Anchored 1:1 at Nose Tip)
        direction = "CENTER"
        if head_result and head_result.raw_data:
            rd = head_result.raw_data
            p1 = rd.get("nose_start")
            p2 = rd.get("nose_endpoint")
            direction = rd.get("direction", "CENTER")

            if p1 and p2:
                sx1, sy1 = int(p1[0]), int(p1[1])
                sx2, sy2 = int(p2[0]), int(p2[1])
                ray_color = self.COLOR_RED if direction != "CENTER" else self.COLOR_GREEN
                cv2.line(frame, (sx1, sy1), (sx2, sy2), ray_color, 3)
                cv2.circle(frame, (sx1, sy1), 5, (0, 255, 255), -1)

            # Render non-overlapping bottom telemetry text (y: height - 55)
            yaw_diff = rd.get("yaw_diff", 0.0)
            pitch_diff = rd.get("pitch_diff", 0.0)
            yaw_thr = rd.get("yaw_threshold", config.HEAD_YAW_THRESHOLD)
            pitch_thr = rd.get("pitch_threshold", config.HEAD_PITCH_THRESHOLD)
            dist_cm = rd.get("dist_cm", 0.0)
            calibrated = rd.get("calibrated", False)

            if calibrated:
                pose_txt = f"Head: {direction} | Diff: [Y:{yaw_diff:+.1f} deg/+-{yaw_thr:.0f} deg, P:{pitch_diff:+.1f} deg/+-{pitch_thr:.0f} deg] | Dist: {dist_cm:.0f}cm"
            else:
                raw_y = rd.get("yaw", 0.0)
                raw_p = rd.get("pitch", 0.0)
                pose_txt = f"Head: {direction} (Calibrating... Raw Yaw:{raw_y:+.1f} deg, Pitch:{raw_p:+.1f} deg)"
            cv2.putText(frame, pose_txt, (20, fh - 55), self.font, 0.52, (255, 255, 255), 2)

        return frame



