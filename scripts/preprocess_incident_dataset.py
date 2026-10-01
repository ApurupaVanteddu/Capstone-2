from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import normalize_columns

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SOURCE_PATH = Path(os.getenv("RAW_INCIDENT_DATA_PATH", str(ROOT / "data" / "incidents.csv"))).expanduser()
OUTPUT_PATH = PROCESSED_DIR / "cleaned_incidents.csv"


def build_processed_dataset(source_path: Path = SOURCE_PATH, output_path: Path = OUTPUT_PATH) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(f"Input incident dataset was not found: {source_path}")

    df = pd.read_csv(source_path, low_memory=False)
    df = normalize_columns(df)

    required = [
        "incident_id",
        "ticket_id",
        "ci_name",
        "category",
        "description",
        "resolution_notes",
        "priority",
        "impact",
        "urgency",
        "assigned_to",
        "incident_state",
    ]
    for column in required:
        if column not in df.columns:
            df[column] = ""

    df["description"] = df["description"].fillna("").astype(str).str.strip()
    df["resolution_notes"] = df["resolution_notes"].fillna("").astype(str).str.strip()
    df = df[df["description"].ne("")].copy()
    df["priority"] = df["priority"].fillna("P3").astype(str).str.upper()
    df["impact"] = df["impact"].fillna("3").astype(str).str.strip()
    df["urgency"] = df["urgency"].fillna("3").astype(str).str.strip()
    df["incident_state"] = df["incident_state"].fillna("Resolved").astype(str).str.strip().replace("", "Resolved")
    df["assigned_to"] = df["assigned_to"].fillna("SRE Media Squad").astype(str).str.strip()
    df["category"] = df["category"].fillna("Application").astype(str).str.strip()

    df = df.drop_duplicates(subset=["incident_id"], keep="first").reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


if __name__ == "__main__":
    df = build_processed_dataset()
    print(f"Cleaned dataset written to {OUTPUT_PATH} ({len(df)} rows)")
