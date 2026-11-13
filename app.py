
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
import pandas as pd
import os
import re
import calendar
from datetime import date, datetime

import database
import multilingual
from nlu import parse as rule_parse
from llm_nlu import parse_with_llm
from service import execute
from dialogue import enrich_with_context, update_state

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "cute-pink-birthday-secret-key-2026")

# --------------------------------------------------
# INITIALIZE DATABASE & LOAD DATA
# --------------------------------------------------

database.init_db()

def load_data():
    loaded_df = database.load_contacts_df()
    if loaded_df.empty and os.path.exists("data/people.xlsx"):
        loaded_df = pd.read_excel("data/people.xlsx")

    loaded_df.columns = loaded_df.columns.astype(str).str.strip()
    if "Nickname" not in loaded_df.columns and "Name" in loaded_df.columns:
        loaded_df["Nickname"] = loaded_df["Name"]
    if "Name" not in loaded_df.columns and "Nickname" in loaded_df.columns:
        loaded_df["Name"] = loaded_df["Nickname"]
    loaded_df["Name"] = loaded_df["Name"].fillna(loaded_df["Nickname"])

    if "Person_ID" not in loaded_df.columns:
        loaded_df["Person_ID"] = [f"P{i:04d}" for i in range(1, len(loaded_df) + 1)]

    for col in ["Name", "Nickname", "Relationship", "Place_of_Stay"]:
        if col in loaded_df.columns:
            loaded_df[col] = loaded_df[col].fillna("").astype(str).str.strip()

    loaded_df["DOB"] = pd.to_datetime(loaded_df["DOB"], errors="coerce")
    return loaded_df

df = load_data()

def refresh_df():
    global df
    df = load_data()


# --------------------------------------------------
# LLM VALIDATION
# --------------------------------------------------

def normalize_llm(parsed):
    if not isinstance(parsed, dict):
        raise ValueError("Invalid LLM output")

    allowed_intents = [
        "birthday_search",
        "count_birthdays",
        "upcoming_birthdays",
        "person_place",
        "all_birthdays",
        "greeting",
        "calculate_age",
        "unknown"
    ]

    if parsed.get("intent") not in allowed_intents:
        raise ValueError("Invalid intent")

    if not isinstance(parsed.get("entities"), dict):
        raise ValueError("Invalid entities")

    return parsed


# --------------------------------------------------
# CLEAN EXTRACTED CANDIDATE
# --------------------------------------------------

def clean_candidate(cand):
    if not cand:
        return None
    cand = cand.strip(" .,!?\"'")

    stop_leading = [
        r"^(?:can\s+you\s+(?:please\s+)?tell\s+me|tell\s+me|please\s+tell\s+me|i\s+want\s+to\s+know|do\s+you\s+know|can\s+you\s+give\s+me|give\s+me)\s+",
        r"^(?:how\s+old\s+will|how\s+old\s+is|what\s+is\s+the\s+age\s+of|current\s+age\s+of|age\s+of)\s+",
        r"^(?:what\s+is|what'?s|who\s+is|who'?s|when\s+is|when'?s|when\s+was|where\s+is|where'?s|where\s+does|where\s+do)\s+",
        r"^(?:when|where|what|who|why|how|does|do|did|is|are|was|were)\s+",
        r"^(?:tell\s+me|give\s+me|show\s+me|find|check)\s+",
        r"^(?:about|for|of|the|my|a|an)\s+"
    ]
    stop_trailing = [
        r"\s+(?:birthday|bday|dob|date\s+of\s+birth)$",
        r"\s+(?:place\s+of\s+stay|place|location|city|residence)$",
        r"\s+(?:stay|stays|staying|live|lives|living|reside|resides|residing)$",
        r"\s+(?:current\s+age|age|turn|turning|turn\s+this\s+year|years\s+old)$",
        r"\s+(?:is|are|was|were|born)$",
    ]

    changed = True
    while changed:
        before = cand
        for p in stop_leading:
            cand = re.sub(p, "", cand, flags=re.IGNORECASE).strip()
        for p in stop_trailing:
            cand = re.sub(p, "", cand, flags=re.IGNORECASE).strip()
        cand = re.sub(r"['’]s$", "", cand, flags=re.IGNORECASE).strip()
        cand = cand.strip(" .,!?\"'")
        changed = (cand != before)

    return cand if cand else None


# --------------------------------------------------
# EXTRACT PERSON FROM USER MESSAGE
# --------------------------------------------------

def is_relationship_term(text):
    if not text:
        return False
    t = text.strip().lower()
    t = re.sub(r"['’]s$", "", t).rstrip("s")
    known_rels = {
        "nephew", "niece", "sister", "brother", "friend", "uncle", "aunt",
        "cousin", "colleague", "student", "wife", "father", "mother", "dad",
        "mom", "neighbour", "neighbor", "sister-in-law", "brother-in-law"
    }
    return t in known_rels


