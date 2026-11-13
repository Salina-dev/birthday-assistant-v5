import re
import json
from app import app

def run_all_tests():
    client = app.test_client()

    print("\n=======================================================")
    print("STEP 1: TESTING CALENDAR EXPORT REMOVAL")
    print("=======================================================")

    # 1. Login
    client.post("/login", data={"username": "user", "password": "user123"})
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Assert Calendar Export popup and buttons are completely removed
    assert "open-calendar-btn" not in html, "open-calendar-btn must be removed"
    assert "calendar-modal" not in html, "calendar-modal must be removed"
    assert "google-cal-btn" not in html, "google-cal-btn must be removed"
    assert "download-ics-btn" not in html, "download-ics-btn must be removed"
    assert "Export Birthday to Calendar" not in html, "Calendar export popup title must be removed"

    # Assert calendar dashboard itself is preserved
    assert 'class="card-column calendar-column"' in html, "Calendar column must be preserved"
    assert 'id="calendar-days"' in html, "Calendar days grid must be preserved"
    assert 'id="cal-month-year"' in html, "Calendar month-year must be preserved"
    assert 'id="today-display"' in html, "Today display must be preserved"

    # Assert endpoints return 404
    ics_res = client.get("/api/calendar/ics/P004")
    assert ics_res.status_code == 404, f"Expected 404 for removed ics route, got {ics_res.status_code}"
    gcal_res = client.get("/api/calendar/google_url/P004")
    assert gcal_res.status_code == 404, f"Expected 404 for removed google_url route, got {gcal_res.status_code}"

    print("PASS: Calendar export feature completely removed; calendar dashboard preserved.")

    print("\n=======================================================")
    print("STEP 2: TESTING NLU RELATIONSHIP DETECTION")
    print("=======================================================")

    def test_rel_query(query, expected_rel, expected_month=None, expected_in_bot=None):
        test_client = app.test_client()
        test_client.post("/login", data={"username": "user", "password": "user123"})
        r = test_client.post("/chat", json={"message": query})
        assert r.status_code == 200, f"Query failed for: {query}"
        data = json.loads(r.get_data(as_text=True))
        ans = data.get("answer", "")
        nlu = data.get("nlu", {})

        print(f"\nQuery: '{query}'")
        print(f"Bot answer:\n{ans}")
        print(f"Detected Relationship: {nlu.get('relationship')}")
        print(f"Detected Month: {nlu.get('month')}")
        print(f"NLU Result: {nlu.get('result')}")

        assert nlu.get("relationship") == expected_rel, f"Expected rel {expected_rel}, got {nlu.get('relationship')}"
        if expected_month:
            assert nlu.get("month") == expected_month, f"Expected month {expected_month}, got {nlu.get('month')}"
        if expected_in_bot:
            for item in expected_in_bot:
                assert item in ans, f"Expected '{item}' in bot response for query '{query}'"

        return data

    # 1. "Show my nephew's birthdays in September."
    test_rel_query(
        "Show my nephew's birthdays in September.",
        expected_rel="Nephew",
        expected_month="September",
        expected_in_bot=["Rahul Patil", "Nikhil Bhat", "Bharath Rao"]
    )

    # 2. "Are there any birthdays for my sisters?"
    test_rel_query(
        "Are there any birthdays for my sisters?",
        expected_rel="Sister",
        expected_in_bot=["Yashaswini Rao", "Soumya Reddy", "Usha K"]
    )

    # 3. "When is my brother's birthday?"
    test_rel_query(
        "When is my brother's birthday?",
        expected_rel="Brother",
        expected_in_bot=["Sanjay Rao", "Aditya Patil", "Harish K", "Manjunath Prasad", "Sanjay Naik"]
    )

    # 4. "Show birthdays of my friends."
    test_rel_query(
        "Show birthdays of my friends.",
        expected_rel="Friend",
        expected_in_bot=["Aditya Joshi", "Vaishnavi Naik", "Pranav Rao", "Nikhil Reddy", "Divya Naik", "Aditya Reddy"]
    )

    # 5. "Any birthdays in October for my nieces?"
    test_rel_query(
        "Any birthdays in October for my nieces?",
        expected_rel="Niece",
        expected_month="October",
        expected_in_bot=["Yashaswini Murthy", "Shruthi R"]
    )

    print("\nPASS: All 5 relationship detection questions verified successfully.")

    print("\n=======================================================")
    print("STEP 3: TESTING BIRTHDAY COUNTDOWN ELEMENTS")
    print("=======================================================")

    assert 'id="nearest-countdown-card"' in html, "nearest-countdown-card missing from HTML"
    assert 'id="nearest-countdown-text"' in html, "nearest-countdown-text missing from HTML"
    assert 'id="upcoming-birthdays-list"' in html, "upcoming-birthdays-list missing from HTML"

    with open("static/chat.js", "r", encoding="utf-8") as f:
        js = f.read()
    assert "nearest-countdown-card" in js, "chat.js must manage nearest-countdown-card"
    assert "nearest-countdown-text" in js, "chat.js must update nearest-countdown-text"
    assert "is-nearest" in js, "chat.js must mark nearest upcoming birthday"
    assert "days." in js or "birthday is in" in js, "chat.js must construct countdown text"

    with open("static/style.css", "r", encoding="utf-8") as f:
        css = f.read()
    assert ".nearest-countdown-card" in css, "style.css must style countdown card"
    assert ".countdown-highlight" in css, "style.css must style countdown highlight"
    assert ".is-nearest" in css, "style.css must style nearest item"

    print("PASS: Birthday Countdown markup, script logic, and styling verified.")

    print("\n=======================================================")
    print("STEP 4: TESTING BIRTHDAY WISH GENERATOR")
    print("=======================================================")

    # Wish generator in English
    eng_wish_res = client.post("/api/wishes/generate", json={"person_id": "P004", "lang": "english"})
    assert eng_wish_res.status_code == 200
    eng_wish_data = json.loads(eng_wish_res.get_data(as_text=True))
    assert eng_wish_data["person_name"] == "Rahul Patil"
    assert eng_wish_data["relationship"] == "Nephew"
    assert "short" in eng_wish_data["wishes"]
    assert "friendly" in eng_wish_data["wishes"]
    assert "emotional" in eng_wish_data["wishes"]
    assert "Rahul" in eng_wish_data["wishes"]["short"]
    assert "nephew" in eng_wish_data["wishes"]["friendly"].lower()
    print("English Wish Sample (Friendly):", eng_wish_data["wishes"]["friendly"])

    # Wish generator in Kannada
    kan_wish_res = client.post("/api/wishes/generate", json={"person_id": "P004", "lang": "kannada"})
    assert kan_wish_res.status_code == 200
    kan_wish_data = json.loads(kan_wish_res.get_data(as_text=True))
    assert "ರಾಹುಲ್" in kan_wish_data["wishes"]["short"] or "Rahul" in kan_wish_data["wishes"]["short"]
    assert "ಹುಟ್ಟುಹಬ್ಬದ" in kan_wish_data["wishes"]["short"]
    print("Kannada Wish Sample (Short):", kan_wish_data["wishes"]["short"])

    # Check UI modal markup exists
    assert 'id="wishes-modal"' in html, "wishes-modal missing from HTML"
    assert 'id="wish-person-select"' in html, "wish-person-select missing from HTML"
    assert 'id="wish-lang-select"' in html, "wish-lang-select missing from HTML"

    print("PASS: Birthday Wish Generator API and UI verified in English & Kannada.")

    print("\n=======================================================")
    print("STEP 5: TESTING BIRTHDAY INSIGHTS")
    print("=======================================================")

    ins_res = client.get("/api/insights")
    assert ins_res.status_code == 200
    ins_data = json.loads(ins_res.get_data(as_text=True))

    print(f"Total Birthdays: {ins_data['total_birthdays']}")
    print(f"Birthdays this month ({ins_data['this_month_name']}): {ins_data['this_month']}")
    print(f"Upcoming next 30 days: {ins_data['upcoming_30_days']}")
    print(f"Top birthday month: {ins_data['most_common_month']}")
    print(f"Total relationships represented: {len(ins_data['relationship_counts'])}")

    assert ins_data["total_birthdays"] >= 100, "Expected at least 100 total birthdays"
    assert ins_data["most_common_month"]["month"] == "September", "Expected September as most common month"
    assert len(ins_data["relationship_counts"]) >= 15, "Expected all relationships in insights"

    # Check UI modal markup exists
    assert 'id="insights-modal"' in html, "insights-modal missing from HTML"
    assert 'id="insight-total"' in html, "insight-total missing from HTML"
    assert 'id="insight-this-month"' in html, "insight-this-month missing from HTML"
    assert 'id="insight-top-month"' in html, "insight-top-month missing from HTML"

    print("PASS: Birthday Insights API and UI verified.")

    print("\n=======================================================")
    print("STEP 6: TESTING LANGUAGE SUPPORT (ENGLISH & KANNADA ONLY)")
    print("=======================================================")

    from multilingual import detect_language, normalize_multilingual_query

    # English query
    lang_eng = detect_language("When is Rahul's birthday?")
    assert lang_eng == "english"

    # Kannada query
    lang_kan = detect_language("ರಾಹುಲ್ ಅವರ ಹುಟ್ಟುಹಬ್ಬ ಯಾವಾಗ?")
    assert lang_kan == "kannada"
    norm_kan, _ = normalize_multilingual_query("ರಾಹುಲ್ ಅವರ ಹುಟ್ಟುಹಬ್ಬ ಯಾವಾಗ?")
    assert "Rahul" in norm_kan

    # Transliterated Kannada
    lang_kan_tr = detect_language("Rahul na huttuhabba yavaga?")
    assert lang_kan_tr == "kannada"

    # Hindi query is detected as english (since Hindi support was removed)
    lang_hin = detect_language("Rahul ka janamdin kab hai?")
    assert lang_hin != "hindi", "Hindi must not be detected as supported language"

    print("PASS: Language support strictly limited to English and Kannada.")

    print("\n=======================================================")
    print("STEP 7: TESTING PRESERVED EXISTING FEATURES")
    print("=======================================================")

    # Person search
    r1 = client.post("/chat", json={"message": "when is Rahul birthday"})
    a1 = json.loads(r1.get_data(as_text=True))["answer"]
    assert "Rahul Patil" in a1 and "September" in a1
    print("Query: 'when is Rahul birthday' ->", a1)

    # Age calculation
    r2 = client.post("/chat", json={"message": "how old is Rahul"})
    a2 = json.loads(r2.get_data(as_text=True))["answer"]
    assert "years old" in a2 and "Rahul" in a2
    print("Query: 'how old is Rahul' ->", a2)

    # Location query
    r3 = client.post("/chat", json={"message": "where does Amma stay"})
    a3 = json.loads(r3.get_data(as_text=True))["answer"]
    assert "Davanagere" in a3
    print("Query: 'where does Amma stay' ->", a3)

    # Clean emojis check
    forbidden = ["🎀", "🌸", "💖", "💕", "✨", "💗", "🎉"]
    for f in forbidden:
        assert f not in html, f"Forbidden emoji '{f}' found in index.html"

    print("PASS: All existing features preserved without decorative emojis.")

    print("\n=======================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")

if __name__ == "__main__":
    run_all_tests()
