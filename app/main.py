from __future__ import annotations
from threading import Lock
from typing import Optional, Any
from datetime import datetime, timezone
import os
import re
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Header, Depends, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import DATA_PATH, TOP_K_DEFAULT, OPENROUTER_API_KEY, GEMINI_API_KEY
from .data import load_incidents
from .retrieval import IncidentRetriever
from .intelligence import classify, estimate_resolution_hours
from .agents import IncidentResolutionOrchestrator
from .evaluation import run_retrieval_evaluation, BENCHMARK_CASES
from .guardrails import sanitize_and_guard_input, validate_and_guard_output
from .llm import summarize_documents, generate_generalized_resolution
from .auth import register_user, login_user, get_current_user, require_user, require_admin, list_users
from .store import (
    init_db, save_feedback, feedback_stats, log_audit, get_audit_logs,
    save_search_history, get_search_history, add_notification, get_notifications,
    get_connection, update_latest_search_history, list_user_feedback, update_password, list_escalations,
    add_ticket_event, list_workflow_tickets, get_workflow_ticket, list_agents,
    get_ticket_review_target, list_ticket_reviews, list_tier_reviews
)

app = FastAPI(
    title="IncidentIQ - AI-Powered Incident Knowledge Base Assistant",
    version="2.0.0",
    description="Enterprise Multi-Agent Incident Retrieval, Automated Triage, Guardrails, Evaluation Suite, and RCA Platform."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB on startup
init_db()

_engine_lock = Lock()
_engine = None
_engine_path = None
_engine_mtime = None


def get_engine():
    global _engine, _engine_path, _engine_mtime
    active_path = DATA_PATH
    active_mtime = active_path.stat().st_mtime_ns if active_path.exists() else None

    if _engine is None or _engine_path != active_path or _engine_mtime != active_mtime:
        with _engine_lock:
            if _engine is None or _engine_path != active_path or _engine_mtime != active_mtime:
                df = load_incidents(active_path)
                retriever = IncidentRetriever(df)
                orchestrator = IncidentResolutionOrchestrator(retriever)
                _engine = (df, retriever, orchestrator)
                _engine_path = active_path
                _engine_mtime = active_mtime
    return _engine


def reload_engine():
    global _engine, _engine_path, _engine_mtime
    with _engine_lock:
        active_path = DATA_PATH
        active_mtime = active_path.stat().st_mtime_ns if active_path.exists() else None
        df = load_incidents(active_path)
        retriever = IncidentRetriever(df)
        orchestrator = IncidentResolutionOrchestrator(retriever)
        _engine = (df, retriever, orchestrator)
        _engine_path = active_path
        _engine_mtime = active_mtime
    return _engine

# --- Request Models ---
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=100)
    role: str = Field(default="user")
    admin_code: Optional[str] = None

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=1, max_length=100)

class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=3000)
    top_k: int = Field(default=TOP_K_DEFAULT, ge=1, le=50)
    filters: dict = Field(default_factory=dict)

class TriageRequest(BaseModel):
    description: str = Field(min_length=2, max_length=3000)

class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=3000)
    incident_id: Optional[str] = None
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)
    accuracy: str = Field(default="Yes")

class CreateIncidentRequest(BaseModel):
    incident_id: str = Field(min_length=2, max_length=50)
    ticket_id: Optional[str] = ""
    description: str = Field(min_length=5, max_length=3000)
    resolution_notes: str = Field(min_length=5, max_length=4000)
    category: str = Field(default="Application")
    priority: str = Field(default="P2")
    impact: str = Field(default="2")
    urgency: str = Field(default="2")
    ci_name: str = Field(default="")
    assigned_to: str = Field(default="SRE Media Squad")
    incident_state: str = Field(default="Resolved")
    kb_status: str = Field(default="Verified")

class UpdateIncidentRequest(BaseModel):
    description: Optional[str] = None
    resolution_notes: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    impact: Optional[str] = None
    urgency: Optional[str] = None
    ci_name: Optional[str] = None
    assigned_to: Optional[str] = None
    incident_state: Optional[str] = None
    kb_status: Optional[str] = None

class EscalateRequest(BaseModel):
    incident_id: str
    current_tier: str = "L1"
    target_tier: str = "L2"
    reason: str
    notes: Optional[str] = ""

class EvaluateRequest(BaseModel):
    custom_cases: Optional[list[dict]] = None

class SettingUpdateRequest(BaseModel):
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_enabled: Optional[bool] = None
    gemini_enabled: Optional[bool] = None
    openai_enabled: Optional[bool] = None

class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=100)
    new_password: str = Field(min_length=8, max_length=100)

class UserRoleRequest(BaseModel):
    role: str

class CreateWorkflowTicketRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(min_length=5, max_length=4000)
    incident_id: Optional[str] = Field(default=None, max_length=50)
    priority: str = "P3"
    new_incident: bool = False

class UpdateWorkflowTicketRequest(BaseModel):
    priority: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = Field(default=None, max_length=6000)
    assigned_to: Optional[str] = None
    current_tier: Optional[str] = None

class EscalateWorkflowTicketRequest(BaseModel):
    target_user: str = Field(min_length=3, max_length=150)
    reason: str = Field(min_length=3, max_length=1200)
    notes: str = Field(default="", max_length=4000)

class TicketReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1500)

# --- Health & Metadata ---
@app.get("/health")
def health():
    try:
        df, _, _ = get_engine()
        return {
            "status": "ok",
            "incident_count": len(df),
            "dataset": str(DATA_PATH),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/metadata")
def metadata():
    df, _, _ = get_engine()
    return {
        "incident_count": len(df),
        "filters": {
            field: sorted([str(x) for x in df[field].dropna().unique() if str(x).strip()])[:200]
            for field in ["priority", "impact", "urgency", "incident_state", "category", "ci_name", "assigned_to"]
            if field in df.columns
        }
    }

# --- Auth Endpoints ---
@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    # Public self-registration never grants administrator privileges.
    return register_user(req.email, req.username, req.password, "l1")

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    return login_user(req.email, req.password)

@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_user)):
    return {"user": user}

@app.post("/api/auth/logout")
def auth_logout(user: dict = Depends(require_user)):
    log_audit("user_logout", f"User logged out: {user.get('email')}", user.get("email"), "info")
    return {"status": "logged_out"}

@app.get("/api/auth/users")
def auth_users(admin: dict = Depends(require_admin)):
    return {"users": list_users()}

@app.put("/api/auth/users/{user_id}")
def auth_update_user(user_id: int, req: UserRoleRequest, admin: dict = Depends(require_admin)):
    role=req.role.lower()
    if role not in ("admin", "l1", "l2", "l3"):
        raise HTTPException(400, "Role must be admin, L1, L2, or L3")
    with get_connection() as con:
        cur = con.execute("UPDATE users SET role=? WHERE id=?", (role, user_id)); con.commit()
        if not cur.rowcount: raise HTTPException(404, "User not found")
    log_audit("user_role_updated", f"User #{user_id} role set to {role}", admin.get("email"), "warning")
    return {"status":"updated"}

@app.post("/api/auth/password")
def auth_change_password(req: PasswordChangeRequest, user: dict = Depends(require_user)):
    if req.current_password == req.new_password:
        raise HTTPException(400, "The new password must be different from the current password.")
    if not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,100}", req.new_password):
        raise HTTPException(400, "New password must be 8 to 100 characters and include uppercase, lowercase, a number, and a special character.")
    if not update_password(user["id"], req.current_password, req.new_password):
        raise HTTPException(400, "Current password is incorrect")
    log_audit("password_changed", "Password changed", user.get("email"), "info")
    return {"status":"updated"}

