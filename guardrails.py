# guardrails.py
# ==============================================================================
# HARNESS ENGINEERING — INPUT GUARDRAILS MODULE
# ==============================================================================
# This module implements a two-tier guardrail system for the chatbot:
#
# TIER 1 (Hardcoded / System-level):
#   - Cannot be disabled from the admin page
#   - Catches case-specific identifying data (names in case context, addresses,
#     case numbers, CONNECTIONS references, child-specific descriptions)
#   - Catches safety-decision queries (users asking the chatbot to make or
#     validate safety determinations for specific cases)
#   - Catches general off-topic queries with zero relation to child welfare
#     or supervisory practice (e.g., "write me a poem", "what's the weather")
#
# TIER 2 (Admin-configurable / Per-chatbot):
#   - Managed from the admin dashboard per chatbot
#   - Custom blocked phrases, program-specific redirect messages,
#     sensitivity keywords unique to a content area
#   - Admin controls the order (priority) in which rules are evaluated
#
# The guardrail check runs BEFORE the message reaches the AI model, ensuring
# that blocked content never leaves the ACS environment.
# ==============================================================================

import re
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Common filler words that should not change Tier 2 match intent.
FILLER_WORDS = {
    "a", "an", "the", "my", "this", "that", "these", "those", "our",
    "your", "their", "his", "her", "its"
}


# ==============================================================================
# TIER 1: SYSTEM-LEVEL GUARDRAILS (Hardcoded — cannot be disabled)
# ==============================================================================

# Category: CASE_DATA
# Detects case-specific identifying information that should never be sent
# to an external AI API. Patterns look for combinations of contextual
# signals (case language + identifying details) rather than isolated names,
# to minimize false positives on legitimate curriculum questions.

CASE_DATA_PATTERNS = [
    # Case numbers / CONNECTIONS references
    r'(?i)\b(?:case\s*(?:number|#|no\.?|id)|connections\s*(?:id|case|number|#))\s*[:\-]?\s*[\w\-]{4,}',
    # Specific address patterns (number + street name)
    r'(?i)\b\d{1,5}\s+(?:west|east|north|south|w\.?|e\.?|n\.?|s\.?)?\s*\d{1,3}(?:st|nd|rd|th)\s+(?:street|st\.?|avenue|ave\.?|place|pl\.?|drive|dr\.?|boulevard|blvd\.?|road|rd\.?)',
    # Full addresses with apartment/apt
    r'(?i)\b\d{1,5}\s+\w+\s+(?:street|avenue|place|drive|boulevard|road)\b.*\b(?:apt|apartment|unit|floor|suite)\b',
    # SCR / State Central Register references
    r'(?i)\b(?:SCR|state\s+central\s+register)\s*(?:number|#|id|report|referral)?\s*[:\-]?\s*\w{3,}',
    # FamilyTeamConferencing / FTC case IDs
    r'(?i)\bFTC\s*(?:case|id|#|number)\s*[:\-]?\s*\w{3,}',
    # ACS-specific case ID formats (e.g., DCP-2024-XXXXX)
    r'(?i)\b(?:DCP|FPS|FC|JJ)\s*[-/]\s*\d{4}\s*[-/]\s*\d{3,}',
]

# Contextual case-data detection: looks for COMBINATIONS of case language
# and personal identifiers (a name alone isn't enough; a name + "my case"
# or "my worker" is a signal)
CASE_CONTEXT_SIGNALS = [
    r'(?i)\bmy\s+(?:case|family|worker|client|child|children|foster\s+child)',
    r'(?i)\bthe\s+(?:family|child|children|mother|father|parent|caretaker|foster\s+parent)\s+(?:I\s+am|I\'m|we\s+are|we\'re)\s+(?:working\s+with|assigned\s+to|investigating)',
    r'(?i)\b(?:I\s+am|I\'m)\s+(?:working\s+on|investigating|assigned\s+to)\s+(?:a|the|this)\s+case',
    r'(?i)\b(?:case\s+)?(?:planner|worker)\s+(?:told|said|reported|observed|noted)\s+that',
    r'(?i)\b(?:during|in|at)\s+(?:my|the|our)\s+(?:last|recent|latest)\s+(?:visit|home\s+visit|contact|interview)',
]

