"""
Access code authentication — code lifecycle, token management, idle purge.

Manages access codes (admin-generated, time-limited) and session tokens
(ephemeral, one-per-code exclusive lock). Persists state to auth_store.json.
"""

import asyncio
import json
import secrets
import string
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, Query


# ── Configuration (set by app.py) ─────────────────────────────────────────
ADMIN_KEY: str = ""
IDLE_TIMEOUT_SECONDS: int = 900   # 15 min default
_AUTH_FILE: Path = Path(".")
_DT_FMT = "%Y-%m-%d %H:%M:%S"


def configure(
    admin_key: str,
    idle_timeout_seconds: int,
    auth_file: Path,
) -> None:
    global ADMIN_KEY, IDLE_TIMEOUT_SECONDS, _AUTH_FILE
    ADMIN_KEY = admin_key
    IDLE_TIMEOUT_SECONDS = idle_timeout_seconds
    _AUTH_FILE = auth_file


# ── Data structures ───────────────────────────────────────────────────────
@dataclass
class _Code:
    code:       str
    expires_at: datetime
    label:      str = ""
    status:     str = "active"     # active | expired | revoked
    created_at: str = ""           # ISO timestamp for audit

    @property
    def is_usable(self) -> bool:
        return self.status == "active" and self.expires_at >= datetime.now()


# ── In-memory auth state ──────────────────────────────────────────────────
_codes:  dict[str, _Code]    = {}   # code -> _Code (permanent, never deleted)
_tokens: dict[str, datetime] = {}   # token -> expires_at (ephemeral session)
_token_to_code:       dict[str, str]   = {}  # token -> code
_code_to_token:       dict[str, str]   = {}  # code  -> active token (exclusive lock)
_token_last_activity: dict[str, float] = {}  # token -> last chat unix timestamp


def get_code_for_token(token: str) -> str:
    """Return the access code associated with a token."""
    return _token_to_code.get(token, "")


def touch_token(token: str) -> None:
    """Update the idle-timeout clock for a token."""
    _token_last_activity[token] = time.time()


# ── Persistence ───────────────────────────────────────────────────────────
def save_auth() -> None:
    """Persist auth state to disk (human-readable JSON)."""
    data = {
        "codes": {
            k: {
                "expires_at": v.expires_at.strftime(_DT_FMT),
                "label":      v.label,
                "status":     v.status,
                "created_at": v.created_at,
            }
            for k, v in _codes.items()
        },
        "tokens": {
            k: v.strftime(_DT_FMT) for k, v in _tokens.items()
        },
        "token_to_code":       dict(_token_to_code),
        "code_to_token":       dict(_code_to_token),
        "token_last_activity": dict(_token_last_activity),
    }
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTH_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_auth() -> None:
    """Load auth state from disk on startup."""
    if not _AUTH_FILE.exists():
        return
    try:
        data = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
        for code, info in data.get("codes", {}).items():
            _codes[code] = _Code(
                code=code,
                expires_at=datetime.strptime(info["expires_at"], _DT_FMT),
                label=info.get("label", ""),
                status=info.get("status", "active"),
                created_at=info.get("created_at", ""),
            )
        for token, exp in data.get("tokens", {}).items():
            _tokens[token] = datetime.strptime(exp, _DT_FMT)
        _token_to_code.update(data.get("token_to_code", {}))
        _code_to_token.update(data.get("code_to_token", {}))
        _token_last_activity.update(data.get("token_last_activity", {}))
    except Exception as e:
        print(f"[auth] Failed to load auth_store.json: {e}", flush=True)


def _evict_token(token: str) -> None:
    """Remove a session token and release the code's exclusive lock."""
    code = _token_to_code.pop(token, None)
    _tokens.pop(token, None)
    _token_last_activity.pop(token, None)
    if code and _code_to_token.get(code) == token:
        _code_to_token.pop(code, None)


def purge() -> None:
    """Mark expired codes, clean up expired/idle tokens."""
    now_dt  = datetime.now()
    now_ts  = time.time()
    changed = False
    for ac in _codes.values():
        if ac.status == "active" and ac.expires_at < now_dt:
            ac.status = "expired"
            changed = True
    for k in list(_tokens):
        if _tokens[k] < now_dt:
            _evict_token(k)
            changed = True
    for k in list(_token_last_activity):
        if k in _tokens and now_ts - _token_last_activity[k] > IDLE_TIMEOUT_SECONDS:
            _evict_token(k)
            changed = True
    if changed:
        save_auth()


