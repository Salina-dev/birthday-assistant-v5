
import calendar
import re

MONTHS = {
    m.lower(): i
    for i, m in enumerate(calendar.month_name)
    if m
}


def parse(message, people):
    text = message.lower().strip()

    result = {
        'intent': 'unknown',
        'entities': {}
    }

    if re.fullmatch(r"(?:hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|namaste|greetings|howdy|hola)[.!]?", text):
        result['intent'] = 'greeting'
    elif re.search(r"\b(all\s+birthdays|every(?:one|body)['’]?s?\s+birthday|list\s+all\s+birthdays|show\s+all\s+birthdays|all\s+the\s+birthdays|show\s+everyone|list\s+birthdays)\b", text):
        result['intent'] = 'all_birthdays'
    elif 'how many' in text or 'count' in text:
        result['intent'] = 'count_birthdays'
    elif 'where' in text or 'stay' in text or 'live' in text or 'reside' in text or 'location' in text:
        result['intent'] = 'person_place'
    elif re.search(r"\b(how old|turn this year|turning this year|will turn|turn \d+|current age|what is .* age|age of)\b", text) or re.search(r"['’]s\s+(?:current\s+)?age\b", text) or text.endswith(" age"):
        result['intent'] = 'calculate_age'
    elif 'upcoming' in text:
        result['intent'] = 'upcoming_birthdays'
    elif re.search(r"\b(birthday|birthdays|bday|born|dob|date\s+of\s+birth)\b", text) or 'when' in text:
        result['intent'] = 'birthday_search'
    else:
        result['intent'] = 'unknown'

    if 'tomorrow' in text:
        result['entities']['relative_date'] = 'tomorrow'

    if 'next month' in text:
        result['entities']['relative_month'] = 'next'

    for name, num in MONTHS.items():
        if name in text:
            result['entities']['month'] = num

    if 'Relationship_Group' in people.columns:
        for group in sorted(
            people['Relationship_Group'].dropna().unique(),
            key=len,
            reverse=True
        ):
            if group.lower() in text:
                result['entities']['relationship_group'] = group
                break

    rel_paths = [
        (r"\b(?:my\s+)?sister['’]?s\s+son\b", "Nephew"),
        (r"\b(?:my\s+)?brother['’]?s\s+son\b", "Nephew"),
        (r"\b(?:my\s+)?sister['’]?s\s+daughter\b", "Niece"),
        (r"\b(?:my\s+)?brother['’]?s\s+daughter\b", "Niece"),
        (r"\b(?:my\s+)?(?:father|mother|dad|mom)['’]?s\s+sister\b", "Aunt"),
        (r"\b(?:my\s+)?(?:father|mother|dad|mom)['’]?s\s+brother\b", "Uncle"),
        (r"\b(?:my\s+)?brother['’]?s\s+wife\b", "Sister-in-law"),
        (r"\b(?:my\s+)?sister['’]?s\s+husband\b", "Brother-in-law"),
        (r"\b(?:my\s+)?(?:husband|wife)['’]?s\s+sister\b", "Sister-in-law"),
        (r"\b(?:my\s+)?(?:husband|wife)['’]?s\s+brother\b", "Brother-in-law"),
        (r"\b(?:my\s+)?(?:uncle|aunt)['’]?s\s+(?:son|daughter)\b", "Cousin"),
    ]
    has_rel_path = False
    for pattern, resolved_rel in rel_paths:
        if re.search(pattern, text, re.IGNORECASE):
            result['entities']['relationship'] = resolved_rel
            if result['intent'] == 'unknown':
                result['intent'] = 'birthday_search'
            has_rel_path = True
            break

    if not has_rel_path:
        rel_patterns = [
            (r"\b(?:my\s+)?nephews?['’]?s?\b", "Nephew"),
            (r"\b(?:my\s+)?nieces?['’]?s?\b", "Niece"),
            (r"\b(?:my\s+)?sisters?['’]?s?\b", "Sister"),
            (r"\b(?:my\s+)?brothers?['’]?s?\b", "Brother"),
            (r"\b(?:my\s+)?friends?['’]?s?\b", "Friend"),
            (r"\b(?:my\s+)?uncles?['’]?s?\b", "Uncle"),
            (r"\b(?:my\s+)?aunts?['’]?s?\b", "Aunt"),
            (r"\b(?:my\s+)?cousins?['’]?s?\b", "Cousin"),
            (r"\b(?:my\s+)?colleagues?['’]?s?\b", "Colleague"),
            (r"\b(?:my\s+)?students?['’]?s?\b", "Student"),
            (r"\b(?:my\s+)?(?:sister[- ]in[- ]laws?|sisters[- ]in[- ]law)['’]?s?\b", "Sister-in-law"),
            (r"\b(?:my\s+)?(?:brother[- ]in[- ]laws?|brothers[- ]in[- ]law)['’]?s?\b", "Brother-in-law"),
            (r"\b(?:my\s+)?(?:wifes?|wives)['’]?s?\b", "Wife"),
            (r"\b(?:my\s+)?(?:fathers?|dads?)['’]?s?\b", "Father"),
            (r"\b(?:my\s+)?(?:mothers?|moms?)['’]?s?\b", "Mother"),
            (r"\b(?:my\s+)?(?:neighbours?|neighbors?)['’]?s?\b", "Neighbour"),
        ]
        for pattern, canonical_rel in rel_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result['entities']['relationship'] = canonical_rel
                if result['intent'] == 'unknown':
                    result['intent'] = 'birthday_search'
                break

        if 'relationship' not in result['entities']:
            for rel in sorted(
                people['Relationship'].dropna().unique(),
                key=len,
                reverse=True
            ):
                token = rel.lower()
                if re.search(r"\b" + re.escape(token) + r"(?:s|es|'s)?\b", text, re.IGNORECASE):
                    result['entities']['relationship'] = rel
                    if result['intent'] == 'unknown':
                        result['intent'] = 'birthday_search'
                    break

    for _, r in people.iterrows():
        for candidate in [
            str(r['Name']),
            str(r.get('Nickname', ''))
        ]:
            c = candidate.lower().strip()

            if (
                c
                and c != 'nan'
                and re.search(r'\b' + re.escape(c) + r'\b', text)
            ):
                result['entities']['person_id'] = r['Person_ID']
                result['entities']['person_name'] = r['Name']
                break

        if 'person_id' in result['entities']:
            break

    return result
