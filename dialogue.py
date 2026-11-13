
def enrich_with_context(parsed, state):
    e = parsed['entities']

    # Do not carry old filters into general upcoming, all-birthdays, greetings, or unknown queries
    if parsed.get('intent') in ('upcoming_birthdays', 'all_birthdays', 'greeting', 'unknown'):
        return parsed

    # Do not carry old filters into a specific person's question.
    if e.get('person_id') or e.get('person_name'):
        return parsed

    # A next-month question must not use old filters.
    if e.get('relative_month') == 'next':
        return parsed

    # If the user explicitly asks about a new relationship, do not carry forward an old month
    if 'relationship' in e:
        state.pop('month', None)

    # If the user explicitly asks about a new month, do not carry forward an old relationship
    if 'month' in e:
        state.pop('relationship', None)

    # Carry forward previous month or relationship
    # only when the new question does not specify them.
    for key in ('month', 'relationship'):
        if key not in e and state.get(key) is not None:
            e[key] = state[key]

    return parsed


def update_state(parsed, state, last_result_ids=None):
    e = parsed['entities']

    # Clear old filters for upcoming or all-birthdays questions.
    if parsed.get('intent') in ('upcoming_birthdays', 'all_birthdays'):
        state.pop('month', None)
        state.pop('relationship', None)

    # Clear old filters after a specific person's question.
    if e.get('person_id') or e.get('person_name'):
        state.pop('month', None)
        state.pop('relationship', None)

    # Clear old filters for a next-month question.
    if e.get('relative_month') == 'next':
        state.pop('month', None)
        state.pop('relationship', None)

    # Save current conversation context.
    for key in ('month', 'relationship', 'person_id', 'person_name'):
        if key in e:
            state[key] = e[key]

    if last_result_ids is not None:
        state['last_result_ids'] = last_result_ids

    return state