# Personal identifiers that, when combined with case context, indicate
# case-specific data (e.g., "Maria Rodriguez in my case" vs "Maria
# Rodriguez who wrote this curriculum")
PERSONAL_ID_PATTERNS = [
    # Date of birth patterns
    r'(?i)\b(?:DOB|date\s+of\s+birth|born\s+on)\s*(?:is\s+|[:\-]\s*)?\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}',
    # SSN patterns
    r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
    # Phone numbers in case context
    r'(?i)(?:phone|cell|mobile|contact)\s*(?:number|#)?\s*(?:is\s+|[:\-]\s*)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}',
]


# Category: SAFETY_DECISION
# Detects when a user asks the chatbot to make, validate, or recommend a
# safety determination for a specific situation. The chatbot may teach
# ABOUT safety frameworks, but must never BE a safety decision tool.

SAFETY_DECISION_PATTERNS = [
    # Direct decision requests
    r'(?i)\b(?:should\s+I|do\s+I\s+need\s+to|would\s+you\s+recommend(?:\s+I)?)\s+(?:remove|place|file|report|call\s+in|indicate|substantiate|unfound|make\s+(?:a\s+|an\s+)?(?:indicated|substantiated|unfounded)\s+finding)',
    r'(?i)\b(?:is\s+(?:this|the|my)\s+(?:child|family|case|situation))\s+(?:safe|unsafe|at\s+risk|in\s+danger|in\s+immediate\s+danger)',
    r'(?i)\b(?:should|do)\s+(?:this|the)\s+(?:child|children)\s+(?:be\s+)?(?:removed|placed|taken)',
    # Safety factor application to specific cases
    r'(?i)\b(?:is\s+(?:this|my)\s+(?:case|situation|family))\s+(?:a\s+)?(?:safety\s+factor)',
    r'(?i)\b(?:which|what)\s+safety\s+(?:factor|decision|intervention)\s+(?:should|applies|fits|matches)\s+(?:to\s+)?(?:this|my|the)\s+(?:case|family|situation)',
    # Which decision to select
    r'(?i)\b(?:which|what)\s+(?:safety\s+)?(?:decision|finding|determination)\s+should\s+I\s+(?:select|choose|make|pick)\s+(?:for|in|on)\s+(?:this|my|the)\s+(?:case|family|situation)',
    # Removal / placement decision requests
    r'(?i)\b(?:should\s+(?:we|I))\s+(?:safety\s+plan|do\s+a\s+removal|file\s+a\s+petition|make\s+a\s+(?:indicated|substantiated)\s+finding)',
    # Risk assessment application
    r'(?i)\b(?:what\s+(?:is|would\s+be)\s+the\s+risk\s+(?:level|rating|score|assessment))\s+(?:for|in|of)\s+(?:this|my|the)\s+(?:case|family|situation)',
    # Soft language around placement/removal suitability
    r'(?i)\b(?:is|does)\s+(?:this|the|the\s+current)\s+(?:environment|home|placement)\s+(?:seem|still\s+seem|appear)?\s*(?:suitable|appropriate|viable|sustainable)',
    # Euphemisms for removal/placement changes
    r'(?i)\b(?:should\s+we|do\s+we\s+need\s+to|start)\s+(?:look\s+into|looking\s+into|explore|exploring)\s+(?:alternative|different|other)\s+(?:living\s+arrangements|housing|placement|options)',
]


# Category: OFF_TOPIC
# Catches queries that have zero relation to child welfare, supervision,
# or professional development — pure ChatGPT-style general queries.
# This is a lightweight filter; the AI model's system prompt handles
# borderline cases. This catches the obvious ones to save API calls.

