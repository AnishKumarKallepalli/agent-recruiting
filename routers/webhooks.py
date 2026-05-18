"""
Webhook handlers for AgentPhone and AgentMail events.

Payload reference: https://docs.agentphone.ai/documentation/guides/webhooks#webhook-payload

agent.call_ended envelope:
{
  "event": "agent.call_ended",
  "channel": "voice",
  "agentId": "...",
  "timestamp": "...",
  "data": {
    "callId": "...",           ← camelCase, inside data
    "from": "...",
    "to": "...",
    "direction": "inbound"|"outbound",
    "durationSeconds": 120,   ← inside data
    "transcript": [{"role": "user"|"assistant", "content": "..."}],  ← ARRAY
    "summary": "...",
    "callSuccessful": true
  }
}
"""
import json
import logging
import os

from fastapi import APIRouter, Request, BackgroundTasks

from agents import gemini
import db
from services import agentmail

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

DEMO_FOUNDER = {"name": "Demo Founder", "phone": "+10000000000", "email": "founder@demo.com"}


def _transcript_to_str(transcript) -> str:
    """
    Convert AgentPhone transcript to a plain string Gemini can process.
    Docs: transcript is an array of {role, content} objects.
    Falls back gracefully if it arrives as a plain string (e.g. future API change).
    """
    if not transcript:
        return ""
    if isinstance(transcript, str):
        return transcript
    if isinstance(transcript, list):
        lines = []
        for turn in transcript:
            role = turn.get("role", "unknown").capitalize()
            content = turn.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    return str(transcript)


def _transcript_len(transcript) -> int:
    """Return meaningful length — number of turns if array, char count if string."""
    if isinstance(transcript, list):
        return len(transcript)
    if isinstance(transcript, str):
        return len(transcript.strip())
    return 0


# ── AgentPhone ─────────────────────────────────────────────────────────────────