async def idle_purge_loop() -> None:
    """Background task: sweep idle/expired tokens every 60 s."""
    while True:
        await asyncio.sleep(60)
        purge()


def valid_token(token: str) -> bool:
    purge()
    return token in _tokens


# ── Endpoint functions (app.py mounts these as routes) ────────────────────
async def admin_new_code(
    key:        str = Query(""),
    expires_in: int = Query(86400, description="Seconds until code expires"),
    label:      str = Query("",    description="Optional label, e.g. client name"),
):
    if key != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")
    purge()
    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    now = datetime.now()
    expires_at = now + timedelta(seconds=expires_in)
    _codes[code] = _Code(
        code=code, expires_at=expires_at, label=label,
        status="active", created_at=now.isoformat(),
    )
    save_auth()
    hours, rem = divmod(expires_in, 3600)
    minutes = rem // 60
    duration = f"{hours}h {minutes}m" if hours else f"{minutes}m"
    return {
        "code":       code,
        "expires_at": expires_at.strftime(_DT_FMT),
        "expires_in": duration,
        "label":      label or "(unnamed)",
    }


async def admin_batch_codes(
    key:        str = Query(""),
    count:      int = Query(5,     description="Number of codes to generate (1-50)"),
    expires_in: int = Query(86400, description="Seconds until codes expire"),
    label:      str = Query("",    description="Optional shared label prefix"),
):
    if key != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")
    count = max(1, min(count, 50))
    purge()
    alphabet = string.ascii_uppercase + string.digits
    now = datetime.now()
    expires_at = now + timedelta(seconds=expires_in)
    hours, rem = divmod(expires_in, 3600)
    minutes = rem // 60
    duration = f"{hours}h {minutes}m" if hours else f"{minutes}m"

    codes = []
    for i in range(count):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        code_label = f"{label} #{i+1}" if label else f"#{i+1}"
        _codes[code] = _Code(
            code=code, expires_at=expires_at, label=code_label,
            status="active", created_at=now.isoformat(),
        )
        codes.append({
            "code":       code,
            "label":      code_label,
            "expires_at": expires_at.strftime(_DT_FMT),
        })
    save_auth()
    return {
        "count":      len(codes),
        "expires_in": duration,
        "codes":      codes,
    }


async def admin_list_codes(key: str = Query("")):
    if key != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")
    purge()
    return [
        {
            "code":       v.code,
            "label":      v.label,
            "status":     v.status,
            "created_at": v.created_at,
            "expires_at": v.expires_at.strftime(_DT_FMT),
            "in_use":     bool(_code_to_token.get(v.code)),
        }
        for v in _codes.values()
    ]


async def auth_verify(body: dict):
    code = body.get("code", "").strip().upper()
    purge()
    ac = _codes.get(code)
    if not ac or not ac.is_usable:
        raise HTTPException(401, "Invalid or expired code")

    # Exclusive-lock check: one active session per code
    existing = _code_to_token.get(code)
    if existing and existing in _tokens:
        last_act  = _token_last_activity.get(existing, 0)
        idle_secs = time.time() - last_act
        if idle_secs < IDLE_TIMEOUT_SECONDS:
            remaining_mins = max(1, round((IDLE_TIMEOUT_SECONDS - idle_secs) / 60))
            raise HTTPException(409, detail={
                "in_use":               True,
                "idle_timeout_minutes": IDLE_TIMEOUT_SECONDS // 60,
                "remaining_minutes":    remaining_mins,
            })
        _evict_token(existing)

    token = secrets.token_urlsafe(32)
    _tokens[token]               = ac.expires_at
    _token_to_code[token]        = code
    _code_to_token[code]         = token
    _token_last_activity[token]  = time.time()
    save_auth()
    return {
        "token":      token,
        "code":       code,
        "expires_at": ac.expires_at.strftime(_DT_FMT),
        "label":      ac.label,
    }


async def auth_logout(body: dict):
    token = body.get("token", "")
    if token in _tokens:
        _evict_token(token)
        save_auth()
    return {"ok": True}
