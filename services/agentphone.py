"""AgentPhone API wrapper.

Docs: https://docs.agentphone.ai/api-reference/calls/create-outbound-call-v-1-calls-post
"""
import httpx
from config import settings

BASE = settings.agentphone_base_url
HEADERS = {"Authorization": f"Bearer {settings.agentphone_api_key}", "Content-Type": "application/json"}


# ── Agent + Number setup (run once) ───────────────────────────────────────────

def create_agent(name: str = "Agent") -> dict:
    """Create an AgentPhone agent. Run once, save the ID to .env."""
    r = httpx.post(f"{BASE}/agents", headers=HEADERS, json={"name": name})
    r.raise_for_status()
    return r.json()


def provision_number() -> dict:
    """Provision a phone number. Run once, save ID + number to .env."""
    r = httpx.post(f"{BASE}/numbers", headers=HEADERS, json={})
    r.raise_for_status()
    return r.json()


def attach_number(agent_id: str, number_id: str) -> dict:
    r = httpx.post(f"{BASE}/agents/{agent_id}/numbers", headers=HEADERS, json={"numberId": number_id})
    r.raise_for_status()
    return r.json()


def register_webhook(url: str) -> dict:
    """Register a webhook to receive call events."""
    r = httpx.post(f"{BASE}/webhooks", headers=HEADERS, json={"url": url})
    r.raise_for_status()
    return r.json()


# ── Outbound calls ─────────────────────────────────────────────────────────────

def make_call(to_phone: str, system_prompt: str, initial_greeting: str) -> dict:
    """
    Initiate an outbound call via AgentPhone.

    POST /v1/calls
    Required: agentId, toNumber
    Optional: fromNumberId, initialGreeting, voice, systemPrompt, variables
    """
    payload = {
        "agentId": settings.agentphone_agent_id,
        "toNumber": to_phone,
        "fromNumberId": settings.agentphone_number_id,
        "initialGreeting": initial_greeting,
        "systemPrompt": system_prompt,
    }
    r = httpx.post(f"{BASE}/calls", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def get_call(call_id: str) -> dict:
    r = httpx.get(f"{BASE}/calls/{call_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_transcript(call_id: str) -> str | None:
    """Fetch transcript for a completed call."""
    data = get_call(call_id)
    return data.get("transcript") or data.get("transcription")
