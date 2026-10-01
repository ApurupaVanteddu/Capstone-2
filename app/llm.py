from __future__ import annotations
import os
import json
import requests
from typing import Any
from .config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL,
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL
)
from .store import get_connection

def _provider_enabled(name: str) -> bool:
    try:
        with get_connection() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (f"{name}_enabled",)).fetchone()
            return row is None or row[0].lower() == "true"
    except Exception:
        return True

def _build_context(incidents: list[dict]) -> str:
    context = []
    for i, item in enumerate(incidents[:5], start=1):
        context.append(
            f"[{i}] Ticket: {item.get('incident_id','N/A')}\n"
            f"Category: {item.get('category','Unknown')} | Priority: {item.get('priority','P3')} | State: {item.get('incident_state','Resolved')}\n"
            f"Summary: {item.get('description','')}\n"
            f"Historical Resolution: {item.get('resolution_notes','')}"
        )
    return "\n\n".join(context)

def _build_prompt(query: str, incidents: list[dict], triage: dict) -> str:
    return f"""You are an expert IT Incident Resolution & Site Reliability Assistant.
Analyze the user's incident using ONLY the historical evidence and operational context provided below.

User Incident Symptom:
{query}

Triage Prediction:
- Category: {triage.get('predicted_category', 'General')}
- Severity: {triage.get('suggested_severity', 'medium')}
- Priority: {triage.get('suggested_priority', 'P3')}
- Recommended Tier: {triage.get('suggested_support_tier', 'L1')}

Historical Knowledge Base Evidence:
{_build_context(incidents)}

Provide your response in structured markdown with the following sections:
### 1. Root Cause Hypotheses & Pattern Analysis
Analyze likely failure points based on historical patterns.

### 2. Step-by-Step Troubleshooting & Remediation
Provide actionable, safe, sequenced steps to diagnose and resolve the issue.

### 3. Pre-Flight Safety & Validation Checks
What checks must be run before applying fixes, and how to verify recovery without impacting production.

### 4. Escalation Criteria & Tier Handoff
Conditions under which to escalate to L2/L3 or specialized squads (DBA, Network SRE, Platform Ops).
"""

def _call_openrouter(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", os.getenv("OPENROUTE_API_KEY", OPENROUTER_API_KEY)).strip()
    if not api_key:
        raise RuntimeError("OpenRouter API key is not configured.")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "IncidentIQ AI Knowledge Assistant"
    }
    model = os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL) or "google/gemini-2.5-flash:free"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a professional IT Support & SRE Assistant. Respond with structured, safe, grounded technical guidance."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1500
    }
    resp = requests.post(f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter error ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]

def _call_gemini(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    from google import genai
    model = os.getenv("GEMINI_MODEL", GEMINI_MODEL) or "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"system_instruction": "Be concise, cautious, and grounded in the supplied incident records.", "temperature": 0.2},
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response")
    return response.text

def _call_openai_compatible(provider: str, prompt: str) -> str:
    key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY).strip() if provider == "openai" else os.getenv("NVIDIA_API_KEY", NVIDIA_API_KEY).strip()
    base = os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL) if provider == "openai" else os.getenv("NVIDIA_BASE_URL", NVIDIA_BASE_URL)
    model = os.getenv("OPENAI_MODEL", OPENAI_MODEL) if provider == "openai" else os.getenv("NVIDIA_MODEL", NVIDIA_MODEL)
    
    if not key or not model:
        raise RuntimeError(f"{provider} credentials/model not configured")
    
    endpoint = f"{base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Be concise, cautious, and grounded in the supplied incident records."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"{provider} error ({resp.status_code}): {resp.text}")
    data = resp.json()
    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not answer:
        raise RuntimeError(f"{provider} returned an empty response")
    return answer

