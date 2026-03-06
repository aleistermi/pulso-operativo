"""Fetch timesheet data from BambooHR and save locally."""

import json
import os
from datetime import date, timedelta

import pandas as pd
from dotenv import load_dotenv

from bamboohr_client import BambooHRClient

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def fetch_and_save(days_back: int = 30):
    """Pull timesheet entries and employee data, save as JSON and CSV."""
    api_key = os.environ["BAMBOOHR_API_KEY"]
    subdomain = os.environ["BAMBOOHR_SUBDOMAIN"]

    client = BambooHRClient(api_key, subdomain)

    # Fetch employee directory for name mapping
    print("Fetching employee directory...")
    employees = client.get_employees()
    emp_map = {str(e["id"]): e.get("displayName", f"Employee {e['id']}") for e in employees}

    with open(os.path.join(DATA_DIR, "employees.json"), "w") as f:
        json.dump(employees, f, indent=2)
    print(f"  -> {len(employees)} employees saved.")

    # Fetch timesheet entries
    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Fetching timesheet entries from {start} to {end}...")
    entries = client.get_timesheet_entries(start.isoformat(), end.isoformat())

    with open(os.path.join(DATA_DIR, "timesheet_entries.json"), "w") as f:
        json.dump(entries, f, indent=2)
    print(f"  -> {len(entries)} entries saved.")

    # Convert to DataFrame and enrich with employee names
    if entries:
        df = pd.json_normalize(entries)
        if "employeeId" in df.columns:
            df["employeeName"] = df["employeeId"].astype(str).map(emp_map).fillna("Unknown")
        df.to_csv(os.path.join(DATA_DIR, "timesheet_entries.csv"), index=False)
        print(f"  -> CSV exported to data/timesheet_entries.csv")
        return df
    else:
        print("  -> No entries found for the given period.")
        return pd.DataFrame()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch BambooHR timesheet data")
    parser.add_argument("--days", type=int, default=30, help="Number of days back to fetch (default: 30)")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    df = fetch_and_save(days_back=args.days)
    if not df.empty:
        print(f"\nSummary: {len(df)} entries, {df['employeeName'].nunique() if 'employeeName' in df.columns else '?'} employees")
