"""
AI response engine using OpenAI GPT-4o-mini.
Generates personalized, conversational SMS replies based on lead context.
"""

import os
import requests as http_requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = "gpt-4o-mini"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

def call_openai(messages: list, max_tokens: int = 150, temperature: float = 0.75) -> str:
    """Direct HTTP call to OpenAI — avoids SDK connection issues."""
    resp = http_requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={"model": MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
        timeout=20
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")

AGENT_NAME = os.getenv("AGENT_NAME", "Mitchell")
BROKERAGE = os.getenv("BROKERAGE", "@properties IND")

HANDOFF_TRIGGERS = [
    "speak to someone", "i want to talk to someone", "talk to a person", "real person",
    "agent please", "stop texting", "unsubscribe", "opt out",
    "ready to buy", "ready to sell", "make an offer", "sign a contract",
    "let's meet", "can we meet", "schedule a showing", "book a showing",
    "i want to stop", "please stop",
]


def should_handoff(message: str) -> bool:
    msg_lower = message.lower()
    return any(trigger in msg_lower for trigger in HANDOFF_TRIGGERS)


def build_system_prompt(lead_context: dict) -> str:
    first_name = lead_context.get("firstName") or lead_context.get("name", "there").split()[0]
    stage = lead_context.get("stage", "unknown")
    source = lead_context.get("source", "unknown")
    tags = lead_context.get("tags", [])
    background = lead_context.get("background", "")
    tags_str = ", ".join(tags[:8]) if tags else "none"

    return f"""You are a friendly, professional real estate assistant texting on behalf of {AGENT_NAME} at {BROKERAGE} in Evansville, Indiana.

You are texting {first_name}, a lead in the CRM.

Lead context:
- Name: {lead_context.get('name', first_name)}
- Stage: {stage}
- Lead source: {source}
- Tags: {tags_str}
- Background notes: {background or 'none'}

Your job:
- Be warm, brief, and conversational — this is a text message, not an email
- Keep replies to 1-3 sentences max
- Use their first name naturally but not in every message
- Ask one focused question at a time to understand their timeline and needs
- Never be pushy or salesy
- If they seem ready to buy/sell/meet, express enthusiasm and let them know {AGENT_NAME} will reach out personally
- If asked something you don't know, say {AGENT_NAME} will follow up directly
- If asked directly whether you're an AI, be honest
- Never discuss commissions or make specific promises about pricing

Tone: friendly neighbor, not corporate salesperson. Short, natural texts only. No hashtags, no emojis unless they use them first."""


def generate_reply(lead_context: dict, conversation_history: list, incoming_message: str) -> dict:
    """
    Generate an AI reply to an incoming text.
    Returns: { "reply": str, "handoff": bool, "handoff_reason": str }
    """
    if should_handoff(incoming_message):
        first_name = lead_context.get("firstName") or lead_context.get("name", "").split()[0] or ""
        thanks = f" Thanks {first_name}!" if first_name else ""
        return {
            "reply": f"Absolutely! I'll have {AGENT_NAME} reach out to you personally very soon.{thanks}",
            "handoff": True,
            "handoff_reason": f"Lead requested human contact: '{incoming_message}'"
        }

    system_prompt = build_system_prompt(lead_context)

    # Build messages array for OpenAI
    messages = [{"role": "system", "content": system_prompt}]
    for entry in conversation_history[-10:]:
        role = "assistant" if entry.get("outgoing") else "user"
        messages.append({"role": role, "content": entry.get("body", "")})
    messages.append({"role": "user", "content": incoming_message})

    try:
        print(f"[AI] Calling OpenAI with {len(messages)} messages, key ends in ...{OPENAI_API_KEY[-6:]}")
        reply_text = call_openai(messages, max_tokens=150, temperature=0.75)
        print(f"[AI] Success: {reply_text[:60]}")
        return {"reply": reply_text, "handoff": False, "handoff_reason": None}

    except Exception as e:
        print(f"[AI] Error generating reply — TYPE: {type(e).__name__} — MSG: {e}")
        first_name = lead_context.get("firstName") or "there"
        return {
            "reply": f"Hey {first_name}! Thanks for reaching out — are you thinking about buying or selling in the Evansville area?",
            "handoff": False,
            "handoff_reason": None
        }


def generate_opening_message(lead_context: dict) -> str:
    """Generate a personalized first outreach text for a lead."""
    first_name = lead_context.get("firstName") or lead_context.get("name", "").split()[0] or "there"
    source = lead_context.get("source", "")
    tags = lead_context.get("tags", [])

    context_hints = []
    if source and source not in ("<unspecified>", "Unknown"):
        context_hints.append(f"came from {source}")
    if "Buyer" in tags:
        context_hints.append("interested in buying")
    if "Seller" in tags:
        context_hints.append("interested in selling")
    context_str = ", ".join(context_hints) if context_hints else "in our database"

    try:
        return call_openai([
                {"role": "system", "content": f"""You write short, personalized opening text messages for a real estate agent named {AGENT_NAME} at {BROKERAGE} in Evansville, Indiana.
Rules: 1-2 sentences only. Say you are texting on behalf of {AGENT_NAME} — use that exact name, never a placeholder. Ask one simple low-pressure question about their real estate needs or timeline. Sound like a real person. No more than one exclamation mark. Not pushy. Return the text message only, no quotes or labels."""},
                {"role": "user", "content": f"Write an opening text to {first_name}, a lead who is {context_str}."}
            ], max_tokens=100, temperature=0.85)
    except Exception as e:
        print(f"[AI] Error generating opening: {e}")
        return f"Hey {first_name}, this is {AGENT_NAME} with {BROKERAGE} — just wanted to check in and see if you have any real estate questions I can help with?"