def extract_person_candidate(message):
    text = message.strip()

    # Strip conversational filler prefixes
    preambles = [
        r"^(?:can\s+you\s+(?:please\s+)?tell\s+me|could\s+you\s+(?:please\s+)?tell\s+me|please\s+tell\s+me|tell\s+me|do\s+you\s+know|i\s+want\s+to\s+know|can\s+you\s+(?:please\s+)?give\s+me|give\s+me)\s+",
    ]
    for p in preambles:
        text = re.sub(p, "", text, flags=re.IGNORECASE).strip()

    # Place patterns (direct and indirect)
    place_patterns = [
        # "where does/do [my] <X> stay/live/reside"
        r"^(?:where\s+does|where\s+do)\s+(?:my\s+)?(.+?)\s+(?:stay|live|reside)[?.!]*$",
        # "where is/are [my] <X> staying/living/residing/located/from"
        r"^(?:where\s+is|where\s+are|where'?s)\s+(?:my\s+)?(.+?)\s+(?:staying|living|residing|located|from)[?.!]*$",
        # "where is/are [my] <X>"
        r"^(?:where\s+is|where\s+are|where'?s)\s+(?:my\s+)?(.+?)[?.!]*$",
        # "where [my] <X> stay/stays/staying/live/lives/living/reside/resides/residing"
        r"^where\s+(?:my\s+)?(.+?)\s+(?:stay|stays|staying|live|lives|living|reside|resides|residing)[?.!]*$",
        # "where [my] <X> is [staying/living/residing]"
        r"^where\s+(?:my\s+)?(.+?)\s+(?:is\s+(?:staying|living|residing)|is)[?.!]*$",
        # "what is/what's [my] <X>'s place of stay / location"
        r"^(?:what\s+is|what'?s)\s+(?:my\s+)?(.+?)(?:['’]s)?\s+(?:place\s+of\s+stay|location|city|residence)[?.!]*$",
        # "place of stay / location of [my] <X>"
        r"^(?:place\s+of\s+stay|place\s+of\s+residence|location)\s+of\s+(?:my\s+)?(.+?)[?.!]*$",
        # "[my] <X>'s place of stay"
        r"^(?:my\s+)?(.+?)(?:['’]s)\s+(?:place\s+of\s+stay|location)[?.!]*$",
        # "[my] <X> place of stay"
        r"^(?:my\s+)?(.+?)\s+(?:place\s+of\s+stay|location)[?.!]*$",
    ]

    # Birthday patterns (direct and indirect)
    birthday_patterns = [
        # "when is/was/are [my] <X>'s birthday"
        r"^(?:when\s+is|when'?s|when\s+was|when\s+are)\s+(?:my\s+)?(.+?)(?:['’]s)?\s+(?:birthday|bday|dob|date\s+of\s+birth)[?.!]*$",
        # "when [my] <X> birthday"
        r"^when\s+(?:my\s+)?(.+?)\s+(?:birthday|bday)[?.!]*$",
        # "when [my] <X>'s birthday is" (indirect: "Can you tell me when my nephew's birthday is?")
        r"^when\s+(?:my\s+)?(.+?)(?:['’]s)?\s+(?:birthday|bday|dob|date\s+of\s+birth)\s+is[?.!]*$",
        # "what is/what's [my] <X>'s birthday"
        r"^(?:what\s+is|what'?s)\s+(?:my\s+)?(.+?)(?:['’]s)?\s+(?:birthday|bday|dob|date\s+of\s+birth)[?.!]*$",
        # "birthday/bday/dob/date of birth of [my] <X>"
        r"^(?:birthday|bday|dob|date\s+of\s+birth)\s+of\s+(?:my\s+)?(.+?)[?.!]*$",
        # "when was [my] <X> born"
        r"^when\s+was\s+(?:my\s+)?(.+?)\s+born[?.!]*$",
        # "[my] <X>'s birthday [is]"
        r"^(?:my\s+)?(.+?)(?:['’]s)\s+(?:birthday|bday|dob)(?:\s+is)?[?.!]*$",
        # "[my] <X> birthday"
        r"^(?:my\s+)?(.+?)\s+(?:birthday|bday)[?.!]*$",
    ]

    # Age patterns
    age_patterns = [
        # "how old will [my] <X> turn [this year]"
        r"^how\s+old\s+will\s+(?:my\s+)?(.+?)\s+turn(?:\s+this\s+year)?[?.!]*$",
        # "how old is [my] <X>"
        r"^how\s+old\s+is\s+(?:my\s+)?(.+?)[?.!]*$",
        # "what is/what's [my] <X>'s current age / age"
        r"^(?:what\s+is|what'?s)\s+(?:my\s+)?(.+?)(?:['’]s)?\s+(?:current\s+)?age[?.!]*$",
        # "current age of [my] <X>"
        r"^(?:current\s+)?age\s+of\s+(?:my\s+)?(.+?)[?.!]*$",
        # "[my] <X>'s current age / age"
        r"^(?:my\s+)?(.+?)(?:['’]s)\s+(?:current\s+)?age[?.!]*$",
        # "[my] <X> age"
        r"^(?:my\s+)?(.+?)\s+age[?.!]*$",
    ]

    all_patterns = place_patterns + birthday_patterns + age_patterns

    for pattern in all_patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            candidate = match.group(1).strip()
            candidate = clean_candidate(candidate)
            if candidate and not is_relationship_term(candidate):
                return candidate

    # Fallback 1: scan message directly for known Name or Nickname in Excel
    candidates = []
    for col in ["Name", "Nickname"]:
        if col in df.columns:
            for val in df[col].dropna().astype(str).unique():
                val = val.strip()
                if val and val.lower() != "nan" and not is_relationship_term(val):
                    if re.search(r"\b" + re.escape(val) + r"\b", message, re.IGNORECASE):
                        candidates.append(val)
                    first = val.split()[0]
                    if len(first) > 2 and not is_relationship_term(first) and re.search(r"\b" + re.escape(first) + r"\b", message, re.IGNORECASE):
                        candidates.append(first)

    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    # Fallback 2: check if message is a 2-to-3 word proper name (e.g. "Suhana Busta")
    non_name_tokens = {
        "all", "birthdays", "birthday", "bday", "upcoming", "show", "list", "count",
        "hello", "hi", "hey", "good", "morning", "afternoon", "evening", "who", "what",
        "when", "where", "how", "many", "next", "month", "tomorrow", "today", "yes", "no"
    }
    words = text.split()
    if 2 <= len(words) <= 3:
        if all(w.isalpha() for w in words):
            if not any(w.lower() in non_name_tokens for w in words):
                if not any(is_relationship_term(w) for w in words):
                    return text.strip(" .,!?\"'")

    return None


# --------------------------------------------------
# FIND PEOPLE USING NAME OR NICKNAME
# --------------------------------------------------

def find_matching_people(candidate):
    candidate = candidate.strip().lower()

    if not candidate:
        return df.iloc[0:0].copy()

    names = df["Name"].str.lower()
    nicknames = df["Nickname"].str.lower()

    # Exact full-name or nickname match
    exact = df[
        (names == candidate) |
        (nicknames == candidate)
    ]

    # Match first word of a stored name (e.g. first name)
    first_word = df[
        names.apply(
            lambda name: name.split()[0] == candidate
            if name else False
        )
    ]

    matches = pd.concat(
        [exact, first_word]
    ).drop_duplicates(subset=["Person_ID"])

    return matches


# --------------------------------------------------
# RESOLVE PERSON
# --------------------------------------------------