OFF_TOPIC_PATTERNS = [
    r'(?i)^(?:write|compose|draft)\s+(?:me\s+)?(?:a\s+)?(?:poem|song|story|essay|joke|recipe|haiku)',
    r'(?i)^(?:what\'?s?\s+(?:the\s+)?(?:weather|temperature|forecast)\s+(?:in|for|at|today|tomorrow))',
    r'(?i)^(?:who\s+won|what\s+(?:is|are)\s+the\s+score|(?:NFL|NBA|MLB|NHL)\s+(?:score|result|standing))',
    r'(?i)^(?:translate|convert)\s+(?:this|the\s+following)\s+(?:to|into)\s+(?:spanish|french|chinese|arabic|korean)',
    r'(?i)^(?:how\s+do\s+(?:I|you)\s+(?:cook|make|bake|prepare)\s+)',
    r'(?i)^(?:tell\s+me\s+(?:a\s+)?(?:joke|fun\s+fact|riddle))',
    r'(?i)^(?:what\s+(?:is|are)\s+(?:the\s+)?(?:capital|population|currency)\s+of\s+)',
]


# ==============================================================================
# REDIRECT MESSAGES
# ==============================================================================
# These are the messages returned to the user when a guardrail triggers.
# They are designed to be professional, non-punitive, and redirect the
# supervisor toward the appropriate resource.

REDIRECT_MESSAGES = {
    "case_data": (
        "**This tool is designed for curriculum-based knowledge retrieval and "
        "should not be used with identifying case information** (names, addresses, "
        "case numbers, or other details specific to a family or individual).\n\n"
        "For case-specific guidance, please consult your direct supervisor."
    ),
    "safety_decision": (
        "**This tool cannot be used to make, validate, or recommend safety "
        "decisions for specific cases.** Safety assessments and decisions must "
        "always be made through proper supervisory channels and documented "
        "through CONNECTIONS.\n\n"
        "For case-specific safety decisions, please consult your supervisor immediately."
    ),
    "off_topic": (
        "I'm designed to help with content related to this learning program. "
        "Your question appears to be outside the scope of the materials I've been "
        "trained on."
    ),
    "custom_rule": (
        "Your message was flagged by a program-specific content guideline. "
        "For case-specific guidance, consult your direct supervisor."
    ),
}


# ==============================================================================
# TIER 2: ADMIN-CONFIGURABLE GUARDRAIL RULES
# ==============================================================================
# These are stored as JSON in the database (ChatbotContent.guardrail_rules_json)
# and can be managed from the admin dashboard.
#
# Rule format:
# {
#     "rules": [
#         {
#             "id": "rule_001",
#             "name": "Block case note requests",
#             "category": "custom",
#             "pattern": "(?i)\\b(?:write|draft|create)\\s+(?:a\\s+)?case\\s+note",
#             "redirect_message": "This tool cannot draft case notes. ...",
#             "is_active": true,
#             "priority": 10
#         }
#     ]
# }

def parse_custom_rules(guardrail_rules_json):
    """
    Parse the JSON guardrail rules stored in the database.
    Returns a list of active rules sorted by priority (lower = higher priority).
    """
    if not guardrail_rules_json:
        return []
    
    try:
        data = json.loads(guardrail_rules_json)
        rules = data.get("rules", [])
        # Filter active rules and sort by priority
        active_rules = [r for r in rules if r.get("is_active", True)]
        # Backward compatibility: if a rule stores plain phrases but no regex
        # pattern, derive one so runtime checks can still evaluate it.
        for rule in active_rules:
            if (not rule.get("pattern")) and rule.get("phrases"):
                rule["pattern"] = _phrases_to_pattern(rule.get("phrases", ""))
        active_rules.sort(key=lambda r: r.get("priority", 100))
        return active_rules
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Failed to parse guardrail rules JSON: {e}")
        return []


