import cv2
import time
import sys
import os
import logging
import argparse
import threading
import numpy as np
from pathlib import Path

import config
from camera.camera_manager import CameraManager
from detectors.face_verifier import FaceVerifier
from detectors.object_detector import ObjectDetector
from detectors.head_pose_detector import HeadPoseDetector
from audio.audio_manager import AudioManager
from audio.speaker_detector import SpeakerDetector
from violations.logger import ViolationLogger
from violations.violation_manager import ViolationManager
from ui.proctoring_ui import ProctoringUI

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MainApp")


def parse_arguments():
    parser = argparse.ArgumentParser(description="AI Exam Proctoring System - Stage 5 (Multimodal Audio & Video Proctoring)")
    parser.add_argument("--reference", type=str, default=str(config.STUDENT_REFERENCE_IMAGE),
                        help="Path to enrolled student reference image")
    parser.add_argument("--camera", type=int, default=config.WEBCAM_INDEX,
                        help="Webcam device index (default: 0)")
    parser.add_argument("--create-sample", action="store_true",
                        help="Generates a sample synthetic reference image if student.jpg is missing")
    return parser.parse_args()


def capture_reference_from_webcam(camera_index: int, target_path: Path) -> bool:
    """
    Opens an interactive webcam window allowing the user to snap their reference photo.
    """
    print("\n" + "=" * 60)
    print("      STUDENT REFERENCE PHOTO ENROLLMENT SETUP")
    print("      Position your face in the box and press SPACEBAR")
    print("=" * 60 + "\n")
    logger.info("Opening webcam for initial enrollment capture...")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.error(f"Cannot access webcam at index {camera_index} for reference photo capture.")
        return False

    window_name = "Enrollment Setup — Press SPACEBAR to Capture Photo"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 960, 540)

    captured = False
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            if config.MIRROR_WEBCAM_FEED:
                frame = cv2.flip(frame, 1)

            display = frame.copy()
            h, w = display.shape[:2]
            box_x1, box_y1 = int(w * 0.25), int(h * 0.15)
            box_x2, box_y2 = int(w * 0.75), int(h * 0.85)

            # Draw guiding alignment overlay
            cv2.rectangle(display, (box_x1, box_y1), (box_x2, box_y2), (85, 195, 60), 2)
            cv2.putText(display, "Align your face inside box & press SPACE to Capture", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(display, "Press ESC to Cancel", (30, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 255), 2)

            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF

            if key == 32:  # SPACEBAR
                target_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(target_path), frame)
                logger.info(f"Reference photo successfully captured and saved to: {target_path}")
                captured = True
                break
            elif key == 27 or key == ord('q') or key == ord('Q'):  # ESC or Q
                logger.info("Reference capture cancelled by user.")
                break

            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                break

    except Exception as e:
        logger.error(f"Error during webcam photo capture: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return captured


def ensure_reference_image(reference_path: Path, camera_index: int = 0, create_sample: bool = False) -> bool:
    """Verifies reference image existence and offers webcam capture or sample creation."""
    if reference_path.exists():
        return True

    logger.warning("=" * 60)
    logger.warning("ENROLLMENT NOTICE: Student reference photo is missing!")
    logger.warning(f"Expected path: {reference_path.resolve()}")
    logger.warning("Starting automatic webcam enrollment snapshot mode...")
    logger.warning("=" * 60)

    if create_sample:
        logger.info("Creating sample reference image for testing...")
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        dummy_img = np.zeros((400, 400, 3), dtype=np.uint8) + 128
        cv2.imwrite(str(reference_path), dummy_img)
        return True

    # Launch interactive webcam enrollment capture
    return capture_reference_from_webcam(camera_index, reference_path)


def main():
    args = parse_arguments()
    reference_path = Path(args.reference)

    print("\n" + "=" * 65)
    print("        AI EXAM PROCTORING SYSTEM — STAGE 5")
    print(" 20s Rolling Speaker Diarization & Multimodal Video Proctoring")
    print("=" * 65 + "\n")

    # 1. Check Reference Image
    if not reference_path.exists():
        if not ensure_reference_image(reference_path, camera_index=args.camera, create_sample=args.create_sample):
            sys.exit(1)

    # 2. Initialize Face Verification Engine & Enroll Student
    try:
        face_verifier = FaceVerifier(similarity_threshold=config.FACE_SIMILARITY_THRESHOLD)
        face_verifier.enroll_reference(str(reference_path))
    except (FileNotFoundError, ValueError) as e:
        logger.critical(f"Enrollment Failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error during face model initialization / enrollment: {e}")
        sys.exit(1)

    # 3. Initialize Unified Stage 3 YOLO Object Detector
    try:
        logger.info(f"Loading Stage 3 Unified YOLO Object Detector ({config.YOLO_MODEL})...")
        object_detector = ObjectDetector(
            model_name=config.YOLO_MODEL,
            img_size=config.YOLO_IMAGE_SIZE,
            device=config.DEVICE
        )
        # Pre-warm YOLO on startup to avoid first-frame latency spike
        logger.info("Pre-warming YOLO Object Detector...")
        dummy_f = np.zeros((config.WEBCAM_HEIGHT, config.WEBCAM_WIDTH, 3), dtype=np.uint8)
        object_detector.process(dummy_f)
    except Exception as e:
        logger.critical(f"Failed to load Stage 3 Object Detector: {e}")
        sys.exit(1)


    # 4. Initialize Stage 4 3D Head Pose Detector & Start Baseline Calibration
    try:
        logger.info("Initializing Stage 4 3D Head Pose Estimator (solvePnP)...")
        head_pose_detector = HeadPoseDetector()
        head_pose_detector.start_calibration(config.HEAD_POSE_CALIBRATION_SECONDS)
    except Exception as e:
        logger.critical(f"Failed to load Head Pose Detector: {e}")
        sys.exit(1)

    # 5. Initialize Stage 5 Live Microphone Audio Manager & Speaker Diarizer
    audio_manager = AudioManager(buffer_duration=config.DIARIZATION_WINDOW_SECONDS)
    audio_started = audio_manager.start()
    speaker_detector = SpeakerDetector()

    # 6. Initialize Camera, Violation Manager, & UI
    camera = CameraManager(camera_index=args.camera, width=config.WEBCAM_WIDTH, height=config.WEBCAM_HEIGHT)
    if not camera.start():
        logger.critical(f"Webcam initialization failed for device index {args.camera}. Exiting.")
        sys.exit(1)

    violation_logger = ViolationLogger()
    violation_mgr = ViolationManager(logger_instance=violation_logger)
    ui_renderer = ProctoringUI()

    logger.info("Starting live proctoring session (All Stages 1–5 Active). Press 'Q' to exit, 'C' to recalibrate.")

    frame_count = 0
    total_frames = 0
    fps = 0.0
    start_time = time.time()

    last_face_result = None
    last_obj_results = None
    last_head_result = None
    last_audio_result = None

    # Asynchronous non-blocking worker states
    is_face_running = False
    is_yolo_running = False
    is_head_running = False
    is_diarization_running = False
    last_diarization_launch = 0.0

    def run_diarization_worker(pcm_20s_audio: np.ndarray, is_available: bool):
        nonlocal is_diarization_running, last_audio_result
        try:
            res = speaker_detector.run_diarization(pcm_20s_audio, is_audio_available=is_available)
            last_audio_result = res
        except Exception as err:
            logger.error(f"Diarization worker execution error: {err}")
        finally:
            is_diarization_running = False

    window_name = "AI Exam Proctoring System - Stage 5"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    first_display_frame = True

    TARGET_FPS = 30.0
    FRAME_TIME = 1.0 / TARGET_FPS
    last_frame_time = 0.0

    try:
        while True:
            now_loop = time.time()
            if now_loop - last_frame_time < FRAME_TIME:
                time.sleep(0.005)
                continue
            
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
                
            last_frame_time = now_loop

            # Single-point horizontal webcam flipping
            if config.MIRROR_WEBCAM_FEED:
                frame = cv2.flip(frame, 1)

            total_frames += 1
            frame_count += 1
            now = time.time()
            elapsed = now - start_time
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                start_time = now

            # A. Run Face Verification AI every Nth frame
            if (total_frames % config.FRAME_SKIP == 0 or last_face_result is None) and not is_face_running:
                is_face_running = True
                def run_face(f):
                    nonlocal last_face_result, is_face_running
                    try:
                        last_face_result = face_verifier.process(f)
                    except Exception as e:
                        logger.error(f"Face verification inference error: {e}")
                    finally:
                        is_face_running = False
                threading.Thread(target=run_face, args=(frame.copy(),), daemon=True).start()

            # B. Run Unified Shared YOLO Inference every Mth frame
            if (total_frames % config.OBJECT_DETECTION_INTERVAL == 0 or last_obj_results is None) and not is_yolo_running:
                is_yolo_running = True
                def run_yolo(f):
                    nonlocal last_obj_results, is_yolo_running
                    try:
                        res = object_detector.process(f)
                        last_obj_results = res
                        ph = res.get("cell_phone")
                        if ph and ph.state == config.STATE_PHONE_DETECTED:
                            logger.warning(f"Phone detected in camera frame (Conf: {ph.similarity_score:.2f})")
                    except Exception as e:
                        logger.error(f"Object detection inference error: {e}")
                    finally:
                        is_yolo_running = False
                threading.Thread(target=run_yolo, args=(frame.copy(),), daemon=True).start()

            # C. Run Stage 4 3D Head Pose Estimation every Kth frame
            if (total_frames % config.HEAD_POSE_PROCESS_INTERVAL == 0 or last_head_result is None) and not is_head_running:
                is_head_running = True
                def run_head(f, tg_marks):
                    nonlocal last_head_result, is_head_running
                    try:
                        last_head_result = head_pose_detector.process(f, target_landmarks=tg_marks)
                    except Exception as e:
                        logger.error(f"Head pose estimation error: {e}")
                    finally:
                        is_head_running = False
                tg = last_face_result.landmarks if (last_face_result and last_face_result.face_detected) else None
                threading.Thread(target=run_head, args=(frame.copy(), tg), daemon=True).start()

            # D. Run Periodic Non-Blocking Speaker Diarization Worker
            if now - last_diarization_launch >= config.DIARIZATION_INTERVAL_SECONDS and not is_diarization_running:
                last_diarization_launch = now
                is_diarization_running = True
                pcm_20s = audio_manager.get_recent_audio(duration_sec=config.DIARIZATION_WINDOW_SECONDS)
                threading.Thread(
                    target=run_diarization_worker,
                    args=(pcm_20s, audio_manager.is_available),
                    daemon=True
                ).start()

            # E. Update Violation Episode Manager with all active detector results
            active_results = []
            if last_face_result:
                active_results.append(last_face_result)
            if last_obj_results:
                active_results.extend(last_obj_results.values())
            if last_head_result:
                active_results.append(last_head_result)
            if last_audio_result:
                active_results.append(last_audio_result)

            annotated_evidence_frame = frame.copy()
            # Draw diagnostics directly on the evidence frame for screenshots
            annotated_evidence_frame = ui_renderer._draw_diagnostics(annotated_evidence_frame, last_face_result, last_obj_results, last_head_result)

            if active_results:
                violation_mgr.update(active_results, annotated_evidence_frame)

            # F. Render Split-Screen UI Canvas
            canvas = ui_renderer.render(frame, last_face_result, last_obj_results, last_head_result, last_audio_result, violation_mgr, fps)

            cv2.imshow(window_name, canvas)
            if first_display_frame:
                cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                first_display_frame = False

            # Keyboard Controls
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q') or key == 27:  # 'q' or Esc
                logger.info("User requested exit.")
                break
            elif key == ord('f') or key == ord('F'):
                curr = cv2.getWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN)
                new_state = cv2.WINDOW_NORMAL if curr == cv2.WINDOW_FULLSCREEN else cv2.WINDOW_FULLSCREEN
                cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, new_state)
                logger.info(f"Fullscreen toggled: {new_state == cv2.WINDOW_FULLSCREEN}")
            elif key == ord('c') or key == ord('C'):
                head_pose_detector.start_calibration(config.HEAD_POSE_CALIBRATION_SECONDS)
                logger.info("Manual baseline calibration triggered.")
            elif key == ord('d') or key == ord('D'):
                config.SHOW_DIAGNOSTICS = not config.SHOW_DIAGNOSTICS
                logger.info(f"Diagnostics display toggled: {config.SHOW_DIAGNOSTICS}")

            # Check window close button (X)
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                logger.info("Window closed by user.")
                break

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.critical(f"Fatal error during main execution loop: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up resources...")
        audio_manager.stop()
        camera.stop()
        cv2.destroyAllWindows()
        violation_mgr.print_post_test_logs()
        logger.info("Session closed successfully.")


if __name__ == "__main__":
    main()
