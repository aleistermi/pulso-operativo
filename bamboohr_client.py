"""BambooHR API client for timesheet data extraction."""

import requests
from datetime import date, timedelta


class BambooHRClient:
    """Client for BambooHR Time Tracking API."""

    def __init__(self, api_key: str, subdomain: str):
        self.api_key = api_key
        self.subdomain = subdomain
        self.base_url = f"https://api.bamboohr.com/api/gateway.php/{subdomain}/v1"
        self.session = requests.Session()
        self.session.auth = (api_key, "x")
        self.session.headers.update({"Accept": "application/json"})

    def get_timesheet_entries(self, start: str, end: str, employee_ids: list[int] | None = None) -> list[dict]:
        """Fetch timesheet entries for a date range.

        Args:
            start: Start date in YYYY-MM-DD format.
            end: End date in YYYY-MM-DD format.
            employee_ids: Optional list of employee IDs to filter by.

        Returns:
            List of timesheet entry dicts.
        """
        url = f"{self.base_url}/time_tracking/timesheet_entries"
        params = {"start": start, "end": end}
        if employee_ids:
            params["employeeIds"] = ",".join(str(eid) for eid in employee_ids)

        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def get_employees(self) -> list[dict]:
        """Fetch employee directory."""
        url = f"{self.base_url}/employees/directory"
        resp = self.session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("employees", [])

    def get_timesheet_entries_for_period(self, days_back: int = 30, employee_ids: list[int] | None = None) -> list[dict]:
        """Convenience method: fetch entries for the last N days."""
        end = date.today()
        start = end - timedelta(days=days_back)
        return self.get_timesheet_entries(start.isoformat(), end.isoformat(), employee_ids)
