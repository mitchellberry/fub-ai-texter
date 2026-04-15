# FUB AI Texter

AI-powered SMS system for Mitchell Berry | @properties IND
Receives texts via Twilio, generates personalized AI replies using lead data from Follow Up Boss.

---

## How It Works

1. Lead texts your Twilio number
2. Twilio sends the message to this server via webhook
3. Server looks up the lead in FUB by phone number
4. Pulls their name, stage, source, tags, and notes for context
5. Claude AI generates a personalized, conversational reply
6. Reply is sent back via Twilio
7. Both incoming and outgoing texts are logged to the lead's FUB timeline
8. If the lead says they're ready to act (buy/sell/meet), the system flags it in FUB and moves them to Active Client

---

## Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server health check |
| `/webhook/incoming` | POST | Twilio webhook — receives all incoming texts |
| `/send` | POST | Send one outbound text to a lead |
| `/campaign` | POST | Send personalized texts to a list of leads |
| `/conversations` | GET | View active conversation history |

---

## Environment Variables

Set these in Railway (or your .env file locally):

```
TWILIO_ACCOUNT_SID=YOUR_TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN=YOUR_TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER=YOUR_TWILIO_PHONE_NUMBER
FUB_API_KEY=YOUR_FUB_API_KEY
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
AGENT_NAME=Mitchell
BROKERAGE=@properties IND
BLOCKED_AGENTS=Emily Gordon,James Lawrence,Kristin Haire
```

---

## Deploy to Railway

1. Go to https://railway.app and sign in with GitHub
2. Click "New Project" → "Deploy from GitHub repo"
3. Select this repo
4. Add all environment variables above under "Variables"
5. Railway auto-deploys — copy the public URL it gives you
6. Set Twilio webhook: Twilio Console → Phone Numbers → [your Twilio number] → Messaging → Webhook URL = `https://YOUR-RAILWAY-URL/webhook/incoming`

---

## Send a Campaign

```bash
curl -X POST https://YOUR-RAILWAY-URL/campaign \
  -H "Content-Type: application/json" \
  -d '{"person_ids": [123, 456, 789]}'
```

Or with a custom message:
```bash
curl -X POST https://YOUR-RAILWAY-URL/campaign \
  -H "Content-Type: application/json" \
  -d '{"person_ids": [123, 456], "message": "Hey, just checking in — are you still thinking about buying this spring?"}'
```

---

## Handoff Logic

The AI automatically flags a lead for human follow-up and adds a note in FUB when:
- Lead says they want to speak to a person
- Lead is ready to buy/sell/make an offer
- Lead wants to schedule a showing or meeting
- Lead says stop/unsubscribe (opt-out handled automatically)
- AI encounters an error

Hot leads (ready to act) are automatically moved to "Active Client" stage in FUB.
