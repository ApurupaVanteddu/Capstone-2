from pathlib import Path
from fastapi.testclient import TestClient
from app.config import resolve_data_path
from app.data import load_incidents
from app.retrieval import IncidentRetriever
from app.intelligence import classify
from app.llm import generate_generalized_resolution
from app.auth import login_user
from app.main import app

client = TestClient(app)

def test_sample_data_and_search():
    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "cleaned_incidents.csv"
    df = load_incidents(path)
    assert len(df) > 0
    results = IncidentRetriever(df).search("Disk space alert storage upload failure", 3)
    assert results
    assert "description" in results[0]

def test_uses_processed_dataset_when_available(tmp_path):
    data_dir = tmp_path / "data"
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True)

    raw_file = data_dir / "incidents.csv"
    raw_file.write_text("incident_id,description,resolution_notes,category,priority,impact,urgency,assigned_to\nINC-1,Database latency,Restart the DB service,Database,P2,3,3,SRE\n", encoding="utf-8")
    processed_file = processed_dir / "cleaned_incidents.csv"
    processed_file.write_text("incident_id,description,resolution_notes,category,priority,impact,urgency,assigned_to\nINC-1,Database latency,Restart the DB service,Database,P2,3,3,SRE\nINC-2,API timeout,Scale the gateway,Application,P2,3,3,SRE\n", encoding="utf-8")

    resolved = resolve_data_path(base_dir=data_dir)
    assert resolved == processed_file


def test_triage():
    result = classify("Production down for all users: database outage")
    assert result["suggested_priority"] == "P1"


def test_generalized_resolution_is_plain_language():
    result = generate_generalized_resolution("Media server is failing with latency spikes", [])
    text = result["answer"]
    assert "###" not in text
    assert "Generalized L3 Troubleshooting Guidance" not in text
    assert "Confirm the scope" in text
    assert "This is generalized guidance" in text


def test_new_ticket_is_escalated_to_admin_and_marked_new_ticket():
    token = login_user("engineer@incidentiq.io", "User@123")["token"]
    response = client.post(
        "/api/tickets",
        json={
            "title": "New incident: media server latency",
            "description": "Search incident created by L1 user after no dataset match for this issue.",
            "incident_id": "INC-NEW-ADMIN-1",
            "priority": "P1",
            "new_incident": True
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticket"]["assigned_to"] == "admin@incidentiq.io"
    assert body["ticket"]["current_tier"] == "l1"

    incident = client.get("/api/incidents/INC-NEW-ADMIN-1", headers={"Authorization": f"Bearer {token}"})
    assert incident.status_code == 200, incident.text
    assert incident.json()["incident"]["incident_state"] == "New Ticket"


def test_standard_ticket_stays_in_user_queue_and_can_escalate():
    token = login_user("engineer@incidentiq.io", "User@123")["token"]
    response = client.post(
        "/api/tickets",
        json={
            "title": "Media server latency investigation",
            "description": "Did an application health check and found the service is unstable during peak load.",
            "incident_id": "INC-USER-QUEUE-1",
            "priority": "P2"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticket"]["assigned_to"] == "engineer@incidentiq.io"
    assert body["ticket"]["current_tier"] == "l1"
    assert body["ticket"]["status"] == "Open"
