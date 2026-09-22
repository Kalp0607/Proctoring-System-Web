import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from detectors.object_detection.schema import Detection, TrackedObject, TelemetryData


class DebugVisualizer:
    """
    Renders comprehensive diagnostic visualization overlays on video frames.
    """

    COLOR_PERSON = (230, 180, 50)       # Cyan (BGR)
    COLOR_PHONE_CONF = (65, 65, 230)    # Red (BGR)
    COLOR_PHONE_CAND = (30, 165, 240)   # Amber (BGR)
    COLOR_BOOK = (40, 200, 240)         # Yellow (BGR)
    COLOR_ROI = (85, 195, 60)           # Green (BGR)
    COLOR_HUD_BG = (24, 24, 37)         # Slate Dark (BGR)
    COLOR_TEXT = (240, 240, 245)

    def __init__(self, font=cv2.FONT_HERSHEY_SIMPLEX):
        self.font = font

    def draw_diagnostics(self,
                         frame: np.ndarray,
                         persons: List[Detection],
                         person_rois: List[Dict[str, Any]],
                         phone_tracks: List[TrackedObject],
                         books: List[Detection],
                         phone_state_info: Dict[str, Any],
                         telemetry: Optional[TelemetryData] = None) -> np.ndarray:
        """
        Draws complete diagnostic overlays onto the frame.
        """
        if frame is None or frame.size == 0:
            return frame

        canvas = frame.copy()

        # 1. Person Bounding Boxes & IDs (Cyan)
        for p in persons:
            px, py, pw, ph = p.bbox
            conf = p.confidence
            pid = p.person_id or 1
            cv2.rectangle(canvas, (px, py), (px + pw, py + ph), self.COLOR_PERSON, 2)
            lbl = f"PERSON #{pid} ({conf:.2f})"
            lbl_sz, _ = cv2.getTextSize(lbl, self.font, 0.50, 1)
            cv2.rectangle(canvas, (px, max(0, py - 22)), (px + lbl_sz[0] + 8, py), self.COLOR_PERSON, -1)
            cv2.putText(canvas, lbl, (px + 4, py - 6), self.font, 0.50, (0, 0, 0), 1)

        # 2. Person High-Res ROI Boundaries (Green)
        for roi_info in person_rois:
            rx, ry, rw, rh = roi_info["roi_rect"]
            pid = roi_info.get("person_id")
            cv2.rectangle(canvas, (rx, ry), (rx + rw, ry + rh), self.COLOR_ROI, 1)
            pid_str = f" #{pid}" if pid else ""
            cv2.putText(canvas, f"PERSON-ROI{pid_str}", (rx + 6, ry + 16), self.font, 0.42, self.COLOR_ROI, 1)

        # 3. Phone Tracks (Red if Confirmed, Amber if Candidate)
        for track in phone_tracks:
            tx, ty, tw, th = track.bbox
            conf = track.confidence
            tid = track.track_id
            src = track.source
            hand_prox = track.hand_proximity
            hits = track.positive_count
            state_str = track.state

            is_confirmed = (phone_state_info.get("in_violation", False) or state_str == "CONFIRMED")
            box_color = self.COLOR_PHONE_CONF if is_confirmed else self.COLOR_PHONE_CAND
            box_thick = 3 if is_confirmed else 2

            cv2.rectangle(canvas, (tx, ty), (tx + tw, ty + th), box_color, box_thick)

            # Format descriptive label
            src_tag = "FULL" if "full" in src else ("ROI" if "roi" in src else "SAHI")
            hand_tag = f" [Hand:{hand_prox:.2f}]" if hand_prox > 0.0 else ""
            pid_tag = f" [P#{track.person_id}]" if track.person_id else ""
            ph_label = f"PHONE #{tid} {conf:.2f} ({src_tag}){hand_tag}{pid_tag}"

            lbl_sz, _ = cv2.getTextSize(ph_label, self.font, 0.48, 1)
            cv2.rectangle(canvas, (tx, max(0, ty - 22)), (tx + lbl_sz[0] + 8, ty), box_color, -1)
            cv2.putText(canvas, ph_label, (tx + 4, ty - 6), self.font, 0.48, (255, 255, 255), 1)

            # Sub-label with hits & state
            sub_lbl = f"State: {phone_state_info.get('state', 'NORMAL')} (Hits: {hits})"
            cv2.putText(canvas, sub_lbl, (tx + 4, ty + th + 15), self.font, 0.40, box_color, 1)

        # 4. Books (Yellow)
        for b in books:
            bx, by, bw, bh = b.bbox
            cv2.rectangle(canvas, (bx, by), (bx + bw, by + bh), self.COLOR_BOOK, 2)
            b_label = f"BOOK {b.confidence:.2f}"
            lbl_sz, _ = cv2.getTextSize(b_label, self.font, 0.50, 1)
            cv2.rectangle(canvas, (bx, max(0, by - 22)), (bx + lbl_sz[0] + 8, by), self.COLOR_BOOK, -1)
            cv2.putText(canvas, b_label, (bx + 4, by - 6), self.font, 0.50, (0, 0, 0), 1)

        # 5. Pipeline Telemetry HUD (Top-Left)
        if telemetry is not None:
            sahi_txt = "YES" if telemetry.sahi_triggered else "NO"
            hud_lines = [
                f"OBJECT PIPELINE HUD | FPS: {telemetry.fps:.1f}",
                f"Full-Frame: {telemetry.full_frame_ms:.1f}ms | Person-ROI: {telemetry.roi_ms:.1f}ms | SAHI ({sahi_txt}): {telemetry.sahi_ms:.1f}ms",
                f"Tracking: {telemetry.tracking_ms:.1f}ms | Total Pipeline: {telemetry.total_ms:.1f}ms"
            ]

            hud_y = 22
            cv2.rectangle(canvas, (10, 8), (480, 72), self.COLOR_HUD_BG, -1)
            cv2.rectangle(canvas, (10, 8), (480, 72), self.COLOR_ROI, 1)
            for line in hud_lines:
                cv2.putText(canvas, line, (18, hud_y + 4), self.font, 0.40, self.COLOR_TEXT, 1)
                hud_y += 18

        return canvas
