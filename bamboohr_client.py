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

    def get_all_projects(self, employee_ids: list[str] | None = None) -> dict[int, str]:
        """Fetch all projects from BambooHR by querying each employee's assigned projects.

        Args:
            employee_ids: List of employee ID strings. If None, fetches employees first.

        Returns:
            Dict mapping project ID -> project name.
        """
        projects, _ = self.get_project_assignments(employee_ids)
        return projects

    def get_project_assignments(self, employee_ids: list[str] | None = None) -> tuple[dict[int, str], dict[str, list[str]]]:
        """Fetch all projects AND employee-project assignments from BambooHR.

        Args:
            employee_ids: List of employee ID strings. If None, fetches employees first.

        Returns:
            Tuple of:
                - Dict mapping project ID -> project name
                - Dict mapping employee ID -> list of project names
        """
        if employee_ids is None:
            employees = self.get_employees()
            employee_ids = [str(e["id"]) for e in employees]

        projects: dict[int, str] = {}
        assignments: dict[str, list[str]] = {}
        for eid in employee_ids:
            url = f"{self.base_url}/time_tracking/employee/{eid}/projects"
            resp = self.session.get(url)
            if resp.status_code == 200:
                emp_projects = []
                for p in resp.json():
                    projects[p["id"]] = p["name"]
                    emp_projects.append(p["name"])
                if emp_projects:
                    assignments[eid] = emp_projects
        return projects, assignments

    def get_salary_report(self) -> list[dict]:
        """Fetch pay rate data for all employees via custom report.

        Returns:
            List of dicts with keys: id, displayName, department,
            payRate, payType, payPer.
        """
        url = f"{self.base_url}/reports/custom"
        params = {"format": "JSON"}
        payload = {
            "title": "Salary Report",
            "fields": ["id", "displayName", "department", "payRate", "payType", "payPer"],
        }
        resp = self.session.post(url, params=params, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("employees", [])