def validate_custom_rules(rules_json_string):
    """
    Validate a guardrail rules JSON string before saving to the database.
    Returns (is_valid: bool, error_message: str or None, parsed_rules: list).
    """
    if not rules_json_string or rules_json_string.strip() == "":
        return True, None, []
    
    try:
        data = json.loads(rules_json_string)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {str(e)}", []
    
    if not isinstance(data, dict) or "rules" not in data:
        return False, "JSON must contain a 'rules' array at the top level.", []
    
    rules = data["rules"]
    if not isinstance(rules, list):
        return False, "'rules' must be an array.", []
    
    for i, rule in enumerate(rules):
        # Required fields
        if not rule.get("id"):
            return False, f"Rule at index {i} is missing 'id'.", []
        if not rule.get("name"):
            return False, f"Rule '{rule.get('id', i)}' is missing 'name'.", []
        if not rule.get("pattern") and not rule.get("phrases"):
            return False, (
                f"Rule '{rule.get('id', i)}' must include either 'pattern' "
                "or 'phrases'."
            ), []
        
        # Validate regex pattern
        pattern = rule.get("pattern") or _phrases_to_pattern(rule.get("phrases", ""))
        if not pattern:
            return False, f"Rule '{rule.get('id', i)}' has empty phrases.", []
        try:
            re.compile(pattern)
        except re.error as e:
            return False, f"Rule '{rule['id']}' has an invalid regex pattern: {str(e)}", []
    
    return True, None, rules


def _phrases_to_pattern(phrases_text):
    """
    Convert comma-separated plain-text phrases into a case-insensitive regex.
    Example:
      "write a case note, draft a case note"
    becomes a pattern that matches either phrase with flexible whitespace.
    """
    if not phrases_text:
        return None

    phrases = [p.strip() for p in str(phrases_text).split(",") if p.strip()]
    parts = []
    filler_group = r"(?:a|an|the|my|this|that|these|those|our|your|their|his|her|its)"
    filler_gap = rf"(?:\s+\b{filler_group}\b)*\s+"

    for phrase in phrases:
        # Keep alphanumeric, apostrophe and hyphen; drop other punctuation
        cleaned = re.sub(r"[^\w\s'\-]", " ", phrase.lower())
        raw_words = [w for w in cleaned.split() if w]
        if not raw_words:
            continue

        # Remove filler words so phrase intent is matched, not article choice.
        core_words = [w for w in raw_words if w not in FILLER_WORDS]
        if not core_words:
            core_words = raw_words

        word_parts = [_word_variant_pattern(w) for w in core_words]
        phrase_pattern = r"\b" + filler_gap.join(word_parts) + r"\b"
        parts.append(phrase_pattern)

    if not parts:
        return None
    return rf"(?i)(?:{'|'.join(parts)})"


def _word_variant_pattern(word):
    """Return a regex that tolerates simple singular/plural variants."""
    escaped = re.escape(word)
    if len(word) <= 3:
        return escaped

    # city -> city|cities
    if word.endswith("y") and len(word) > 3:
        stem = re.escape(word[:-1])
        return rf"(?:{escaped}|{stem}ies)"

    # class -> class|classes, match -> match|matches, box -> box|boxes
    if word.endswith(("s", "ss", "sh", "ch", "x", "z")):
        return rf"(?:{escaped}|{escaped}es)"

    # note -> note|notes
    return rf"(?:{escaped}|{escaped}s)"


def build_rules_json(rules_list):
    """Build JSON payload from a list of guardrail rules."""
    return json.dumps({"rules": rules_list}, indent=2)


def add_rule_to_json(existing_json, name, phrases, redirect_message=""):
    """
    Add a rule in the stored guardrail JSON.
    Returns (updated_json, new_rule_id).
    """
    rules = []
    if existing_json:
        try:
            data = json.loads(existing_json)
            rules = data.get("rules", [])
        except json.JSONDecodeError:
            rules = []

    existing_ids = {r.get("id", "") for r in rules}
    counter = 1
    while f"rule_{counter}" in existing_ids:
        counter += 1
    new_id = f"rule_{counter}"

    pattern = _phrases_to_pattern(phrases)
    if not pattern:
        raise ValueError("At least one blocked phrase is required.")

    rules.append({
        "id": new_id,
        "name": (name or "").strip(),
        "category": "custom",
        "phrases": (phrases or "").strip(),
        "pattern": pattern,
        "redirect_message": (redirect_message or "").strip(),
        "is_active": True,
        "priority": len(rules) + 1
    })
    return build_rules_json(rules), new_id