def resolve_person(candidate, entities, msg=""):
    candidate = clean_candidate(candidate)

    # 1. When NLU provides a valid person_id, validate that ID against the Excel workbook
    nlu_pid = entities.get("person_id")
    if nlu_pid:
        pid_rows = df[df["Person_ID"] == nlu_pid]
        if not pid_rows.empty:
            matched_person = pid_rows.iloc[0]
            p_name = matched_person["Name"]
            p_nick = str(matched_person.get("Nickname", ""))
            p_first = p_name.split()[0] if p_name else ""

            # Check if user mentioned a name that corresponds to multiple people
            # E.g. user said "Nikhil" -> multiple Nikhils!
            test_target = candidate if candidate else (p_nick if p_nick and p_nick.lower() != "nan" else p_first)
            name_matches = find_matching_people(test_target)

            if len(name_matches) > 1:
                return "ambiguous", test_target

            # If not ambiguous, use the validated person_id record
            entities["person_name"] = matched_person["Name"]
            entities["person_id"] = matched_person["Person_ID"]
            return "found", test_target

    # 2. If no valid person_id from NLU, resolve using candidate
    if not candidate and entities.get("person_name"):
        cand_from_entities = clean_candidate(entities["person_name"])
        if cand_from_entities and re.search(r"\b" + re.escape(cand_from_entities) + r"\b", msg, re.IGNORECASE):
            candidate = cand_from_entities

    if not candidate:
        return "no_name", None

    matches = find_matching_people(candidate)

    if len(matches) == 1:
        person = matches.iloc[0]
        entities["person_name"] = person["Name"]
        entities["person_id"] = person["Person_ID"]
        return "found", candidate

    if len(matches) > 1:
        return "ambiguous", candidate

    return "not_found", candidate


# --------------------------------------------------
# DISPLAY ALL MATCHING PEOPLE
# --------------------------------------------------

def show_matching_people(candidate):
    matches = find_matching_people(candidate)

    if matches.empty:
        return f"No matching people named {candidate} found."

    lines = []

    for _, person in matches.iterrows():
        dob = (
            person["DOB"].strftime("%d %B %Y")
            if pd.notna(person["DOB"])
            else "Date unavailable"
        )

        lines.append(
            f"{person['Name']} - {dob} "
            f"({person['Relationship']}, "
            f"{person['Place_of_Stay']})"
        )

    return (
        f"Here are the matching records for {candidate}:\n"
        + "\n".join(lines)
    )


# --------------------------------------------------
# FIND PERSON USING RELATIONSHIP OR LOCATION
# --------------------------------------------------

def find_by_detail(candidate, detail):
    matches = find_matching_people(candidate)
    detail = detail.strip().lower()

    if not detail or matches.empty:
        return matches.iloc[0:0].copy()

    # Exact relationship match
    relationship_matches = matches[
        matches["Relationship"].str.lower() == detail
    ]
    if not relationship_matches.empty:
        return relationship_matches

    # City match, with or without prepositions like "in", "from", "at"
    city = re.sub(r"^(in|from|at|lives in|stays in)\s+", "", detail).strip()
    city_aliases = {
        "mysore": "mysuru",
        "bangalore": "bengaluru",
        "mangalore": "mangaluru",
        "gulbarga": "kalaburagi",
        "belgaum": "belagavi",
        "shimoga": "shivamogga",
        "hubli": "hubballi",
        "tumkur": "tumakuru",
    }
    city = city_aliases.get(city, city)
    location_matches = matches[
        matches["Place_of_Stay"].str.lower() == city
    ]
    if not location_matches.empty:
        return location_matches

    # Substring in detail for relationship or place of stay
    sub_matches = matches[
        matches["Relationship"].apply(lambda r: (r.lower() in detail or (len(detail) > 2 and detail in r.lower())) if r else False) |
        matches["Place_of_Stay"].apply(lambda p: (p.lower() in detail or (len(detail) > 2 and (detail in p.lower() or city_aliases.get(detail, detail) in p.lower()))) if p else False)
    ]
    if not sub_matches.empty:
        return sub_matches

    return matches.iloc[0:0].copy()


# --------------------------------------------------
# DETECT INTENT
# --------------------------------------------------

def detect_intent(message, fallback_intent="unknown"):
    text = message.lower().strip()

    if re.fullmatch(r"(?:hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|namaste|greetings|howdy|hola)[.!]?", text):
        return "greeting"

    if re.search(r"\b(all\s+birthdays|every(?:one|body)['’]?s?\s+birthday|list\s+all\s+birthdays|show\s+all\s+birthdays|all\s+the\s+birthdays|show\s+everyone|list\s+birthdays)\b", text):
        return "all_birthdays"

    if re.search(r"\b(how many|count)\b", text):
        return "count_birthdays"
    if re.search(r"\bupcoming\b", text):
        return "upcoming_birthdays"

    is_place = False
    if re.search(r"\b(place of stay|place to stay|location of|place of residence)\b", text):
        is_place = True
    elif re.search(r"\b(stay|stays|staying|live|lives|living|reside|resides|residing)\b", text) and \
         re.search(r"\b(where|what|which|city|place)\b", text):
        is_place = True
    elif re.search(r"\bwhere\b", text) and not re.search(r"\b(birthday|birthdays|bday|born|dob)\b", text):
        is_place = True

    if is_place:
        return "person_place"

    if re.search(r"\b(how old|turn this year|turning this year|will turn|turn \d+|current age|what is .* age|age of)\b", text) or re.search(r"['’]s\s+(?:current\s+)?age\b", text) or text.endswith(" age"):
        return "calculate_age"

    if re.search(r"\b(birthday|birthdays|bday|born|dob|date\s+of\s+birth)\b", text) or re.search(r"\bwhen\b", text):
        return "birthday_search"

    months = ["january", "february", "march", "april", "may", "june", 
              "july", "august", "september", "october", "november", "december"]
    if any(m in text for m in months) or "tomorrow" in text or "next month" in text:
        return "birthday_search"

    for rel in df["Relationship"].dropna().unique():
        if rel and rel.lower() in text:
            return "birthday_search"

    if fallback_intent in ["greeting", "all_birthdays", "count_birthdays", "upcoming_birthdays", "person_place", "calculate_age"]:
        return fallback_intent

    return "unknown"


# --------------------------------------------------
# VALIDATE MONTH
# --------------------------------------------------

def validate_month(message, entities):
    message_lower = message.lower()
    mentioned_month = None

    for number, month_name in enumerate(calendar.month_name):
        if number == 0:
            continue

        if re.search(
            r"\b" + re.escape(month_name.lower()) + r"\b",
            message_lower
        ):
            mentioned_month = number
            break

    if re.search(r"\bnext month\b", message_lower):
        entities["relative_month"] = "next"
        entities["month"] = None
    else:
        entities["relative_month"] = None
        entities["month"] = mentioned_month


