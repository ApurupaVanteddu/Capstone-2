"""Expand the incident CSV to 2,500 rows with clearly identified synthetic examples."""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "incidents.csv"
TARGET_ROWS = 2500

INCIDENT_PATTERNS = {
    "Storage": {
        "titles": ["Storage Capacity Alert", "Upload Volume Exhaustion", "Media Archive Growth", "Filesystem Utilization Warning", "Object Store Quota Alert", "Temporary Disk Pressure", "Snapshot Retention Capacity", "Inode Utilization Alert"],
        "symptoms": [
            "media uploads fail after the shared volume reaches its capacity threshold",
            "the transcoding queue cannot write temporary files because the workspace is full",
            "archive growth is consuming the retention volume faster than expected",
            "filesystem usage rises sharply after scheduled media imports",
            "object uploads return quota errors while the bucket approaches its limit",
            "temporary render files are filling the local scratch disk",
            "snapshot retention jobs stop when the backup volume runs out of space",
            "new files cannot be created although reported disk capacity appears available",
        ],
        "causes": ["stale temporary artifacts", "an undersized data volume", "an unexpectedly large ingest batch", "retention policy drift", "duplicate media archives", "inode exhaustion", "unbounded application logs", "a delayed cleanup job"],
        "solutions": ["Remove confirmed obsolete temporary files, verify retention requirements, and increase the affected volume if sustained capacity requires it.", "Review the largest directories and archive only approved inactive media before expanding the storage volume.", "Restore the scheduled cleanup task, confirm its output, and monitor volume utilization through the next ingest cycle.", "Adjust the media retention policy with the content owner and verify that the backup copy is intact before removing old versions.", "Increase the object-store quota through the approved change process and check that upload retries complete successfully.", "Free space by rotating eligible application logs, then confirm the service can create and remove a test file.", "Check inode usage and identify the file-producing process; clean up only files confirmed safe to remove.", "Move approved cold media to the archive tier and validate retrieval before changing the active storage allocation."],
        "team": "Storage SRE",
    },
    "Application": {
        "titles": ["Media Delivery Latency", "CDN Cache Miss Spike", "Playback Service Error", "Upload API Slow Response", "Media Transform Failure", "Session Service Degradation", "Thumbnail Generation Delay", "Application Pool Saturation"],
        "symptoms": [
            "media pages load slowly while edge requests repeatedly miss the CDN cache",
            "the upload API returns intermittent timeouts during large file transfers",
            "playback requests fail after a recent application configuration change",
            "thumbnail generation falls behind the incoming media processing queue",
            "the media service returns elevated server errors for a subset of users",
            "user sessions expire during long-running media uploads",
            "delivery latency increases after a new compression profile is enabled",
            "application workers stop accepting requests during peak publishing hours",
        ],
        "causes": ["an expired cache entry", "a recent configuration rollout", "a saturated worker pool", "an incompatible media profile", "an upstream API slowdown", "an oversized upload request", "a session timeout mismatch", "a stalled background job"],
        "solutions": ["Purge the affected CDN path, confirm the origin response is healthy, and verify that subsequent requests are served from cache.", "Compare the active configuration with the last known good version and roll back only the implicated setting through change control.", "Inspect worker utilization and queue depth, then scale the service pool using the approved deployment procedure.", "Validate the compression profile against a representative media sample and restore the previous profile if output checks fail.", "Review upstream request traces and retry rates, then confirm the dependency has recovered before increasing client retries.", "Check upload size limits and session lifetime settings together, then test a controlled upload from an affected client.", "Restart the failed background worker after capturing its logs, and verify that queued jobs complete without duplication.", "Refresh the relevant CDN cache after validating the origin content and confirm delivery latency returns to baseline."],
        "team": "Application SRE",
    },
    "Security": {
        "titles": ["Suspicious Login Attempts", "Encoder Process Crash", "Service Account Authentication Failure", "Unexpected Privilege Change", "MFA Challenge Failure", "Certificate Validation Error", "Repeated API Token Rejection", "Security Agent Alert"],
        "symptoms": [
            "multiple failed sign-in attempts target media administration accounts from unfamiliar addresses",
            "the encoder process exits unexpectedly while loading a media codec",
            "a service account can no longer authenticate after a credential rotation",
            "an account receives access denied errors after a role assignment change",
            "users cannot complete multifactor challenges for the publishing console",
            "the media gateway rejects a certificate chain during service authentication",
            "API requests fail because the service token is repeatedly rejected",
            "endpoint security reports an unsigned binary in the media processing directory",
        ],
        "causes": ["a stale service credential", "an unsupported codec library", "a certificate chain mismatch", "an incorrect role mapping", "a blocked authentication callback", "a token rotation mismatch", "an untrusted binary update", "a source address triggering access policy"],
        "solutions": ["Review the authentication audit trail, block confirmed malicious sources, and require MFA for affected privileged accounts.", "Capture the encoder crash details, verify the codec package signature, and restore the approved library version if integrity checks fail.", "Rotate the service credential through the secret manager and verify access using the least-privileged service identity.", "Compare the assigned role with the approved access request and restore the authorized role mapping.", "Validate the certificate chain and expiry on both endpoints, then renew it through the approved certificate process if needed.", "Reissue the API token from the authorized identity provider and confirm the consuming service has loaded the new secret.", "Isolate the affected host if the binary is untrusted, preserve the security logs, and follow the incident response procedure.", "Inspect sign-in events and conditional access results, then unblock only verified users after confirming their identity."],
        "team": "Security Operations",
    },
    "Performance": {
        "titles": ["Worker CPU Saturation", "Memory Pressure Warning", "Media Processing Backlog", "Elevated Request Latency", "Cache Eviction Spike", "Thread Pool Exhaustion", "High I/O Wait", "Service Throughput Drop"],
        "symptoms": [
            "processing workers sustain high CPU usage and media jobs complete more slowly",
            "memory pressure triggers repeated garbage collection in the streaming service",
            "the media processing backlog grows faster than workers can drain it",
            "request latency rises sharply during concurrent playback sessions",
            "frequent cache evictions increase origin traffic and slow page delivery",
            "application threads remain busy and new requests queue until timeout",
            "storage I/O wait increases while media previews are generated",
            "service throughput drops after traffic shifts to a smaller worker group",
        ],
        "causes": ["a resource-heavy processing profile", "an uneven workload distribution", "a memory leak in a worker", "an undersized thread pool", "a cache allocation change", "a slow storage dependency", "a sudden traffic increase", "an inefficient batch size"],
        "solutions": ["Compare resource use by worker and job type, then tune the processing concurrency within the service capacity limits.", "Capture a memory profile, recycle only the affected worker through the normal procedure, and track memory after it rejoins.", "Inspect queue age and worker health, then add capacity using the approved scaling policy while monitoring error rates.", "Review recent cache and workload changes, restore the last known good setting if needed, and measure latency under a controlled load.", "Identify the slow I/O path from host metrics and storage traces before changing concurrency or moving workloads.", "Distribute queued jobs across healthy workers and verify balanced CPU, memory, and completion rates.", "Confirm the thread pool is blocked on a dependency or exhausted by active work before adjusting its configured limits.", "Reduce non-urgent batch concurrency and monitor throughput until the service returns to its normal operating range."],
        "team": "Performance Engineering",
    },
    "Database": {
        "titles": ["Catalog Query Timeout", "Database Connection Pool Exhaustion", "Indexing Job Delay", "Transaction Lock Wait", "Replication Lag Alert", "Media Metadata Write Failure", "Slow Search Query", "Database Storage Warning"],
        "symptoms": [
            "catalog searches time out while metadata indexing is running",
            "the application reports that no database connections are available",
            "media metadata updates remain queued behind long-running transactions",
            "replica freshness falls behind the primary during peak ingest activity",
            "a search query scans a large catalog table and exceeds its request deadline",
            "index maintenance jobs run longer and block interactive catalog requests",
            "new media records fail to persist after a brief database connectivity interruption",
            "database storage usage approaches its configured allocation limit",
        ],
        "causes": ["a missing query index", "a connection pool leak", "a long-running transaction", "a heavy ingest batch", "replication bandwidth contention", "stale query statistics", "an inefficient join plan", "database growth exceeding its forecast"],
        "solutions": ["Review the query plan and current index coverage, then apply an index change only after validating it in staging.", "Check active and idle connections for leaks, release confirmed abandoned sessions, and verify pool metrics after recovery.", "Identify the transaction holding locks and coordinate with its owner before terminating or retrying any work.", "Reduce non-urgent batch concurrency and monitor replication lag until the replica is within the service objective.", "Refresh query statistics in the approved maintenance window and compare execution plans before and after the change.", "Inspect the failed write and database logs, retry only idempotent requests, and confirm the record appears once.", "Check database allocation and growth trends, then extend capacity using the approved change procedure.", "Schedule index maintenance outside peak query periods and verify interactive query latency afterward."],
        "team": "Database Operations",
    },
    "Hardware": {
        "titles": ["Disk Controller Warning", "Host Memory ECC Alert", "Network Interface Fault", "Cooling Fan Degradation", "Power Supply Health Alert", "Storage Device Retry Spike", "Host Sensor Threshold Warning", "Hardware Redundancy Loss"],
        "symptoms": [
            "a media host reports repeated disk controller resets during file access",
            "correctable memory errors increase on a virtualization node",
            "the host network interface drops link intermittently under load",
            "a chassis fan reports reduced speed and the host temperature rises",
            "a redundant power supply reports a fault while the host remains online",
            "storage devices show elevated retry counts during media reads",
            "hardware sensor readings cross the warning threshold after sustained processing",
            "a host loses one member of its redundant storage path",
        ],
        "causes": ["a degraded device", "a loose or failing connection", "blocked airflow", "firmware drift", "a failing power component", "a controller cache fault", "a sensor reporting intermittent values", "a path cable issue"],
        "solutions": ["Collect controller health logs and schedule a replacement for the confirmed failing component under the hardware support plan.", "Move workloads using the normal maintenance process, run the vendor memory diagnostic, and replace hardware if errors persist.", "Check interface and switch-port counters, reseat or replace the suspect cable during a maintenance window, and verify link stability.", "Confirm airflow is unobstructed and replace the degraded fan through the approved hardware maintenance procedure.", "Keep the host under observation, open a hardware support case, and restore power redundancy before the next maintenance cycle.", "Check device health and controller logs, then migrate data before replacing any drive reported as degraded.", "Compare sensor telemetry with a calibrated reading and escalate persistent threshold events to hardware support.", "Restore the redundant path after validating the cable and controller port, then confirm multipath health."],
        "team": "Infrastructure Hardware",
    },
    "Network": {
        "titles": ["Streaming Packet Loss", "Media Gateway DNS Failure", "CDN Origin Connectivity Alert", "Network Interface Congestion", "TLS Handshake Timeout", "Intermittent Route Failure", "High Gateway Latency", "Firewall Policy Block"],
        "symptoms": [
            "viewers report buffering while packet loss rises between the media host and edge gateway",
            "media services fail to resolve the configured origin hostname",
            "the CDN cannot establish a connection to the media origin during peak traffic",
            "gateway interface utilization remains high and streaming latency increases",
            "TLS connections to the publishing endpoint time out intermittently",
            "traffic to one media region follows an unexpected network route",
            "round-trip latency increases between the storage subnet and media workers",
            "a recently changed firewall policy blocks approved media delivery traffic",
        ],
        "causes": ["a congested uplink", "stale DNS records", "a route advertisement change", "a firewall rule mismatch", "an expiring certificate", "an overloaded gateway", "a duplex or interface negotiation issue", "packet filtering on an intermediate hop"],
        "solutions": ["Compare interface error and utilization counters at each hop, then coordinate capacity or routing changes with network operations.", "Verify resolver responses from the affected host and correct stale records through the DNS change process.", "Check origin reachability and CDN health probes, then restore the approved route or firewall access if it changed unexpectedly.", "Review firewall logs against the approved traffic matrix and update only the specific rule required for the media flow.", "Measure latency and loss hop by hop, capture timestamps, and escalate to the carrier if the fault is outside the managed network.", "Validate the endpoint certificate chain and expiry, then renew it using the approved certificate workflow.", "Check gateway CPU, connection counts, and interface errors before applying any traffic-shaping change.", "Confirm route announcements with network operations and restore the last known good route if the change caused the outage."],
        "team": "Network Operations",
    },
}