def remove_rule_from_json(existing_json, rule_id):
    """Remove a rule by ID and re-sequence priorities."""
    if not existing_json:
        return None
    try:
        data = json.loads(existing_json)
        rules = data.get("rules", [])
    except json.JSONDecodeError:
        return existing_json

    rules = [r for r in rules if r.get("id") != rule_id]
    for idx, rule in enumerate(rules):
        rule["priority"] = idx + 1

    if not rules:
        return None
    return build_rules_json(rules)


def toggle_rule_in_json(existing_json, rule_id):
    """Toggle rule active state. Returns (updated_json, new_state)."""
    if not existing_json:
        return existing_json, None
    try:
        data = json.loads(existing_json)
        rules = data.get("rules", [])
    except json.JSONDecodeError:
        return existing_json, None

    new_state = None
    for rule in rules:
        if rule.get("id") == rule_id:
            rule["is_active"] = not rule.get("is_active", True)
            new_state = rule["is_active"]
            break

    return build_rules_json(rules), new_state


def update_rule_in_json(existing_json, rule_id, name=None, phrases=None, redirect_message=None):
    """Update editable fields for a specific rule."""
    if not existing_json:
        return existing_json
    try:
        data = json.loads(existing_json)
        rules = data.get("rules", [])
    except json.JSONDecodeError:
        return existing_json

    for rule in rules:
        if rule.get("id") != rule_id:
            continue
        if name is not None:
            rule["name"] = name.strip()
        if phrases is not None:
            rule["phrases"] = phrases.strip()
            rule["pattern"] = _phrases_to_pattern(rule["phrases"])
        elif (not rule.get("pattern")) and rule.get("phrases"):
            rule["pattern"] = _phrases_to_pattern(rule["phrases"])
        if redirect_message is not None:
            rule["redirect_message"] = redirect_message.strip()
        break

    return build_rules_json(rules)


def reorder_rules_in_json(existing_json, rule_ids_in_order):
    """Reorder rules according to supplied rule IDs and re-sequence priorities."""
    if not existing_json:
        return existing_json
    try:
        data = json.loads(existing_json)
        rules = data.get("rules", [])
    except json.JSONDecodeError:
        return existing_json

    by_id = {r.get("id"): r for r in rules}
    ordered = []
    seen = set()
    for rid in rule_ids_in_order:
        if rid in by_id and rid not in seen:
            ordered.append(by_id[rid])
            seen.add(rid)
    # Keep any missing IDs at end in original order
    for rule in rules:
        rid = rule.get("id")
        if rid not in seen:
            ordered.append(rule)

    for idx, rule in enumerate(ordered):
        rule["priority"] = idx + 1
    return build_rules_json(ordered)


# ==============================================================================
# MAIN GUARDRAIL CHECK FUNCTION
# ==============================================================================