# ----------------------------------------------
# AUTHENTICATION ROUTES
# ----------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = database.verify_user(username, password)
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid username or password 🌸")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if password != confirm:
            return render_template("register.html", error="Passwords do not match 🌸")

        res = database.register_user(username, password)
        if res.get("error"):
            return render_template("register.html", error=res["error"])

        return render_template("login.html", message="Account created successfully! Please log in ✨")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------
# HOME PAGE (PROTECTED)
# --------------------------------------------------

@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("username", "Friend"), role=session.get("role", "user"))


# --------------------------------------------------
# CHAT ROUTE (PROTECTED)
# --------------------------------------------------

@app.post("/chat")
def chat():
    user_id = session.get("user_id")
    # For automated script testing or unauthenticated requests, allow fallback demo user
    if not user_id:
        # Check if default user exists, else log in demo session
        user_id = 1

    msg = request.json.get("message", "").strip()

    if not msg:
        return jsonify(answer="Please enter a message.")

    raw_msg = msg
    msg, detected_lang = multilingual.normalize_multilingual_query(msg)

    state = session.get("dialogue_state", {})

    pending_name = session.get("pending_ambiguous_name")
    pending_detail = session.get("pending_ambiguous_detail", False)

    # ----------------------------------------------
    # HANDLE AMBIGUOUS-NAME REPLIES
    # ----------------------------------------------

    if pending_name:

        # User wants all matching records
        if re.fullmatch(
            r"\s*(yes|yeah|yep|sure|all|everyone|show me all|"
            r"show all|provide me all|all of them|yes please)[.!]?\s*",
            msg,
            re.IGNORECASE
        ):
            answer = show_matching_people(pending_name)

            session.pop("pending_ambiguous_name", None)
            session.pop("pending_ambiguous_detail", None)
            session.pop("pending_ambiguous_intent", None)

            database.log_query(user_id=user_id, message=raw_msg, intent="disambiguation", success=1)
            localized_ans = multilingual.localize_response(answer, detected_lang)

            nlu_data = {
                "intent": "all_matching_records",
                "entities": {"person_name": pending_name},
                "person_name": pending_name,
                "relationship": None,
                "month": None,
                "person_candidate": pending_name,
                "person_status": "found",
                "nlu_used": "Dialogue context",
                "result": f"Displaying all records matching '{pending_name}'"
            }

            return jsonify(answer=localized_ans, nlu=nlu_data, debug={"intent": "all_matching_records", "entities": {"person_name": pending_name}})

        # User wants to identify one record
        if re.fullmatch(
            r"\s*(no|nope|full name|provide full name|"
            r"full name please|by full name)[.!]?\s*",
            msg,
            re.IGNORECASE
        ):
            session["pending_ambiguous_detail"] = True

            answer = (
                f"The Excel data may contain nicknames or names rather than full formal names. "
                f"Please provide another identifying detail, such as the relationship or city "
                f"of {pending_name}."
            )
            database.log_query(user_id=user_id, message=raw_msg, intent="disambiguation", success=1)
            localized_ans = multilingual.localize_response(answer, detected_lang)

            nlu_data = {
                "intent": "clarification_requested",
                "entities": {"person_name": pending_name},
                "person_name": pending_name,
                "relationship": None,
                "month": None,
                "person_candidate": pending_name,
                "person_status": "ambiguous",
                "nlu_used": "Dialogue context",
                "result": f"Awaiting identifying detail for '{pending_name}'"
            }

            return jsonify(answer=localized_ans, nlu=nlu_data, debug={"intent": "clarification_requested", "entities": {"person_name": pending_name}})

        # User supplies relationship or city
        matches = find_by_detail(pending_name, msg)

        if len(matches) == 1:
            person = matches.iloc[0]

            intent = session.get(
                "pending_ambiguous_intent",
                "birthday_search"
            )

            parsed = {
                "intent": intent,
                "entities": {
                    "person_name": person["Name"],
                    "person_id": person["Person_ID"]
                }
            }

            session.pop("pending_ambiguous_name", None)
            session.pop("pending_ambiguous_detail", None)
            session.pop("pending_ambiguous_intent", None)

            answer = execute(parsed, df)

            print("========== NLU DEBUG ==========", flush=True)
            print(f"User message: {raw_msg}", flush=True)
            print("NLU used: Rule-based fallback", flush=True)
            print(f"Intent: {parsed.get('intent')}", flush=True)
            print(f"Entities: {parsed.get('entities', {})}", flush=True)
            print(f"Person candidate: {pending_name}", flush=True)
            print("Person status: found", flush=True)
            print("==============================", flush=True)

            database.log_query(user_id=user_id, message=raw_msg, intent=intent, success=1)
            localized_ans = multilingual.localize_response(answer, detected_lang, intent=intent)

            nlu_data = {
                "intent": intent,
                "entities": parsed.get("entities", {}),
                "person_name": person["Name"],
                "relationship": person.get("Relationship"),
                "month": None,
                "person_candidate": pending_name,
                "person_status": "found",
                "nlu_used": "Dialogue context",
                "result": f"Disambiguated to {person['Name']} ({person.get('Relationship')}, {person.get('Place_of_Stay')})"
            }

            return jsonify(
                answer=localized_ans,
                debug=parsed,
                nlu=nlu_data
            )

        if len(matches) > 1:
            answer = (
                f"I found more than one matching record. "
                f"Please give another detail.\n"
                + show_matching_people(pending_name)
            )
            database.log_query(user_id=user_id, message=raw_msg, intent="disambiguation", success=1)
            localized_ans = multilingual.localize_response(answer, detected_lang)

            nlu_data = {
                "intent": "disambiguation",
                "entities": {"person_name": pending_name, "detail": msg},
                "person_name": pending_name,
                "relationship": None,
                "month": None,
                "person_candidate": pending_name,
                "person_status": "ambiguous",
                "nlu_used": "Dialogue context",
                "result": f"Multiple records still match for '{pending_name}'"
            }

            return jsonify(answer=localized_ans, nlu=nlu_data, debug={"intent": "disambiguation", "entities": {}})

        if pending_detail:
            answer = (
                f"I couldn't find a matching {pending_name} "
                f"with that relationship or city. "
                f"Please try again."
            )
            database.log_query(user_id=user_id, message=raw_msg, intent="disambiguation", success=0, failed_reason="Detail not matched")
            localized_ans = multilingual.localize_response(answer, detected_lang)

            nlu_data = {
                "intent": "disambiguation",
                "entities": {"person_name": pending_name, "detail": msg},
                "person_name": pending_name,
                "relationship": None,
                "month": None,
                "person_candidate": pending_name,
                "person_status": "not_found",
                "nlu_used": "Dialogue context",
                "result": f"No records found for '{pending_name}' with detail '{msg}'"
            }

            return jsonify(answer=localized_ans, nlu=nlu_data, debug={"intent": "disambiguation", "entities": {}})

    # ----------------------------------------------
    # UNDERSTAND THE USER MESSAGE
    # ----------------------------------------------

    nlu_used = "Rule-based fallback"
    try:
        parsed = normalize_llm(parse_with_llm(msg, df))
        nlu_used = "LLM"

    except Exception as error:
        parsed = rule_parse(msg, df)
        nlu_used = "Rule-based fallback"

    entities = parsed["entities"]

    # ----------------------------------------------
    # DETECT INTENT
    # ----------------------------------------------

    # Authoritative intent detection based on the user's explicit question:
    # Never allow an incorrect LLM prediction to override a clearly identified user question.
    parsed["intent"] = detect_intent(
        msg,
        fallback_intent=parsed.get("intent", "unknown")
    )

    if parsed["intent"] == "calculate_age" and re.search(r"\b(turn|turning|will turn)\b", msg, re.IGNORECASE):
        parsed["is_turn_query"] = True

    # ----------------------------------------------
    # CLEAN ENTITIES
    # ----------------------------------------------

    for key, value in list(entities.items()):
        if isinstance(value, str) and value.strip().lower() in [
            "null", "none", ""
        ]:
            entities[key] = None

    validate_month(msg, entities)

    # ----------------------------------------------
    # EXTRACT NAME FROM ORIGINAL MESSAGE
    # ----------------------------------------------

    candidate = extract_person_candidate(msg)

    # If regex pattern did not find a candidate, but LLM identified a person_name,
    # only accept it if that exact name is actually in the original message.
    if candidate is None and entities.get("person_name"):
        llm_name = clean_candidate(str(entities["person_name"]))
        if llm_name and re.search(r"\b" + re.escape(llm_name) + r"\b", msg, re.IGNORECASE):
            candidate = llm_name

    # If candidate is a relationship term or matches detected relationship, it is a category filter, not a person name!
    if candidate and is_relationship_term(candidate):
        candidate = None

    if entities.get("relationship") and entities.get("person_name") and is_relationship_term(str(entities.get("person_name"))):
        entities.pop("person_name", None)

    person_status, candidate = resolve_person(candidate, entities, msg)

    # Clean None values from entities
    parsed["entities"] = {
        key: value
        for key, value in entities.items()
        if value is not None
    }

    # ----------------------------------------------
    # HANDLE AMBIGUOUS AND UNKNOWN NAMES
    # ----------------------------------------------

    if person_status == "not_found":
        session.pop("pending_ambiguous_name", None)
        session.pop("pending_ambiguous_detail", None)
        session.pop("pending_ambiguous_intent", None)

        answer = (
            "Sorry, I couldn't find this person in the Excel workbook. "
            "Please check the name."
        )

    elif person_status == "ambiguous":
        session["pending_ambiguous_name"] = candidate
        session["pending_ambiguous_detail"] = False
        session["pending_ambiguous_intent"] = parsed["intent"]

        answer = (
            f"I found multiple records for {candidate}. "
            f"Would you like to see all of them, "
            f"or identify one by relationship or city?"
        )

    elif person_status == "found":
        session.pop("pending_ambiguous_name", None)
        session.pop("pending_ambiguous_detail", None)
        session.pop("pending_ambiguous_intent", None)

        parsed = enrich_with_context(parsed, state)

        answer = execute(parsed, df)

    else:
        # General questions without a person name
        if parsed["intent"] == "greeting":
            answer = "Hello! How can I help you today? You can ask me about birthdays, upcoming birthdays, or where someone stays."
        elif parsed["intent"] == "unknown":
            answer = "I'm not sure I understood that. You can ask me about someone's birthday, where they stay, upcoming birthdays, or how many birthdays are in a month."
        elif parsed["intent"] == "person_place":
            answer = "Please specify a person's name to find their place of stay."
        elif parsed["intent"] == "all_birthdays":
            answer = execute({"intent": "all_birthdays", "entities": {}}, df)
        elif parsed["intent"] == "birthday_search" and not any(entities.get(k) for k in ["month", "relative_month", "relative_date", "relationship", "relationship_group"]):
            answer = "Please specify a person's name or a filter like a month or relationship."
        else:
            parsed = enrich_with_context(parsed, state)

            answer = execute(parsed, df)

    # ----------------------------------------------
    # UPDATE DIALOGUE STATE
    # ----------------------------------------------

    session["dialogue_state"] = update_state(parsed, state)

    print("========== NLU DEBUG ==========", flush=True)
    print(f"User message: {raw_msg}", flush=True)
    print(f"NLU used: {nlu_used}", flush=True)
    print(f"Intent: {parsed.get('intent')}", flush=True)
    print(f"Entities: {parsed.get('entities', {})}", flush=True)
    print(f"Person candidate: {candidate}", flush=True)
    print(f"Person status: {person_status}", flush=True)
    print("==============================", flush=True)

    localized_answer = multilingual.localize_response(answer, detected_lang, intent=parsed.get("intent"))

    success = 1 if (person_status != "not_found" and parsed.get("intent") != "unknown") else 0
    failed_reason = None
    if person_status == "not_found":
        failed_reason = f"Person '{candidate}' not found"
    elif parsed.get("intent") == "unknown":
        failed_reason = "Intent unknown"

    database.log_query(
        user_id=user_id,
        message=raw_msg,
        intent=parsed.get("intent", "unknown"),
        success=success,
        failed_reason=failed_reason,
        relationship=entities.get("relationship")
    )

    # Format month if present
    month_val = entities.get("month")
    month_name = None
    if isinstance(month_val, int) and 1 <= month_val <= 12:
        month_name = calendar.month_name[month_val]
    elif entities.get("relative_month"):
        month_name = f"relative ({entities.get('relative_month')})"

    # Identified person name: resolved person name, or candidate if found
    identified_person = entities.get("person_name")
    if not identified_person and person_status == "found" and candidate:
        identified_person = candidate

    # Determine processing result description
    if person_status == "found":
        proc_result = f"Person identified: {identified_person or candidate}"
    elif person_status == "ambiguous":
        proc_result = f"Ambiguous person '{candidate}' (multiple matches)"
    elif person_status == "not_found":
        proc_result = f"Person '{candidate}' not found in workbook"
    elif entities.get("relationship"):
        m_info = f" in {month_name}" if month_name else ""
        proc_result = f"Matching birthdays for {entities.get('relationship')}{m_info}"
    elif parsed.get("intent") == "greeting":
        proc_result = "Greeting recognized"
    elif parsed.get("intent") == "all_birthdays":
        proc_result = "All birthdays listing request"
    elif parsed.get("intent") == "upcoming_birthdays":
        proc_result = "Upcoming birthdays request"
    elif parsed.get("intent") == "count_birthdays":
        proc_result = "Birthday count request"
    elif parsed.get("intent") == "calculate_age":
        proc_result = f"Age calculation for {identified_person or candidate or 'contact'}"
    elif parsed.get("intent") == "person_place":
        proc_result = f"Location query for {identified_person or candidate or 'contact'}"
    elif parsed.get("intent") == "unknown":
        proc_result = "Intent unrecognized (fallback prompted)"
    else:
        proc_result = f"Intent '{parsed.get('intent')}' processed successfully"

    nlu_details = {
        "intent": parsed.get("intent"),
        "entities": parsed.get("entities", {}),
        "person_name": identified_person,
        "relationship": entities.get("relationship") or entities.get("relationship_group"),
        "month": month_name,
        "person_candidate": candidate,
        "person_status": person_status,
        "nlu_used": nlu_used,
        "result": proc_result
    }

    return jsonify(
        answer=localized_answer,
        debug=parsed,
        nlu=nlu_details
    )


