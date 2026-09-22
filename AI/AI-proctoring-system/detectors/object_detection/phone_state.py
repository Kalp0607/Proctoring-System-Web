import logging
import time
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PhoneState(str, Enum):
    NO_PHONE = "NO_PHONE"
    PHONE_CANDIDATE = "PHONE_CANDIDATE"
    PHONE_CONFIRMED = "PHONE_CONFIRMED"
    PHONE_LOST = "PHONE_LOST"


class PhoneStateMachine:
    """
    Explicit Finite State Machine managing phone violation transitions, cooldown, and single event emission.
    """

    def __init__(self, cooldown_seconds: float = 3.0, lost_grace_seconds: float = 1.5):
        self.state: PhoneState = PhoneState.NO_PHONE
        self.cooldown_seconds = cooldown_seconds
        self.lost_grace_seconds = lost_grace_seconds

        self.last_confirmed_time: float = 0.0
        self.last_seen_time: float = 0.0
        self.lost_start_time: float = 0.0
        self.violation_emitted: bool = False

    def update(self, temporal_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Advances the state machine given the current temporal evidence.
        
        Returns:
            {
                "state": PhoneState,
                "emit_violation": bool,
                "in_violation": bool,
                "message": str
            }
        """
        now = time.time()
        is_confirmed = temporal_info.get("is_confirmed", False)
        is_candidate = temporal_info.get("is_candidate", False)
        emit_violation = False

        if is_confirmed:
            self.last_seen_time = now
            if self.state != PhoneState.PHONE_CONFIRMED:
                # Check cooldown
                if (now - self.last_confirmed_time) >= self.cooldown_seconds:
                    self.state = PhoneState.PHONE_CONFIRMED
                    self.last_confirmed_time = now
                    emit_violation = True
                    self.violation_emitted = True
                    logger.warning(f"Phone state transitioned to PHONE_CONFIRMED (Score: {temporal_info.get('final_score')})")
                else:
                    self.state = PhoneState.PHONE_CANDIDATE
            else:
                # Already confirmed, keep in confirmed state
                pass

        elif is_candidate:
            self.last_seen_time = now
            if self.state == PhoneState.NO_PHONE:
                self.state = PhoneState.PHONE_CANDIDATE
            elif self.state == PhoneState.PHONE_LOST:
                self.state = PhoneState.PHONE_CANDIDATE

        else:
            # No candidate or confirmed in current frame
            if self.state == PhoneState.PHONE_CONFIRMED:
                self.state = PhoneState.PHONE_LOST
                self.lost_start_time = now
            elif self.state == PhoneState.PHONE_LOST:
                if (now - self.lost_start_time) >= self.lost_grace_seconds:
                    self.state = PhoneState.NO_PHONE
                    self.violation_emitted = False
            elif self.state == PhoneState.PHONE_CANDIDATE:
                self.state = PhoneState.NO_PHONE

        in_violation = (self.state == PhoneState.PHONE_CONFIRMED)

        return {
            "state": self.state.value,
            "emit_violation": emit_violation,
            "in_violation": in_violation,
            "final_score": temporal_info.get("final_score", 0.0)
        }
