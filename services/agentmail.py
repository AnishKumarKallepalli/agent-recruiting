"""AgentMail API wrapper. Inbox: recagent@agentmail.to"""
import httpx
from config import settings

BASE = settings.agentmail_base_url
HEADERS = {"Authorization": f"Bearer {settings.agentmail_api_key}", "Content-Type": "application/json"}
INBOX = settings.agentmail_inbox_id  # recagent@agentmail.to


def send_email(to: str, subject: str, body: str, html: str | None = None) -> dict:
    """Send an email from recagent@agentmail.to."""
    payload: dict = {"to": to, "subject": subject, "text": body}
    if html:
        payload["html"] = html
    r = httpx.post(f"{BASE}/inboxes/{INBOX}/messages/send", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()  # {"message_id": "...", "thread_id": "..."}


def list_messages(limit: int = 10) -> list[dict]:
    r = httpx.get(f"{BASE}/inboxes/{INBOX}/messages", headers=HEADERS, params={"limit": limit})
    r.raise_for_status()
    return r.json().get("messages", [])


def list_threads(limit: int = 10) -> list[dict]:
    r = httpx.get(f"{BASE}/inboxes/{INBOX}/threads", headers=HEADERS, params={"limit": limit})
    r.raise_for_status()
    return r.json().get("threads", [])