@router.post("/agentphone")
async def agentphone_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive AgentPhone events."""
    payload = await request.json()

    # Log full payload on every call — essential for debugging
    logger.info(f"AgentPhone webhook:\n{json.dumps(payload, indent=2)}")

    event_type = payload.get("event", "")
    logger.info(f"Event type: {event_type!r}")

    if event_type == "agent.call_ended":
        background_tasks.add_task(_handle_call_ended, payload)

    # voice turn in webhook mode — not used (Built-in AI mode), but handle gracefully
    elif event_type == "agent.message" and payload.get("channel") == "voice":
        logger.info("Voice turn received (webhook mode) — not handled in Built-in AI mode")

    return {"ok": True}


async def _handle_call_ended(payload: dict):
    """Route completed call to intake or screening handler."""
    data = payload.get("data", {})

    # All fields live inside `data` per docs
    agentphone_call_id = data.get("callId", "")
    transcript_raw = data.get("transcript", [])   # array of {role, content}
    duration = int(data.get("durationSeconds") or 0)  # AgentPhone returns float e.g. 30.37
    direction = data.get("direction", "")          # "inbound" | "outbound"
    call_successful = data.get("callSuccessful", False)

    transcript_str = _transcript_to_str(transcript_raw)
    transcript_turns = _transcript_len(transcript_raw)

    logger.info(
        f"Call ended — id={agentphone_call_id} direction={direction} "
        f"turns={transcript_turns} duration={duration}s successful={call_successful}"
    )

    # Check if this is a known outbound screening call
    call_record = db.get_call_by_agentphone_id(agentphone_call_id) if agentphone_call_id else None

    if call_record and call_record.get("call_type") == "screening":
        await _process_screening_call(call_record, transcript_raw, transcript_str, duration)
    else:
        # Inbound call from founder = intake
        logger.info("No matching call record — treating as inbound intake call")
        await _process_inbound_intake(agentphone_call_id, transcript_raw, transcript_str, duration)


async def _process_inbound_intake(
    agentphone_call_id: str,
    transcript_raw: list,
    transcript_str: str,
    duration: int,
):
    """
    Handle an inbound call from a founder.
    Creates founder + role, extracts brief via Gemini, loads candidates, calls top candidate.
    """
    if _transcript_len(transcript_raw) < 2:
        logger.warning(f"Intake call has too few turns ({_transcript_len(transcript_raw)}) — skipping")
        return

    founder = db.get_or_create_founder(**DEMO_FOUNDER)

    # Create placeholder role
    role_row = db.create_role(founder["id"], {
        "title": "Pending extraction",
        "raw_transcript": transcript_str,
    })
    role_id = role_row["id"]

    # Record the call
    call_row = db.create_call(
        call_type="intake",
        role_id=role_id,
        agentphone_call_id=agentphone_call_id,
    )
    db.update_call(call_row["id"], status="completed", transcript=transcript_str, duration_seconds=duration)

    logger.info(f"Intake call saved. Role ID: {role_id}. Running Gemini extraction...")

    # Extract structured brief
    brief = gemini.extract_role_brief(transcript_str)
    brief["id"] = role_id

    db.get_db().table("roles").update({
        "title":             brief.get("title"),
        "company":           brief.get("company"),
        "location":          brief.get("location"),
        "must_haves":        brief.get("must_haves", []),
        "nice_haves":        brief.get("nice_haves", []),
        "comp_range":        brief.get("comp_range"),
        "target_background": brief.get("target_background"),
        "dealbreakers":      brief.get("dealbreakers"),
        "booking_link":      brief.get("booking_link"),
        "raw_transcript":    transcript_str,
    }).eq("id", role_id).execute()

    logger.info(f"Brief extracted: {brief.get('title')} @ {brief.get('company')}")

    # Load pre-cached candidates
    candidates_path = os.path.join(os.path.dirname(__file__), "..", "data", "candidates.json")
    with open(candidates_path) as f:
        cached = json.load(f)

    inserted = db.insert_candidates(role_id, cached)
    logger.info(f"Loaded {len(inserted)} candidates")

    # Call top candidate immediately
    top = max(inserted, key=lambda c: c.get("fit_score", 0))
    logger.info(f"Top candidate: {top['name']} ({top['fit_score']}%) — initiating call")
    await _initiate_screening_call(top, brief)


async def _process_screening_call(
    call_record: dict,
    transcript_raw: list,
    transcript_str: str,
    duration: int,
):
    """Summarize screening call, update candidate status, send follow-up email if qualified."""
    candidate_id = call_record.get("candidate_id")
    role_id = call_record["role_id"]

    role = db.get_role(role_id)
    candidate = (
        db.get_db()
        .table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .single()
        .execute()
        .data
    )

    # Voicemail / no answer = 0 or 1 turns
    if _transcript_len(transcript_raw) < 2:
        logger.info(f"No real conversation — voicemail for {candidate['name']}")
        db.update_call(
            call_record["id"],
            status="voicemail", transcript=transcript_str,
            outcome="voicemail", duration_seconds=duration,
            summary="Candidate did not answer. Voicemail left.",
        )
        db.update_candidate_status(candidate_id, "rejected")
        return

    result = gemini.summarize_screening_call(transcript_str, role, candidate["name"])
    outcome = result.get("outcome", "rejected")

    db.update_call(
        call_record["id"],
        status="completed", transcript=transcript_str,
        outcome=outcome, duration_seconds=duration,
        summary=result.get("summary", ""),
    )

    new_status = "qualified" if outcome == "qualified" else "rejected"
    db.update_candidate_status(candidate_id, new_status)
    logger.info(f"{candidate['name']} → {new_status}")

    # Send follow-up email if qualified
    if result.get("send_followup") and candidate.get("email"):
        email_content = gemini.draft_followup_email(role, candidate)
        resp = agentmail.send_email(
            to=candidate["email"],
            subject=email_content["subject"],
            body=email_content["body"],
            html=email_content.get("html"),
        )
        db.create_email(
            candidate_id=candidate_id,
            role_id=role_id,
            to_email=candidate["email"],
            subject=email_content["subject"],
            body=email_content["body"],
            agentmail_id=resp.get("message_id"),
        )
        logger.info(f"Follow-up email sent to {candidate['name']}")


async def _initiate_screening_call(candidate: dict, role_brief: dict):
    """Make an outbound call to a candidate."""
    from services.agentphone import make_call

    script = gemini.generate_screening_script(role_brief, candidate)
    call_row = db.create_call(
        call_type="screening",
        role_id=role_brief.get("id", ""),
        candidate_id=candidate["id"],
    )
    db.update_candidate_status(candidate["id"], "calling")

    try:
        company  = role_brief.get("company")  or "NovaMind AI"
        title    = role_brief.get("title")    or "Founding AI Engineer"
        location = role_brief.get("location") or "San Francisco"
        call_resp = make_call(
            to_phone=candidate["phone"],
            system_prompt=script,
            initial_greeting=(
                f"Hi {candidate['name'].split()[0]}, this is Ava calling on behalf of {company}. "
                f"I'm reaching out about a {title} role "
                f"in {location}. "
                f"Do you have 30 seconds?"
            ),
        )
        # Response shape not formally documented — try known patterns
        ap_call_id = (
            call_resp.get("callId")
            or call_resp.get("id")
            or call_resp.get("call_id")
            or ""
        )
        db.update_call(call_row["id"], agentphone_call_id=ap_call_id)
        logger.info(f"Outbound call to {candidate['name']} initiated — callId: {ap_call_id}")
    except Exception as e:
        logger.error(f"Failed to call {candidate['name']}: {e}")
        db.update_call(call_row["id"], status="failed")


# ── AgentMail ──────────────────────────────────────────────────────────────────

@router.post("/agentmail")
async def agentmail_webhook(request: Request):
    """Receive AgentMail events."""
    payload = await request.json()
    logger.info(f"AgentMail webhook:\n{json.dumps(payload, indent=2)}")

    if payload.get("event_type") == "message.received":
        data = payload.get("data", {})
        logger.info(f"Reply from {data.get('from')} — {data.get('subject')}")

    return {"ok": True}