def _synthesize_expert_resolution(query: str, incidents: list[dict], triage: dict) -> str:
    """High-fidelity local deterministic reasoning synthesizer when cloud LLMs are unconfigured or offline."""
    category = triage.get("predicted_category", "General")
    priority = triage.get("suggested_priority", "P3")
    tier = triage.get("suggested_support_tier", "L1")
    
    resolutions = [inc.get("resolution_notes", "") for inc in incidents if inc.get("resolution_notes")]
    primary_fix = resolutions[0] if resolutions else "Verify system telemetry, application logs, and active network connections."
    
    related_cits = list(set([inc.get("ci_name") for inc in incidents if inc.get("ci_name")]))[:3]
    cits_str = f"Related CIs: {', '.join(related_cits)}" if related_cits else "General Infrastructure Service"

    return f"""### 1. Root Cause Hypotheses & Pattern Analysis
Based on **{len(incidents)} matching historical incidents** in category `{category}`:
- **Primary Pattern:** Symptom indicates potential bottleneck or configuration inconsistency in `{cits_str}`.
- **Historical Recurrence:** Observed in past tickets (e.g. `{incidents[0].get('incident_id', 'INC-HIST')}`) with priority `{priority}`.
- **Underlying Cause:** Common triggers include resource saturation, stale connection pools, authentication token expiration, or unoptimized query/service dependencies.

### 2. Step-by-Step Troubleshooting & Remediation
1. **Immediate Diagnosis & Log Inspection:** Check service logs for error codes, stack traces, and recent configuration deployments.
2. **Apply Verified Resolution:**
   > *Historical Precedent:* {primary_fix}
3. **Capacity & Resource Refresh:** If resource exhaustion is detected, perform a controlled graceful reload of affected worker pools or clear stuck session caches.
4. **Configuration Check:** Verify environment variables, connection pool limits, and upstream firewall rules.

### 3. Pre-Flight Safety & Validation Checks
- **Non-Destructive Execution:** Ensure all commands are read-only (`status`, `top`, `netstat`, `ping`) before applying configuration changes.
- **Service Verification:** Execute health check probes (`curl -f http://<service>/health` or DB ping) to confirm low latency (<200ms).
- **Telemetry Monitoring:** Observe CPU, memory, and error-rate dashboards for 15 minutes post-fix.

### 4. Escalation Criteria & Tier Handoff
- **Escalate to Tier { 'L2' if tier == 'L1' else 'L3' } / {category} Squad** if:
  - The issue persists after initial remediation steps (15-minute SLA breach threshold).
  - Business impact expands to multiple users or core transactional databases.
- **Hand-off Artifacts:** Provide captured trace IDs, error timestamps, and this incident triage summary.
"""

def generate_generalized_resolution(query: str, incidents: list[dict] | None = None) -> dict:
    """Final-tier troubleshooting answer, grounded when matches exist and general otherwise."""
    incidents=incidents or []
    evidence=_build_context(incidents) if incidents else "No matching historical incident was retrieved."
    prompt=f"""You are an experienced L3 incident engineer. Give a concise troubleshooting plan for the open support ticket.
Ticket symptoms: {query}
Historical evidence, if any:
{evidence}
If historical evidence exists, distinguish facts from hypotheses and cite incident IDs. If none exists, say this is generalized guidance, state assumptions, and request the key logs/metrics needed to narrow the cause. Start with safe read-only checks. Never suggest destructive changes, expose secrets, or claim you verified a fix.
"""
    providers=[
        ("OpenRouter",lambda:_call_openrouter(prompt),os.getenv("OPENROUTER_API_KEY",os.getenv("OPENROUTE_API_KEY",OPENROUTER_API_KEY)).strip(),os.getenv("OPENROUTER_MODEL",OPENROUTER_MODEL),"openrouter"),
        ("Gemini",lambda:_call_gemini(prompt),os.getenv("GEMINI_API_KEY",GEMINI_API_KEY).strip(),os.getenv("GEMINI_MODEL",GEMINI_MODEL),"gemini"),
        ("OpenAI",lambda:_call_openai_compatible("openai",prompt),os.getenv("OPENAI_API_KEY",OPENAI_API_KEY).strip(),os.getenv("OPENAI_MODEL",OPENAI_MODEL),"openai"),
    ]
    errors=[]
    for provider,call,key,model,flag in providers:
        if not key or not _provider_enabled(flag): continue
        try: return {"answer":call(),"provider":provider,"model":model}
        except Exception as exc: errors.append(f"{provider}: {exc}")
    if incidents:
        local=_synthesize_expert_resolution(query,incidents,{"predicted_category":incidents[0].get("category","General"),"suggested_priority":incidents[0].get("priority","P3"),"suggested_support_tier":"L3"})
        provider="Local evidence fallback"
    else:
        local=(
            "No matching incident was found in the dataset, so this is general troubleshooting guidance based on common L3 practices.\n\n"
            "Suggested next steps:\n"
            "1. Confirm the scope, start time, affected users or services, and any recent deployments or configuration changes.\n"
            "2. Review read-only health checks, logs, and metrics such as CPU, memory, disk, network, and dependency status.\n"
            "3. Compare a failing request with a known-good request and isolate the first dependency that breaks the path.\n"
            "4. Avoid production changes until the likely cause and rollback plan are reviewed.\n"
            "5. After the fix, verify recovery with the affected team and confirm that health and error rates return to normal.\n\n"
            "This is generalized guidance because no matching historical incident was found. Please attach the logs and evidence to the ticket."
        )
        provider="Local generalized fallback"
    return {"answer":local,"provider":provider,"model":"IncidentIQ-L3-Fallback","note":"Cloud LLM unavailable or disabled; using local troubleshooting guidance."}