def check_input_guardrails(user_message, chatbot=None):
    """
    Run all guardrail checks against a user message.
    
    This function is called from the /chat endpoint BEFORE the message is
    sent to the AI model. It returns a dict with:
    
    {
        "blocked": bool,           # True if the message should be blocked
        "category": str or None,   # "case_data", "safety_decision", "off_topic", "custom_rule"
        "rule_id": str or None,    # For custom rules, the ID of the matched rule
        "rule_name": str or None,  # For custom rules, the name of the matched rule
        "redirect_message": str,   # The message to show the user (only if blocked)
        "matched_pattern": str,    # The pattern that triggered (for logging)
    }
    
    Args:
        user_message: The raw user input string.
        chatbot: The ChatbotContent object (optional; needed for Tier 2 rules).
    
    Returns:
        dict with guardrail check results.
    """
    if not user_message or not user_message.strip():
        return _pass_result()
    
    message = user_message.strip()
    
    # ---- TIER 1: System-level guardrails (always active, cannot be disabled) ----
    
    # Check 1: Case-specific identifying data
    # First check for explicit case identifiers (case numbers, SCR, etc.)
    for pattern in CASE_DATA_PATTERNS:
        match = re.search(pattern, message)
        if match:
            logger.warning(
                f"GUARDRAIL BLOCKED [case_data]: Matched pattern '{pattern}' "
                f"on text: '{message[:80]}...'"
            )
            return _block_result(
                category="case_data",
                redirect_message=REDIRECT_MESSAGES["case_data"],
                matched_pattern=pattern
            )
    
    # Then check for personal identifiers (DOB, SSN, phone) in case context
    for pid_pattern in PERSONAL_ID_PATTERNS:
        if re.search(pid_pattern, message):
            logger.warning(
                f"GUARDRAIL BLOCKED [case_data/personal_id]: Matched pattern "
                f"'{pid_pattern}' on text: '{message[:80]}...'"
            )
            return _block_result(
                category="case_data",
                redirect_message=REDIRECT_MESSAGES["case_data"],
                matched_pattern=pid_pattern
            )
    
    # Check for case-context signals combined with detailed descriptions
    # (A context signal alone doesn't block, but context + lengthy detail does)
    has_case_context = any(
        re.search(p, message) for p in CASE_CONTEXT_SIGNALS
    )
    if has_case_context and len(message) > 200:
        # Long messages with case context signals are likely describing
        # a specific case situation in detail
        logger.warning(
            f"GUARDRAIL BLOCKED [case_data/context]: Case context signal "
            f"detected in long message ({len(message)} chars): '{message[:80]}...'"
        )
        return _block_result(
            category="case_data",
            redirect_message=REDIRECT_MESSAGES["case_data"],
            matched_pattern="case_context_signal + length > 200"
        )
    
    # Check 2: Safety decision queries
    for pattern in SAFETY_DECISION_PATTERNS:
        match = re.search(pattern, message)
        if match:
            logger.warning(
                f"GUARDRAIL BLOCKED [safety_decision]: Matched pattern "
                f"'{pattern}' on text: '{message[:80]}...'"
            )
            return _block_result(
                category="safety_decision",
                redirect_message=REDIRECT_MESSAGES["safety_decision"],
                matched_pattern=pattern
            )
    
    # Check 3: Off-topic queries (lightweight — catches obvious non-CW queries)
    for pattern in OFF_TOPIC_PATTERNS:
        match = re.search(pattern, message)
        if match:
            logger.info(
                f"GUARDRAIL BLOCKED [off_topic]: Matched pattern "
                f"'{pattern}' on text: '{message[:80]}...'"
            )
            return _block_result(
                category="off_topic",
                redirect_message=REDIRECT_MESSAGES["off_topic"],
                matched_pattern=pattern
            )
    
    # ---- TIER 2: Per-chatbot configurable rules (from admin dashboard) ----
    if chatbot:
        custom_rules = parse_custom_rules(
            getattr(chatbot, 'guardrail_rules_json', None)
        )
        for rule in custom_rules:
            try:
                pattern = rule["pattern"]
                if re.search(pattern, message):
                    custom_redirect = rule.get(
                        "redirect_message",
                        REDIRECT_MESSAGES["custom_rule"]
                    )
                    logger.warning(
                        f"GUARDRAIL BLOCKED [custom_rule/{rule['id']}]: "
                        f"Rule '{rule['name']}' matched on text: '{message[:80]}...'"
                    )
                    return _block_result(
                        category="custom_rule",
                        redirect_message=custom_redirect,
                        matched_pattern=pattern,
                        rule_id=rule["id"],
                        rule_name=rule["name"]
                    )
            except (re.error, KeyError) as e:
                logger.error(
                    f"Error evaluating custom guardrail rule '{rule.get('id', '?')}': {e}"
                )
                continue
    
    # ---- All checks passed ----
    return _pass_result()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _pass_result():
    """Return a result indicating the message is allowed through."""
    return {
        "blocked": False,
        "category": None,
        "rule_id": None,
        "rule_name": None,
        "redirect_message": "",
        "matched_pattern": None,
    }


