from __future__ import annotations
from typing import Any
import time
from .intelligence import classify, estimate_resolution_hours
from .guardrails import sanitize_and_guard_input, validate_and_guard_output

class AgentStep:
    def __init__(self, name: str, role: str, description: str):
        self.name = name
        self.role = role
        self.description = description
        self.status = "pending"
        self.output: Any = None
        self.execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "status": self.status,
            "output": self.output,
            "execution_time_ms": round(self.execution_time_ms, 2)
        }

class IncidentResolutionOrchestrator:
    """Multi-Agent Incident Intelligence Orchestrator.
    Coordinates specialized agents for end-to-end incident management:
    1. Input Guardrail Agent (PII & Injection screening)
    2. Triage & SLA Agent (Classification, Severity, Priority, Support Tier)
    3. Hybrid Retrieval Agent (Dense semantic + BM25 keyword search)
    4. Root Cause Analysis (RCA) Agent (Failure mode & 5-Whys pattern)
    5. Resolution Synthesis Agent (Action plan & safe remediation)
    6. Output Guardrail & Safety Auditor (Command validation & grounding score)
    7. Tier Escalation & Handoff Agent (L1/L2/L3 packet generation)
    """

    def __init__(self, retriever):
        self.retriever = retriever

    def process_incident(
        self,
        raw_query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        user_email: str = "anonymous"
    ) -> dict[str, Any]:
        workflow_start = time.time()
        agent_steps: list[AgentStep] = []

        # --- STEP 1: Input Guardrail Agent ---
        step1 = AgentStep("Input Guardrail Agent", "Security & Privacy", "Sanitizes query, masks PII, and screens for prompt injections.")
        t0 = time.time()
        sanitized_query, input_guard_report = sanitize_and_guard_input(raw_query, user_email)
        step1.execution_time_ms = (time.time() - t0) * 1000
        step1.output = input_guard_report.to_dict()
        step1.status = "completed" if input_guard_report.input_safe else "flagged"
        agent_steps.append(step1)

        if not input_guard_report.input_safe:
            return {
                "query": raw_query,
                "sanitized_query": sanitized_query,
                "blocked": True,
                "reason": "Query blocked by input security guardrails.",
                "agent_steps": [s.to_dict() for s in agent_steps],
                "guardrail_report": input_guard_report.to_dict()
            }

        # --- STEP 2: Triage & SLA Agent ---
        step2 = AgentStep("Triage & SLA Agent", "Incident Classification", "Predicts category, severity, SLA urgency, and support routing.")
        t0 = time.time()
        triage = classify(sanitized_query)
        # SLA calculation
        sla_hours = {"P1": 1.0, "P2": 4.0, "P3": 12.0, "P4": 24.0}.get(triage.get("suggested_priority", "P3"), 8.0)
        triage["target_sla_hours"] = sla_hours
        triage["squad_assignment"] = {
            "Database": "Data Operations & DBA SRE",
            "Network/VPN": "Core Network & Connectivity Squad",
            "Authentication/Access": "Identity & Access Management (IAM)",
            "Performance": "Platform & Observability Team",
            "Application": "Core Application Support",
            "Hardware": "Workplace IT & Endpoint Services"
        }.get(triage.get("predicted_category", "General"), "General Service Desk")
        step2.execution_time_ms = (time.time() - t0) * 1000
        step2.output = triage
        step2.status = "completed"
        agent_steps.append(step2)

        # --- STEP 3: Hybrid Retrieval Agent ---
        step3 = AgentStep("Hybrid Retrieval Agent", "Knowledge Discovery", "Searches 46k+ historical ITSM tickets and verified KB.")
        t0 = time.time()
        retrieved = [
            item for item in self.retriever.search(sanitized_query, top_k=top_k, filters=filters)
            if float(item.get("score") or 0) >= 0.08
        ]
        step3.execution_time_ms = (time.time() - t0) * 1000
        step3.output = {"count": len(retrieved), "top_matches": [r.get("incident_id") for r in retrieved[:3]]}
        step3.status = "completed"
        agent_steps.append(step3)

        # --- STEP 4: Root Cause Analysis (RCA) Agent ---
        step4 = AgentStep("RCA & Pattern Agent", "Root Cause Analysis", "Extracts recurring failure triggers and contributing components.")
        t0 = time.time()
        rca_patterns = self._analyze_root_cause(sanitized_query, retrieved, triage)
        step4.execution_time_ms = (time.time() - t0) * 1000
        step4.output = rca_patterns
        step4.status = "completed"
        agent_steps.append(step4)

        documented = next((item for item in retrieved if str(item.get("resolution_notes", "")).strip()), None)

        # Use documented runbook text directly. Defer generation until a user asks
        # for an instant solution when the retrieved records contain no solution.
        step5 = AgentStep("Resolution Agent", "Remediation Synthesizer", "Uses documented resolution notes when available; otherwise offers an on-demand grounded summary.")
        t0 = time.time()
        if documented:
            resolution_res = {
                "answer": documented["resolution_notes"],
                "provider": "Knowledge Base",
                "model": "documented_resolution",
                "source_incident_id": documented.get("incident_id"),
            }
        elif retrieved:
            resolution_res = {"answer": "", "provider": "none", "model": "instant_solution_available"}
        else:
            from .llm import generate_generalized_resolution
            general_response = generate_generalized_resolution(sanitized_query, [])
            resolution_res = {
                "answer": general_response.get("answer", ""),
                "provider": general_response.get("provider", "Local generalized fallback"),
                "model": general_response.get("model", "IncidentIQ-L3-Fallback"),
                "note": general_response.get("note"),
            }
        raw_answer = resolution_res.get("answer", "")
        step5.execution_time_ms = (time.time() - t0) * 1000
        step5.output = {"provider": resolution_res.get("provider"), "model": resolution_res.get("model")}
        step5.status = "completed"
        agent_steps.append(step5)

        # --- STEP 6: Output Guardrail & Safety Auditor ---
        step6 = AgentStep("Safety Auditor Agent", "Guardrails & Compliance", "Scans generated resolution for destructive commands and verifies grounding.")
        t0 = time.time()
        guarded_answer, output_guard_report = validate_and_guard_output(raw_answer, retrieved, user_email)
        resolution_res["answer"] = guarded_answer
        step6.execution_time_ms = (time.time() - t0) * 1000
        step6.output = output_guard_report.to_dict()
        step6.status = "completed" if output_guard_report.output_safe else "flagged"
        agent_steps.append(step6)

        # --- STEP 7: Escalation & Handoff Agent ---
        step7 = AgentStep("Escalation & Handoff Agent", "Operations Coordination", "Builds handoff packets and next-tier escalation criteria.")
        t0 = time.time()
        handoff_packet = self._build_handoff_packet(sanitized_query, triage, retrieved, rca_patterns)
        step7.execution_time_ms = (time.time() - t0) * 1000
        step7.output = handoff_packet
        step7.status = "completed"
        agent_steps.append(step7)

        # Time estimation
        time_est = estimate_resolution_hours(retrieved)
        total_latency_ms = (time.time() - workflow_start) * 1000

        return {
            "query": raw_query,
            "sanitized_query": sanitized_query,
            "triage": triage,
            "retrieved_incidents": retrieved,
            "resolution_assistance": resolution_res,
            "has_documented_answer": documented is not None,
            "needs_instant_solution": bool(retrieved) and documented is None,
            "resolution_time": time_est,
            "rca": rca_patterns,
            "handoff": handoff_packet,
            "guardrail_report": {
                "input": input_guard_report.to_dict(),
                "output": output_guard_report.to_dict()
            },
            "agent_steps": [s.to_dict() for s in agent_steps],
            "workflow_latency_ms": round(total_latency_ms, 2)
        }

    def _analyze_root_cause(self, query: str, incidents: list[dict], triage: dict) -> dict[str, Any]:
        cat = triage.get("predicted_category", "General")
        hypotheses = []
        if cat == "Database":
            hypotheses = ["Connection pool starvation", "Unindexed heavy query table scan", "Transaction lock deadlock"]
        elif cat == "Network/VPN":
            hypotheses = ["DNS resolution stale cache", "VPN client certificate expiration", "Gateway route firewall packet drop"]
        elif cat == "Authentication/Access":
            hypotheses = ["MFA session token invalidation", "Active Directory sync lag", "Service account secret rotation mismatch"]
        elif cat == "Performance":
            hypotheses = ["Memory leak accumulating in heap", "CPU throttling on host worker", "Upstream API dependency timeout"]
        else:
            hypotheses = ["Configuration drift post-deployment", "Uncaught runtime exception in worker service", "Dependency availability degradation"]

        return {
            "primary_hypothesis": hypotheses[0],
            "differential_diagnoses": hypotheses[1:],
            "affected_subsystems": [inc.get("ci_name") for inc in incidents if inc.get("ci_name")][:4] or ["Core Infrastructure"],
            "historical_frequency": f"Found in {len(incidents)} similar records"
        }

    def _build_handoff_packet(self, query: str, triage: dict, incidents: list[dict], rca: dict) -> dict[str, Any]:
        tier = triage.get("suggested_support_tier", "L1")
        next_tier = "L2 Specialist" if tier == "L1" else "L3 Core Engineering"
        return {
            "recommended_next_tier": next_tier,
            "target_squad": triage.get("squad_assignment", "Service Desk"),
            "escalation_sla_window": f"{triage.get('target_sla_hours', 4)}h",
            "handoff_summary": f"Incident in {triage.get('predicted_category')} triage. Suspected {rca.get('primary_hypothesis')}.",
            "required_diagnostic_attachments": ["Application stdout/stderr log snippets", "Host resource telemetry (CPU/RAM/IOPS)", "Active connection pool metrics"]
        }