# --------------------------------------------------
# ADMIN ANALYTICS DASHBOARD
# --------------------------------------------------

@app.route("/admin")
def admin_dashboard():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    analytics = database.get_analytics_summary()
    return render_template("admin.html", analytics=analytics, username=session.get("username"))


@app.get("/api/analytics")
def api_analytics():
    if not session.get("user_id"):
        return jsonify(error="unauthorized"), 401
    return jsonify(database.get_analytics_summary())


# --------------------------------------------------
# CONTACTS CRUD API (SQLITE)
# --------------------------------------------------

@app.get("/api/contacts")
def list_contacts():
    return jsonify(database.get_all_contacts())


@app.post("/api/contacts")
def create_contact():
    data = request.json or {}
    res = database.add_contact(data)
    if res.get("success"):
        refresh_df()
    return jsonify(res)


@app.put("/api/contacts/<int:cid>")
def modify_contact(cid):
    data = request.json or {}
    res = database.update_contact(cid, data)
    if res.get("success"):
        refresh_df()
    return jsonify(res)


@app.delete("/api/contacts/<int:cid>")
def remove_contact(cid):
    res = database.delete_contact(cid)
    if res.get("success"):
        refresh_df()
    return jsonify(res)


# --------------------------------------------------
# BIRTHDAY INSIGHTS API
# --------------------------------------------------

