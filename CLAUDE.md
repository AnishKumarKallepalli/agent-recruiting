# Ava — AI Recruiting Agent

Hackathon project for AgentPhone "Call My Agent" at YC (May 17 2026).
**Ava** is an AI recruiter: founders call in → Ava conducts intake → finds candidates → calls them → screens → sends follow-up email. Fully autonomous end-to-end.

---

## Stack

| Layer | Tool |
|-------|------|
| Backend | FastAPI (Python), deployed on Railway |
| Voice | AgentPhone — Built-in AI mode (voiceMode: "hosted") |
| Email | AgentMail — inbox: recagent@agentmail.to |
| LLM | Gemini 2.5 Flash (gemini-2.5-flash) |
| DB | Supabase (5 tables) |
| Deploy | Railway — `railway up` to redeploy |

**Live URL:** https://ava-production-cf8f.up.railway.app  
**Ava's phone:** +1 (775) 256-7153  
**Demo candidate (Alex Chen):** +16199538267, anishkumar2002.k@gmail.com

---

## How It Works

```
Founder calls +17752567153
  → AgentPhone runs intake interview (Built-in AI)
  → agent.call_ended webhook → /webhooks/agentphone
  → Gemini extracts role brief
  → Candidates loaded from data/candidates.json
  → Ava calls top candidate (outbound)
  → agent.call_ended webhook again (direction: outbound)
  → Gemini summarizes screening call
  → If qualified → AgentMail sends follow-up email
```

---

## Key Files

```
main.py                    FastAPI app entry point
config.py                  All settings via pydantic-settings (.env)
db.py                      Supabase helpers (founders/roles/candidates/calls/emails)
agents/gemini.py           All Gemini calls (6 functions)
agents/prompts.py          All 6 prompts — tweak here for quality
routers/webhooks.py        Core pipeline logic — most critical file
routers/dashboard.py       /api/roles, /api/candidates endpoints
routers/test.py            Test endpoints (no phone credits)
services/agentphone.py     make_call() for outbound calls
services/agentmail.py      send_email()
dashboard/index.html       Live pipeline dashboard (auto-refreshes every 5s)
data/candidates.json       Pre-loaded candidates (Alex 94%, Maya 87%, Jordan 81%)
seed.py                    Wipe DB: python seed.py | Check: python seed.py --check
```

---

## Supabase Tables

```
founders    id, name, phone, email
roles       id, founder_id, title, company, location, must_haves, nice_haves,
            comp_range, target_background, dealbreakers, booking_link,
            raw_transcript, status
candidates  id, role_id, name, current_title, location, email, phone,
            fit_score, fit_reason, raw_profile, status
calls       id, role_id, candidate_id, call_type (intake|screening),
            agentphone_call_id, status, transcript, duration_seconds, outcome, summary
emails      id, candidate_id, role_id, to_email, subject, body, agentmail_id, status
```

---

## AgentPhone Gotchas

- All webhook data is nested under `payload["data"]`, not root
- `transcript` arrives as array `[{role, content}]` — use `_transcript_to_str()`
- `durationSeconds` is a float — cast with `int(...)`
- `callId` is camelCase inside `data`
- Outbound call response callId: try `callId`, `id`, `call_id` in order
- voiceMode must be `"hosted"` for Built-in AI (not "llm" or "built-in")
- Inbound calls have no pre-existing DB record — treat as intake when call_record not found

---

## Test Endpoints

```
POST /test/intake/no-call   Gemini extraction + Supabase writes only — zero credits
POST /test/intake           Full pipeline including real outbound call to Alex
GET  /test/db               Current DB state snapshot
GET  /api/roles             List all roles (used by dashboard)
```

**Dashboard:** https://ava-production-cf8f.up.railway.app (auto-loads latest role)  
**Before every demo:** `python seed.py` to wipe DB clean

---

## Environment (.env — gitignored)

Keys needed: `AGENTPHONE_API_KEY`, `AGENTPHONE_AGENT_ID`, `AGENTPHONE_NUMBER_ID`,
`AGENTPHONE_PHONE_NUMBER`, `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID`,
`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `WEBHOOK_BASE_URL`

---

## TODO — Demo Polish

### High priority
- [ ] **Dashboard redesign** — full visual overhaul; should look polished and impressive for demo
- [ ] **Update candidates** — replace data/candidates.json with a new full list (pending from user)
- [ ] **Remove hardcoded "HyperVelocity"** — Ava should never say a company name; extract it from the founder intake call and use it dynamically when calling candidates. Check `routers/webhooks.py` initial_greeting and all prompts in `agents/prompts.py`
- [ ] **Improve intake system prompt** — Ava should feel warmer, more natural; currently too robotic
- [ ] **Improve screening call script** — `SCREENING_CALL_SCRIPT_PROMPT` should reference the actual company name from the role brief, and mention specific fit reasons for the candidate
- [ ] **HTML email** — `send_email()` sends plain text; upgrade to styled HTML with booking CTA button
- [ ] **AgentPhone intake system prompt** — update via PATCH /v1/agents/{id} so the intake call flows better

### Nice to have
- [ ] **Video demo** — record 90-second walkthrough: call in → watch dashboard update live → email lands

---

## Test Endpoints (use these instead of real calls)

All live at: `https://ava-production-cf8f.up.railway.app`

```
POST /test/intake            Full pipeline with fake transcript — WILL call Alex Chen's real number
POST /test/intake/no-call    Gemini extraction + Supabase writes only — zero phone credits, zero API cost
GET  /test/db                Snapshot of entire DB (founders, roles, candidates, calls, emails)
GET  /api/roles              List all roles (used by dashboard)
GET  /api/roles/{id}/status  Full pipeline status for one role (used by dashboard polling)
GET  /health                 Health check
```

### Quick test commands (PowerShell)

```powershell
# Check DB state
Invoke-RestMethod https://ava-production-cf8f.up.railway.app/test/db | ConvertTo-Json -Depth 5

# Run extraction only (no credits, safe to run anytime)
Invoke-RestMethod -Method Post https://ava-production-cf8f.up.railway.app/test/intake/no-call | ConvertTo-Json -Depth 5

# Run full pipeline (fires real call to Alex at +16199538267)
Invoke-RestMethod -Method Post https://ava-production-cf8f.up.railway.app/test/intake

# Wipe DB clean before demo
python seed.py
```

### Demo flow checklist
1. `python seed.py` — wipe DB clean
2. Open dashboard: https://ava-production-cf8f.up.railway.app
3. Press "Start Demo" on the dashboard to begin scripted playback
4. OR call +1 (775) 256-7153 directly — Ava will do a real intake call
5. Ava calls Alex Chen (+16199538267) automatically
6. Follow-up email lands at anishkumar2002.k@gmail.com
