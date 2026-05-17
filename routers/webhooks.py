"""
Webhook handlers for AgentPhone and AgentMail events.

AgentPhone events:
  - agent.call_ended  → transcript arrives, Gemini processes it, triggers next step

AgentMail events:
  - message.received  → candidate replied to follow-up (log it)
"""
import json
import logging
import os

from fastapi import APIRouter, Request, BackgroundTasks

from agents import gemini
import db
from services import agentmail
from config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# Demo founder — used for all inbound intake calls
DEMO_FOUNDER = {"name": "Demo Founder", "phone": "+10000000000", "email": "founder@demo.com"}


# ── AgentPhone ─────────────────────────────────────────────────────────────────

@router.post("/agentphone")
async def agentphone_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive AgentPhone events. Log full payload so we can see exact shape on first call."""
    payload = await request.json()

    # Log EVERYTHING on first call — helps us verify field names
    logger.info(f"AgentPhone webhook raw payload: {json.dumps(payload, indent=2)}")

    # AgentPhone may use different field names — try all known variants
    event_type = (
        payload.get("event")
        or payload.get("type")
        or payload.get("eventType")
        or payload.get("event_type")
        or ""
    )
    logger.info(f"AgentPhone event type: {event_type!r}")

    if "call_ended" in event_type.lower() or event_type == "":
        # Some providers send no event type for call_ended — handle both
        if payload.get("transcript") or payload.get("summary"):
            background_tasks.add_task(_handle_call_ended, payload)

    return {"ok": True}


async def _handle_call_ended(payload: dict):
    """Route completed call to intake or screening handler."""
    # Try multiple possible field names for call ID
    agentphone_call_id = (
        payload.get("call_id")
        or payload.get("callId")
        or payload.get("id")
        or ""
    )
    transcript = (
        payload.get("transcript")
        or payload.get("transcription")
        or payload.get("transcript_text")
        or ""
    )
    duration = (
        payload.get("duration_seconds")
        or payload.get("duration")
        or payload.get("durationSeconds")
        or 0
    )

    logger.info(f"Call ended — id={agentphone_call_id}, transcript length={len(transcript)}")

    # Check if this is a known outbound screening call
    call_record = db.get_call_by_agentphone_id(agentphone_call_id) if agentphone_call_id else None

    if call_record and call_record.get("call_type") == "screening":
        await _process_screening_call(call_record, transcript, duration)
    else:
        # Unknown call = inbound intake call from a founder
        logger.info("No matching call record — treating as inbound intake call")
        await _process_inbound_intake(agentphone_call_id, transcript, duration, payload)


async def _process_inbound_intake(agentphone_call_id: str, transcript: str, duration: int, payload: dict):
    """
    Handle an inbound call from a founder.
    Creates founder + role on the fly, extracts brief, loads candidates, calls top candidate.
    """
    if not transcript or len(transcript.strip()) < 30:
        logger.warning("Intake call ended with no/short transcript — skipping")
        return

    # Get or create the demo founder
    founder = db.get_or_create_founder(
        name=DEMO_FOUNDER["name"],
        phone=DEMO_FOUNDER["phone"],
        email=DEMO_FOUNDER["email"],
    )

    # Create a placeholder role (will be filled by Gemini below)
    role_row = db.create_role(founder["id"], {
        "title": "Pending extraction",
        "raw_transcript": transcript,
    })
    role_id = role_row["id"]

    # Log the intake call
    call_row = db.create_call(
        call_type="intake",
        role_id=role_id,
        agentphone_call_id=agentphone_call_id,
    )
    db.update_call(call_row["id"], status="completed", transcript=transcript, duration_seconds=duration)

    logger.info(f"Intake call recorded. Role ID: {role_id}. Extracting brief...")

    # Extract structured brief from transcript via Gemini
    brief = gemini.extract_role_brief(transcript)
    brief["id"] = role_id

    # Update role with extracted fields
    db.get_db().table("roles").update({
        "title": brief.get("title"),
        "company": brief.get("company"),
        "location": brief.get("location"),
        "must_haves": brief.get("must_haves", []),
        "nice_haves": brief.get("nice_haves", []),
        "comp_range": brief.get("comp_range"),
        "target_background": brief.get("target_background"),
        "dealbreakers": brief.get("dealbreakers"),
        "booking_link": brief.get("booking_link"),
        "raw_transcript": transcript,
    }).eq("id", role_id).execute()

    logger.info(f"Role brief extracted: {brief.get('title')} @ {brief.get('company')}")

    # Load pre-cached candidates
    candidates_path = os.path.join(os.path.dirname(__file__), "..", "data", "candidates.json")
    with open(candidates_path) as f:
        cached = json.load(f)

    inserted = db.insert_candidates(role_id, cached)
    logger.info(f"Loaded {len(inserted)} candidates for role {role_id}")

    # Call the top candidate
    top = max(inserted, key=lambda c: c.get("fit_score", 0))
    logger.info(f"Top candidate: {top['name']} ({top['fit_score']}% fit) — initiating call")

    await _initiate_screening_call(top, brief)


async def _process_screening_call(call_record: dict, transcript: str, duration: int):
    """Summarize screening call, update candidate status, send follow-up email if qualified."""
    candidate_id = call_record.get("candidate_id")
    role_id = call_record["role_id"]

    role = db.get_role(role_id)
    candidate = db.get_db().table("candidates").select("*").eq("id", candidate_id).single().execute().data

    # Detect voicemail / no answer
    if not transcript or len(transcript.strip()) < 20:
        logger.info(f"No transcript — marking as voicemail for {candidate['name']}")
        db.update_call(call_record["id"], status="voicemail", transcript=transcript,
                       outcome="voicemail", duration_seconds=duration,
                       summary="Candidate did not answer. Voicemail left.")
        db.update_candidate_status(candidate_id, "rejected")
        return

    result = gemini.summarize_screening_call(transcript, role, candidate["name"])
    outcome = result.get("outcome", "rejected")
    summary = result.get("summary", "")

    db.update_call(call_record["id"], status="completed", transcript=transcript,
                   outcome=outcome, duration_seconds=duration, summary=summary)

    new_status = "qualified" if outcome == "qualified" else "rejected"
    db.update_candidate_status(candidate_id, new_status)
    logger.info(f"Candidate {candidate['name']} → {new_status}")

    # Send follow-up email if qualified
    if result.get("send_followup") and candidate.get("email"):
        email_content = gemini.draft_followup_email(role, candidate)
        resp = agentmail.send_email(
            to=candidate["email"],
            subject=email_content["subject"],
            body=email_content["body"],
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
        call_resp = make_call(
            to_phone=candidate["phone"],
            system_prompt=script,
            initial_greeting=(
                f"Hi {candidate['name'].split()[0]}, this is Ava from HyperVelocity. "
                f"I'm reaching out about a {role_brief.get('title', 'founding engineer')} role "
                f"at an early-stage AI startup in {role_brief.get('location', 'San Francisco')}. "
                f"Do you have 30 seconds?"
            ),
        )
        ap_call_id = call_resp.get("id") or call_resp.get("callId") or call_resp.get("call_id")
        db.update_call(call_row["id"], agentphone_call_id=ap_call_id)
        logger.info(f"Outbound call to {candidate['name']} initiated — AP call id: {ap_call_id}")
    except Exception as e:
        logger.error(f"Failed to call {candidate['name']}: {e}")
        db.update_call(call_row["id"], status="failed")


# ── AgentMail ──────────────────────────────────────────────────────────────────

@router.post("/agentmail")
async def agentmail_webhook(request: Request):
    """Receive AgentMail events (candidate replies)."""
    payload = await request.json()
    logger.info(f"AgentMail webhook: {json.dumps(payload, indent=2)}")

    event_type = payload.get("event_type", "")
    if event_type == "message.received":
        data = payload.get("data", {})
        logger.info(f"Email reply from {data.get('from')} — subject: {data.get('subject')}")

    return {"ok": True}
