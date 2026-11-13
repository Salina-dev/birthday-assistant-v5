
from datetime import date, timedelta
import calendar
import pandas as pd


def format_rows(rows):
    if rows.empty:
        return 'No matching people found.'

    return '\n'.join(
        f"{r.Name} - {r.DOB.strftime('%d %B')} ({r.Relationship})"
        for _, r in rows.iterrows()
    )


def execute(parsed, df):
    intent = parsed['intent']
    e = parsed['entities']

    work = df.copy()
    today = date.today()

    if intent == 'greeting':
        return "Hello! How can I help you today? You can ask me about birthdays, upcoming birthdays, or where someone stays."

    if intent == 'unknown':
        return "I'm not sure I understood that. You can ask me about someone's birthday, where they stay, upcoming birthdays, or how many birthdays are in a month."

    # Place of stay query
    if intent == 'person_place':
        if 'person_id' in e:
            r = df[df.Person_ID == e['person_id']].iloc[0]
            return f"{r.Name} stays in {r.Place_of_Stay}."
        if e.get('person_name'):
            return "Sorry, I couldn't find this person in the Excel workbook. Please check the name."
        return "Please specify a person to find their place of stay."

    # Age calculation query
    if intent == 'calculate_age':
        target_row = None
        if 'person_id' in e:
            target_row = df[df.Person_ID == e['person_id']].iloc[0]
        elif e.get('relationship'):
            rel_matches = df[df['Relationship'].str.lower() == e['relationship'].lower()]
            if len(rel_matches) == 1:
                target_row = rel_matches.iloc[0]
            elif len(rel_matches) > 1:
                return f"I found multiple people with relationship {e['relationship']}. Please specify which one:\n" + format_rows(rel_matches)

        if target_row is not None:
            r = target_row
            if pd.isna(r.DOB):
                return f"Sorry, date of birth for {r.Name} is unavailable."
            dob = r.DOB.date() if hasattr(r.DOB, 'date') else r.DOB
            current_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            turn_age = today.year - dob.year
            bday_this_year = date(today.year, dob.month, dob.day)

            if parsed.get('is_turn_query'):
                if today < bday_this_year:
                    return f"{r.Name} will turn {turn_age} years old on {r.DOB.strftime('%d %B %Y')}."
                elif today == bday_this_year:
                    return f"Today is {r.Name}'s birthday! They turn {turn_age} years old today! 🎉"
                else:
                    return f"{r.Name} turned {turn_age} years old this year on {r.DOB.strftime('%d %B %Y')}."
            else:
                return f"{r.Name} is currently {current_age} years old (born {r.DOB.strftime('%d %B %Y')})."

        if e.get('person_name'):
            return "Sorry, I couldn't find this person in the Excel workbook. Please check the name."
        return "Please specify a person to calculate their age."

    # Search for a specific person's birthday
    if 'person_id' in e:
        r = df[df.Person_ID == e['person_id']].iloc[0]
        return f"{r.Name}'s birthday is {r.DOB.strftime('%d %B %Y')}."

    has_filter = False

    # Filter by relationship group
    if e.get('relationship_group'):
        work = work[
            work['Relationship_Group'].str.lower()
            == e['relationship_group'].lower()
        ]
        has_filter = True

    # Filter by individual relationship
    if e.get('relationship'):
        work = work[
            work['Relationship'].str.lower()
            == e['relationship'].lower()
        ]
        has_filter = True
        if intent == 'birthday_search' and not (e.get('month') or e.get('relative_month') or e.get('relative_date') or e.get('relationship_group')):
            if len(work) == 1:
                r = work.iloc[0]
                return f"{r.Name}'s birthday is {r.DOB.strftime('%d %B %Y')} ({r.Relationship})."
            elif len(work) > 1:
                return f"Here are the matching records for {e['relationship']}:\n" + format_rows(work)
            else:
                return f"No matching {e['relationship']} found in the records."

    # Filter tomorrow's birthdays
    if e.get('relative_date') == 'tomorrow':
        tomorrow = today + timedelta(days=1)

        work = work[
            (work.DOB.dt.month == tomorrow.month)
            & (work.DOB.dt.day == tomorrow.day)
        ]
        has_filter = True

    # Filter by month
    month = e.get('month')

    if e.get('relative_month') == 'next':
        month = 1 if today.month == 12 else today.month + 1

    if month:
        if isinstance(month, str):
            month = month.strip()

            if month.isdigit():
                month = int(month)
            else:
                month = list(calendar.month_name).index(
                    month.capitalize()
                )

        work = work[work.DOB.dt.month == int(month)]
        has_filter = True

    # Count birthdays
    if intent == 'count_birthdays':
        return f"I found {len(work)} matching birthdays."

    # Upcoming birthdays
    if intent == 'upcoming_birthdays':

        def days(r):
            birthday = date(today.year, r.DOB.month, r.DOB.day)

            if birthday < today:
                birthday = date(
                    today.year + 1,
                    r.DOB.month,
                    r.DOB.day
                )

            return (birthday - today).days

        work = work.assign(_days=work.apply(days, axis=1))

        work = work[
            (work._days >= 0) & (work._days <= 30)
        ].sort_values('_days')

        return format_rows(work)

    # Explicit request to view all birthdays
    if intent == 'all_birthdays':
        return format_rows(work)

    # If any specific filter matched
    if has_filter:
        if work.empty:
            m_name = calendar.month_name[int(month)] if (month and str(month).isdigit() and 1 <= int(month) <= 12) else ""
            m_str = f" in {m_name}" if m_name else ""
            r_str = f" for {e['relationship']}" if e.get('relationship') else ""
            return f"No matching birthdays found{r_str}{m_str}."
        return format_rows(work)

    # Default fallback when no person, filter, or explicit all-birthdays request matched
    return "I'm not sure I understood that. You can ask me about someone's birthday, where they stay, upcoming birthdays, or how many birthdays are in a month."
