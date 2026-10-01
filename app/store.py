import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import secrets
import json
from .config import DB_PATH

def get_connection():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()
    return hashed, salt

def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(new_hash, hashed_password)

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as con:
        # Users Table
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            hashed_password TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            last_login TEXT
        )""")

        # Feedback Table
        con.execute("""CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            query TEXT NOT NULL,
            incident_id TEXT,
            rating INTEGER NOT NULL,
            comment TEXT,
            accuracy TEXT DEFAULT 'Yes',
            user_email TEXT DEFAULT 'anonymous'
        )""")
        fb_cols = {row[1] for row in con.execute("PRAGMA table_info(feedback)").fetchall()}
        if "accuracy" not in fb_cols:
            con.execute("ALTER TABLE feedback ADD COLUMN accuracy TEXT DEFAULT 'Yes'")
        if "user_email" not in fb_cols:
            con.execute("ALTER TABLE feedback ADD COLUMN user_email TEXT DEFAULT 'anonymous'")

        # Custom Incidents Table (allows full CRUD and status flags)
        con.execute("""CREATE TABLE IF NOT EXISTS custom_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT UNIQUE NOT NULL,
            ticket_id TEXT DEFAULT '',
            description TEXT NOT NULL,
            resolution_notes TEXT NOT NULL,
            incident_state TEXT NOT NULL DEFAULT 'Resolved',
            priority TEXT NOT NULL DEFAULT 'P2',
            impact TEXT NOT NULL DEFAULT '2',
            urgency TEXT NOT NULL DEFAULT '2',
            category TEXT NOT NULL DEFAULT 'Application',
            ci_name TEXT DEFAULT '',
            assigned_to TEXT DEFAULT 'SRE Media Squad',
            kb_status TEXT DEFAULT 'Verified',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            created_by TEXT DEFAULT 'admin'
        )""")
        incident_cols = {row[1] for row in con.execute("PRAGMA table_info(custom_incidents)").fetchall()}
        for col_name, col_def in {
            "ticket_id": "TEXT DEFAULT ''",
            "description": "TEXT NOT NULL DEFAULT ''",
            "resolution_notes": "TEXT NOT NULL DEFAULT ''",
            "incident_state": "TEXT NOT NULL DEFAULT 'Resolved'",
            "priority": "TEXT NOT NULL DEFAULT 'P2'",
            "impact": "TEXT NOT NULL DEFAULT '2'",
            "urgency": "TEXT NOT NULL DEFAULT '2'",
            "category": "TEXT NOT NULL DEFAULT 'Application'",
            "ci_name": "TEXT DEFAULT ''",
            "assigned_to": "TEXT DEFAULT 'SRE Media Squad'",
            "kb_status": "TEXT DEFAULT 'Verified'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "resolved_at": "TEXT",
            "created_by": "TEXT DEFAULT 'admin'"
        }.items():
            if col_name not in incident_cols:
                con.execute(f"ALTER TABLE custom_incidents ADD COLUMN {col_name} {col_def}")

        # Search Query History Table
        con.execute("""CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_email TEXT NOT NULL,
            query TEXT NOT NULL,
            result_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Resolved',
            feedback_rating INTEGER,
            response_json TEXT
        )""")
        # Additive migration for databases created before full conversations were stored.
        columns = {row[1] for row in con.execute("PRAGMA table_info(search_history)").fetchall()}
        if "response_json" not in columns:
            con.execute("ALTER TABLE search_history ADD COLUMN response_json TEXT")

        # Notifications Table
        con.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_email TEXT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            category TEXT DEFAULT 'system',
            read_status INTEGER DEFAULT 0
        )""")

        # Audit Logs Table (Guardrails & Security)
        con.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_email TEXT,
            action TEXT NOT NULL,
            details TEXT,
            status TEXT NOT NULL
        )""")

        # Settings Table
        con.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL,
            current_tier TEXT NOT NULL, target_tier TEXT NOT NULL, reason TEXT NOT NULL,
            notes TEXT DEFAULT '', created_by TEXT NOT NULL, created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open'
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS workflow_tickets (
            ticket_id TEXT PRIMARY KEY,
            incident_id TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'P3',
            status TEXT NOT NULL DEFAULT 'Open',
            resolution TEXT DEFAULT '',
            current_tier TEXT NOT NULL DEFAULT 'l1',
            assigned_to TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS ticket_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_email TEXT NOT NULL,
            recipient_email TEXT,
            from_tier TEXT,
            to_tier TEXT,
            message TEXT DEFAULT '',
            payload TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS ticket_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            source_event_id INTEGER NOT NULL,
            reviewer_email TEXT NOT NULL,
            reviewer_tier TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            recipient_tier TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(ticket_id, source_event_id)
        )""")
        # Migrate older generic user accounts to the initial support tier.
        con.execute("UPDATE users SET role='l1' WHERE lower(role)='user'")

        con.commit()

    # Seed Default Admin and User if not already present
    seed_default_users()
    seed_default_notifications()

