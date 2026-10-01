from pathlib import Path
from app.data import load_incidents


def test_incidents_dataset_is_loaded_and_has_incident_fields():
    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "cleaned_incidents.csv"
    df = load_incidents(path)
    assert len(df) > 0
    assert {"incident_id", "ticket_id", "ci_name", "category", "description", "resolution_notes", "priority", "incident_state"}.issubset(df.columns)
    assert df["incident_id"].is_unique
    assert df["description"].str.strip().ne("").all()