# --- Core Retrieval & Multi-Agent Resolution ---
@app.post("/search")
@app.post("/api/search")
@app.post("/api/incidents/search")
def search(req: SearchRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    user_email = user.get("email", "anonymous") if user else "anonymous"

    # Input guardrail
    clean_query, guard_report = sanitize_and_guard_input(req.query, user_email)
    if not guard_report.input_safe:
        return {
            "query": req.query,
            "blocked": True,
            "violations": guard_report.violations,
            "count": 0,
            "results": []
        }

    df, engine, _ = get_engine()
    triage = classify(clean_query)
    results = engine.search(clean_query, req.top_k, req.filters)
    
    # Save search history
    response = {
        "query": clean_query,
        "triage": triage,
        "count": len(results),
        "results": results,
        "guardrail": guard_report.to_dict(),
    }
    save_search_history(clean_query, user_email, len(results), triage.get("suggested_priority", "P2"), response)
    log_audit("search_query", f"Query: {clean_query[:80]} | Results: {len(results)}", user_email, "info")
    
    return response

@app.post("/resolve")
@app.post("/api/resolve")
def resolve(req: SearchRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    user_email = user.get("email", "anonymous") if user else "anonymous"

    _, _, orchestrator = get_engine()
    result = orchestrator.process_incident(
        raw_query=req.query,
        top_k=req.top_k,
        filters=req.filters,
        user_email=user_email
    )
    
    # Save search history
    save_search_history(req.query, user_email, len(result.get("retrieved_incidents", [])), result.get("triage", {}).get("suggested_priority", "P2"), result)
    log_audit("resolve_incident", f"Query: {req.query[:80]} | Status: Success", user_email, "info")
    return result

@app.post("/api/resolve/instant-solution")
def instant_solution(req: SearchRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    user_email = user.get("email", "anonymous") if user else "anonymous"
    clean_query, guard_report = sanitize_and_guard_input(req.query, user_email)
    if not guard_report.input_safe:
        raise HTTPException(status_code=400, detail="Question was blocked by input security guardrails.")

    _, retriever, _ = get_engine()
    documents = [
        doc for doc in retriever.search(clean_query, req.top_k, req.filters)
        if float(doc.get("score") or 0) >= 0.08
    ]
    if not documents:
        raise HTTPException(status_code=404, detail="No related incident documents were found to summarize.")
    if any(str(doc.get("resolution_notes", "")).strip() for doc in documents):
        raise HTTPException(status_code=409, detail="A documented resolution is available. Run the search again to view it.")

    try:
        summary = summarize_documents(clean_query, documents)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    answer, output_guard = validate_and_guard_output(summary["answer"], documents, user_email)
    if not output_guard.output_safe:
        raise HTTPException(status_code=422, detail="The generated answer did not pass the safety review.")
    summary["answer"] = answer
    update_latest_search_history(req.query, user_email, {
        "resolution_assistance": summary,
        "has_documented_answer": False,
        "needs_instant_solution": False,
        "instant_solution_generated": True,
    })
    return {"resolution_assistance": summary, "sources": [doc.get("incident_id") for doc in documents]}

@app.post("/api/incidents/triage")
def triage_endpoint(req: TriageRequest):
    return classify(req.description)

@app.post("/api/incidents/escalate")
def escalate_incident(req: EscalateRequest, user: dict = Depends(require_user)):
    user_email = user.get("email", "engineer@incidentiq.io")
    title = f"Incident Escalated: {req.incident_id} → {req.target_tier}"
    msg = f"Escalated from {req.current_tier} to {req.target_tier} by {user_email}. Reason: {req.reason}"
    with get_connection() as con:
        con.execute("INSERT INTO escalations(incident_id,current_tier,target_tier,reason,notes,created_by,created_at) VALUES(?,?,?,?,?,?,?)", (req.incident_id,req.current_tier,req.target_tier,req.reason,req.notes or "",user_email,datetime.now(timezone.utc).isoformat())); con.commit()
    add_notification(title, msg, "escalation", "all")
    add_notification(title, msg, "escalation", user_email)
    log_audit("incident_escalated", msg, user_email, "warning")
    return {
        "status": "escalated",
        "incident_id": req.incident_id,
        "current_tier": req.target_tier,
        "handoff_summary": f"Incident {req.incident_id} successfully handed off to {req.target_tier} specialist team."
    }

# --- L1 / L2 / L3 Support Ticket Workflow ---
def _ticket_visible(ticket: dict, user: dict) -> bool:
    if (user.get("role") == "admin" or ticket.get("created_by") == user.get("email")
            or ticket.get("assigned_to") == user.get("email")
            or (ticket.get("assigned_to") is None and ticket.get("current_tier") == user.get("role"))):
        return True
    with get_connection() as con:
        return bool(con.execute("SELECT 1 FROM ticket_events WHERE ticket_id=? AND recipient_email=? LIMIT 1",(ticket.get("ticket_id"),user.get("email"))).fetchone())

def _ticket_events_visible(ticket: dict, user: dict):
    if user.get("role")=="admin": return ticket.get("events",[])
    return [event for event in ticket.get("events",[]) if event.get("event_type")!="tier_feedback" or user.get("email") in (event.get("actor_email"),event.get("recipient_email"))]

def _ticket_workable(ticket: dict, user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    return (user.get("role") == ticket.get("current_tier")
            and ticket.get("assigned_to") == user.get("email"))

@app.get("/api/agents")
def get_agents(role: Optional[str] = Query(default=None, pattern="^(l1|l2|l3)$"), user: dict = Depends(require_user)):
    return {"agents": list_agents(role)}

@app.get("/api/tickets")
def get_tickets(user: dict = Depends(require_user)):
    tickets=list_workflow_tickets(user)
    for ticket in tickets:
        ticket["events"]=_ticket_events_visible(ticket,user)
        reviews=list_ticket_reviews(ticket["ticket_id"])
        ticket["reviews"]=reviews if user.get("role")=="admin" else [review for review in reviews if user.get("email") in (review.get("reviewer_email"),review.get("recipient_email"))]
        ticket["review_eligibility"]=get_ticket_review_target(ticket["ticket_id"],user)
    return {"tickets": tickets}

@app.post("/api/tickets")
def create_workflow_ticket(req: CreateWorkflowTicketRequest, user: dict = Depends(require_user)):
    role=user.get("role")
    if role not in ("l1", "l2", "l3", "admin"):
        raise HTTPException(403, "Your account is not assigned to a support tier")
    if role == "l3" and not req.new_incident:
        raise HTTPException(403, "L3 specialists cannot open new tickets; they resolve active tickets and add handoff feedback.")
    if len(req.title.strip()) < 3 or len(req.description.strip()) < 5:
        raise HTTPException(400, "Ticket title and symptoms must contain meaningful text")
    priority=req.priority.upper()
    if priority not in ("P1", "P2", "P3", "P4"):
        raise HTTPException(400, "Priority must be P1, P2, P3, or P4")

    ticket_id=f"SUP-{datetime.now(timezone.utc):%y%m%d}-{uuid4().hex[:6].upper()}"
    incident_ref = (req.incident_id or f"NEW-{ticket_id}").strip() or f"NEW-{ticket_id}"
    now=datetime.now(timezone.utc).isoformat()
    admin_email = "admin@incidentiq.io"
    is_new_incident = bool(req.new_incident)
    current_tier = "l1" if role == "admin" else role
    assignee = admin_email if is_new_incident else (None if role == "admin" else user.get("email"))

    with get_connection() as con:
        con.execute(
            "INSERT INTO workflow_tickets(ticket_id,incident_id,title,description,priority,status,resolution,current_tier,assigned_to,created_by,created_at,updated_at) VALUES(?,?,?,?,?,'Open','',?,?,?,?,?)",
            (ticket_id, incident_ref, req.title.strip(), req.description.strip(), priority, current_tier, assignee, user.get("email"), now, now)
        )
        if is_new_incident:
            con.execute(
                """INSERT INTO custom_incidents (
                    incident_id, ticket_id, description, resolution_notes, incident_state, priority, impact, urgency, category, ci_name, assigned_to, kb_status, created_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    ticket_id=excluded.ticket_id,
                    description=excluded.description,
                    resolution_notes=excluded.resolution_notes,
                    incident_state=excluded.incident_state,
                    priority=excluded.priority,
                    impact=excluded.impact,
                    urgency=excluded.urgency,
                    category=excluded.category,
                    ci_name=excluded.ci_name,
                    assigned_to=excluded.assigned_to,
                    kb_status=excluded.kb_status,
                    created_by=excluded.created_by,
                    created_at=excluded.created_at
                """,
                (
                    incident_ref,
                    ticket_id,
                    req.description.strip(),
                    "Ticket created and awaiting admin review.",
                    "New Ticket",
                    priority,
                    "2",
                    "2",
                    "Application",
                    "",
                    admin_email,
                    "New Ticket",
                    now,
                    user.get("email")
                )
            )
        con.commit()

    if is_new_incident:
        add_ticket_event(ticket_id,"created",user.get("email"),f"Ticket created and escalated to admin for review.",recipient_email=admin_email,from_tier=role,to_tier="admin",payload={"incident_id":incident_ref,"priority":priority})
        add_ticket_event(ticket_id,"escalated",user.get("email"),"Ticket escalated to the admin queue.",recipient_email=admin_email,from_tier=role,to_tier="admin",payload={"incident_id":incident_ref,"priority":priority})
        log_audit("support_ticket_created",f"{ticket_id} created by {user.get('email')} and escalated to admin",user.get("email"),"warning")
        add_notification(f"New support ticket {ticket_id}",f"{req.title.strip()} escalated to admin for review.","ticket",admin_email)
    else:
        add_ticket_event(ticket_id,"created",user.get("email"),f"Ticket created at {current_tier.upper()}.",to_tier=current_tier,payload={"incident_id":incident_ref,"priority":priority})
        log_audit("support_ticket_created",f"{ticket_id} created at {current_tier.upper()}",user.get("email"),"info")
        add_notification(f"New support ticket {ticket_id}",req.title,"ticket",user.get("email"))
    return {"ticket":get_workflow_ticket(ticket_id)}

@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str, user: dict = Depends(require_user)):
    ticket=get_workflow_ticket(ticket_id)
    if not ticket: raise HTTPException(404,"Ticket not found")
    if not _ticket_visible(ticket,user): raise HTTPException(403,"This ticket is not assigned to your queue")
    ticket["events"]=_ticket_events_visible(ticket,user)
    reviews=list_ticket_reviews(ticket_id)
    ticket["reviews"]=reviews if user.get("role")=="admin" else [review for review in reviews if user.get("email") in (review.get("reviewer_email"),review.get("recipient_email"))]
    ticket["review_eligibility"]=get_ticket_review_target(ticket_id,user)
    return {"ticket":ticket}

@app.post("/api/tickets/{ticket_id}/reviews")
def submit_ticket_review(ticket_id: str, req: TicketReviewRequest, user: dict = Depends(require_user)):
    ticket=get_workflow_ticket(ticket_id)
    if not ticket: raise HTTPException(404,"Ticket not found")
    if user.get("role") not in ("l2","l3"):
        raise HTTPException(403,"Only L2 and L3 agents can review work from the previous support tier")
    if ticket.get("status") != "Resolved":
        raise HTTPException(409,"Tier feedback becomes available after the ticket is resolved")
    target=get_ticket_review_target(ticket_id,user)
    if not target:
        raise HTTPException(403,"This ticket was not handed to you from the tier you are allowed to review")
    if target["submitted"]:
        raise HTTPException(409,"You have already submitted feedback for this handoff")
    now=datetime.now(timezone.utc).isoformat()
    try:
        with get_connection() as con:
            cur=con.execute("INSERT INTO ticket_reviews(ticket_id,source_event_id,reviewer_email,reviewer_tier,recipient_email,recipient_tier,rating,comment,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(ticket_id,target["source_event_id"],user["email"],target["reviewer_tier"],target["recipient_email"],target["recipient_tier"],req.rating,req.comment.strip(),now))
            review_id=cur.lastrowid
            con.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409,"Feedback for this support handoff was already submitted") from exc
    add_ticket_event(ticket_id,"tier_feedback",user["email"],req.comment.strip() or f"Rated {target['recipient_tier'].upper()} handoff {req.rating}/5",recipient_email=target["recipient_email"],from_tier=user["role"],to_tier=target["recipient_tier"],payload={"rating":req.rating,"review_id":review_id})
    add_notification(f"Ticket feedback received: {ticket_id}",f"{user.get('email')} rated your {target['recipient_tier'].upper()} handoff {req.rating}/5.","feedback",target["recipient_email"])
    log_audit("ticket_tier_feedback_submitted",f"{ticket_id}: {user['role'].upper()} rated {target['recipient_tier'].upper()} {req.rating}/5",user["email"],"info")
    return {"status":"saved","review":next((r for r in list_ticket_reviews(ticket_id) if r["id"]==review_id),None)}

@app.post("/api/tickets/{ticket_id}/claim")
def claim_ticket(ticket_id: str, user: dict = Depends(require_user)):
    ticket=get_workflow_ticket(ticket_id)
    if not ticket: raise HTTPException(404,"Ticket not found")
    if user.get("role") != ticket["current_tier"] or ticket.get("assigned_to") is not None:
        raise HTTPException(409,"Only an unassigned ticket in your tier can be claimed")
    now=datetime.now(timezone.utc).isoformat()
    with get_connection() as con:
        cur=con.execute("UPDATE workflow_tickets SET assigned_to=?,status='In Progress',updated_at=? WHERE ticket_id=? AND assigned_to IS NULL AND current_tier=? AND status!='Resolved'",(user.get("email"),now,ticket_id,user.get("role")));con.commit()
        if not cur.rowcount: raise HTTPException(409,"This ticket was claimed or updated by another agent. Refresh the queue.")
    add_ticket_event(ticket_id,"claimed",user.get("email"),f"Claimed by {user.get('email')}.",from_tier=ticket["current_tier"],to_tier=ticket["current_tier"])
    return {"ticket":get_workflow_ticket(ticket_id)}

@app.put("/api/tickets/{ticket_id}")
def update_workflow_ticket(ticket_id: str, req: UpdateWorkflowTicketRequest, user: dict = Depends(require_user)):
    ticket=get_workflow_ticket(ticket_id)
    if not ticket: raise HTTPException(404,"Ticket not found")
    if not _ticket_workable(ticket,user): raise HTTPException(403,"Claim this ticket or work from its current support tier")
    if (req.assigned_to is not None or req.current_tier is not None) and user.get("role") != "admin": raise HTTPException(403,"Only administrators can reassign tickets")
    tier=req.current_tier.lower() if req.current_tier else ticket["current_tier"]
    if tier not in ("l1","l2","l3"): raise HTTPException(400,"Tier must be L1, L2, or L3")
    priority=req.priority.upper() if req.priority else ticket["priority"]
    status=req.status.title() if req.status else ticket["status"]
    if priority not in ("P1","P2","P3","P4"): raise HTTPException(400,"Priority must be P1, P2, P3, or P4")
    if status not in ("Open","In Progress","Waiting","Resolved"): raise HTTPException(400,"Unsupported ticket status")
    if status == "Resolved" and not (req.resolution or ticket.get("resolution")):
        raise HTTPException(400,"Add resolution notes before resolving this ticket")
    assignee=ticket.get("assigned_to")
    if tier != ticket["current_tier"] and req.assigned_to is None:
        assignee=None
    if req.assigned_to is not None:
        if req.assigned_to:
            with get_connection() as con: target=con.execute("SELECT role FROM users WHERE email=?",(req.assigned_to,)).fetchone()
            if not target or target["role"] != tier: raise HTTPException(400,"Assignee must be an active agent in the ticket's current tier")
        assignee=req.assigned_to or None
    now=datetime.now(timezone.utc).isoformat()
    resolution=req.resolution if req.resolution is not None else ticket.get("resolution","")
    resolved_at=now if status == "Resolved" else None
    with get_connection() as con:
        con.execute("UPDATE workflow_tickets SET priority=?,status=?,resolution=?,assigned_to=?,current_tier=?,updated_at=?,resolved_at=? WHERE ticket_id=?",(priority,status,resolution,assignee,tier,now,resolved_at,ticket_id));con.commit()
    add_ticket_event(ticket_id,"resolved" if status == "Resolved" else "updated",user.get("email"),req.resolution or f"Ticket updated: {status}, {priority}.",from_tier=ticket["current_tier"],to_tier=tier,payload={"status":status,"priority":priority,"resolution":req.resolution})
    log_audit("support_ticket_updated",f"{ticket_id}: {status}, {priority}",user.get("email"),"info")
    return {"ticket":get_workflow_ticket(ticket_id)}

@app.delete("/api/tickets/{ticket_id}")
def delete_workflow_ticket(ticket_id: str, admin: dict = Depends(require_admin)):
    with get_connection() as con:
        cur=con.execute("DELETE FROM workflow_tickets WHERE ticket_id=?",(ticket_id,))
        con.execute("DELETE FROM ticket_events WHERE ticket_id=?",(ticket_id,));con.commit()
    if not cur.rowcount: raise HTTPException(404,"Ticket not found")
    log_audit("support_ticket_deleted",f"{ticket_id} deleted",admin.get("email"),"warning")
    return {"status":"deleted","ticket_id":ticket_id}

@app.post("/api/tickets/{ticket_id}/escalate")
def escalate_workflow_ticket(ticket_id: str, req: EscalateWorkflowTicketRequest, user: dict = Depends(require_user)):
    ticket=get_workflow_ticket(ticket_id)
    if not ticket: raise HTTPException(404,"Ticket not found")
    if ticket["current_tier"] == "l3": raise HTTPException(409,"L3 is the final support tier. Request AI guidance or resolve the ticket.")
    if not _ticket_workable(ticket,user): raise HTTPException(403,"Only the current ticket owner or tier can escalate it")
    target_tier={"l1":"l2","l2":"l3"}[ticket["current_tier"]]
    with get_connection() as con: target=con.execute("SELECT role,username FROM users WHERE email=?",(req.target_user.lower(),)).fetchone()
    if not target or target["role"] != target_tier: raise HTTPException(400,f"Select an active {target_tier.upper()} agent")
    now=datetime.now(timezone.utc).isoformat(); old_tier=ticket["current_tier"]
    with get_connection() as con:
        con.execute("UPDATE workflow_tickets SET current_tier=?,assigned_to=?,status='Open',updated_at=?,resolved_at=NULL WHERE ticket_id=?",(target_tier,req.target_user.lower(),now,ticket_id))
        con.execute("INSERT INTO escalations(incident_id,current_tier,target_tier,reason,notes,created_by,created_at,status) VALUES(?,?,?,?,?,?,?,'Open')",(ticket.get("incident_id") or ticket_id,old_tier.upper(),target_tier.upper(),req.reason,req.notes,user.get("email"),now))
        con.commit()
    payload={"previous_owner":user.get("email"),"target_user":req.target_user.lower(),"ticket_title":ticket["title"],"ticket_description":ticket["description"],"priority":ticket["priority"]}
    add_ticket_event(ticket_id,"escalated",user.get("email"),req.reason,recipient_email=req.target_user.lower(),from_tier=old_tier,to_tier=target_tier,payload={**payload,"notes":req.notes})
    add_notification(f"Ticket handoff: {ticket_id}",f"{ticket['title']} escalated to {target_tier.upper()} by {user.get('email')}: {req.reason}","escalation",req.target_user.lower())
    add_notification(f"Ticket handoff: {ticket_id}",f"You escalated {ticket['title']} to {target['username']} ({target_tier.upper()}).","escalation",user.get("email"))
    log_audit("support_ticket_escalated",f"{ticket_id} {old_tier.upper()} to {target_tier.upper()} assigned to {req.target_user}",user.get("email"),"warning")
    return {"ticket":get_workflow_ticket(ticket_id)}

@app.post("/api/tickets/{ticket_id}/ai-guidance")
def ticket_ai_guidance(ticket_id: str, user: dict = Depends(require_user)):
    ticket=get_workflow_ticket(ticket_id)
    if not ticket: raise HTTPException(404,"Ticket not found")
    if user.get("role") not in ("l3","admin") or not _ticket_visible(ticket,user):
        raise HTTPException(403,"L3 agents handling this ticket can request final-tier AI guidance")
    if ticket.get("status") == "Resolved": raise HTTPException(409,"Ticket is already resolved")
    query=f"{ticket['title']}. {ticket['description']}"
    _,retriever,_=get_engine()
    sources=retriever.search(query,top_k=5)
    response=generate_generalized_resolution(query,sources)
    answer,guard=validate_and_guard_output(response["answer"],sources,user.get("email"))
    if not guard.output_safe: raise HTTPException(422,"Guidance did not pass the output safety check")
    response["answer"]=answer
    add_ticket_event(ticket_id,"ai_guidance",user.get("email"),"L3 requested AI troubleshooting guidance.",from_tier="l3",to_tier="l3",payload={**response,"sources":[r.get("incident_id") for r in sources],"guardrail":guard.to_dict()})
    return {"guidance":response,"sources":sources,"guardrail":guard.to_dict()}

@app.get("/api/incidents/escalations")
def get_escalations(user: dict = Depends(require_user)):
    return {"escalations": list_escalations(None if user.get("role") == "admin" else user.get("email"))}

# --- Evaluation Suite API ---
@app.post("/api/evaluate/run")
@app.post("/api/admin/evaluation/run")
def evaluate_run(req: EvaluateRequest = EvaluateRequest(), admin: dict = Depends(require_admin)):
    _, retriever, _ = get_engine()
    metrics = run_retrieval_evaluation(retriever, req.custom_cases)
    log_audit("evaluation_benchmark_run", f"Evaluated {metrics['total_test_cases']} queries with MRR {metrics['mean_reciprocal_rank_mrr']}", "system", "info")
    return metrics

@app.get("/api/evaluate/benchmark")
@app.get("/api/admin/evaluation")
def evaluate_benchmark(admin: dict = Depends(require_admin)):
    return {"benchmark_cases": BENCHMARK_CASES}

# --- Incident Management & Knowledge Base ---
@app.get("/incidents")
@app.get("/api/incidents")
def list_incidents(
    limit: int = 5000,
    offset: int = 0,
    query: str = "",
    priority: str = "",
    category: str = "",
    state: str = ""
):
    df, retriever, _ = get_engine()
    limit = max(1, min(limit, 5000))
    offset = max(0, offset)
    
    filtered_df = df.copy()
    if priority:
        filtered_df = filtered_df[filtered_df["priority"].astype(str).str.lower() == priority.lower()]
    if category:
        filtered_df = filtered_df[filtered_df["category"].astype(str).str.lower() == category.lower()]
    if state:
        filtered_df = filtered_df[filtered_df["incident_state"].astype(str).str.lower() == state.lower()]

    if query.strip():
        # Hybrid filtered search
        filters = {}
        if priority: filters["priority"] = priority
        if category: filters["category"] = category
        if state: filters["incident_state"] = state
        matches = retriever.search(query, top_k=limit, filters=filters)
        return {"total": len(matches), "limit": limit, "offset": offset, "items": matches}
    
    total = int(len(filtered_df))
    rows = filtered_df.iloc[offset:offset + limit].copy()
    records = []
    for row in rows.to_dict(orient="records"):
        rec = {k: (None if row.get(k) is None or str(row.get(k)) == "nan" else str(row.get(k)))
               for k in row if k != "search_text"}
        # Ensure kb_status is present
        if "kb_status" not in rec or not rec["kb_status"]:
            rec["kb_status"] = "Verified"
        records.append(rec)
    return {"total": total, "limit": limit, "offset": offset, "items": records}

@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str = Path(...)):
    df, _, _ = get_engine()
    matches = df[df["incident_id"].astype(str).str.lower() == incident_id.lower()]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    row = matches.iloc[0].to_dict()
    item = {k: (None if row.get(k) is None or str(row.get(k)) == "nan" else str(row.get(k)))
            for k in row if k != "search_text"}
    return {"incident": item}

@app.get("/api/incidents/similar/{incident_id}")
def get_similar_incidents(incident_id: str = Path(...), top_k: int = 4):
    df, retriever, _ = get_engine()
    matches = df[df["incident_id"].astype(str).str.lower() == incident_id.lower()]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    row = matches.iloc[0]
    search_q = f"{row.get('description', '')} {row.get('category', '')}"
    results = retriever.search(search_q, top_k=top_k + 1)
    # Exclude itself
    filtered = [r for r in results if str(r.get("incident_id")).lower() != incident_id.lower()][:top_k]
    return {"incident_id": incident_id, "similar_incidents": filtered}

@app.post("/api/incidents/create")
def create_incident(req: CreateIncidentRequest, user: dict = Depends(require_user)):
    with get_connection() as con:
        cur = con.cursor()
        now = datetime.now(timezone.utc).isoformat()
        try:
            cur.execute("""INSERT INTO custom_incidents (
                incident_id, ticket_id, description, resolution_notes, incident_state, priority, impact, urgency, category, ci_name, assigned_to, kb_status, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (req.incident_id, req.ticket_id or req.incident_id, req.description, req.resolution_notes, req.incident_state, req.priority, req.impact, req.urgency, req.category, req.ci_name, req.assigned_to, req.kb_status, now, user.get("email")))
            con.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to create incident: {str(e)}")

    # Hot reload memory retriever to instantly make the new ticket searchable
    reload_engine()
    add_notification(f"New Knowledge Entry: {req.incident_id}", f"Created by {user.get('email')} in category {req.category}", "kb", "all")
    log_audit("incident_created", f"Created ticket {req.incident_id} by {user.get('email')}", user.get("email"), "success")
    return {"status": "created", "incident_id": req.incident_id}

@app.put("/api/incidents/{incident_id}")
def update_incident(incident_id: str, req: UpdateIncidentRequest, admin: dict = Depends(require_admin)):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT * FROM custom_incidents WHERE incident_id = ?", (incident_id,))
        exists = cur.fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if exists:
            cur.execute("""UPDATE custom_incidents SET
                description = COALESCE(?, description),
                resolution_notes = COALESCE(?, resolution_notes),
                category = COALESCE(?, category),
                priority = COALESCE(?, priority),
                impact = COALESCE(?, impact),
                urgency = COALESCE(?, urgency),
                ci_name = COALESCE(?, ci_name),
                assigned_to = COALESCE(?, assigned_to),
                incident_state = COALESCE(?, incident_state),
                kb_status = COALESCE(?, kb_status)
                WHERE incident_id = ?""",
                (req.description, req.resolution_notes, req.category, req.priority, req.impact, req.urgency, req.ci_name, req.assigned_to, req.incident_state, req.kb_status, incident_id))
        else:
            # Insert into custom_incidents override
            cur.execute("""INSERT INTO custom_incidents (
                incident_id, ticket_id, description, resolution_notes, incident_state, priority, impact, urgency, category, ci_name, assigned_to, kb_status, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (incident_id, incident_id, req.description or "Updated incident", req.resolution_notes or "Updated resolution", req.incident_state or "Resolved", req.priority or "P2", req.impact or "2", req.urgency or "2", req.category or "Application", req.ci_name or "", req.assigned_to or "SRE Squad", req.kb_status or "Verified", now, admin.get("email")))
        con.commit()

    reload_engine()
    log_audit("incident_updated", f"Incident {incident_id} updated by {admin.get('email')}", admin.get("email"), "info")
    return {"status": "updated", "incident_id": incident_id}

@app.delete("/api/incidents/{incident_id}")
def delete_incident(incident_id: str, admin: dict = Depends(require_admin)):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM custom_incidents WHERE incident_id = ?", (incident_id,))
        con.commit()
    reload_engine()
    log_audit("incident_deleted", f"Incident {incident_id} deleted by {admin.get('email')}", admin.get("email"), "warning")
    return {"status": "deleted", "incident_id": incident_id}

# --- Analytics & Reporting ---
@app.get("/analytics")
@app.get("/api/analytics")
@app.get("/api/admin/analytics")
def analytics(admin: dict = Depends(require_admin)):
    df, _, _ = get_engine()
    def counts(field, limit=20):
        if field not in df.columns:
            return []
        values = df[field].fillna("Unknown").astype(str).replace("", "Unknown").value_counts().head(limit)
        return [{"label": str(label), "count": int(count)} for label, count in values.items()]

    state = df["incident_state"].fillna("").astype(str).str.lower()
    resolved_mask = state.str.contains(r"resolved|closed|complete", regex=True)
    total = int(len(df))
    resolved = int(resolved_mask.sum())
    
    # Priority counts
    p1 = int((df["priority"].astype(str) == "P1").sum())
    p2 = int((df["priority"].astype(str) == "P2").sum())
    p3 = int((df["priority"].astype(str) == "P3").sum())
    p4 = int((df["priority"].astype(str) == "P4").sum())

    return {
        "total_incidents": total,
        "resolved_count": resolved,
        "open_count": total - resolved,
        "critical_count": p1,
        "high_priority_count": p2,
        "resolution_rate": round((resolved / total) * 100, 2) if total else 98.6,
        "average_resolution_time_hrs": 3.4,
        "total_users": 18,
        "by_priority": counts("priority"),
        "by_status": counts("incident_state"),
        "by_category": counts("category"),
        "by_ci_name": counts("ci_name", 10) if "ci_name" in df.columns else []
    }

# --- Feedback Endpoints ---
@app.post("/feedback")
@app.post("/api/feedback")
@app.post("/api/incidents/feedback")
def feedback(req: FeedbackRequest, user: dict = Depends(require_user)):
    user_email = user["email"]
    save_feedback(req.query, req.incident_id, req.rating, req.comment, req.accuracy, user_email)
    log_audit("feedback_submitted", f"Rating: {req.rating} ({req.accuracy}) for ticket: {req.incident_id}", user_email, "info")
    return {"status": "saved"}

@app.get("/feedback/stats")
@app.get("/api/feedback/stats")
@app.get("/api/admin/feedback")
def stats(admin: dict = Depends(require_admin)):
    return feedback_stats()

@app.get("/api/feedback/tier")
def all_tier_feedback(admin: dict = Depends(require_admin)):
    return {"reviews":list_tier_reviews()}

@app.get("/api/feedback/mine")
def my_feedback(user: dict = Depends(require_user)):
    return {"feedback": list_user_feedback(user["email"])}

@app.get("/api/feedback/tier/mine")
def my_tier_feedback(user: dict = Depends(require_user)):
    return {"reviews":list_tier_reviews(user["email"])}

# --- Search History Endpoint ---
@app.get("/api/incidents/history")
@app.get("/api/history")
def search_history_endpoint(user: dict = Depends(require_user)):
    return {"history": get_search_history(user["email"], limit=30)}

# --- Notifications Endpoint ---
@app.get("/api/notifications")
def notifications_endpoint(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    user_email = user.get("email", "all") if user else "all"
    return {"notifications": get_notifications(user_email, limit=20)}

# --- Audit Logs Endpoint ---
@app.get("/api/audit-logs")
def audit_logs(admin: dict = Depends(require_admin)):
    return {"logs": get_audit_logs(60)}

# --- Settings & Provider Configuration ---
@app.post("/api/settings")
def update_settings(req: SettingUpdateRequest, admin: dict = Depends(require_admin)):
    if req.openrouter_api_key is not None:
        os.environ["OPENROUTER_API_KEY"] = req.openrouter_api_key.strip()
    if req.openrouter_model is not None:
        os.environ["OPENROUTER_MODEL"] = req.openrouter_model.strip()
    if req.gemini_api_key is not None:
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if req.openai_api_key is not None:
        os.environ["OPENAI_API_KEY"] = req.openai_api_key.strip()
    with get_connection() as con:
        for key in ("openrouter_enabled", "gemini_enabled", "openai_enabled"):
            value = getattr(req, key)
            if value is not None:
                con.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, "true" if value else "false", datetime.now(timezone.utc).isoformat()))
        con.commit()
    log_audit("settings_updated", "API keys or model configurations updated", admin.get("email"), "info")
    return {"status": "updated"}

@app.get("/api/settings/info")
def get_settings_info(admin: dict = Depends(require_admin)):
    openrouter_key = os.getenv("OPENROUTER_API_KEY", os.getenv("OPENROUTE_API_KEY", ""))
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    with get_connection() as con:
        flags = {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings WHERE key LIKE '%_enabled'").fetchall()}
    return {
        "openrouter_configured": bool(openrouter_key),
        "openrouter_model": os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash:free"),
        "gemini_configured": bool(gemini_key),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "openai_configured": bool(openai_key),
        "openrouter_enabled": flags.get("openrouter_enabled", "true") == "true",
        "gemini_enabled": flags.get("gemini_enabled", "true") == "true",
        "openai_enabled": flags.get("openai_enabled", "true") == "true",
        "guardrails_enabled": True
    }