def seed_default_users():
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE email = ?", ("admin@incidentiq.io",))
        if cur.fetchone()[0] == 0:
            h, s = hash_password("Admin@123")
            cur.execute("""INSERT INTO users (email, username, hashed_password, salt, role, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        ("admin@incidentiq.io", "Admin SRE Lead", h, s, "admin", datetime.now(timezone.utc).isoformat()))

        cur.execute("SELECT COUNT(*) FROM users WHERE email = ?", ("engineer@incidentiq.io",))
        if cur.fetchone()[0] == 0:
            h, s = hash_password("User@123")
            cur.execute("""INSERT INTO users (email, username, hashed_password, salt, role, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        ("engineer@incidentiq.io", "L1 Support Engineer", h, s, "l1", datetime.now(timezone.utc).isoformat()))
        con.commit()

def seed_default_notifications():
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM notifications")
        if cur.fetchone()[0] == 0:
            now = datetime.now(timezone.utc).isoformat()
            items = [
                ("System Intelligence Ready", "IncidentIQ Hybrid Retrieval Engine indexed 150 knowledge base incidents with sub-10ms query latency.", "system"),
                ("New Verified KB Article", "Storage volume expansion and cleanup runbook for MediaServer01 verified by SRE Squad.", "kb"),
                ("Escalation Handoff", "Ticket INC-5004 assigned to L2 Security Incident Squad.", "escalation"),
                ("Benchmark Evaluation", "Live evaluation completed with 100% Top-1 Precision and 1.000 MRR.", "evaluation")
            ]
            for title, msg, cat in items:
                cur.execute("INSERT INTO notifications (created_at, user_email, title, message, category, read_status) VALUES (?, ?, ?, ?, ?, 0)",
                            (now, "all", title, msg, cat))
            con.commit()

# --- Search History Methods ---
def save_search_history(query: str, user_email: str, result_count: int = 0, status: str = "Resolved", response: dict | None = None):
    init_db()
    with get_connection() as con:
        con.execute(
            "INSERT INTO search_history (created_at, user_email, query, result_count, status, response_json) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), user_email, query, result_count, status,
             json.dumps(response, ensure_ascii=False) if response is not None else None)
        )
        con.commit()

