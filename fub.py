"""
Follow Up Boss API helper
- Look up a lead by phone number
- Pull their name, stage, source, tags, last activity
- Log outgoing/incoming texts back to FUB timeline
"""

import os
import requests
import base64
from datetime import datetime, timezone

FUB_API_KEY = os.getenv("FUB_API_KEY")
BASE_URL = "https://api.followupboss.com/v1"

def _auth():
    token = base64.b64encode(f"{FUB_API_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def find_lead_by_phone(phone_number):
    """
    Search FUB for a person by phone number.
    Returns the person dict or None.
    """
    # Normalize phone — strip non-digits
    digits = "".join(c for c in phone_number if c.isdigit())
    # Try last 10 digits
    short = digits[-10:] if len(digits) >= 10 else digits

    try:
        resp = requests.get(
            f"{BASE_URL}/people",
            headers=_auth(),
            params={"phone": short, "limit": 5},
            timeout=10
        )
        data = resp.json()
        people = data.get("people", [])
        if people:
            return people[0]

        # Fallback: try with area code variations
        resp2 = requests.get(
            f"{BASE_URL}/people",
            headers=_auth(),
            params={"phone": phone_number, "limit": 5},
            timeout=10
        )
        data2 = resp2.json()
        people2 = data2.get("people", [])
        return people2[0] if people2 else None

    except Exception as e:
        print(f"[FUB] Error finding lead by phone: {e}")
        return None


def get_lead_context(person_id):
    """
    Pull full context for a lead: name, stage, source, tags, notes, recent activity.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/people/{person_id}",
            headers=_auth(),
            params={"fields": "name,firstName,lastName,stage,source,tags,emails,phones,background,created,lastActivity,assignedTo"},
            timeout=10
        )
        return resp.json()
    except Exception as e:
        print(f"[FUB] Error getting lead context: {e}")
        return {}


def get_recent_notes(person_id, limit=5):
    """Pull recent notes/activity from FUB for conversation context."""
    try:
        resp = requests.get(
            f"{BASE_URL}/notes",
            headers=_auth(),
            params={"personId": person_id, "limit": limit},
            timeout=10
        )
        data = resp.json()
        return data.get("notes", [])
    except Exception as e:
        print(f"[FUB] Error getting notes: {e}")
        return []


def log_text_to_fub(person_id, body, phone_to, phone_from, is_outgoing=True):
    """
    Log a text message to the FUB timeline.
    Note: FUB logs the record only — does not send the actual text.
    """
    try:
        payload = {
            "personId": person_id,
            "body": body,
            "toNumber": phone_to,
            "fromNumber": phone_from,
            "isOutgoing": is_outgoing,
        }
        resp = requests.post(
            f"{BASE_URL}/textMessages",
            headers=_auth(),
            json=payload,
            timeout=10
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[FUB] Error logging text: {e}")
        return False


def update_lead_stage(person_id, stage):
    """Update a lead's stage in FUB."""
    try:
        resp = requests.put(
            f"{BASE_URL}/people/{person_id}",
            headers=_auth(),
            json={"stage": stage},
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[FUB] Error updating stage: {e}")
        return False


def add_note_to_lead(person_id, note_body):
    """Add a note to a lead's timeline."""
    try:
        resp = requests.post(
            f"{BASE_URL}/notes",
            headers=_auth(),
            json={"personId": person_id, "body": note_body},
            timeout=10
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[FUB] Error adding note: {e}")
        return False
