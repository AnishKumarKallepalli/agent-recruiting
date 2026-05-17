"""
Seed / reset script for Ava demo.

Usage:
  python seed.py          — wipe DB and confirm clean state
  python seed.py --check  — just show current DB state, no changes

Run this before every demo recording to start fresh.
"""
import sys
import json
import os
sys.path.insert(0, os.path.dirname(__file__))

from db import get_db

def wipe():
    db = get_db()
    # Delete in FK-safe order
    db.table("emails").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    db.table("calls").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    db.table("candidates").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    db.table("roles").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    db.table("founders").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    print("✅ All tables wiped.")

def check():
    db = get_db()
    tables = ["founders", "roles", "candidates", "calls", "emails"]
    print("\n── DB State ──────────────────────────")
    for t in tables:
        rows = db.table(t).select("*").execute().data
        print(f"  {t:<12} {len(rows)} rows")
        for r in rows:
            if t == "founders":   print(f"    → {r['name']} ({r['phone']})")
            if t == "roles":      print(f"    → {r['title']} @ {r.get('company','?')} [{r['status']}]")
            if t == "candidates": print(f"    → {r['name']} — {r['fit_score']}% fit — status: {r['status']}")
            if t == "calls":      print(f"    → {r['call_type']} | {r['status']} | outcome: {r.get('outcome','—')}")
            if t == "emails":     print(f"    → to: {r['to_email']} | {r['status']}")
    print("──────────────────────────────────────\n")

def show_candidates():
    candidates_path = os.path.join(os.path.dirname(__file__), "data", "candidates.json")
    with open(candidates_path) as f:
        candidates = json.load(f)
    print("\n── Candidates (data/candidates.json) ─")
    for c in candidates:
        print(f"  {c['name']:<20} {c['fit_score']}% fit  📞 {c['phone']}")
        print(f"    {c['current_title']} | {c['location']}")
        print(f"    {c['fit_reason'][:80]}...")
    print("──────────────────────────────────────\n")

if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
        show_candidates()
    else:
        print("\n🧹 Resetting Agent demo database...\n")
        wipe()
        check()
        show_candidates()
        print("Ready for demo. Call +17752567153 to begin.\n")
