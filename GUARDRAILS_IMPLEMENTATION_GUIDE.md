# Guardrails Implementation Guide

## What You're Getting

Three files to add to your project:

| File | What it does |
|------|-------------|
| `guardrails.py` | **NEW** — the guardrails engine (drop into project root) |
| `models.py` | **UPDATED** — adds `guardrail_rules_json` column to ChatbotContent |
| `main.py` | **UPDATED** — guardrail check in `/chat` + 6 new admin API endpoints |

Additional UI wiring included in this implementation:

| File | What it does |
|------|-------------|
| `templates/admin.html` | **UPDATED** — Tier 2 guardrail UI for existing chatbots **and** Create New Chatbot tab |
| `static/js/admin_scripts.js` | **UPDATED** — Create-tab Tier 2 row add/remove behavior and submission handling |

## How It Works

Every user message goes through two layers of checks **before** it reaches the AI model.

**Tier 1 (System — always on, cannot be disabled):**

| Category | What it catches | Example blocked | Example allowed |
|----------|----------------|-----------------|-----------------|
| Case Data | Case numbers, addresses, DOB, SSN, phone numbers, long case narratives | "Case number DCP-2024-78432" | "What are common case documentation errors?" |
| Safety Decisions | Asking the chatbot to make/validate safety determinations | "Should I remove this child?" | "What are the 19 safety factors?" |
| Off-Topic | Poems, weather, sports, cooking, trivia | "Write me a poem about spring" | "Give me a scenario to practice coaching" |

**Tier 2 (Custom — admin manages from dashboard):**

Admins add rules using **plain English phrases**. No coding, no regex.

Example: Admin types these blocked phrases:
```
write a case note, draft a case note, create case notes
```

The system automatically matches variations like:
- "Write a case note for my visit today" → **BLOCKED**
- "Help me draft the case notes" → **BLOCKED**
- "Write my case note about today" → **BLOCKED**
- "What are the components of good case documentation?" → **ALLOWED**
- "What is a case note?" → **ALLOWED**

It works by stripping filler words (a, the, my, this, etc.) and comparing the core phrases. So "write a case note" and "write my case notes" both normalize to "write case note" and match.

## Setup Steps

### Step 1: Drop in `guardrails.py`

Place it in the same directory as `main.py` and `models.py`. No pip installs needed.

### Step 2: Replace `models.py`

Replace your existing `models.py` with the updated version. The only change is one new column:

```python
guardrail_rules_json = Column(Text, nullable=True, default=None)
```

### Step 3: Run the database migration

The new column needs to be added to your existing database.

**For SQLite (local dev):**
```bash
python -c "
from models import engine
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text('ALTER TABLE chatbot_contents ADD COLUMN guardrail_rules_json TEXT'))
    conn.commit()
print('Migration complete')
"
```

**For PostgreSQL (Render / production):**
```sql
ALTER TABLE chatbot_contents ADD COLUMN guardrail_rules_json TEXT;
```

### Step 4: Replace `main.py`

Replace your existing `main.py` with the updated version. Key changes were made:

1. **Import added** (top of file):
```python
from guardrails import (
    check_input_guardrails, validate_custom_rules, format_guardrail_log_entry,
    add_rule_to_json, remove_rule_from_json, toggle_rule_in_json,
    update_rule_in_json, reorder_rules_in_json, parse_custom_rules
)
```

2. **Guardrail check inserted in `/chat` endpoint** (before `start_time = time.time()`):
   - Runs `check_input_guardrails(user_message, chatbot)` on every message
   - If blocked, returns the redirect message immediately without calling the AI model
   - Does NOT count against the user's daily quota
   - Logs the guardrail trigger category for CQI analytics

3. **Six new admin API endpoints added:**

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/admin/get_guardrail_rules/<code>` | GET | Get all rules for a chatbot |
| `/admin/add_guardrail_rule` | POST | Add a new rule (name + phrases + message) |
| `/admin/update_guardrail_rule` | POST | Edit a rule's name, phrases, or message |
| `/admin/delete_guardrail_rule` | POST | Delete a rule |
| `/admin/toggle_guardrail_rule` | POST | Turn a rule on/off |
| `/admin/reorder_guardrail_rules` | POST | Change the order rules are checked |

4. **Create-tab Tier 2 guardrails are now persisted during chatbot creation (`/admin/upload`):**
   - Reads rule arrays from form fields:
     - `create_guardrail_rule_name[]`
     - `create_guardrail_rule_phrases[]`
     - `create_guardrail_rule_message[]`
   - Validates that each non-empty row has both **name** and **phrases**
   - Builds `guardrail_rules_json` using existing helper `add_rule_to_json(...)`
   - Saves through `ChatbotContent.create_or_update(..., guardrail_rules_json=...)`
   - Keeps one source of truth for Tier 2 rule format (no duplicate rule engine in UI code)

### Step 5: Update Admin UI (`templates/admin.html` + `static/js/admin_scripts.js`)

The Admin page now supports Tier 2 in two places:

1. **Existing chatbot cards (Manage Chatbots tab):**
   - Add / toggle / delete custom guardrail rules via API

2. **Create New Chatbot tab:**
   - Tier 2 section added directly in the creation form
   - Prefilled starter rules included by default:
     - Block case note drafting
     - Block investigation advice
     - Block placement recommendations
     - Block service termination decisions
   - Phrases and redirect-message boxes are larger (System Prompt-like sizing)
   - "Add Another Rule" and per-row "Remove Rule" are supported before save

### Step 6: Test

Quick smoke test after deployment:
```
# Should be BLOCKED (Tier 1 - safety decision)
"Should I remove this child?"