def _block_result(category, redirect_message, matched_pattern,
                  rule_id=None, rule_name=None):
    """Return a result indicating the message is blocked."""
    return {
        "blocked": True,
        "category": category,
        "rule_id": rule_id,
        "rule_name": rule_name,
        "redirect_message": redirect_message,
        "matched_pattern": matched_pattern,
    }


# ==============================================================================
# DEFAULT CUSTOM RULES TEMPLATES
# ==============================================================================
# These are starter rule sets that admins can use as templates when setting
# up guardrails for specific program areas.

def get_default_rules_dcp():
    """Default custom guardrail rules for DCP-related chatbots."""
    return json.dumps({
        "rules": [
            {
                "id": "dcp_001",
                "name": "Block case note drafting",
                "category": "custom",
                "pattern": r"(?i)\b(?:write|draft|create|compose|help\s+me\s+write)\s+(?:a\s+)?(?:case\s+note|progress\s+note|court\s+report|petition|removal\s+request)",
                "redirect_message": (
                    "This tool cannot draft case notes, court reports, or other case-specific "
                    "documents. For case documentation guidance, please consult your supervisor "
                    "and refer to your agency's documentation protocols."
                ),
                "is_active": True,
                "priority": 10
            },
            {
                "id": "dcp_002",
                "name": "Block investigation advice",
                "category": "custom",
                "pattern": r"(?i)\b(?:how\s+should\s+I|what\s+should\s+I\s+do\s+(?:about|with|in))\s+(?:investigate\s+)?(?:this|my|the)\s+(?:investigation|allegation|report|referral|intake)",
                "redirect_message": (
                    "I cannot provide guidance on specific investigations or cases. "
                    "Please consult your supervisor for case-specific direction."
                ),
                "is_active": True,
                "priority": 20
            }
        ]
    }, indent=2)


def get_default_rules_foster_care():
    """Default custom guardrail rules for Foster Care-related chatbots."""
    return json.dumps({
        "rules": [
            {
                "id": "fc_001",
                "name": "Block placement recommendations",
                "category": "custom",
                "pattern": r"(?i)\b(?:should|can|do)\s+(?:I|we)\s+(?:place|move|transfer|discharge)\s+(?:this|the|my)\s+(?:child|children|youth|foster\s+child)",
                "redirect_message": (
                    "This tool cannot make placement or discharge recommendations for specific "
                    "children or families. Placement decisions must be made through your "
                    "supervisory chain and in accordance with agency policy."
                ),
                "is_active": True,
                "priority": 10
            }
        ]
    }, indent=2)


def get_default_rules_prevention():
    """Default custom guardrail rules for Prevention-related chatbots."""
    return json.dumps({
        "rules": [
            {
                "id": "prev_001",
                "name": "Block service termination decisions",
                "category": "custom",
                "pattern": r"(?i)\b(?:should|can|do)\s+(?:I|we)\s+(?:close|terminate|end|discontinue)\s+(?:services?|the\s+case|this\s+case)\s+(?:for|with)",
                "redirect_message": (
                    "This tool cannot advise on service termination decisions for specific "
                    "families. Service closure decisions must follow your agency's protocols "
                    "and be discussed with your supervisor."
                ),
                "is_active": True,
                "priority": 10
            }
        ]
    }, indent=2)


# ==============================================================================
# GUARDRAIL ANALYTICS
# ==============================================================================
# Helper function to format guardrail trigger data for admin reporting.

def format_guardrail_log_entry(user_id, program_code, guardrail_result):
    """
    Create a structured log entry for a guardrail trigger.
    This can be stored in the database or sent to an analytics pipeline.
    """
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "program_code": program_code,
        "category": guardrail_result.get("category"),
        "rule_id": guardrail_result.get("rule_id"),
        "rule_name": guardrail_result.get("rule_name"),
        "matched_pattern": guardrail_result.get("matched_pattern"),
        # NOTE: We intentionally do NOT log the user's message content
        # when a guardrail triggers on case data, to avoid storing the
        # very data we're trying to protect.
    }
