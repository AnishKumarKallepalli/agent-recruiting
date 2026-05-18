import json
import re
import google.generativeai as genai
from config import settings
from agents.prompts import (
    INTAKE_EXTRACTION_PROMPT,
    CANDIDATE_SCORING_PROMPT,
    SCREENING_CALL_SCRIPT_PROMPT,
    SCREENING_SUMMARY_PROMPT,
    FOLLOWUP_EMAIL_PROMPT,
    VOICEMAIL_SCRIPT_PROMPT,
)

genai.configure(api_key=settings.gemini_api_key)
# Flash — fast + cheap. Only upgrade to Pro if quality is bad.
_model = genai.GenerativeModel("gemini-2.5-flash")


def _call(prompt: str) -> str:
    response = _model.generate_content(prompt)
    return response.text.strip()


def _parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


# ── Public functions ───────────────────────────────────────────────────────────

def extract_role_brief(transcript: str) -> dict:
    """Parse intake call transcript → structured hiring brief."""
    prompt = INTAKE_EXTRACTION_PROMPT.format(transcript=transcript)
    raw = _call(prompt)
    brief = _parse_json(raw)
    brief["raw_transcript"] = transcript
    return brief


def score_candidate(role_brief: dict, candidate_profile: dict) -> dict:
    """Score a candidate against a role brief. Returns fit_score, fit_reason, recommended."""
    prompt = CANDIDATE_SCORING_PROMPT.format(
        role_brief=json.dumps(role_brief, indent=2),
        candidate_profile=json.dumps(candidate_profile, indent=2),
    )
    raw = _call(prompt)
    return _parse_json(raw)


def _safe_brief(role_brief: dict) -> dict:
    """Fill null/None fields that would produce 'None' in spoken text."""
    return {
        **role_brief,
        "company":  role_brief.get("company")  or "NovaMind AI",
        "title":    role_brief.get("title")    or "Founding AI Engineer",
        "location": role_brief.get("location") or "San Francisco",
    }


def generate_screening_script(role_brief: dict, candidate: dict) -> str:
    """Generate an outbound call script for screening a candidate."""
    brief = _safe_brief(role_brief)
    prompt = SCREENING_CALL_SCRIPT_PROMPT.format(
        role_brief=json.dumps(brief, indent=2),
        candidate_name=candidate.get("name", ""),
        candidate_title=candidate.get("current_title", ""),
        candidate_location=candidate.get("location", ""),
        fit_reason=candidate.get("fit_reason", "Strong background relevant to this role."),
        title=brief.get("title") or "Founding AI Engineer",
        company=brief.get("company") or "NovaMind AI",
    )
    return _call(prompt)


def summarize_screening_call(transcript: str, role_brief: dict, candidate_name: str) -> dict:
    """Analyze a completed screening call transcript → outcome + summary."""
    prompt = SCREENING_SUMMARY_PROMPT.format(
        role_brief=json.dumps(role_brief, indent=2),
        candidate_name=candidate_name,
        transcript=transcript,
    )
    raw = _call(prompt)
    return _parse_json(raw)


def draft_followup_email(role_brief: dict, candidate: dict) -> dict:
    """Draft a follow-up email for a qualified candidate. Returns subject + body."""
    brief = _safe_brief(role_brief)
    prompt = FOLLOWUP_EMAIL_PROMPT.format(
        role_brief=json.dumps(brief, indent=2),
        candidate_name=candidate.get("name", ""),
        fit_reason=candidate.get("fit_reason", ""),
        booking_link=brief.get("booking_link", "[booking link]"),
    )
    raw = _call(prompt)
    return _parse_json(raw)


def generate_voicemail_script(role_brief: dict, candidate_name: str, ava_phone: str) -> str:
    """Generate a voicemail script when candidate doesn't answer."""
    prompt = VOICEMAIL_SCRIPT_PROMPT.format(
        role_title=role_brief.get("title", ""),
        company=role_brief.get("company", ""),
        candidate_name=candidate_name,
        ava_phone=ava_phone,
    )
    return _call(prompt)
