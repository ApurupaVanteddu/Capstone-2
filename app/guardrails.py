from __future__ import annotations
import re
from typing import Any
from .store import log_audit

# Sensitive PII Patterns
PATTERNS = {
    "api_key": r"(?:sk-[a-zA-Z0-9]{20,}|key-[a-zA-Z0-9]{16,}|ghp_[a-zA-Z0-9]{36}|AIza[0-9A-Za-z-_]{35})",
    "password": r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\";,]+)['\"]?",
    "ip_address": r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
    "jwt": r"eyJ[a-zA-Z0-9-_]+\.eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+",
}

# Prompt Injection Patterns
INJECTION_TRIGGERS = [
    r"ignore previous instructions",
    r"disregard all previous",
    r"you are now in developer mode",
    r"act as an unfiltered",
    r"override system prompt",
    r"reveal secret",
    r"system prompt leak",
    r"jailbreak",
]

# Dangerous Destructive Command Patterns
DESTRUCTIVE_COMMANDS = [
    r"rm\s+-rf\s+[/~]",
    r"mkfs",
    r"dd\s+if=",
    r":\(\)\{\s*:\|:&\s*\};:", # Fork bomb
    r"drop\s+database",
    r"drop\s+table",
    r"truncate\s+table",
    r"chmod\s+-R\s+777\s+/",
]

class GuardrailReport:
    def __init__(self):
        self.input_safe = True
        self.output_safe = True
        self.pii_redacted = 0
        self.violations: list[str] = []
        self.warnings: list[str] = []
        self.groundedness_score = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_safe": self.input_safe,
            "output_safe": self.output_safe,
            "pii_redacted_count": self.pii_redacted,
            "violations": self.violations,
            "warnings": self.warnings,
            "groundedness_score": round(self.groundedness_score, 2),
            "status": "passed" if (self.input_safe and self.output_safe and not self.violations) else "flagged"
        }

def sanitize_and_guard_input(query: str, user_email: str = "anonymous") -> tuple[str, GuardrailReport]:
    report = GuardrailReport()
    clean_query = query

    # 1. Prompt Injection Detection
    for pattern in INJECTION_TRIGGERS:
        if re.search(pattern, query, re.IGNORECASE):
            report.input_safe = False
            report.violations.append(f"Prompt injection attempt detected: '{pattern}'")
            log_audit("guardrail_injection_block", f"Triggered by: {query[:100]}", user_email, "blocked")

    # 2. PII / Secret Redaction
    for pii_type, pattern in PATTERNS.items():
        matches = list(re.finditer(pattern, clean_query, re.IGNORECASE))
        if matches:
            report.pii_redacted += len(matches)
            report.warnings.append(f"Redacted sensitive {pii_type} pattern(s) from query.")
            clean_query = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", clean_query, flags=re.IGNORECASE)

    # 3. Minimum Quality / Length Guard
    if len(clean_query.strip()) < 3:
        report.input_safe = False
        report.violations.append("Query is too short to process safely.")

    return clean_query, report

def validate_and_guard_output(
    generated_text: str,
    retrieved_incidents: list[dict],
    user_email: str = "anonymous"
) -> tuple[str, GuardrailReport]:
    report = GuardrailReport()
    filtered_text = generated_text

    # 1. Destructive Commands Detection
    for pattern in DESTRUCTIVE_COMMANDS:
        if re.search(pattern, generated_text, re.IGNORECASE):
            report.output_safe = False
            report.violations.append(f"Destructive or unconstrained command prevented: {pattern}")
            log_audit("guardrail_output_destructive_block", f"Prevented pattern: {pattern}", user_email, "blocked")
            filtered_text = re.sub(
                pattern,
                "[BLOCKED: UNSAFE DESTRUCTIVE COMMAND DETECTED BY GUARDRAILS]",
                filtered_text,
                flags=re.IGNORECASE
            )

    # 2. Groundedness & Hallucination Scoring
    if retrieved_incidents:
        kb_text = " ".join([
            f"{inc.get('description', '')} {inc.get('resolution_notes', '')} {inc.get('category', '')}"
            for inc in retrieved_incidents
        ]).lower()
        kb_words = set(re.findall(r"[a-z0-9]{3,}", kb_text))
        gen_words = set(re.findall(r"[a-z0-9]{3,}", generated_text.lower()))

        if gen_words:
            overlap = len(kb_words & gen_words)
            ratio = overlap / min(len(gen_words), 50)
            score = max(0.4, min(1.0, 0.4 + (0.6 * ratio)))
            report.groundedness_score = score
        else:
            report.groundedness_score = 0.5
    else:
        report.groundedness_score = 0.6
        report.warnings.append("No historical records available for ground-truth cross-referencing.")

    return filtered_text, report