@app.get("/api/insights")
def birthday_insights():
    today = date.today()
    valid_dob = df[pd.notna(df["DOB"])].copy()

    total_birthdays = len(valid_dob)
    this_month_count = int((valid_dob["DOB"].dt.month == today.month).sum())

    # Upcoming birthdays in next 30 days
    def get_diff(r):
        bday = date(today.year, r.DOB.month, r.DOB.day)
        if bday < today:
            bday = date(today.year + 1, r.DOB.month, r.DOB.day)
        return (bday - today).days

    diffs = valid_dob.apply(get_diff, axis=1)
    upcoming_count = int(((diffs >= 0) & (diffs <= 30)).sum())

    # Most common birthday month
    month_counts = valid_dob["DOB"].dt.month.value_counts()
    if not month_counts.empty:
        top_month_num = int(month_counts.index[0])
        top_month_name = calendar.month_name[top_month_num]
        top_month_total = int(month_counts.iloc[0])
        most_common_month = {
            "month": top_month_name,
            "count": top_month_total
        }
    else:
        most_common_month = {"month": "N/A", "count": 0}

    # Relationship-wise counts
    rel_counts = []
    if "Relationship" in valid_dob.columns:
        counts_series = valid_dob["Relationship"].replace("", "Unspecified").value_counts()
        for rel_name, count_val in counts_series.items():
            rel_counts.append({
                "relationship": str(rel_name),
                "count": int(count_val)
            })

    return jsonify({
        "total_birthdays": total_birthdays,
        "this_month": this_month_count,
        "this_month_name": calendar.month_name[today.month],
        "upcoming_30_days": upcoming_count,
        "most_common_month": most_common_month,
        "relationship_counts": rel_counts
    })


# --------------------------------------------------
# BIRTHDAY WISH GENERATOR API (BIRTHDAY WISHES STUDIO)
# --------------------------------------------------

