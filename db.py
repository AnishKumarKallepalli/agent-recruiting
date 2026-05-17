from supabase import create_client, Client
from config import settings

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


# ── Founders ──────────────────────────────────────────────────────────────────

def get_or_create_founder(name: str, phone: str = "", email: str = "") -> dict:
    db = get_db()
    result = db.table("founders").select("*").eq("phone", phone).execute()
    if result.data:
        return result.data[0]
    insert = db.table("founders").insert({"name": name, "phone": phone, "email": email}).execute()
    return insert.data[0]


# ── Roles ─────────────────────────────────────────────────────────────────────

def create_role(founder_id: str, brief: dict) -> dict:
    db = get_db()
    result = db.table("roles").insert({
        "founder_id": founder_id,
        "title": brief.get("title"),
        "company": brief.get("company"),
        "location": brief.get("location"),
        "must_haves": brief.get("must_haves", []),
        "nice_haves": brief.get("nice_haves", []),
        "comp_range": brief.get("comp_range"),
        "target_background": brief.get("target_background"),
        "dealbreakers": brief.get("dealbreakers"),
        "booking_link": brief.get("booking_link"),
        "raw_transcript": brief.get("raw_transcript"),
    }).execute()
    return result.data[0]


def get_role(role_id: str) -> dict:
    db = get_db()
    result = db.table("roles").select("*").eq("id", role_id).single().execute()
    return result.data


# ── Candidates ────────────────────────────────────────────────────────────────

def insert_candidates(role_id: str, candidates: list[dict]) -> list[dict]:
    db = get_db()
    rows = [{**c, "role_id": role_id} for c in candidates]
    result = db.table("candidates").insert(rows).execute()
    return result.data


def update_candidate_status(candidate_id: str, status: str) -> dict:
    db = get_db()
    result = db.table("candidates").update({"status": status}).eq("id", candidate_id).execute()
    return result.data[0]


def get_candidates_for_role(role_id: str) -> list[dict]:
    db = get_db()
    result = db.table("candidates").select("*").eq("role_id", role_id).order("fit_score", desc=True).execute()
    return result.data


# ── Calls ─────────────────────────────────────────────────────────────────────

def create_call(call_type: str, role_id: str, candidate_id: str | None = None,
                agentphone_call_id: str | None = None) -> dict:
    db = get_db()
    result = db.table("calls").insert({
        "call_type": call_type,
        "role_id": role_id,
        "candidate_id": candidate_id,
        "agentphone_call_id": agentphone_call_id,
        "status": "initiated",
    }).execute()
    return result.data[0]


def update_call(call_id: str, **kwargs) -> dict:
    db = get_db()
    result = db.table("calls").update(kwargs).eq("id", call_id).execute()
    return result.data[0]


def get_call_by_agentphone_id(agentphone_call_id: str) -> dict | None:
    db = get_db()
    result = db.table("calls").select("*").eq("agentphone_call_id", agentphone_call_id).execute()
    return result.data[0] if result.data else None


# ── Emails ────────────────────────────────────────────────────────────────────

def create_email(candidate_id: str, role_id: str, to_email: str,
                 subject: str, body: str, agentmail_id: str | None = None) -> dict:
    db = get_db()
    result = db.table("emails").insert({
        "candidate_id": candidate_id,
        "role_id": role_id,
        "to_email": to_email,
        "subject": subject,
        "body": body,
        "agentmail_id": agentmail_id,
        "status": "sent",
    }).execute()
    return result.data[0]
