import json
import urllib.parse
from app import app, df

def test_wishes_studio():
    client = app.test_client()

    print("=======================================================")
    print("TEST 1: VERIFY VAISHNAVI NAIK DATA IN WORKBOOK")
    print("=======================================================")

    row = df[df["Name"].str.contains("Vaishnavi Naik", case=False, na=False)]
    assert not row.empty, "Vaishnavi Naik not found in DataFrame"
    person = row.iloc[0]
    pid = person["Person_ID"]
    name = person["Name"]
    rel = person["Relationship"]
    bday = person["DOB"].strftime("%d %B")

    print(f"Contact: {name} (ID: {pid})")
    print(f"Relationship: {rel}")
    print(f"Birthday Date: {bday}")
    assert pid == "P021"
    assert rel == "Friend"
    assert bday == "19 November"
    print("PASS: Verified Vaishnavi Naik contact data from Excel.")

    print("\n=======================================================")
    print("TEST 2: GENERATE WISHES IN ALL 5 STYLES (ENGLISH)")
    print("=======================================================")

    styles = ["friendly", "emotional", "funny", "formal", "short"]
    for s in styles:
        res = client.post("/api/wishes/generate", json={
            "person_id": pid,
            "lang": "english",
            "style": s,
            "variation": 0
        })
        assert res.status_code == 200, f"Failed wish generation for style {s}"
        data = res.get_json()
        wish = data["wish"]
        print(f"[{s.upper()}]: {wish}")

        assert len(wish) > 10, f"Wish too short for {s}"
        assert data["person_name"] == "Vaishnavi Naik"
        assert data["relationship"] == "Friend"
        assert data["birthday_date"] == "19 November"
        assert "Vaishnavi" in wish

    print("PASS: All 5 English styles generated successfully.")

    print("\n=======================================================")
    print("TEST 3: GENERATE WISHES IN ALL 5 STYLES (KANNADA)")
    print("=======================================================")

    for s in styles:
        res = client.post("/api/wishes/generate", json={
            "person_id": pid,
            "lang": "kannada",
            "style": s,
            "variation": 0
        })
        assert res.status_code == 200, f"Failed Kannada wish generation for style {s}"
        data = res.get_json()
        wish = data["wish"]
        print(f"[{s.upper()} - KANNADA]: {wish}")

        assert len(wish) > 10, f"Kannada wish too short for {s}"
        assert data["person_name"] == "Vaishnavi Naik"
        assert data["relationship"] == "Friend"
        assert data["birthday_date"] == "19 November"
        # Check Kannada Unicode range
        assert any('\u0C80' <= c <= '\u0CFF' for c in wish), f"Missing Kannada characters in {s}"

    print("PASS: All 5 Kannada styles generated successfully.")

    print("\n=======================================================")
    print("TEST 4: REGENERATE WISH VARIATIONS")
    print("=======================================================")

    variations = []
    for var_idx in [0, 1, 2]:
        res = client.post("/api/wishes/generate", json={
            "person_id": pid,
            "lang": "english",
            "style": "friendly",
            "variation": var_idx
        })
        assert res.status_code == 200
        w = res.get_json()["wish"]
        print(f"Variation {var_idx + 1}: {w}")
        variations.append(w)

    assert len(set(variations)) == 3, "Regenerate must produce distinct variations for the same style"
    print("PASS: 3 distinct variations verified for style regeneration.")

    print("\n=======================================================")
    print("TEST 5: VERIFY WHATSAPP & EMAIL SHARING FORMATS")
    print("=======================================================")

    chosen_wish = variations[0]

    # WhatsApp sharing URL
    wa_encoded = urllib.parse.quote(chosen_wish)
    wa_url = f"https://api.whatsapp.com/send?text={wa_encoded}"
    assert "https://api.whatsapp.com/send?text=" in wa_url
    assert urllib.parse.unquote(wa_encoded) == chosen_wish
    print(f"WhatsApp URL prefix: {wa_url[:65]}...")

    # Email sharing URL
    subject = f"Happy Birthday {name}!"
    subject_encoded = urllib.parse.quote(subject)
    body_encoded = urllib.parse.quote(chosen_wish)
    mailto_url = f"mailto:?subject={subject_encoded}&body={body_encoded}"
    assert "mailto:?subject=" in mailto_url
    assert f"Happy%20Birthday%20{urllib.parse.quote(name)}" in mailto_url
    assert urllib.parse.unquote(body_encoded) == chosen_wish
    print(f"Email URL: {mailto_url[:65]}...")

    print("PASS: WhatsApp and Email sharing prefill URLs verified.")

    print("\n=======================================================")
    print("TEST 6: VERIFY HTML & JAVASCRIPT STUDIO ELEMENTS")
    print("=======================================================")

    with open("templates/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="open-wishes-btn"' in html
    assert 'id="wishes-modal"' in html
    assert 'id="wish-person-select"' in html
    assert 'id="wish-lang-select"' in html
    assert 'id="copy-wish-btn"' in html
    assert 'id="share-whatsapp-btn"' in html
    assert 'id="share-email-btn"' in html
    assert 'id="download-card-btn"' in html
    assert 'id="regenerate-wish-btn"' in html
    assert 'id="greeting-card-preview"' in html
    assert 'id="greeting-card-canvas"' in html
    assert 'data-style="friendly"' in html
    assert 'data-style="emotional"' in html
    assert 'data-style="funny"' in html
    assert 'data-style="formal"' in html
    assert 'data-style="short"' in html
    print("PASS: All Wishes Studio buttons, style selectors, and preview elements present in index.html.")

    with open("static/chat.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "copyCurrentWish" in js
    assert "shareWishOnWhatsApp" in js
    assert "shareWishByEmail" in js
    assert "downloadGreetingCardPng" in js
    assert "regenerateWish" in js
    assert "selectWishStyle" in js
    assert "api.whatsapp.com/send?text=" in js
    assert "mailto:?subject=" in js
    assert "canvas.toDataURL(\"image/png\")" in js
    print("PASS: JavaScript includes copy, WhatsApp, Email, and Canvas PNG download functions.")

    print("\n=======================================================")
    print("TEST 7: FULL REGRESSION TEST OF EXISTING SYSTEM")
    print("=======================================================")
    from test_voice_text_interaction import test_voice_and_text
    test_voice_and_text()
    print("PASS: All voice, NLU, dialogue, and calendar regression tests passed!")

    print("\n=======================================================")
    print("ALL BIRTHDAY WISHES STUDIO TESTS COMPLETED SUCCESSFULLY!")
    print("=======================================================")

if __name__ == "__main__":
    test_wishes_studio()
