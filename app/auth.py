from __future__ import annotations
import secrets
import json
import base64
import time
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, Header, Depends
from .store import get_connection, hash_password, verify_password, log_audit
from .config import JWT_SECRET, JWT_EXPIRATION_HOURS

# Token format: base64(payload).signature
def _sign(payload: dict) -> str:
    payload_str = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip('=')
    import hmac, hashlib
    sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def _verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        # re-pad
        rem = len(payload_b64) % 4
        padded = payload_b64 + ('=' * (4 - rem) if rem else '')
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        import hmac, hashlib
        expected_sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def register_user(email: str, username: str, password: str, role: str = "user") -> dict:
    email = email.strip().lower()
    username = username.strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")
    role = role.lower()
    if role not in ("admin", "l1", "l2", "l3"):
        role = "l1"

    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="User with this email already exists.")

        hashed, salt = hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            """INSERT INTO users (email, username, hashed_password, salt, role, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (email, username, hashed, salt, role, now)
        )
        con.commit()
        user_id = cur.lastrowid
        log_audit("user_register", f"User registered: {email} with role {role}", email, "success")

    # Generate login token immediately
    token = create_user_token({"id": user_id, "email": email, "username": username, "role": role})
    return {
        "token": token,
        "user": {"id": user_id, "email": email, "username": username, "role": role}
    }

def login_user(email: str, password: str) -> dict:
    email = email.strip().lower()
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT id, email, username, hashed_password, salt, role FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if not row:
            log_audit("user_login_failed", f"Unknown email: {email}", email, "warning")
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if not verify_password(password, row["hashed_password"], row["salt"]):
            log_audit("user_login_failed", f"Incorrect password for: {email}", email, "warning")
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        now = datetime.now(timezone.utc).isoformat()
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, row["id"]))
        con.commit()

        user = {"id": row["id"], "email": row["email"], "username": row["username"], "role": row["role"]}
        token = create_user_token(user)
        log_audit("user_login_success", f"User logged in: {email}", email, "success")
        return {"token": token, "user": user}

def create_user_token(user_data: dict) -> str:
    payload = {
        "id": user_data["id"],
        "email": user_data["email"],
        "username": user_data["username"],
        "role": user_data["role"],
        "exp": int(time.time()) + (JWT_EXPIRATION_HOURS * 3600)
    }
    return _sign(payload)

def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization:
        return None
    token = authorization
    if token.startswith("Bearer "):
        token = token[7:]
    payload = _verify_token(token)
    return payload

def require_user(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    # Read the current role from SQLite so role changes take effect immediately,
    # rather than waiting for the signed token to expire.
    with get_connection() as con:
        row = con.execute("SELECT role, username, email FROM users WHERE id=?", (user.get("id"),)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Account no longer exists. Please log in again.")
    user.update({"role": row["role"], "username": row["username"], "email": row["email"]})
    return user

def require_admin(authorization: Optional[str] = Header(None)) -> dict:
    user = require_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required for this action.")
    return user

def list_users() -> list[dict]:
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT id, email, username, role, created_at, last_login FROM users ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]
