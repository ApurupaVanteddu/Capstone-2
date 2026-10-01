from __future__ import annotations
import time
import json
from pathlib import Path
from typing import Any
import pandas as pd
from .retrieval import IncidentRetriever

BENCHMARK_CASES = [
    {
        "id": "TC-01",
        "category": "Storage",
        "query": "Disk Space Alert - Storage exceeded threshold causing upload failures",
        "expected_category": "Storage",
        "expected_priority": "P2",
        "relevant_ids": ["INC-5001", "INC-5008", "INC-5015", "INC-5022"]
    },
    {
        "id": "TC-02",
        "category": "Application",
        "query": "Slow Delivery - Media loading slowly due to cache miss and CDN latency",
        "expected_category": "Application",
        "expected_priority": "P3",
        # INC-5100 repeats the same symptom and verified fix as INC-5002.
        "relevant_ids": ["INC-5002", "INC-5009", "INC-5016", "INC-5023", "INC-5100"]
    },
    {
        "id": "TC-03",
        "category": "Security",
        "query": "Encoding Crash - Encoder crashed during media conversion and codec processing",
        "expected_category": "Security",
        "expected_priority": "P1",
        # INC-5101 is an exact symptom/resolution duplicate of INC-5003.
        "relevant_ids": ["INC-5003", "INC-5010", "INC-5017", "INC-5024", "INC-5101"]
    },
    {
        "id": "TC-04",
        "category": "Performance",
        "query": "Unauthorized Access Attempt - Multiple failed login attempts detected on media server",
        "expected_category": "Performance",
        "expected_priority": "P2",
        # INC-5102 is an exact symptom/resolution duplicate of INC-5004.
        "relevant_ids": ["INC-5004", "INC-5011", "INC-5018", "INC-5025", "INC-5102"]
    },
    {
        "id": "TC-05",
        "category": "Database",
        "query": "High CPU Usage - Processing service consuming excessive CPU resources",
        "expected_category": "Database",
        "expected_priority": "P2",
        # INC-5103 is an exact symptom/resolution duplicate of INC-5005.
        "relevant_ids": ["INC-5005", "INC-5012", "INC-5019", "INC-5026", "INC-5103"]
    },
    {
        "id": "TC-06",
        "category": "Hardware",
        "query": "Database Timeout - Database queries timing out during media catalog indexing",
        "expected_category": "Hardware",
        "expected_priority": "P3",
        "relevant_ids": ["INC-5006", "INC-5013", "INC-5020", "INC-5027"]
    },
    {
        "id": "TC-07",
        "category": "Network",
        "query": "Streaming Failure - Users experiencing frequent buffering during video playback",
        "expected_category": "Network",
        "expected_priority": "P3",
        "relevant_ids": ["INC-5007", "INC-5014", "INC-5021", "INC-5028"]
    }
]

def run_retrieval_evaluation(retriever: IncidentRetriever, cases: list[dict] | None = None) -> dict[str, Any]:
    cases_to_run = cases or BENCHMARK_CASES
    start_time = time.time()

    hit1 = 0
    hit3 = 0
    hit5 = 0
    reciprocal_ranks = []
    ap_scores = []
    latencies = []
    detailed_results = []

    for case in cases_to_run:
        q = case["query"]
        t0 = time.time()
        results = retriever.search(q, top_k=5)
        latency = (time.time() - t0) * 1000
        latencies.append(latency)

        retrieved_ids = [str(r.get("incident_id")) for r in results]
        relevant_set = set(case.get("relevant_ids", []))

        # Check hits
        ranks = [i + 1 for i, rid in enumerate(retrieved_ids) if rid in relevant_set]

        is_hit1 = bool(ranks and ranks[0] == 1)
        is_hit3 = bool(ranks and ranks[0] <= 3)
        is_hit5 = bool(ranks and ranks[0] <= 5)

        if is_hit1:
            hit1 += 1
        if is_hit3:
            hit3 += 1
        if is_hit5:
            hit5 += 1

        rr = (1.0 / ranks[0]) if ranks else 0.0
        reciprocal_ranks.append(rr)

        # Average Precision for this query
        if relevant_set:
            precisions = []
            rel_count = 0
            for idx, rid in enumerate(retrieved_ids, start=1):
                if rid in relevant_set:
                    rel_count += 1
                    precisions.append(rel_count / idx)
            ap = (sum(precisions) / len(relevant_set)) if precisions else 0.0
        else:
            ap = 1.0
        ap_scores.append(ap)

        detailed_results.append({
            "id": case.get("id", "Custom"),
            "query": q,
            "category": case.get("category", "General"),
            "expected_ids": list(relevant_set),
            "retrieved_top5": retrieved_ids,
            "hit_rank_1": is_hit1,
            "hit_top_3": is_hit3,
            "reciprocal_rank": round(rr, 3),
            "latency_ms": round(latency, 2),
            "top_match_details": results[0] if results else None
        })

    n = max(1, len(cases_to_run))
    mrr = sum(reciprocal_ranks) / n
    map_score = sum(ap_scores) / n
    avg_latency = sum(latencies) / n
    total_time = (time.time() - start_time) * 1000

    metrics = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_test_cases": n,
        "precision_at_1": round(hit1 / n, 4),
        "hit_rate_at_3": round(hit3 / n, 4),
        "hit_rate_at_5": round(hit5 / n, 4),
        "mean_reciprocal_rank_mrr": round(mrr, 4),
        "mean_average_precision_map": round(map_score, 4),
        "average_query_latency_ms": round(avg_latency, 2),
        "total_evaluation_time_ms": round(total_time, 2),
        "evaluation_grade": "EXCELLENT" if mrr >= 0.85 else "GOOD" if mrr >= 0.7 else "FAIR",
        "detailed_cases": detailed_results
    }
    return metrics