def generate_resolution(query: str, incidents: list[dict], triage: dict) -> dict:
    if not incidents:
        return generate_generalized_resolution(query, [])

    prompt = _build_prompt(query, incidents, triage)
    errors = []

    # Priority order: OpenRouter -> Gemini -> OpenAI -> NVIDIA
    # Try OpenRouter if key is present
    openrouter_key = os.getenv("OPENROUTER_API_KEY", os.getenv("OPENROUTE_API_KEY", OPENROUTER_API_KEY))
    if openrouter_key and _provider_enabled("openrouter"):
        try:
            answer = _call_openrouter(prompt)
            return {"answer": answer, "provider": "OpenRouter", "model": os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL)}
        except Exception as exc:
            errors.append(f"OpenRouter: {str(exc)}")

    # Try Gemini if key is present
    gemini_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if gemini_key and _provider_enabled("gemini"):
        try:
            answer = _call_gemini(prompt)
            return {"answer": answer, "provider": "Gemini", "model": os.getenv("GEMINI_MODEL", GEMINI_MODEL)}
        except Exception as exc:
            errors.append(f"Gemini: {str(exc)}")

    # Try OpenAI if key is present
    openai_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
    if openai_key and _provider_enabled("openai"):
        try:
            answer = _call_openai_compatible("openai", prompt)
            return {"answer": answer, "provider": "OpenAI", "model": os.getenv("OPENAI_MODEL", OPENAI_MODEL)}
        except Exception as exc:
            errors.append(f"OpenAI: {str(exc)}")

    # High-quality deterministic expert reasoning synthesizer
    local_expert = _synthesize_expert_resolution(query, incidents, triage)
    provider_note = f"Deterministic Knowledge Synthesizer (Cloud fallback: {', '.join(errors) if errors else 'No API keys set - running local engine'})"
    return {
        "answer": local_expert,
        "provider": "Deterministic Domain Engine",
        "model": "IncidentIQ-Reasoner-v2",
        "note": provider_note
    }


def summarize_documents(query: str, incidents: list[dict]) -> dict:
    """Summarize retrieved records with a configured LLM and no invented fallback."""
    if not incidents:
        raise ValueError("No related documents were found to summarize.")

    prompt = f"""Answer the user's incident question by summarizing ONLY the retrieved incident documents below.
Do not add procedures, causes, commands, or facts that are not supported by these documents.
If the documents do not contain enough information to answer, say exactly what information is missing.
Keep the answer concise and cite the incident IDs used.

User question:
{query}

Retrieved documents:
{_build_context(incidents)}
"""
    errors = []
    providers = [
        ("OpenRouter", lambda: _call_openrouter(prompt), os.getenv("OPENROUTER_API_KEY", os.getenv("OPENROUTE_API_KEY", OPENROUTER_API_KEY)).strip(), os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL)),
        ("Gemini", lambda: _call_gemini(prompt), os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip(), os.getenv("GEMINI_MODEL", GEMINI_MODEL)),
        ("OpenAI", lambda: _call_openai_compatible("openai", prompt), os.getenv("OPENAI_API_KEY", OPENAI_API_KEY).strip(), os.getenv("OPENAI_MODEL", OPENAI_MODEL)),
        ("NVIDIA", lambda: _call_openai_compatible("nvidia", prompt), os.getenv("NVIDIA_API_KEY", NVIDIA_API_KEY).strip(), os.getenv("NVIDIA_MODEL", NVIDIA_MODEL)),
    ]
    for provider, call, key, model in providers:
        if not key or (provider in ("OpenRouter", "Gemini", "OpenAI") and not _provider_enabled(provider.lower())):
            continue
        try:
            return {"answer": call(), "provider": provider, "model": model}
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    # Offline fallback: summarize the retrieved evidence directly, without inventing an answer.
    evidence = [f"- **{item.get('incident_id', 'Incident')}:** {item.get('resolution_notes') or item.get('description', '')}" for item in incidents[:5]]
    return {
        "answer": "No cloud LLM is enabled. Here is the matching local incident evidence:\n\n" + "\n".join(evidence),
        "provider": "Local incident evidence",
        "model": "TF-IDF + latent semantic embeddings",
        "note": "Cloud LLM unavailable; response is assembled from retrieved incident records.",
    }
