"""
Main Flask webhook server.
Receives incoming texts from Twilio, generates AI replies, logs to FUB.
"""

import os
import json
from datetime import datetime, timezone
from flask import Flask, request, Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

load_dotenv()

import fub
import ai

app = Flask(__name__)

# Twilio client
twilio_client = TwilioClient(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# In-memory conversation store (keyed by phone number)
# In production you'd use Redis or a database
conversations = {}


BLOCKED_AGENTS = [a.strip().lower() for a in os.getenv("BLOCKED_AGENTS", "").split(",") if a.strip()]

def is_blocked_lead(lead_context: dict) -> bool:
    """Returns True if the lead is assigned to a blocked agent."""
    assigned_to = (lead_context.get("assignedTo") or "").lower()
    return any(blocked in assigned_to for blocked in BLOCKED_AGENTS)

def get_conversation_history(phone: str) -> list:
    return conversations.get(phone, [])


def add_to_history(phone: str, body: str, outgoing: bool):
    if phone not in conversations:
        conversations[phone] = []
    conversations[phone].append({
        "body": body,
        "outgoing": outgoing,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    # Keep last 20 messages only
    conversations[phone] = conversations[phone][-20:]


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "FUB AI Texter", "number": TWILIO_NUMBER}


@app.route("/webhook/incoming", methods=["POST"])
def incoming_sms():
    """
    Twilio calls this endpoint every time a text is received on +18126127398.
    """
    from_number = request.form.get("From", "")
    to_number = request.form.get("To", "")
    body = request.form.get("Body", "").strip()

    print(f"[INCOMING] From: {from_number} | Body: {body}")

    # Look up lead in FUB
    lead = fub.find_lead_by_phone(from_number)

    if lead:
        lead_id = lead["id"]
        # Get full context
        lead_context = fub.get_lead_context(lead_id)
        first_name = lead_context.get("firstName") or lead_context.get("name", "there").split()[0]
        print(f"[FUB] Matched lead: {lead_context.get('name')} (ID: {lead_id}, Stage: {lead_context.get('stage')})")

        # Log incoming text to FUB timeline
        fub.log_text_to_fub(
            person_id=lead_id,
            body=body,
            phone_to=to_number,
            phone_from=from_number,
            is_outgoing=False
        )
    else:
        # Unknown number — create minimal context
        print(f"[FUB] No lead found for {from_number}")
        lead_id = None
        lead_context = {"firstName": "there", "name": "Unknown", "stage": "Unknown", "source": "Unknown", "tags": []}

    # Get conversation history
    history = get_conversation_history(from_number)

    # Add incoming message to history
    add_to_history(from_number, body, outgoing=False)

    # Safety check: never reply to leads assigned to blocked agents
    if lead_id and is_blocked_lead(lead_context):
        assigned_to = lead_context.get("assignedTo", "unknown")
        print(f"[INCOMING] BLOCKED — lead assigned to {assigned_to}, not replying")
        fub.add_note_to_lead(lead_id, f"Text received on Mitchell's number but lead is assigned to {assigned_to}. No auto-reply sent.\nMessage: \"{body}\"")
        return Response(str(MessagingResponse()), mimetype="text/xml")

    # Generate AI reply
    result = ai.generate_reply(lead_context, history, body)
    reply_text = result["reply"]
    is_handoff = result["handoff"]

    print(f"[AI] Reply: {reply_text} | Handoff: {is_handoff}")

    # If handoff needed, flag in FUB
    if is_handoff and lead_id:
        handoff_note = f"⚠️ AI Texter flagged for human follow-up.\nReason: {result.get('handoff_reason', 'Lead requested agent')}\nLast message: \"{body}\""
        fub.add_note_to_lead(lead_id, handoff_note)
        # Move to Active Client stage if they're hot
        hot_keywords = ["ready to buy", "ready to sell", "make an offer", "let's meet", "schedule a showing"]
        if any(kw in body.lower() for kw in hot_keywords):
            fub.update_lead_stage(lead_id, "Active Client")
            print(f"[FUB] Upgraded {lead_context.get('name')} to Active Client")

    # Add outgoing reply to history
    add_to_history(from_number, reply_text, outgoing=True)

    # Log outgoing reply to FUB timeline
    if lead_id:
        fub.log_text_to_fub(
            person_id=lead_id,
            body=reply_text,
            phone_to=from_number,
            phone_from=to_number,
            is_outgoing=True
        )

    # Send reply via Twilio TwiML
    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(str(twiml), mimetype="text/xml")


@app.route("/send", methods=["POST"])
def send_outbound():
    """
    Manually trigger an outbound text to a lead.
    POST JSON: { "person_id": 123 } or { "phone": "+18125551234" }
    Also used for bulk outreach campaigns.
    """
    data = request.get_json() or {}
    person_id = data.get("person_id")
    phone_override = data.get("phone")
    custom_message = data.get("message")  # Optional — if not provided, AI generates opening

    if person_id:
        lead_context = fub.get_lead_context(person_id)
    else:
        lead_context = {"firstName": "there", "name": "Unknown", "stage": "Lead", "source": "Unknown", "tags": []}

    # Find phone number
    phones = lead_context.get("phones", [])
    to_number = phone_override
    if not to_number and phones:
        to_number = phones[0].get("value", "")

    if not to_number:
        return {"error": "No phone number found"}, 400

    # Generate or use provided message
    if custom_message:
        message_body = custom_message
    else:
        message_body = ai.generate_opening_message(lead_context)

    # Send via Twilio
    try:
        msg = twilio_client.messages.create(
            body=message_body,
            from_=TWILIO_NUMBER,
            to=to_number
        )
        print(f"[OUTBOUND] Sent to {to_number}: {message_body} | SID: {msg.sid}")

        # Log to FUB
        if person_id:
            fub.log_text_to_fub(
                person_id=person_id,
                body=message_body,
                phone_to=to_number,
                phone_from=TWILIO_NUMBER,
                is_outgoing=True
            )
            add_to_history(to_number, message_body, outgoing=True)

        return {"status": "sent", "to": to_number, "message": message_body, "sid": msg.sid}

    except Exception as e:
        print(f"[OUTBOUND] Error sending to {to_number}: {e}")
        return {"error": str(e)}, 500


@app.route("/campaign", methods=["POST"])
def run_campaign():
    """
    Send personalized opening texts to a list of FUB leads.
    POST JSON: { "person_ids": [123, 456, 789], "message": "optional override" }
    Only sends to leads assigned to Mitchell Berry.
    """
    import time
    data = request.get_json() or {}
    person_ids = data.get("person_ids", [])
    custom_message = data.get("message")
    results = {"sent": [], "failed": [], "skipped": []}

    for person_id in person_ids:
        lead_context = fub.get_lead_context(person_id)

        # Safety check: never text leads assigned to blocked agents
        if is_blocked_lead(lead_context):
            assigned_to = lead_context.get("assignedTo", "unknown")
            results["skipped"].append({
                "id": person_id,
                "name": lead_context.get("name"),
                "reason": f"BLOCKED — assigned to {assigned_to}"
            })
            print(f"[CAMPAIGN] BLOCKED {lead_context.get('name')} — assigned to {assigned_to}")
            continue

        phones = lead_context.get("phones", [])
        if not phones:
            results["skipped"].append({"id": person_id, "name": lead_context.get("name"), "reason": "no phone"})
            continue

        to_number = phones[0].get("value", "")
        if not to_number:
            results["skipped"].append({"id": person_id, "name": lead_context.get("name"), "reason": "empty phone"})
            continue

        message_body = custom_message or ai.generate_opening_message(lead_context)

        try:
            msg = twilio_client.messages.create(
                body=message_body,
                from_=TWILIO_NUMBER,
                to=to_number
            )
            fub.log_text_to_fub(person_id, message_body, to_number, TWILIO_NUMBER, is_outgoing=True)
            add_to_history(to_number, message_body, outgoing=True)
            results["sent"].append({"id": person_id, "name": lead_context.get("name"), "to": to_number})
            print(f"[CAMPAIGN] Sent to {lead_context.get('name')} ({to_number})")
            time.sleep(1)  # Rate limiting — 1 text/second

        except Exception as e:
            results["failed"].append({"id": person_id, "error": str(e)})
            print(f"[CAMPAIGN] Failed for {person_id}: {e}")

    return {
        "summary": {
            "sent": len(results["sent"]),
            "failed": len(results["failed"]),
            "skipped": len(results["skipped"])
        },
        "details": results
    }


@app.route("/conversations", methods=["GET"])
def list_conversations():
    """View all active in-memory conversations."""
    summary = {}
    for phone, history in conversations.items():
        summary[phone] = {
            "message_count": len(history),
            "last_message": history[-1] if history else None
        }
    return summary


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
