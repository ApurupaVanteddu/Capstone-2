from __future__ import annotations
import re
import os
import sqlite3
from pathlib import Path
import pandas as pd
from .config import BASE_DIR, DB_PATH

ALIASES = {
    "incident_id": ["incident_id", "incident id", "number", "id", "ticket_id", "ticket id", "incident number", "incident_id_norm"],
    "ticket_id": ["ticket_id", "ticket id"],
    "ci_name": ["ci_name", "media asset", "media_asset", "configuration_item", "ci", "server"],
    "incident_details": ["incident_details", "incident details"],
    "description": ["description", "short_description", "short description", "incident_description", "summary"],
    "resolution_notes": ["resolution_notes", "solution", "resolution", "close_notes", "resolution_summary", "work_notes"],
    "incident_state": ["incident_state", "state", "status"],
    "impact": ["impact"],
    "urgency": ["urgency"],
    "priority": ["priority", "priority_code"],
    "assigned_to": ["assigned_to", "assigned to", "assignee", "owner"],
    "category": ["category", "incident_category", "service", "subcategory"],
    "created_at": ["created_at", "opened_at", "created", "opened"],
    "resolved_at": ["resolved_at", "closed_at", "resolved", "closed"],
}

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    original = {str(c).strip().lower(): c for c in df.columns}
    rename = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if alias.lower() in original:
                rename[original[alias.lower()]] = target
                break
    df = df.rename(columns=rename)
    
    # If both incident_details and description exist and description doesn't contain details, merge them
    if "incident_details" in df.columns and "description" in df.columns:
        details = df["incident_details"].fillna("").astype(str).str.strip()
        desc = df["description"].fillna("").astype(str).str.strip()
        combined = []
        for d, s in zip(details, desc):
            if d and s and d.lower() not in s.lower():
                combined.append(f"{d} - {s}")
            elif s:
                combined.append(s)
            else:
                combined.append(d)
        df["description"] = combined

    for col in ["incident_id", "description", "resolution_notes", "incident_state", "impact", "urgency", "priority", "assigned_to", "category", "created_at", "resolved_at"]:
        if col not in df.columns:
            df[col] = ""
    return df

def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    value = str(value).replace("\x00", " ")
    return re.sub(r"\s+", " ", value).strip()

def load_incidents(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    dfs = []

    # Load custom user-created incidents from SQLite database if available
    if Path(DB_PATH).exists():
        try:
            with sqlite3.connect(DB_PATH) as con:
                df_custom = pd.read_sql_query("SELECT * FROM custom_incidents", con)
                if not df_custom.empty:
                    df_custom = normalize_columns(df_custom)
                    dfs.append(df_custom)
        except Exception:
            pass

    # Load primary dataset
    if path.exists():
        df_primary = pd.read_csv(path, low_memory=False)
        df_primary = normalize_columns(df_primary)
        dfs.append(df_primary)
    elif not dfs:
        raise FileNotFoundError(f"Incident CSV not found: {path}")

    df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]

    if "record_source" in df.columns:
        df = df[df["record_source"].astype(str).str.lower().ne("synthetic example")].copy()

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(clean_text)
    
    df = df.dropna(how="all")
    df["description"] = df["description"].fillna("").astype(str)
    df["resolution_notes"] = df["resolution_notes"].fillna("").astype(str)
    df = df[df["description"].str.strip().ne("")]
    
    # Stable identifiers for records without a ticket number
    missing = df["incident_id"].astype(str).str.strip().isin(["", "nan", "None"])
    if missing.any():
        df.loc[missing, "incident_id"] = [f"INC-LOCAL-{i:06d}" for i in range(1, int(missing.sum()) + 1)]
    
    extra_search_cols = [c for c in ["ci_name", "category", "ticket_id", "incident_details"] if c in df.columns]
    extra_search = df[extra_search_cols].fillna("").astype(str).agg(" ".join, axis=1) if extra_search_cols else pd.Series("", index=df.index)
    
    df["search_text"] = (
        "Incident: " + df["description"].astype(str) +
        " Category: " + df["category"].astype(str) +
        " Resolution outcome: " + df["resolution_notes"].astype(str) +
        " Metadata: " + extra_search.astype(str)
    ).str.strip()
    
    # Deduplicate by incident_id keeping first
    df = df.drop_duplicates(subset=["incident_id"], keep="first")
    return df.reset_index(drop=True)
