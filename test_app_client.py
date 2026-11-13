import re
import json
from app import app

def run_tests():
    client = app.test_client()

    print("\n--- 1. Testing Login Page & Clean Emoji Check ---")
    res = client.get("/login")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    login_html = res.get_data(as_text=True)
    forbidden_emojis = ["🎀", "🌸", "💖", "💕", "✨", "💗", "🎉"]
    for emoji in forbidden_emojis:
        assert emoji not in login_html, f"Forbidden emoji '{emoji}' found in login.html"
    print("PASS: Login page loaded without decorative emojis.")

    print("\n--- 2. Testing Authentication & Dashboard Layout ---")
    login_res = client.post("/login", data={"username": "user", "password": "user123"}, follow_redirects=True)
    assert login_res.status_code == 200
    dashboard_html = login_res.get_data(as_text=True)

    assert "Hello! I am your Birthday Assistant. 😀" in dashboard_html
    print("PASS: Dashboard authenticated and loaded.")

    print("\n--- 3. Testing NLU Details in Chat Response ---")

    def test_query(msg, expected_intent=None, expected_person=None, expected_month=None, expected_rel=None):
        res = client.post("/chat", json={"message": msg})
        assert res.status_code == 200, f"Chat failed for '{msg}'"
        data = json.loads(res.get_data(as_text=True))

        assert "answer" in data, "Response missing 'answer'"
        assert "nlu" in data, f"Response missing 'nlu' object for query: '{msg}'"

        nlu = data["nlu"]
        print(f"\nQuery: '{msg}'")
        print(f"  Bot answer: {data['answer']}")
        print(f"  1. Detected Intent: {nlu.get('intent')}")
        print(f"  2. Extracted Entities: {nlu.get('entities')}")
        print(f"  3. Identified Person: {nlu.get('person_name')}")
        print(f"  4. Detected Relationship: {nlu.get('relationship')} | Month: {nlu.get('month')}")
        print(f"  5. Processing Result: {nlu.get('result')}")

        # Assert mandatory 5 fields exist
        assert "intent" in nlu, "nlu missing 'intent'"
        assert "entities" in nlu, "nlu missing 'entities'"
        assert "person_name" in nlu, "nlu missing 'person_name'"
        assert "result" in nlu, "nlu missing 'result'"
        assert "relationship" in nlu, "nlu missing 'relationship'"
        assert "month" in nlu, "nlu missing 'month'"

        if expected_intent:
            assert nlu["intent"] == expected_intent, f"Expected intent {expected_intent}, got {nlu['intent']}"
        if expected_person:
            assert nlu["person_name"] == expected_person, f"Expected person {expected_person}, got {nlu['person_name']}"
        if expected_month:
            assert nlu["month"] == expected_month, f"Expected month {expected_month}, got {nlu['month']}"
        if expected_rel:
            assert nlu["relationship"] == expected_rel, f"Expected relationship {expected_rel}, got {nlu['relationship']}"

        return data

    # Test 1: Birthday query
    test_query(
        "when is Rahul birthday",
        expected_intent="birthday_search",
        expected_person="Rahul Patil"
    )

    # Test 2: Age calculation
    test_query(
        "how old is Rahul",
        expected_intent="calculate_age",
        expected_person="Rahul Patil"
    )

    # Test 3: Location query
    test_query(
        "where does Amma stay",
        expected_intent="person_place",
        expected_person="Shantha Gowda"
    )

    # Test 4: Month search
    test_query(
        "who has a birthday in September",
        expected_intent="birthday_search",
        expected_month="September"
    )

    # Test 5: Relationship query
    test_query(
        "when is my nephew's birthday",
        expected_intent="birthday_search",
        expected_rel="Nephew"
    )

    # Test 6: Greeting
    test_query(
        "Hello",
        expected_intent="greeting"
    )

    # Test 7: Unknown message
    test_query(
        "Venice",
        expected_intent="unknown"
    )

    print("\n--- 4. Verifying CSS & JS Expandable NLU Markup ---")
    with open("static/chat.js", "r", encoding="utf-8") as f:
        js_content = f.read()
    assert "nlu-details" in js_content, "chat.js missing nlu-details"
    assert "nlu-summary" in js_content, "chat.js missing nlu-summary"
    assert "Detected Intent" in js_content, "chat.js missing Detected Intent"
    assert "Extracted Entities" in js_content, "chat.js missing Extracted Entities"
    assert "Identified Person Name" in js_content, "chat.js missing Identified Person Name"
    assert "NLU Processing Result" in js_content, "chat.js missing NLU Processing Result"

    with open("static/style.css", "r", encoding="utf-8") as f:
        css_content = f.read()
    assert ".nlu-details" in css_content, "style.css missing .nlu-details"
    assert ".nlu-summary" in css_content, "style.css missing .nlu-summary"
    assert ".nlu-content" in css_content, "style.css missing .nlu-content"
    assert ".nlu-row" in css_content, "style.css missing .nlu-row"

    print("PASS: Frontend markup and CSS definitions verified.")

    print("\n================ ALL NLU DIALOGUE DISPLAY TESTS PASSED! ================\n")

if __name__ == "__main__":
    run_tests()