def get_search_history(user_email: str, limit: int = 20):
    init_db()
    with get_connection() as con:
        cur = con.cursor()
        if user_email and user_email != "all":
            cur.execute("SELECT * FROM search_history WHERE user_email = ? ORDER BY id DESC LIMIT ?", (user_email, limit))
        else:
            cur.execute("SELECT * FROM search_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            try:
                row["response"] = json.loads(row.pop("response_json")) if row.get("response_json") else None
            except (TypeError, json.JSONDecodeError):
                row["response"] = None
                row.pop("response_json", None)
        return rows

def update_latest_search_history(query: str, user_email: str, updates: dict):
    """Attach a deferred answer to the most recent matching conversation."""
    init_db()
    with get_connection() as con:
        row = con.execute(
            "SELECT id, response_json FROM search_history WHERE user_email = ? AND query = ? ORDER BY id DESC LIMIT 1",
            (user_email, query),
        ).fetchone()
        if not row:
            return
        try:
            response = json.loads(row["response_json"]) if row["response_json"] else {}
        except (TypeError, json.JSONDecodeError):
            response = {}
        response.update(updates)
        con.execute("UPDATE search_history SET response_json = ? WHERE id = ?", (json.dumps(response, ensure_ascii=False), row["id"]))
        con.commit()

# --- Notification Methods ---
def add_notification(title: str, message: str, category: str = "system", user_email: str = "all"):
    init_db()
    with get_connection() as con:
        con.execute(
            "INSERT INTO notifications (created_at, user_email, title, message, category, read_status) VALUES (?, ?, ?, ?, ?, 0)",
            (datetime.now(timezone.utc).isoformat(), user_email, title, message, category)
        )
        con.commit()

def get_notifications(user_email: str = "all", limit: int = 15):
    init_db()
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

# --- Feedback Methods ---
def save_feedback(query: str, incident_id: str | None, rating: int, comment: str = "", accuracy: str = "Yes", user_email: str = "anonymous"):
    init_db()
    with get_connection() as con:
        con.execute(
            "INSERT INTO feedback(created_at, query, incident_id, rating, comment, accuracy, user_email) VALUES(?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), query, incident_id, rating, comment, accuracy, user_email)
        )
        con.execute("UPDATE search_history SET feedback_rating=? WHERE id=(SELECT id FROM search_history WHERE user_email=? AND lower(trim(query))=lower(trim(?)) ORDER BY id DESC LIMIT 1)",(rating,user_email,query))
        con.commit()

def feedback_stats():
    init_db()
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*), AVG(rating) FROM feedback")
        total, avg = cur.fetchone()
        cur.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating")
        breakdown = {int(r[0]): int(r[1]) for r in cur.fetchall() if r[0] is not None}
        
        cur.execute("SELECT accuracy, COUNT(*) FROM feedback GROUP BY accuracy")
        accuracy_breakdown = {str(r[0]): int(r[1]) for r in cur.fetchall() if r[0] is not None}
        
        cur.execute("SELECT * FROM feedback ORDER BY id DESC")
        recent = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM ticket_reviews ORDER BY id DESC")
        tier_reviews = [dict(r) for r in cur.fetchall()]
        
        helpful_count = breakdown.get(5, 0) + breakdown.get(4, 0)
        unhelpful_count = breakdown.get(1, 0) + breakdown.get(2, 0)

        return {
            "feedback_count": total or 0,
            "average_rating": round(avg, 2) if avg is not None else 0,
            "rating_breakdown": breakdown,
            "accuracy_breakdown": accuracy_breakdown,
            "helpful_count": helpful_count,
            "unhelpful_count": unhelpful_count,
            "recent_feedback": recent,
            "tier_reviews": tier_reviews
        }

def list_user_feedback(user_email: str):
    with get_connection() as con:
        return [dict(r) for r in con.execute("SELECT * FROM feedback WHERE user_email=? ORDER BY id DESC", (user_email,)).fetchall()]

