import json
import re
from app import app

def test_voice_and_text():
    client = app.test_client()

    print("=======================================================")
    print("TEST 1: HTML & STATIC CODE VERIFICATION")
    print("=======================================================")

    with open("templates/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="user-input"' in html, "Missing #user-input in HTML"
    assert 'id="send-btn"' in html, "Missing #send-btn in HTML"
    assert 'id="speak-btn"' in html, "Missing #speak-btn in HTML"
    assert 'id="voice-lang-select"' in html, "Missing #voice-lang-select in HTML"
    assert 'value="en-IN"' in html, "Missing en-IN in voice language select"
    assert 'value="kn-IN"' in html, "Missing kn-IN in voice language select"
    print("PASS: Index HTML contains user-input, send-btn, speak-btn, and English/Kannada voice options.")

    with open("static/chat.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "handleUserSubmission(text, false)" in js, "Typing mode must call handleUserSubmission with isVoice=false"
    assert "handleUserSubmission(spokenText, true)" in js, "Voice mode must call handleUserSubmission with isVoice=true"
    assert "if (isVoice)" in js, "Voice output must only occur when isVoice is true"
    assert "speakResponse(data.answer" in js, "Voice mode must trigger speakResponse"
    assert "window.speechSynthesis.cancel()" in js, "Must cancel previous speech to prevent duplicate speech"
    assert "not-allowed" in js, "Microphone permission error handling must be present"
    assert "resetSpeakButton()" in js, "Speak button must reset after recognition finishes"
    assert "userInput.value = spokenText" in js, "Spoken text must be converted to visible text before sending"
    print("PASS: JavaScript logic correctly separates typing (no voice) and voice mode (with SpeechSynthesis).")

    print("\n=======================================================")
    print("TEST 2: VAISHNAVI NAIK BIRTHDAY QUERY")
    print("=======================================================")

    # Test question specified in prompt: "When is Vaishnavi Naik's birthday?"
    res = client.post("/chat", json={"message": "When is Vaishnavi Naik's birthday?"})
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.get_json()

    print("Query: \"When is Vaishnavi Naik's birthday?\"")
    print("Answer:", data["answer"])
    print("NLU:", data["nlu"])

    assert "Vaishnavi Naik" in data["answer"], "Answer must contain Vaishnavi Naik"
    assert "19 November" in data["answer"], "Answer must contain 19 November"
    assert data["nlu"]["intent"] == "birthday_search", "Intent must be birthday_search"
    assert data["nlu"]["person_name"] == "Vaishnavi Naik", "Person name must be Vaishnavi Naik"
    print("PASS: Query returns correct birthday and NLU details.")

    print("\n=======================================================")
    print("TEST 3: FULL REGRESSION TEST OF ENHANCED FEATURES")
    print("=======================================================")
    from test_enhanced_features import run_all_tests
    run_all_tests()
    print("PASS: Full regression suite passed!")

    print("\n=======================================================")
    print("ALL VOICE & TEXT INTERACTION TESTS PASSED!")
    print("=======================================================")

if __name__ == "__main__":
    test_voice_and_text()
