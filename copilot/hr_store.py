"""Tiny JSON-backed 'HR system' so the agent has real records to read and write.

In production this would be Workday/SuccessFactors/ServiceNow behind an authenticated API.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from copilot import config

LEAVE_TYPES = ("annual", "sick", "casual")
_lock = threading.Lock()


class HRError(ValueError):
    pass


def business_days(start: date, end: date) -> int:
    days, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


class HRStore:
    def __init__(self, records_path: Path = config.HR_RECORDS_PATH, requests_path: Path = config.REQUESTS_PATH):
        self.records_path = records_path
        self.requests_path = requests_path

    def _employees(self) -> dict:
        return json.loads(self.records_path.read_text(encoding="utf-8"))["employees"]

    def _requests(self) -> list[dict]:
        if not self.requests_path.exists():
            return []
        return json.loads(self.requests_path.read_text(encoding="utf-8"))

    def list_employees(self) -> dict:
        return {eid: e["name"] for eid, e in self._employees().items()}

    def get_employee(self, employee_id: str) -> dict:
        emp = self._employees().get(employee_id)
        if not emp:
            raise HRError(f"Unknown employee {employee_id}")
        return {"employee_id": employee_id, **emp}

    def list_requests(self, employee_id: str) -> list[dict]:
        return [r for r in self._requests() if r["employee_id"] == employee_id]

    def get_balance(self, employee_id: str) -> dict:
        emp = self.get_employee(employee_id)
        pending = {t: 0 for t in LEAVE_TYPES}
        for r in self.list_requests(employee_id):
            if r["status"] == "Pending approval":
                pending[r["leave_type"]] += r["days"]
        return {t: {"entitled_remaining": emp["leave_balance"][t], "pending": pending[t],
                    "available": emp["leave_balance"][t] - pending[t]} for t in LEAVE_TYPES}

    def create_leave_request(self, employee_id: str, leave_type: str, start_date: str, end_date: str,
                             reason: str = "", today: date | None = None) -> dict:
        today = today or date.today()
        leave_type = leave_type.lower().strip()
        if leave_type not in LEAVE_TYPES:
            raise HRError(f"leave_type must be one of {', '.join(LEAVE_TYPES)}")
        try:
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except ValueError as exc:
            raise HRError("Dates must be in YYYY-MM-DD format") from exc
        if end < start:
            raise HRError("end_date is before start_date")
        if start < today and leave_type != "sick":
            raise HRError("Only sick leave can be backdated")
        days = business_days(start, end)
        if days == 0:
            raise HRError("The selected dates contain no working days")
        available = self.get_balance(employee_id)[leave_type]["available"]
        if days > available:
            raise HRError(f"Insufficient {leave_type} leave: requested {days} days, available {available}")

        emp = self.get_employee(employee_id)
        with _lock:
            requests = self._requests()
            request = {
                "request_id": f"LR-{1001 + len(requests)}",
                "employee_id": employee_id, "leave_type": leave_type,
                "start_date": start.isoformat(), "end_date": end.isoformat(), "days": days,
                "reason": reason[:300], "approver": emp["manager"], "status": "Pending approval",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            requests.append(request)
            self.requests_path.parent.mkdir(parents=True, exist_ok=True)
            self.requests_path.write_text(json.dumps(requests, indent=2), encoding="utf-8")
        return request
