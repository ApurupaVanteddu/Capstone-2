"""Fetch and update dataset from the Google Sheet URL."""
import urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "incidents.csv"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1IE8ox8-B9wu6qUZkBIy0i3Iwsvfa0qo7/export?format=csv&gid=1365699075"

def main():
    print(f"Fetching dataset from Google Sheet: {SHEET_URL}")
    temp_file = DATA_DIR / "google_sheet_temp.csv"
    urllib.request.urlretrieve(SHEET_URL, temp_file)
    
    df = pd.read_csv(temp_file)
    temp_file.unlink(missing_ok=True)
    
    df.columns = [c.strip() for c in df.columns]
    df['incident_id'] = df['Incident ID'].str.strip()
    df['ticket_id'] = df['Ticket ID'].str.strip()
    df['ci_name'] = df['Media Asset'].str.strip()
    df['category'] = df['Category'].str.strip()
    df['incident_details'] = df['Incident Details'].str.strip()
    df['description'] = df['Incident Details'].str.strip() + ' - ' + df['Description'].str.strip()
    df['resolution_notes'] = df['Solution'].str.strip()
    df['incident_state'] = 'Resolved'

    priority_map = {
        'Security': 'P1',
        'Database': 'P2',
        'Storage': 'P2',
        'Performance': 'P2',
        'Application': 'P3',
        'Network': 'P3',
        'Hardware': 'P3'
    }
    df['priority'] = df['category'].map(lambda c: priority_map.get(c, 'P3'))
    df['impact'] = '3'
    df['urgency'] = '3'
    df['assigned_to'] = 'SRE Media Squad'

    df.to_csv(OUTPUT, index=False)
    from expand_dataset import main as expand_to_target
    expand_to_target()
    print(f"Successfully processed source data and expanded the dataset to {OUTPUT}")

if __name__ == "__main__":
    main()