def next_number(values: list[str], prefix: str, fallback: int) -> int:
    numbers = []
    for value in values:
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", value.strip())
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=fallback - 1) + 1


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        raise ValueError("incidents.csv has no header row")
    if len(rows) >= TARGET_ROWS:
        print(f"Dataset already has {len(rows)} rows; target is {TARGET_ROWS}.")
        return

    provenance_column = "record_source"
    if provenance_column not in fieldnames:
        fieldnames.append(provenance_column)
    for row in rows:
        row[provenance_column] = row.get(provenance_column) or "Original source record"

    incident_number = next_number([row.get("incident_id", "") for row in rows], "INC-", 5001)
    ticket_number = next_number([row.get("ticket_id", "") for row in rows], "TKT-", 1001)
    category_order = list(INCIDENT_PATTERNS)
    counts = {category: 0 for category in category_order}
    needed = TARGET_ROWS - len(rows)
    for index in range(needed):
        category = category_order[index % len(category_order)]
        pattern = INCIDENT_PATTERNS[category]
        variant = counts[category]
        counts[category] += 1
        title = pattern["titles"][variant % len(pattern["titles"])]
        symptom = pattern["symptoms"][(variant * 3 + variant // len(pattern["titles"])) % len(pattern["symptoms"])]
        cause = pattern["causes"][(variant * 5 + variant // len(pattern["symptoms"])) % len(pattern["causes"])]
        resolution = pattern["solutions"][(variant * 7 + variant // len(pattern["causes"])) % len(pattern["solutions"])]
        asset_number = (variant * 17 + index) % 120 + 1
        asset = f"MediaServer{asset_number:03d}"
        priority = "P1" if category == "Security" and variant % 3 == 0 else "P2" if category in {"Storage", "Database", "Performance"} else "P3"
        impact = str(1 + (variant % 3 == 0) + (variant % 5 == 0))
        urgency = str(1 + (variant % 4 == 0) + (variant % 7 == 0))
        incident_id = f"INC-{incident_number}"
        ticket_id = f"TKT-{ticket_number}"
        row = {
            "Media Asset": asset,
            "Category": category,
            "Ticket ID": ticket_id,
            "Incident ID": incident_id,
            "Incident Details": title,
            "Description": f"{symptom.capitalize()}; investigation identified {cause}.",
            "Solution": resolution,
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "ci_name": asset,
            "category": category,
            "incident_details": title,
            "description": f"{title} - {symptom.capitalize()}; investigation identified {cause}.",
            "resolution_notes": resolution,
            "incident_state": "Resolved",
            "priority": priority,
            "impact": str(min(int(impact), 3)),
            "urgency": str(min(int(urgency), 3)),
            "assigned_to": pattern["team"],
            provenance_column: "Synthetic example",
        }
        rows.append(row)
        incident_number += 1
        ticket_number += 1

    with CSV_PATH.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Expanded dataset to {len(rows)} rows ({needed} synthetic examples).")


if __name__ == "__main__":
    main()