def update_password(user_id: int, current_password: str, new_password: str):
    with get_connection() as con:
        row = con.execute("SELECT hashed_password,salt FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not verify_password(current_password, row['hashed_password'], row['salt']):
            return False
        hashed, salt = hash_password(new_password)
        con.execute("UPDATE users SET hashed_password=?,salt=? WHERE id=?", (hashed,salt,user_id))
        con.commit()
        return True

def list_escalations(user_email: str | None = None):
    with get_connection() as con:
        if user_email:
            rows = con.execute("SELECT * FROM escalations WHERE created_by=? ORDER BY id DESC",(user_email,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM escalations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

def add_ticket_event(ticket_id: str, event_type: str, actor_email: str, message: str = "", recipient_email: str | None = None, from_tier: str | None = None, to_tier: str | None = None, payload: dict | None = None):
    with get_connection() as con:
        con.execute("INSERT INTO ticket_events(ticket_id,event_type,actor_email,recipient_email,from_tier,to_tier,message,payload,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (ticket_id,event_type,actor_email,recipient_email,from_tier,to_tier,message,json.dumps(payload or {},ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        con.commit()

def list_workflow_tickets(user: dict):
    with get_connection() as con:
        if user.get("role") == "admin":
            rows=con.execute("SELECT * FROM workflow_tickets ORDER BY updated_at DESC").fetchall()
        else:
            rows=con.execute("SELECT * FROM workflow_tickets WHERE created_by=? OR assigned_to=? OR (assigned_to IS NULL AND current_tier=?) OR ticket_id IN (SELECT ticket_id FROM ticket_events WHERE recipient_email=?) ORDER BY updated_at DESC", (user.get("email"),user.get("email"),user.get("role"),user.get("email"))).fetchall()
        tickets=[dict(r) for r in rows]
        for ticket in tickets:
            ticket["events"]=[dict(e) for e in con.execute("SELECT id,event_type,actor_email,recipient_email,from_tier,to_tier,message,payload,created_at FROM ticket_events WHERE ticket_id=? ORDER BY id DESC LIMIT 8",(ticket["ticket_id"],)).fetchall()]
            for event in ticket["events"]:
                try: event["payload"]=json.loads(event["payload"] or "{}")
                except (TypeError,json.JSONDecodeError): event["payload"]={}
            ticket["events"].reverse()
        return tickets

def get_workflow_ticket(ticket_id: str):
    with get_connection() as con:
        row=con.execute("SELECT * FROM workflow_tickets WHERE ticket_id=?",(ticket_id,)).fetchone()
        if not row: return None
        ticket=dict(row)
        events=con.execute("SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY id ASC",(ticket_id,)).fetchall()
        ticket["events"]=[]
        for event in events:
            item=dict(event)
            try: item["payload"]=json.loads(item["payload"] or "{}")
            except (TypeError,json.JSONDecodeError): item["payload"]={}
            ticket["events"].append(item)
        return ticket

def list_agents(role: str | None = None):
    with get_connection() as con:
        if role:
            return [dict(r) for r in con.execute("SELECT id,email,username,role FROM users WHERE lower(role)=? ORDER BY username",(role.lower(),)).fetchall()]
        return [dict(r) for r in con.execute("SELECT id,email,username,role FROM users WHERE lower(role) IN ('l1','l2','l3') ORDER BY role,username").fetchall()]

def get_ticket_review_target(ticket_id: str, user: dict):
    reviewer_tier=user.get("role")
    tier_pair={"l2":("l1","l2"),"l3":("l2","l3")}.get(reviewer_tier)
    if not tier_pair: return None
    from_tier,to_tier=tier_pair
    with get_connection() as con:
        event=con.execute("SELECT id,actor_email,recipient_email FROM ticket_events WHERE ticket_id=? AND event_type='escalated' AND from_tier=? AND to_tier=? AND recipient_email=? ORDER BY id DESC LIMIT 1",(ticket_id,from_tier,to_tier,user.get("email"))).fetchone()
        if not event: return None
        already=con.execute("SELECT 1 FROM ticket_reviews WHERE ticket_id=? AND source_event_id=?",(ticket_id,event["id"])).fetchone()
        target=con.execute("SELECT username FROM users WHERE email=?",(event["actor_email"],)).fetchone()
        return {"can_submit":not bool(already),"reviewer_tier":reviewer_tier,"recipient_tier":from_tier,"recipient_email":event["actor_email"],"recipient_name":target["username"] if target else event["actor_email"],"source_event_id":event["id"],"submitted":bool(already)}

def list_ticket_reviews(ticket_id: str):
    with get_connection() as con:
        return [dict(row) for row in con.execute("SELECT r.*,t.title,t.incident_id FROM ticket_reviews r LEFT JOIN workflow_tickets t ON t.ticket_id=r.ticket_id WHERE r.ticket_id=? ORDER BY r.id ASC",(ticket_id,)).fetchall()]

def list_tier_reviews(user_email: str | None = None):
    with get_connection() as con:
        if user_email:
            rows=con.execute("SELECT r.*,t.title,t.incident_id FROM ticket_reviews r LEFT JOIN workflow_tickets t ON t.ticket_id=r.ticket_id WHERE r.reviewer_email=? OR r.recipient_email=? ORDER BY r.id DESC",(user_email,user_email)).fetchall()
            items=[]
            for row in rows:
                item=dict(row)
                item["direction"]="received" if item["recipient_email"]==user_email else "given"
                items.append(item)
            return items
        return [dict(row) for row in con.execute("SELECT r.*,t.title,t.incident_id FROM ticket_reviews r LEFT JOIN workflow_tickets t ON t.ticket_id=r.ticket_id ORDER BY r.id DESC").fetchall()]

# --- Audit Log Methods ---
def log_audit(action: str, details: str = "", user_email: str = "system", status: str = "info"):
    init_db()
    with get_connection() as con:
        con.execute(
            "INSERT INTO audit_logs(timestamp, user_email, action, details, status) VALUES(?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), user_email, action, details, status)
        )
        con.commit()

def get_audit_logs(limit: int = 60):
    init_db()
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]
