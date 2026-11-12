"""Tools turn a chatbot into an agent: the model decides when to call them, our code does the work.

Note the security pattern: employee_id comes from the signed-in session (closure), never from the model,
so a prompt cannot make the agent read or act on someone else's records.
"""
from __future__ import annotations

import json
from datetime import date

from langchain_core.tools import tool

from copilot.hr_store import HRError, HRStore
from copilot.retriever import Retriever, format_context


def make_tools(retriever: Retriever, store: HRStore, employee_id: str, today: date | None = None) -> list:
    @tool(response_format="content_and_artifact")
    def search_hr_policies(query: str):
        """Search the company HR policy documents (leave, hybrid/remote work, travel and expenses).
        Use this for ANY question about rules, entitlements or processes. Returns excerpts with citations."""
        hits = retriever.search(query)
        return format_context(hits), hits

    @tool
    def get_my_profile_and_leave_balance() -> str:
        """Get the signed-in employee's profile (name, manager, joining date) and current leave balances,
        including days pending approval and days available."""
        try:
            emp = store.get_employee(employee_id)
            profile = {k: emp[k] for k in ("employee_id", "name", "title", "department", "manager", "joining_date")}
            return json.dumps({"profile": profile, "leave_balance": store.get_balance(employee_id),
                               "requests": store.list_requests(employee_id)})
        except HRError as exc:
            return f"ERROR: {exc}"

    @tool
    def raise_leave_request(leave_type: str, start_date: str, end_date: str, reason: str = "") -> str:
        """Submit a leave request for the signed-in employee to their manager.
        leave_type: one of annual, sick, casual. Dates: YYYY-MM-DD (inclusive).
        Only call this after the user has clearly asked to submit and confirmed the type and dates."""
        try:
            req = store.create_leave_request(employee_id, leave_type, start_date, end_date, reason, today=today)
            return "SUCCESS: " + json.dumps(req)
        except HRError as exc:
            return f"ERROR: {exc}"

    return [search_hr_policies, get_my_profile_and_leave_balance, raise_leave_request]
