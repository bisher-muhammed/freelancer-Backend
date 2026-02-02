from django.utils import timezone
from apps.tracking.models import TimeBlock

# ============================================
# CONFIG
# ============================================

# Flag automatically if idle reaches 30 minutes
IDLE_FLAG_SECONDS = 30 * 60  # 1800 seconds

# Ignore very small blocks (avoid false flags)
MIN_BLOCK_DURATION = 5 * 60  # 5 minutes


# ============================================
# MAIN FLAGGING FUNCTION
# ============================================

def evaluate_timeblock_flag(block: TimeBlock):
    """
    SYSTEM automatic flagging.

    Rules:
    - Only evaluates CLOSED blocks
    - Flags if idle >= 30 minutes
    - SYSTEM never overrides ADMIN decisions
    - Flagging is only for dispute/review (not billing)
    """

    # ✅ Only closed blocks are evaluated
    if not block.ended_at:
        return

    # ✅ Admin decisions are FINAL
    if block.flag_source == "ADMIN":
        return

    duration = block.total_seconds

    # ✅ Guardrail: ignore tiny blocks
    if duration < MIN_BLOCK_DURATION:
        _clear_system_flag(block)
        return

    # ✅ Absolute idle rule: 30 minutes or more
    if block.idle_seconds >= IDLE_FLAG_SECONDS:
        _apply_system_flag(block)
    else:
        _clear_system_flag(block)


# ============================================
# APPLY SYSTEM FLAG
# ============================================

def _apply_system_flag(block: TimeBlock):
    """
    Apply a SYSTEM flag when idle >= threshold.
    """

    block.is_flagged = True
    block.flag_source = "SYSTEM"
    block.flag_reason = (
        f"Idle exceeded 30 min: {block.idle_seconds // 60} minutes"
    )
    block.flagged_at = timezone.now()

    block.save(update_fields=[
        "is_flagged",
        "flag_source",
        "flag_reason",
        "flagged_at",
    ])


# ============================================
# CLEAR SYSTEM FLAG
# ============================================

def _clear_system_flag(block: TimeBlock):
    """
    Clears ONLY system-generated flags.
    Never touches admin flags.
    """

    if block.flag_source != "SYSTEM":
        return

    block.is_flagged = False
    block.flag_source = "NONE"
    block.flag_reason = ""
    block.flagged_at = None

    block.save(update_fields=[
        "is_flagged",
        "flag_source",
        "flag_reason",
        "flagged_at",
    ])

