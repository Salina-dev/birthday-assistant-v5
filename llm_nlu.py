
import json
import ollama
import pandas as pd


SYSTEM = """
You are an NLU parser for a birthday assistant.

Your ONLY task is to understand the user's message
and return structured JSON.

Never answer the user's question.
Never invent information.
Never guess missing entities.

Return JSON using this exact structure:

{
    "intent": "birthday_search",
    "entities": {
        "person_name": null,
        "relationship": null,
        "relationship_group": null,
        "month": null,
        "relative_date": null,
        "relative_month": null,
        "place": null
    }
}

Allowed intents:
birthday_search, count_birthdays, upcoming_birthdays,
person_place, calculate_age, greeting, all_birthdays, unknown.

STRICT ENTITY EXTRACTION RULES:

1. Extract a month ONLY if the user explicitly
   mentions a month name.

2. If no month is mentioned, month MUST be null.

3. Never guess a month from the current date,
   previous questions, or conversation history.

4. Extract a person's name only if the user
   explicitly mentions that person.

5. Use only names from the supplied Excel name list.

6. If a name is not in the Excel list, preserve
   the mentioned name in person_name.
   Do not replace it with another name.

7. Extract relationship only when explicitly mentioned.

8. If the user says "sibling family", set
   relationship_group to "Sibling Family".

9. Do not confuse relationship_group with relationship.

10. For "next month", use relative_month = "next".
    Do not also set month.

11. For "tomorrow", use relative_date = "tomorrow".

12. If the user asks where someone lives, stays,
    or resides, use person_place.

13. If the user asks when someone's birthday is,
    use birthday_search.

14. If the user asks how many birthdays there are,
    use count_birthdays.

15. If the user asks about upcoming birthdays,
    use upcoming_birthdays.

16. Every entity not explicitly found in the
    user's message MUST be null.

17. If the user asks how old someone is, their age, or how old they turn, use calculate_age.

18. Return valid JSON only.
"""


def parse_with_llm(message, people):

    nicknames = people.get('Nickname', pd.Series(dtype=object))
    known_names = (
        pd.concat([people['Name'], nicknames])
        .dropna()
        .astype(str)
        .str.strip()
        .replace('', pd.NA)
        .dropna()
        .unique()
        .tolist()
    )

    prompt = (
        "Excel names available:\n"
        + json.dumps(known_names)
        + "\n\nParse this user message only:\n"
        + message
    )

    client = ollama.Client(timeout=2.0)
    response = client.chat(
        model='llama3.2:3b',
        messages=[
            {
                'role': 'system',
                'content': SYSTEM
            },
            {
                'role': 'user',
                'content': prompt
            }
        ],
        format='json'
    )

    result = json.loads(response['message']['content'])

    if not isinstance(result, dict):
        raise ValueError("Invalid LLM output")

    if not isinstance(result.get('entities'), dict):
        raise ValueError("Invalid entities")

    return result