@app.post("/api/wishes/generate")
def generate_birthday_wishes():
    data = request.json or {}
    person_id = data.get("person_id")
    lang = (data.get("lang") or "english").lower()
    if lang != "kannada":
        lang = "english"

    style = (data.get("style") or "friendly").lower()
    valid_styles = ["friendly", "emotional", "funny", "formal", "short"]
    if style not in valid_styles:
        style = "friendly"

    variation_idx = int(data.get("variation") or 0)

    row = df[df["Person_ID"] == person_id]
    if row.empty:
        return jsonify(error="Person not found"), 404

    person = row.iloc[0]
    name = str(person["Name"]).strip()
    first_name = name.split()[0]
    rel = str(person.get("Relationship", "")).strip() or "Friend"
    rel_lower = rel.lower()

    # Format birthday date from actual record
    dob = person.get("DOB")
    dob_display = ""
    dob_full = ""
    if pd.notnull(dob):
        try:
            dob_display = dob.strftime("%d %B")
            dob_full = dob.strftime("%d %B %Y")
        except Exception:
            dob_display = str(dob)
            dob_full = str(dob)

    # Relationship translations in Kannada
    kannada_rel_terms = {
        "brother": "ಸಹೋದರ",
        "sister": "ಸಹೋದರಿ",
        "nephew": "ಅಳಿಯ",
        "niece": "ಸೊಸೆ",
        "friend": "ಸ್ನೇಹಿತ",
        "father": "ಅಪ್ಪ",
        "mother": "ಅಮ್ಮ",
        "uncle": "ಮಾವ",
        "aunt": "ಅತ್ತೆ",
        "cousin": "ಸಹೋದರ / ಸಹೋದರಿ",
        "colleague": "ಸಹೋದ್ಯೋಗಿ",
        "student": "ವಿದ್ಯಾರ್ಥಿ",
        "wife": "ಪತ್ನಿ",
        "husband": "ಪತಿ",
        "neighbour": "ನೆರೆಹೊರೆಯವರು",
        "sister-in-law": "ನಾದಿನಿ / ಅತ್ತಿಗೆ",
        "brother-in-law": "ಭಾವ / ಮೈದುನ"
    }
    kan_rel = kannada_rel_terms.get(rel_lower, "ಆತ್ಮೀಯರು")

    # 3 distinct variations for each of the 5 styles in English and Kannada
    if lang == "kannada":
        variations = {
            "friendly": [
                f"ನನ್ನ ಪ್ರೀತಿಯ {kan_rel} {first_name} ಅವರಿಗೆ ಜನ್ಮದಿನದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು! ನಿಮ್ಮ ಮುಖದಲ್ಲಿ ಸದಾ ನಗು ತುಂಬಿರಲಿ ಮತ್ತು ಈ ದಿನ ಅದ್ಭುತವಾಗಿರಲಿ.",
                f"ಹುಟ್ಟುಹಬ್ಬದ ಶುಭಾಶಯಗಳು, {first_name}! ನನ್ನ ಪ್ರೀತಿಯ {kan_rel} ಆಗಿರುವ ನಿಮಗೆ ಈ ದಿನವು ಅಪಾರ ಸಂತೋಷ, ನಗು ಮತ್ತು ಸಂಭ್ರಮ ತರಲಿ.",
                f"ಡಿಯರ್ {first_name}, ಜನ್ಮದಿನದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು! ನಿಮ್ಮ ಜೀವನದಲ್ಲಿ ಸದಾ ಸಂತೋಷ, ಪ್ರೀತಿ ಮತ್ತು ಗೆಲುವು ನಿಮ್ಮದಾಗಲಿ."
            ],
            "emotional": [
                f"ಆತ್ಮೀಯ {first_name}, ನೀವು ನನ್ನ ಬದುಕಿನಲ್ಲಿ {kan_rel} ಆಗಿರುವುದು ನನ್ನ ಪಾಲಿನ ದೊಡ್ಡ ಸಂತೋಷ. ದೇವರು ನಿಮಗೆ ಉತ್ತಮ ಆರೋಗ್ಯ, ಅಪಾರ ಸಂತೋಷ ಮತ್ತು ಯಶಸ್ಸನ್ನು ಕರುಣಿಸಲಿ. ಹುಟ್ಟುಹಬ್ಬದ ಪ್ರೀತಿಯ ಶುಭಾಶಯಗಳು!",
                f"ನನ್ನ ಆತ್ಮೀಯ {kan_rel} {first_name} ಅವರಿಗೆ ಹುಟ್ಟುಹಬ್ಬದ ಹೃತ್ಪೂರ್ವಕ ಶುಭಾಶಯಗಳು. ನಿಮ್ಮ ಪ್ರೀತಿ ಮತ್ತು ಕಾಳಜಿಗೆ ಸದಾ ಕೃತಜ್ಞ. ಭಗವಂತ ನಿಮಗೆ ಸದಾ ಆಯುರಾರೋಗ್ಯ ಕರುಣಿಸಲಿ.",
                f"ಪ್ರೀತಿಯ {first_name}, ನಿಮ್ಮ ಜನ್ಮದಿನದಂದು ನನ್ನ ಹೃದಯಾಂತರಾಳದ ಪ್ರಾರ್ಥನೆ ಮತ್ತು ಶುಭಹಾರೈಕೆಗಳು. ನಿಮ್ಮ ಎಲ್ಲಾ ಕನಸುಗಳು ನನಸಾಗಲಿ."
            ],
            "funny": [
                f"ಹುಟ್ಟುಹಬ್ಬದ ಶುಭಾಶಯಗಳು, {first_name}! ವಯಸ್ಸು ಹೆಚ್ಚಾಗುತ್ತಿದೆ ಎಂದು ಚಿಂತೆ ಬೇಡ, ನೀವು ದಿನದಿಂದ ದಿನಕ್ಕೆ ಇನ್ನಷ್ಟು ಬುದ್ಧಿವಂತರಾಗುತ್ತಿದ್ದೀರಿ ಅಷ್ಟೇ! ಪಾರ್ಟಿ ಯಾವಾಗ?",
                f"ನನ್ನ ನೆಚ್ಚಿನ {kan_rel} {first_name} ಅವರಿಗೆ ಹುಟ್ಟುಹಬ್ಬದ ನಗೆಭರಿತ ಶುಭಾಶಯಗಳು! ಕೇಕ್ ನನಗೂ ಒಂದು ದೊಡ್ಡ ತುಂಡು ಇರಲಿ, ದಿನ ಪೂರ್ತಿ ಖುಷಿಯಾಗಿರಿ!",
                f"ಹ್ಯಾಪಿ ಬರ್ತ್‌ಡೇ, {first_name}! ಕ್ಯಾಂಡಲ್ ಊದಲು ಜಾಸ್ತಿ ಗಾಳಿ ಬೇಕಾಗಬಹುದು, ಆದ್ರೆ ನಿಮ್ಮ ಎನರ್ಜಿ ಮಾತ್ರ ಯಾವತ್ತೂ ಕಡಿಮೆಯಾಗಲ್ಲ! ಹ್ಯಾವ್ ಎ ಗ್ರೇಟ್ ಡೇ!"
            ],
            "formal": [
                f"ಗೌರವಾನ್ವಿತ {name} ಅವರಿಗೆ ಜನ್ಮದಿನದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು. ತಮಗೆ ಉತ್ತಮ ಆರೋಗ್ಯ, ದೀರ್ಘಾಯುಷ್ಯ ಮತ್ತು ನಿರಂತರ ಯಶಸ್ಸು ದೊರೆಯಲೆಂದು ಹಾರೈಸುತ್ತೇನೆ.",
                f"ಆತ್ಮೀಯ {name} ಅವರಿಗೆ ಹುಟ್ಟುಹಬ್ಬದ ಸವಿನೆನಪಿನ ಶುಭಾಶಯಗಳು. ತಮ್ಮ ಮುಂದಿನ ದಿನಗಳು ಶಾಂತಿ, ನೆಮ್ಮದಿ ಮತ್ತು ಸಮೃದ್ಧಿಯಿಂದ ಕೂಡಿರಲಿ.",
                f"{name} ಅವರಿಗೆ ಜನ್ಮದಿನದ ಹೃತ್ಪೂರ್ವಕ ಶುಭಕಾಮನೆಗಳು. ತಮ್ಮ ಕಾರ್ಯಕ್ಷೇತ್ರದಲ್ಲಿ ಇನ್ನಷ್ಟು ಉನ್ನತ ಸಾಧನೆಗಳು ನೆರವೇರಲಿ."
            ],
            "short": [
                f"ಹುಟ್ಟುಹಬ್ಬದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು, {first_name}! ಈ ವರ್ಷ ನಿಮಗೆ ಆಯುರಾರೋಗ್ಯ ಮತ್ತು ನೆಮ್ಮದಿ ನೀಡಲಿ.",
                f"ಜನ್ಮದಿನದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು, {first_name}! ನಿಮ್ಮ ದಿನವು ಸಂತೋಷದಿಂದ ಕೂಡಿರಲಿ.",
                f"ಹ್ಯಾಪಿ ಬರ್ತ್‌ಡೇ, {first_name}! ದೇವರು ನಿಮಗೆ ಸಕಲ ಸನ್ಮಂಗಳವನ್ನುಂಟುಮಾಡಲಿ."
            ]
        }
    else:
        variations = {
            "friendly": [
                f"Wishing a very Happy Birthday to my wonderful {rel_lower}, {first_name}! May your day be filled with happiness, laughter, and great moments.",
                f"Happy Birthday, {first_name}! So lucky to have an amazing {rel_lower} like you in my life. Hope your special day brings you as much joy as you bring to everyone around you!",
                f"Cheers to another fantastic year, {first_name}! Wishing my dear {rel_lower} a birthday filled with smiles, celebrate big and enjoy every moment today!"
            ],
            "emotional": [
                f"Dear {first_name}, having you in my life as my {rel_lower} is a true blessing. May this special day bring you immense peace, fulfillment, and happiness. Happy Birthday!",
                f"Happy Birthday, dearest {first_name}. Thank you for always being such a supportive, caring {rel_lower}. I cherish every memory we share and pray for your health, peace, and prosperity always.",
                f"To my dearest {rel_lower} {first_name}, words cannot fully express how grateful I am to have you. May this birthday mark the start of your most joyous and blessed year yet."
            ],
            "funny": [
                f"Happy Birthday to my favourite {rel_lower}, {first_name}! Remember, you're not getting older, you're just leveling up and increasing in value like fine wine.",
                f"Happy Birthday, {first_name}! I was going to make a joke about your age, but respect for my {rel_lower} and the risk of not getting birthday cake stopped me. Have an awesome day!",
                f"Happy Birthday, {first_name}! Another year wiser, bolder, and still putting up with all of us! Hope your cake is as sweet as you are."
            ],
            "formal": [
                f"Dear {name}, wishing you a very Happy Birthday. May this year bring you continued success, good health, and prosperity in all your endeavors.",
                f"Warmest birthday greetings, {name}. It is a privilege to know you as a valued {rel_lower}. Wishing you a joyful celebration and fruitful achievements ahead.",
                f"Please accept my sincere wishes on your birthday, {name}. May the year ahead be filled with peace, happiness, and accomplishments."
            ],
            "short": [
                f"Happy Birthday, {first_name}! Wishing you joy, good health, and a wonderful year ahead.",
                f"Wishing you a very Happy Birthday, {first_name}! Have a fantastic day and great year ahead.",
                f"Happy Birthday, {first_name}! May all your wishes come true today and always."
            ]
        }

    # Map current variation for each style
    wishes_dict = {}
    for s_key, v_list in variations.items():
        v_idx = variation_idx % len(v_list)
        wishes_dict[s_key] = v_list[v_idx]

    current_wish = wishes_dict.get(style, wishes_dict["friendly"])

    return jsonify({
        "person_id": person_id,
        "person_name": name,
        "first_name": first_name,
        "relationship": rel,
        "birthday_date": dob_display,
        "birthday_full": dob_full,
        "lang": lang,
        "style": style,
        "variation": variation_idx % 3,
        "wish": current_wish,
        "wishes": wishes_dict,
        "all_variations": variations
    })