# Should be BLOCKED (Tier 1 - case data)
"Case number DCP-2024-78432"

# Should PASS (legitimate curriculum question)
"What are the 19 safety factors?"
"What are common decision-making errors?"
```

## Admin API Usage

### Adding a rule from the admin page

```javascript
// Example: Add a rule that blocks case note drafting requests
fetch('/admin/add_guardrail_rule', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams({
        chatbot_code: 'SUPCORE',
        rule_name: 'Block case note requests',
        phrases: 'write a case note, draft a case note, create case notes, compose a case note',
        redirect_message: 'This tool cannot draft case notes. For documentation guidance, consult your supervisor.'
    })
});
```

### Getting all rules for a chatbot

```javascript
fetch('/admin/get_guardrail_rules/SUPCORE')
    .then(r => r.json())
    .then(data => {
        // data.rules = [{id, name, phrases, redirect_message, is_active, priority}, ...]
        // data.rule_count = total rules
        // data.active_count = active rules only
    });
```

### Toggling a rule on/off

```javascript
fetch('/admin/toggle_guardrail_rule', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams({
        chatbot_code: 'SUPCORE',
        rule_id: 'rule_1'
    })
});
```

### Deleting a rule

```javascript
fetch('/admin/delete_guardrail_rule', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams({
        chatbot_code: 'SUPCORE',
        rule_id: 'rule_1'
    })
});
```

## Admin UI Status

The admin UI is now implemented in `templates/admin.html` and `static/js/admin_scripts.js` (not just a mockup/future concept).

Implemented UI includes:
- Existing-chatbot guardrail management controls
- Create-tab Tier 2 rule entry with prefilled starter rows
- Larger input boxes for phrases and redirect messages

Reference mock layout:

```
┌─────────────────────────────────────────────────────┐
│  Content Guardrails                                  │
│                                                      │
│  System guardrails (always active):                  │
│  ✓ Case-specific data protection                     │
│  ✓ Safety decision prevention                        │
│  ✓ Off-topic filtering                               │
│                                                      │
│  Custom rules for this chatbot:                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │ ☑ Block case note requests          [Edit] [✕]  │ │
│  │   "write a case note, draft a case note..."     │ │
│  ├─────────────────────────────────────────────────┤ │
│  │ ☑ Block investigation advice        [Edit] [✕]  │ │
│  │   "how should I investigate, what should I..."  │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  [+ Add Rule]                                        │
│                                                      │
│  ┌── Add New Rule ─────────────────────────────────┐ │
│  │ Rule name: ___________________________          │ │
│  │                                                 │ │
│  │ Blocked phrases (comma-separated):              │ │
│  │ ________________________________________        │ │
│  │ ________________________________________        │ │
│  │                                                 │ │
│  │ Message shown when blocked (optional):          │ │
│  │ ________________________________________        │ │
│  │ ________________________________________        │ │
│  │                                                 │ │
│  │ [Save Rule]  [Cancel]                           │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

The admin types phrases in plain English. The system handles everything else.

## Starter Rules (Now Prefilled in Create Tab)

The Create New Chatbot form now preloads starter Tier 2 rules so admins do not need to manually enter them each time.

You can still edit/remove them before saving:

**For DCP chatbots:**
- Name: "Block case note drafting"
- Phrases: `write a case note, draft a case note, create case notes, compose a case note, help me write a progress note, draft a court report`

- Name: "Block investigation advice"
- Phrases: `how should I investigate, what should I do about my investigation, advise me on my investigation, help me with this allegation`

**For Foster Care chatbots:**
- Name: "Block placement recommendations"
- Phrases: `should I place this child, should we move this child, recommend placement for, transfer this child to`

**For Prevention chatbots:**
- Name: "Block service termination decisions"
- Phrases: `should I close services, should we end services, terminate services for, discontinue services for`

## Checklist

- [ ] `guardrails.py` placed in project root
- [ ] `models.py` replaced with updated version
- [ ] Database migration run (ALTER TABLE)
- [ ] `main.py` replaced with updated version
- [ ] `templates/admin.html` updated with Create-tab Tier 2 section
- [ ] `static/js/admin_scripts.js` updated with create-row add/remove logic
- [ ] Smoke test: "Should I remove this child?" returns guardrail message
- [ ] Smoke test: "What are the 19 safety factors?" returns normal response
- [ ] Confirm Create-tab prefilled Tier 2 rules save into `guardrail_rules_json`
- [ ] Confirm blocked Tier 2 prompts return redirect without AI call
