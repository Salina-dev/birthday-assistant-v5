import re

def detect_language(text):
    text_lower = text.lower()

    # Kannada Script
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kannada"

    # Kannada transliterated tokens
    kannada_tokens = [
        r"\byavaga\b", r"\byavaaga\b", r"\belli\b", r"\belliddare\b", r"\bstay\s+madthare\b",
        r"\birthare\b", r"\bestu\b", r"\bvayassu\b", r"\bhuttuhabba\b", r"\bthorsi\b",
        r"\bnamaskara\b", r"\bnamaskaram\b", r"\bmundina\b", r"\bellara\b", r"\bellaru\b",
        r"\bhege\b", r"\byaru\b", r"\bnanna\b"
    ]
    for token in kannada_tokens:
        if re.search(token, text_lower):
            return "kannada"

    return "english"


def normalize_multilingual_query(text):
    """
    Translates or normalizes Kannada questions into canonical English representations
    while preserving names, relationships, and entities.
    Supports only English and Kannada.
    """
    lang = detect_language(text)
    if lang == "english":
        return text, lang

    normalized = text

    # Name mappings for Kannada script
    name_map = {
        "ರಾಹುಲ್": "Rahul", "ಲಕ್ಷ್ಮಿ": "Lakshmi", "ಅಪ್ಪ": "Appa", "ಅಮ್ಮ": "Amma",
        "ನಿಕಿಲ್": "Nikhil", "ನಿಖಿಲ್": "Nikhil", "ರಾಘವೇಂದ್ರ": "Raghavendra", "ಶಾಂತ": "Shantha"
    }
    for script_name, eng_name in name_map.items():
        normalized = re.sub(re.escape(script_name), eng_name, normalized)

    # Greetings
    if re.search(r"(?:namaskara|namaskaram|ನಮಸ್ಕಾರ)", normalized, re.IGNORECASE):
        return "Hello", lang

    # Kannada Script normalizations
    if lang == "kannada":
        # Birthday query
        if re.search(r"(?:ಯಾವಾಗ|ಹುಟ್ಟುಹಬ್ಬ|yavaga|yavaaga|huttuhabba)", normalized, re.IGNORECASE):
            name_match = re.search(r"(?:when\s+is\s+)?([a-zA-Z\u0C80-\u0CFF\s]+?)(?:['’]?(?:na|ra|da|avara|ಅವರ))?\s+(?:birthday|huttuhabba|ಹುಟ್ಟುಹಬ್ಬ)?\s*(?:ಯಾವಾಗ|yavaga|yavaaga)", normalized, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()
                return f"When is {name}'s birthday?", lang
            return "When is birthday?", lang

        # Place query
        if re.search(r"(?:ಎಲ್ಲಿ|elli|elliddare|stay\s+madthare|irthare|ಇರುತ್ತಾರೆ|ಎಲ್ಲಿದ್ದಾರೆ)", normalized, re.IGNORECASE):
            name_match = re.search(r"([a-zA-Z\u0C80-\u0CFF\s]+?)(?:['’]?(?:na|ra|da|avara|ಅವರ))?\s+(?:elli|stay\s+madthare|irthare|ಎಲ್ಲಿ|ಇರುತ್ತಾರೆ|ಎಲ್ಲಿದ್ದಾರೆ)", normalized, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()
                return f"Where does {name} stay?", lang
            return "Where do they stay?", lang

        # Age query
        if re.search(r"(?:ವಯಸ್ಸು|ಎಷ್ಟು|estu|vayassu|varsha)", normalized, re.IGNORECASE):
            name_match = re.search(r"([a-zA-Z\u0C80-\u0CFF\s]+?)(?:['’]?(?:ya|na|ra|da|avara|ಅವರ))?\s+(?:age|vayassu|ವಯಸ್ಸು|estu|ಎಷ್ಟು)", normalized, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()
                return f"How old is {name}?", lang
            return "How old are they?", lang

        # All birthdays
        if re.search(r"(?:ಎಲ್ಲರ|ellaru|ellara|thorsi|ತೋರಿಸಿ)", normalized, re.IGNORECASE):
            return "show all birthdays", lang

        # Upcoming
        if re.search(r"(?:ಮುಂದಿನ|mundina)", normalized, re.IGNORECASE):
            return "upcoming birthdays", lang

    return normalized, lang


def localize_response(english_response, lang, intent=None):
    """
    Localizes standard English response into Kannada if requested.
    Supports only English and Kannada.
    """
    if lang != "kannada" or not english_response:
        return english_response

    # Greetings
    if "Hello! How can I help you today?" in english_response:
        return "ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ ಬರ್ತ್‌ಡೇ ಅಸಿಸ್ಟೆಂಟ್. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"

    # Not found in workbook
    if "Sorry, I couldn't find this person in the Excel workbook" in english_response:
        return "ಕ್ಷಮಿಸಿ, ಈ ವ್ಯಕ್ತಿ ನಮ್ಮ ದಾಖಲೆಗಳಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ. ದಯವಿಟ್ಟು ಹೆಸರನ್ನು ಪರಿಶೀಲಿಸಿ."

    # Clarification / Unknown
    if "I'm not sure I understood that" in english_response:
        return "ನನಗೆ ಸರಿಯಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ನೀವು ಹುಟ್ಟುಹಬ್ಬ, ಅವರು ಇರುವ ಸ್ಥಳ, ವಯಸ್ಸು ಅಥವಾ ಮುಂಬರುವ ಹುಟ್ಟುಹಬ್ಬಗಳ ಬಗ್ಗೆ ಕೇಳಬಹುದು."

    # Ambiguity prompt
    if "I found multiple records for" in english_response:
        match = re.search(r"records for ([^.]+)\.", english_response)
        name = match.group(1) if match else "ಈ ಹೆಸರಿನಲ್ಲಿ"
        return f"{name} ಹೆಸರಿನಲ್ಲಿ ಹಲವು ದಾಖಲೆಗಳು ಕಂಡುಬಂದಿವೆ. ಎಲ್ಲವನ್ನೂ ನೋಡಲು ಬಯಸುವಿರಾ, ಅಥವಾ ಸಂಬಂಧ/ಊರನ್ನು ತಿಳಿಸುವಿರಾ?"

    # Birthday response
    bday_match = re.search(r"^(.+?)'s birthday is (.+?)\.?$", english_response)
    if bday_match:
        name = bday_match.group(1)
        dob = bday_match.group(2)
        return f"{name} ಅವರ ಹುಟ್ಟುಹಬ್ಬ {dob} ಆಗಿದೆ."

    # Place response
    place_match = re.search(r"^(.+?) stays in (.+?)\.?$", english_response)
    if place_match:
        name = place_match.group(1)
        place = place_match.group(2)
        return f"{name} ಅವರು {place} ನಲ್ಲಿ ಇರುತ್ತಾರೆ."

    # Age response
    age_match = re.search(r"^(.+?) is currently (\d+) years old \(born (.+?)\)\.?$", english_response)
    if age_match:
        name = age_match.group(1)
        age = age_match.group(2)
        dob = age_match.group(3)
        return f"{name} ಅವರಿಗೆ ಈಗ {age} ವರ್ಷ ವಯಸ್ಸು (ಜನನ: {dob})."

    # Age turning response
    turn_match = re.search(r"^(.+?) will turn (\d+) years old on (.+?)\.?$", english_response)
    if turn_match:
        name = turn_match.group(1)
        age = turn_match.group(2)
        dob = turn_match.group(3)
        return f"{name} ಅವರಿಗೆ {dob} ರಂದು {age} ವರ್ಷ ತುಂಬಲಿದೆ."

    # Count response
    count_match = re.search(r"I found (\d+) matching birthdays", english_response)
    if count_match:
        cnt = count_match.group(1)
        return f"ನನಗೆ {cnt} ಹೊಂದಾಣಿಕೆಯಾಗುವ ಹುಟ್ಟುಹಬ್ಬಗಳು ಸಿಕ್ಕಿವೆ."

    return f"ಇಲ್ಲಿ ವಿವರಗಳಿವೆ:\n{english_response}"