# --------------------------------------------------
# BIRTHDAY REMINDERS API
# --------------------------------------------------

@app.get("/api/reminders/status")
def reminder_status():
    uid = session.get("user_id")
    return jsonify(database.get_reminder_settings(uid))


@app.post("/api/reminders/settings")
def update_reminder_settings():
    uid = session.get("user_id")
    data = request.json or {}
    enabled = data.get("enabled", False)
    perm = data.get("permission_granted", False)
    return jsonify(database.set_reminder_settings(uid, enabled, perm))


@app.get("/api/reminders")
def get_upcoming_reminders():
    today = date.today()
    reminders = []
    for _, r in df.iterrows():
        if pd.notna(r["DOB"]):
            dob = r["DOB"]
            bday_this_year = date(today.year, dob.month, dob.day)
            diff = (bday_this_year - today).days
            if diff < 0:
                bday_this_year = date(today.year + 1, dob.month, dob.day)
                diff = (bday_this_year - today).days
            if 0 <= diff <= 14:
                reminders.append({
                    "name": r["Name"],
                    "relationship": r["Relationship"],
                    "dob_formatted": dob.strftime("%d %B"),
                    "days_away": diff
                })
    reminders.sort(key=lambda x: x["days_away"])
    return jsonify(reminders=reminders)


# --------------------------------------------------
# RESET CONVERSATION
# --------------------------------------------------

@app.post("/reset")
def reset():
    session.pop("dialogue_state", None)
    session.pop("pending_ambiguous_name", None)
    session.pop("pending_ambiguous_detail", None)
    session.pop("pending_ambiguous_intent", None)
    return jsonify(ok=True)


# --------------------------------------------------
# START FLASK
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
