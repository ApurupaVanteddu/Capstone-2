from __future__ import annotations
import re
from typing import Any

CATEGORY_RULES = {
    "Storage": ["storage", "disk", "disk space", "volume", "archive", "capacity", "upload failure", "full"],
    "Security": ["security", "unauthorized", "access attempt", "failed login", "authentication", "permission", "mfa", "threat"],
    "Database": ["database", "sql", "query", "deadlock", "connection pool", "db", "indexing", "query timeout"],
    "Performance": ["slow", "latency", "high cpu", "memory", "performance", "cpu", "bottleneck", "consumption"],
    "Network": ["network", "buffering", "streaming", "packet", "bandwidth", "interface", "connectivity", "vpn", "delivery"],
    "Application": ["application", "app", "crash", "encoding", "encoder", "codec", "conversion", "exception", "error", "service"],
    "Hardware": ["hardware", "device", "server", "disk failure", "component", "power"],
}

def classify(text: str) -> dict[str, Any]:
    t = (text or "").lower()
    counts = {cat: sum(1 for kw in kws if kw in t) for cat, kws in CATEGORY_RULES.items()}
    category = max(counts, key=counts.get) if max(counts.values(), default=0) else "General"
    severity_terms = {
        "critical": ["production down", "all users", "outage", "complete outage", "critical"],
        "high": ["many users", "business critical", "system down", "major", "unresponsive"],
        "medium": ["intermittent", "slow", "timeout", "degraded", "unable"],
        "low": ["single user", "minor", "question", "how to"],
    }
    severity = "medium"
    for level in ["critical", "high", "medium", "low"]:
        if any(term in t for term in severity_terms[level]):
            severity = level
            break
    priority = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}[severity]
    if severity == "critical":
        tier = "L3"
    elif severity == "high":
        tier = "L2"
    else:
        tier = "L1"
    return {"predicted_category": category, "suggested_severity": severity, "suggested_priority": priority, "suggested_support_tier": tier}

def estimate_resolution_hours(incidents: list[dict]) -> dict[str, Any]:
    # Estimate only from observed timestamp pairs; do not invent an estimate if unavailable.
    import pandas as pd
    durations = []
    for row in incidents:
        created, resolved = row.get("created_at"), row.get("resolved_at")
        try:
            a, b = pd.to_datetime(created), pd.to_datetime(resolved)
            hours = (b - a).total_seconds() / 3600
            if 0 <= hours <= 24 * 365:
                durations.append(hours)
        except Exception:
            pass
    if not durations:
        return {"resolution_time_estimate_hours": None, "resolution_time_note": "Not enough valid timestamp pairs in retrieved incidents."}
    return {"resolution_time_estimate_hours": round(float(sorted(durations)[len(durations)//2]), 2),
            "resolution_time_note": "Median duration among retrieved incidents with valid created/resolved timestamps; not a guarantee."}
