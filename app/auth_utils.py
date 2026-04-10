"""
Simple signed session tokens for Engineer/Admin (no external JWT dependency).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Literal, Optional, Tuple

Role = Literal["engineer", "admin"]

_TOKEN_TTL_SEC = 86400 * 7  # 7 days


def _normalize_env_password(s: Optional[str]) -> str:
    if not s:
        return ""
    return str(s).strip().strip('"').strip("'")


def load_auth_config() -> Tuple[str, str, str]:
    engineer = _normalize_env_password(os.getenv("ENGINEER_PASSWORD"))
    admin = _normalize_env_password(os.getenv("ADMIN_PASSWORD"))
    secret = os.getenv("AUTH_SECRET", "").strip()
    if not secret:
        # Dev-friendly fallback; set AUTH_SECRET in .env for production
        raw = (engineer + "|" + admin + "|rza-calculator").encode("utf-8")
        secret = hashlib.sha256(raw).hexdigest()
    return engineer, admin, secret


def verify_password(role: Role, password: str) -> bool:
    engineer, admin, _ = load_auth_config()
    pw = _normalize_env_password(password)
    if role == "admin":
        return bool(admin) and hmac.compare_digest(pw, admin)
    if role == "engineer":
        return bool(engineer) and hmac.compare_digest(pw, engineer)
    return False


def mint_token(role: Role) -> str:
    _, _, secret = load_auth_config()
    payload = {"role": role, "exp": int(time.time()) + _TOKEN_TTL_SEC}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64 = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def parse_token(token: str) -> Optional[dict[str, Any]]:
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    _, _, secret = load_auth_config()
    # restore base64 padding
    pad = "=" * ((4 - len(b64) % 4) % 4)
    try:
        body = base64.urlsafe_b64decode(b64 + pad)
    except Exception:
        return None
    expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    exp = int(data.get("exp") or 0)
    if exp < int(time.time()):
        return None
    role = data.get("role")
    if role not in ("engineer", "admin"):
        return None
    return data


def require_staff_token(authorization: Optional[str]) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionError("missing_token")
    token = authorization.split(" ", 1)[1].strip()
    data = parse_token(token)
    if not data:
        raise PermissionError("invalid_token")
    return data
