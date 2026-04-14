"""
Session persistence — web session storage helpers.

Handles creation, save/load, and inference of session metadata.
"""

import json
import re
import secrets
from datetime import datetime
from pathlib import Path


# ── Paths (set by app.py at import time) ──────────────────────────────────
SESSIONS_DIR: Path = Path(".")  # overridden by app.py


def configure(sessions_dir: Path) -> None:
    """Called by app.py to set the sessions directory."""
    global SESSIONS_DIR
    SESSIONS_DIR = sessions_dir


def new_web_session_id() -> str:
    return datetime.now().strftime("session_%Y%m%d_%H%M%S")


def session_dir_for_code(code: str) -> Path:
    """Return the per-code subdirectory under SESSIONS_DIR."""
    bucket = code if code else "_anonymous"
    d = SESSIONS_DIR / bucket
    d.mkdir(parents=True, exist_ok=True)
    return d


def infer_session_meta(conversation: list[dict]) -> tuple[str, str]:
    """Infer customer_type and resolution from conversation text.

    customer_type is inferred from USER messages ONLY.
    Bot messages frequently list all customer types as options which would
    cause false positives if scanned.
    Resolution is inferred from ALL messages (transfer language comes from bot).
    """
    user_text = " ".join(
        t.get("content", "") for t in conversation if t.get("role") == "user"
    ).lower()
    all_text = " ".join(t.get("content", "") for t in conversation).lower()

    # customer_type: scan user messages only
    if any(k in user_text for k in [
        "partner", "reseller", "system integrator",
    ]):
        customer_type = "partner"
    elif any(k in user_text for k in [
        "existing customer", "my account", "our agent",
        "cannot receive", "overcharged", "billing",
    ]):
        customer_type = "existing_customer"
    elif any(k in user_text for k in [
        "new customer", "i'm new", "first time",
        "interested in", "looking for", "want to try",
    ]):
        customer_type = "new_customer"
    else:
        # Fallback: infer from bot messages
        bot_text_fb = " ".join(
            t.get("content", "") for t in conversation if t.get("role") == "bot"
        ).lower()
        if any(k in bot_text_fb for k in [
            "account id", "service number",
            "i found your account", "i can see your account",
        ]):
            customer_type = "existing_customer"
        elif any(k in all_text for k in [
            "your email", "phone number", "email address",
        ]):
            customer_type = "new_customer"
        elif re.search(
            r'(?:name|company).{0,400}(?:email|@)', bot_text_fb, re.DOTALL
        ):
            customer_type = "new_customer"
        else:
            customer_type = "unknown"

    # Resolution: scan all messages (transfer/escalation language from bot)
    resolution = "abandoned"
    if any(k in all_text for k in [
        "connect you with", "transfer", "please hold", "our team will",
    ]):
        resolution = "transferred"

    return customer_type, resolution


def save_session_data(web_session_id: str, data: dict) -> None:
    code = data.get("access_code", "")
    d = session_dir_for_code(code)
    f = d / f"{web_session_id}.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session_data(web_session_id: str, code_hint: str = "") -> dict | None:
    if not re.match(r'^session_\d{8}_\d{6}$', web_session_id):
        return None
    # Fast path: check the caller's own code directory first
    if code_hint is not None:
        d = session_dir_for_code(code_hint)
        f = d / f"{web_session_id}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                return None
    # Fallback: scan all subdirectories
    if SESSIONS_DIR.exists():
        for subdir in SESSIONS_DIR.iterdir():
            if subdir.is_dir():
                f = subdir / f"{web_session_id}.json"
                if f.exists():
                    try:
                        return json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        return None
    return None
