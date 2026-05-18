"""Browser Use cloud API wrapper for candidate sourcing."""
import httpx
from config import settings

BASE = "https://api.browser-use.com/v1"
HEADERS = {"Authorization": f"Bearer {settings.browser_use_api_key}", "Content-Type": "application/json"}


def run_sourcing_task(role_brief: dict) -> str:
    """
    Kick off a browser task to source candidates.
    Returns a task_id — poll get_task_result() until done.

"""
    instruction = (
        f"Search GitHub profiles, Wellfound, and LinkedIn for engineers who match this role: "
        f"{role_brief.get('title')} in {role_brief.get('location')}. "
        f"Must have: {', '.join(role_brief.get('must_haves', []))}. "
        f"Find 5 candidates and return their name, current title, location, profile URL, "
        f"email if visible, and a brief description of their background."
    )
    r = httpx.post(f"{BASE}/run", headers=HEADERS, json={"task": instruction}, timeout=60)
    r.raise_for_status()
    return r.json().get("task_id")


def get_task_result(task_id: str) -> dict:
    """Poll for task completion. Status: running | completed | failed."""
    r = httpx.get(f"{BASE}/task/{task_id}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()
