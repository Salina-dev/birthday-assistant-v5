// ==================================================
// Birthday Assistant - Dashboard & Calendar Logic
// ==================================================

const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-btn");
const speakButton = document.getElementById("speak-btn");
const voiceLangSelect = document.getElementById("voice-lang-select");

// --------------------------------------------------
// CHAT MESSAGES & VOICE
// --------------------------------------------------

function addMessage(message, className, nlu = null) {
    const messageDiv = document.createElement("div");
    messageDiv.className = className;

    const textDiv = document.createElement("div");
    textDiv.className = "bot-text";
    textDiv.textContent = message;
    messageDiv.appendChild(textDiv);

    // Expandable NLU details section below chatbot response
    if (className === "bot-message" && nlu) {
        const detailsEl = createNluDetailsElement(nlu);
        messageDiv.appendChild(detailsEl);
    }

    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function createNluDetailsElement(nlu) {
    const details = document.createElement("details");
    details.className = "nlu-details";

    const summary = document.createElement("summary");
    summary.className = "nlu-summary";
    summary.textContent = "NLU Details";
    details.appendChild(summary);

    const content = document.createElement("div");
    content.className = "nlu-content";

    // 1. Detected intent
    const rowIntent = createNluRow("Detected Intent", nlu.intent || "None", true);
    content.appendChild(rowIntent);

    // 2. Extracted entities
    let entitiesText = "None";
    if (nlu.entities && Object.keys(nlu.entities).length > 0) {
        entitiesText = Object.entries(nlu.entities)
            .map(([k, v]) => `${k}: ${v}`)
            .join(", ");
    }
    const rowEntities = createNluRow("Extracted Entities", entitiesText);
    content.appendChild(rowEntities);

    // 3. Identified person name
    const rowPerson = createNluRow("Identified Person Name", nlu.person_name || "None");
    content.appendChild(rowPerson);

    // 4. Detected relationship or month, when available
    if (nlu.relationship) {
        content.appendChild(createNluRow("Detected Relationship", nlu.relationship));
    }
    if (nlu.month) {
        content.appendChild(createNluRow("Detected Month", nlu.month));
    }
    if (!nlu.relationship && !nlu.month) {
        content.appendChild(createNluRow("Detected Relationship / Month", "None"));
    }

    // 5. NLU processing result
    const rowResult = createNluRow("NLU Processing Result", nlu.result || nlu.person_status || "Processed");
    content.appendChild(rowResult);

    details.appendChild(content);
    return details;
}

function createNluRow(label, value, isBadge = false) {
    const row = document.createElement("div");
    row.className = "nlu-row";

    const labelSpan = document.createElement("span");
    labelSpan.className = "nlu-label";
    labelSpan.textContent = label + ":";

    const valSpan = document.createElement("span");
    valSpan.className = "nlu-value";
    if (isBadge) {
        const badge = document.createElement("span");
        badge.className = "nlu-badge";
        badge.textContent = String(value);
        valSpan.appendChild(badge);
    } else {
        valSpan.textContent = String(value);
    }

    row.appendChild(labelSpan);
    row.appendChild(valSpan);
    return row;
}

function speakResponse(message, langCode = "en-IN") {
    if ("speechSynthesis" in window) {
        // Cancel any active speech to avoid duplicate or overlapping voice output
        window.speechSynthesis.cancel();
        const speech = new SpeechSynthesisUtterance(message);

        // Detect Kannada script or user preference
        if (/[\u0C80-\u0CFF]/.test(message) || langCode === "kn-IN") {
            speech.lang = "kn-IN";
        } else {
            speech.lang = "en-IN";
        }

        // Match available system voice if present
        const voices = window.speechSynthesis.getVoices();
        if (voices && voices.length > 0) {
            const targetPrefix = speech.lang.slice(0, 2).toLowerCase();
            const matched = voices.find(v => v.lang && v.lang.toLowerCase().startsWith(targetPrefix));
            if (matched) {
                speech.voice = matched;
            }
        }

        window.speechSynthesis.speak(speech);
    }
}

// Unified submission handler
// isVoice = true: reads chatbot answer aloud using SpeechSynthesis
// isVoice = false (typing mode): displays text answer only, NO voice output
async function handleUserSubmission(messageText, isVoice = false) {
    const message = (messageText || "").trim();

    if (message === "") {
        return;
    }

    // Display user message in conversation
    addMessage(message, "user-message");
    userInput.value = "";

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message
            })
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }

        const data = await response.json();
        addMessage(data.answer, "bot-message", data.nlu);

        // Voice output MUST ONLY occur for questions submitted via voice mode
        if (isVoice) {
            const currentVoiceLang = (voiceLangSelect && voiceLangSelect.value) ? voiceLangSelect.value : "en-IN";
            speakResponse(data.answer, currentVoiceLang);
        }

    } catch (error) {
        console.error("Chat error:", error);
        addMessage(
            "Sorry, something went wrong. Please try again.",
            "bot-message"
        );
    }
}

// --------------------------------------------------
// TYPING MODE (TEXT INPUT)
// --------------------------------------------------
function sendTypedMessage() {
    const text = userInput.value;
    handleUserSubmission(text, false); // isVoice = false -> never triggers voice output or microphone
}

sendButton.addEventListener("click", sendTypedMessage);

userInput.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        sendTypedMessage();
    }
});

// --------------------------------------------------
// SPEECH RECOGNITION (VOICE INPUT)
// --------------------------------------------------

const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;

    let isListening = false;

    function resetSpeakButton() {
        isListening = false;
        speakButton.textContent = "Speak";
        speakButton.classList.remove("is-listening");
    }

    speakButton.addEventListener("click", function() {
        if (isListening) {
            try {
                recognition.stop();
            } catch (e) {}
            resetSpeakButton();
            return;
        }

        // Support English and Kannada only
        const selectedLang = (voiceLangSelect && voiceLangSelect.value) ? voiceLangSelect.value : "en-IN";
        recognition.lang = selectedLang;

        try {
            recognition.start();
            isListening = true;
            speakButton.textContent = "Listening...";
            speakButton.classList.add("is-listening");
        } catch (err) {
            console.error("Speech recognition start failed:", err);
            resetSpeakButton();
        }
    });

    recognition.onresult = function(event) {
        resetSpeakButton();

        if (!event.results || !event.results[0] || !event.results[0][0]) {
            return;
        }

        const spokenText = event.results[0][0].transcript.trim();
        if (!spokenText) {
            return;
        }

        // Display recognized text visibly in input box first
        userInput.value = spokenText;

        if (/^(when is|when's|when are|where is|where does)$/i.test(spokenText)) {
            const promptMsg = "Please say the complete question, including the person's name.";
            addMessage(promptMsg, "bot-message");
            speakResponse(promptMsg, recognition.lang);
            return;
        }

        // Send recognized question to /chat with voice mode enabled (isVoice = true)
        handleUserSubmission(spokenText, true);
    };

    recognition.onerror = function(event) {
        resetSpeakButton();
        console.warn("Speech recognition error:", event.error);

        let errorMsg = "Voice recognition failed. Please try again.";
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
            errorMsg = "Microphone access was denied. Please allow microphone permissions in your browser.";
        } else if (event.error === "no-speech") {
            errorMsg = "No speech detected. Please try speaking again.";
        }
        addMessage(errorMsg, "bot-message");
    };

    recognition.onend = function() {
        resetSpeakButton();
    };

} else {
    speakButton.disabled = true;
    speakButton.textContent = "Voice Not Supported";
}


// --------------------------------------------------
// GLOBAL CONTACTS STORE
// --------------------------------------------------

let allContactsList = [];

async function fetchContactsData() {
    try {
        const res = await fetch("/api/contacts");
        if (res.ok) {
            allContactsList = await res.json();
            renderCalendar(calCurrentDate);
            renderUpcomingBirthdays(allContactsList);
            populateWishPersonSelect();
            populateWishPersonSelect();
        }
    } catch (e) {
        console.error("Error fetching contacts:", e);
    }
}


// --------------------------------------------------
// RIGHT SIDE: BIRTHDAY CALENDAR
// --------------------------------------------------

const calPrevBtn = document.getElementById("cal-prev-btn");
const calNextBtn = document.getElementById("cal-next-btn");
const calMonthYear = document.getElementById("cal-month-year");
const calDaysContainer = document.getElementById("calendar-days");
const todayDisplay = document.getElementById("today-display");
const selectedDateTitle = document.getElementById("selected-date-title");
const selectedDateContent = document.getElementById("selected-date-content");
const upcomingBirthdaysList = document.getElementById("upcoming-birthdays-list");

let calCurrentDate = new Date();

const MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
];

function initCalendar() {
    const today = new Date();
    if (todayDisplay) {
        const options = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
        todayDisplay.textContent = `Today: ${today.toLocaleDateString('en-GB', options)}`;
    }

    if (calPrevBtn) {
        calPrevBtn.addEventListener("click", () => {
            calCurrentDate.setMonth(calCurrentDate.getMonth() - 1);
            renderCalendar(calCurrentDate);
        });
    }

    if (calNextBtn) {
        calNextBtn.addEventListener("click", () => {
            calCurrentDate.setMonth(calCurrentDate.getMonth() + 1);
            renderCalendar(calCurrentDate);
        });
    }

    renderCalendar(calCurrentDate);
}

function parseDobMonthDay(dobStr) {
    if (!dobStr) return null;
    const parts = dobStr.split("-");
    if (parts.length >= 3) {
        return {
            month: parseInt(parts[1], 10),
            day: parseInt(parts[2], 10),
            year: parseInt(parts[0], 10)
        };
    }
    return null;
}

function renderCalendar(dateObj) {
    if (!calDaysContainer || !calMonthYear) return;

    const year = dateObj.getFullYear();
    const month = dateObj.getMonth(); // 0-indexed

    calMonthYear.textContent = `${MONTH_NAMES[month]} ${year}`;
    calDaysContainer.innerHTML = "";

    const firstDayIndex = new Date(year, month, 1).getDay(); // 0 is Sunday
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

    // Render leading empty cells
    for (let i = 0; i < firstDayIndex; i++) {
        const emptyCell = document.createElement("div");
        emptyCell.className = "cal-cell empty";
        calDaysContainer.appendChild(emptyCell);
    }

    // Render active day cells
    for (let day = 1; day <= daysInMonth; day++) {
        const cell = document.createElement("div");
        cell.className = "cal-cell";
        cell.textContent = day;

        // Check if today
        if (isCurrentMonth && today.getDate() === day) {
            cell.classList.add("is-today");
            cell.title = "Today";
        }

        // Find birthdays on this day (contacts month is 1-indexed)
        const dayMonth = month + 1;
        const matchingContacts = allContactsList.filter(c => {
            const parsed = parseDobMonthDay(c.dob);
            return parsed && parsed.month === dayMonth && parsed.day === day;
        });

        if (matchingContacts.length > 0) {
            cell.classList.add("has-birthday");
            const names = matchingContacts.map(c => c.name).join(", ");
            cell.title = `Birthday: ${names}`;
        }

        cell.addEventListener("click", () => {
            // Deselect other cells
            document.querySelectorAll(".cal-cell.is-selected").forEach(el => el.classList.remove("is-selected"));
            cell.classList.add("is-selected");

            showSelectedDateDetails(day, month, year, matchingContacts);
        });

        calDaysContainer.appendChild(cell);
    }
}

function showSelectedDateDetails(day, month, year, contacts) {
    if (!selectedDateTitle || !selectedDateContent) return;

    selectedDateTitle.textContent = `Birthdays on ${day} ${MONTH_NAMES[month]}`;

    if (!contacts || contacts.length === 0) {
        selectedDateContent.innerHTML = `<p class="text-muted">No birthdays recorded on this date.</p>`;
        return;
    }

    let html = "";
    contacts.forEach(c => {
        const parsed = parseDobMonthDay(c.dob);
        const birthYear = parsed ? parsed.year : null;
        let ageInfo = "";
        if (birthYear) {
            const thisYearAge = year - birthYear;
            ageInfo = ` (Turning ${thisYearAge})`;
        }

        html += `
            <div class="birthday-person-item">
                <strong>${c.name}</strong>${ageInfo}
                <div class="upcoming-details">
                    ${c.relationship ? `<span class="badge">${c.relationship}</span> ` : ""}
                    ${c.place_of_stay ? `Location: ${c.place_of_stay}` : ""}
                </div>
            </div>
        `;
    });

    selectedDateContent.innerHTML = html;
}

function renderUpcomingBirthdays(contacts) {
    if (!upcomingBirthdaysList) return;
    upcomingBirthdaysList.innerHTML = "";

    const nearestCard = document.getElementById("nearest-countdown-card");
    const nearestText = document.getElementById("nearest-countdown-text");
    const nearestSub = document.getElementById("nearest-countdown-sub");

    if (!contacts || contacts.length === 0) {
        upcomingBirthdaysList.innerHTML = `<li class="upcoming-item text-muted">No upcoming birthdays found.</li>`;
        if (nearestCard) nearestCard.style.display = "none";
        return;
    }

    const today = new Date();

    // Map each contact to their next upcoming birthday
    const upcomingWithDiff = contacts.map(c => {
        const parsed = parseDobMonthDay(c.dob);
        if (!parsed) return null;

        let bdayThisYear = new Date(today.getFullYear(), parsed.month - 1, parsed.day);
        if (bdayThisYear < new Date(today.getFullYear(), today.getMonth(), today.getDate())) {
            // Birthday has passed this year, take next year
            bdayThisYear = new Date(today.getFullYear() + 1, parsed.month - 1, parsed.day);
        }

        const diffTime = bdayThisYear - today;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        return {
            contact: c,
            nextDate: bdayThisYear,
            diffDays: diffDays,
            displayDate: `${parsed.day} ${MONTH_NAMES[parsed.month - 1].substring(0, 3)}`
        };
    }).filter(item => item !== null);

    // Sort by smallest positive days remaining
    upcomingWithDiff.sort((a, b) => a.diffDays - b.diffDays);

    const topUpcoming = upcomingWithDiff.slice(0, 6);

    if (topUpcoming.length === 0) {
        upcomingBirthdaysList.innerHTML = `<li class="upcoming-item text-muted">No upcoming birthdays found.</li>`;
        if (nearestCard) nearestCard.style.display = "none";
        return;
    }

    // Nearest Birthday Countdown Card
    if (nearestCard && nearestText) {
        const nearest = topUpcoming[0];
        const firstName = nearest.contact.name.split(" ")[0];
        let countdownStr = "";
        if (nearest.diffDays === 0) {
            countdownStr = `${firstName}'s birthday is today!`;
        } else if (nearest.diffDays === 1) {
            countdownStr = `${firstName}'s birthday is tomorrow!`;
        } else {
            countdownStr = `${firstName}'s birthday is in ${nearest.diffDays} days.`;
        }
        nearestText.textContent = countdownStr;
        if (nearestSub) {
            nearestSub.textContent = `${nearest.contact.name} (${nearest.contact.relationship || 'Contact'}) • ${nearest.displayDate}`;
        }
        nearestCard.style.display = "block";
    }

    topUpcoming.forEach((item, index) => {
        const c = item.contact;
        const li = document.createElement("li");
        li.className = "upcoming-item" + (index === 0 ? " is-nearest" : "");

        let daysText = item.diffDays === 0 ? "Today" : (item.diffDays === 1 ? "Tomorrow" : `In ${item.diffDays} days`);

        li.innerHTML = `
            <div>
                <div class="upcoming-name">${c.name} ${index === 0 ? '<span class="badge" style="font-size: 10px; margin-left: 4px;">Nearest</span>' : ''}</div>
                <div class="upcoming-details">${c.relationship || 'Contact'} &bull; ${daysText}</div>
            </div>
            <span class="upcoming-date">${item.displayDate}</span>
        `;
        upcomingBirthdaysList.appendChild(li);
    });
}


// --------------------------------------------------
// FEATURE 1: BIRTHDAY REMINDER NOTIFICATIONS
// --------------------------------------------------

const reminderToggleBtn = document.getElementById("reminder-toggle-btn");
const reminderStatusText = document.getElementById("reminder-status-text");
const reminderModal = document.getElementById("reminder-modal");
const allowRemindersBtn = document.getElementById("allow-reminders-btn");
const reminderBanner = document.getElementById("reminder-banner");
const reminderBannerText = document.getElementById("reminder-banner-text");
const closeReminderBannerBtn = document.getElementById("close-reminder-banner");

let remindersActive = false;

async function checkReminderStatus() {
    try {
        const res = await fetch("/api/reminders/status");
        if (res.ok) {
            const data = await res.json();
            remindersActive = data.enabled && data.permission_granted;
            updateReminderUI(remindersActive);
            if (remindersActive) {
                fetchAndDisplayUpcomingReminders();
            }
        }
    } catch (e) {
        console.log("Reminder status check error:", e);
    }
}

function updateReminderUI(active) {
    if (reminderStatusText) {
        reminderStatusText.textContent = active ? "ON" : "OFF";
        if (reminderToggleBtn) {
            reminderToggleBtn.style.background = active ? "#f5dfe5" : "#fbeff2";
            reminderToggleBtn.style.borderColor = active ? "#c96b86" : "#ebdce1";
        }
    }
}

function openReminderModal() {
    if (reminderModal) reminderModal.style.display = "flex";
}

function closeReminderModal() {
    if (reminderModal) reminderModal.style.display = "none";
}

if (reminderToggleBtn) {
    reminderToggleBtn.addEventListener("click", () => {
        if (!remindersActive) {
            openReminderModal();
        } else {
            disableReminders();
        }
    });
}

if (allowRemindersBtn) {
    allowRemindersBtn.addEventListener("click", async () => {
        closeReminderModal();
        if ("Notification" in window) {
            const permission = await Notification.requestPermission();
            if (permission === "granted") {
                await saveReminderSettings(true, true);
                remindersActive = true;
                updateReminderUI(true);
                fetchAndDisplayUpcomingReminders();
                new Notification("Birthday Assistant", {
                    body: "Reminders enabled. You will receive notifications for upcoming birthdays."
                });
            } else {
                alert("Notification permission was not granted by your browser.");
                await saveReminderSettings(false, false);
                remindersActive = false;
                updateReminderUI(false);
            }
        } else {
            await saveReminderSettings(true, true);
            remindersActive = true;
            updateReminderUI(true);
            fetchAndDisplayUpcomingReminders();
        }
    });
}

async function disableReminders() {
    await saveReminderSettings(false, false);
    remindersActive = false;
    updateReminderUI(false);
    if (reminderBanner) reminderBanner.style.display = "none";
}

async function saveReminderSettings(enabled, permissionGranted) {
    try {
        await fetch("/api/reminders/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled, permission_granted: permissionGranted })
        });
    } catch (e) {
        console.error("Error saving reminder settings:", e);
    }
}

async function fetchAndDisplayUpcomingReminders() {
    if (!remindersActive) return;
    try {
        const res = await fetch("/api/reminders");
        if (res.ok) {
            const data = await res.json();
            const reminders = data.reminders || [];
            if (reminders.length > 0) {
                const names = reminders.map(r => `${r.name} (${r.dob_formatted})`).join(", ");
                if (reminderBanner && reminderBannerText) {
                    reminderBannerText.textContent = `Upcoming Birthday Reminder: ${names}`;
                    reminderBanner.style.display = "flex";
                }
            }
        }
    } catch (e) {
        console.log("Reminders fetch error:", e);
    }
}

if (closeReminderBannerBtn) {
    closeReminderBannerBtn.addEventListener("click", () => {
        if (reminderBanner) reminderBanner.style.display = "none";
    });
}


// --------------------------------------------------
// FEATURE: BIRTHDAY WISH GENERATOR
// --------------------------------------------------

// ==================================================
// FEATURE: BIRTHDAY WISHES STUDIO
// ==================================================

const openWishesBtn = document.getElementById("open-wishes-btn");
const wishesModal = document.getElementById("wishes-modal");
const wishPersonSelect = document.getElementById("wish-person-select");
const wishLangSelect = document.getElementById("wish-lang-select");
const wishPersonInfo = document.getElementById("wish-person-info");
const wishPersonName = document.getElementById("wish-person-name");
const wishPersonBadge = document.getElementById("wish-person-badge");
const wishPersonBday = document.getElementById("wish-person-bday");
const wishPersonLocation = document.getElementById("wish-person-location");
const wishesResultsContainer = document.getElementById("wishes-results-container");
const wishPlaceholder = document.getElementById("wish-placeholder");
const generatedWishText = document.getElementById("generated-wish-text");
const currentStyleLabel = document.getElementById("current-style-label");
const variationIndicator = document.getElementById("variation-indicator");

// Card preview elements
const cardPreviewName = document.getElementById("card-preview-name");
const cardPreviewRel = document.getElementById("card-preview-rel");
const cardPreviewWish = document.getElementById("card-preview-wish");
const cardPreviewDate = document.getElementById("card-preview-date");

let currentWishData = null;
let currentSelectedStyle = "friendly";
let currentVariationIndex = 0;

function openWishesModal() {
    if (wishesModal) {
        wishesModal.style.display = "flex";
        populateWishPersonSelect();
    }
}

function closeWishesModal() {
    if (wishesModal) wishesModal.style.display = "none";
}

if (openWishesBtn) {
    openWishesBtn.addEventListener("click", openWishesModal);
}

function populateWishPersonSelect() {
    if (!wishPersonSelect) return;
    const currentVal = wishPersonSelect.value;
    wishPersonSelect.innerHTML = '<option value="">-- Choose a contact --</option>';
    allContactsList.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.person_id;
        opt.textContent = `${c.name} (${c.relationship || 'Contact'})`;
        wishPersonSelect.appendChild(opt);
    });
    if (currentVal) wishPersonSelect.value = currentVal;
}

function selectWishStyle(style) {
    currentSelectedStyle = style;
    document.querySelectorAll(".style-pill").forEach(pill => {
        if (pill.getAttribute("data-style") === style) {
            pill.classList.add("active");
        } else {
            pill.classList.remove("active");
        }
    });

    if (currentWishData && currentWishData.wishes && currentWishData.wishes[style]) {
        currentWishData.style = style;
        currentWishData.wish = currentWishData.wishes[style];
        updateWishStudioDisplay();
    } else {
        generateWishes();
    }
}

function regenerateWish() {
    currentVariationIndex = (currentVariationIndex + 1) % 3;
    generateWishes();
}

async function generateWishes() {
    const pid = wishPersonSelect ? wishPersonSelect.value : "";
    const lang = wishLangSelect ? wishLangSelect.value : "english";

    if (!pid) {
        if (wishesResultsContainer) wishesResultsContainer.style.display = "none";
        if (wishPersonInfo) wishPersonInfo.style.display = "none";
        if (wishPlaceholder) wishPlaceholder.style.display = "block";
        currentWishData = null;
        return;
    }

    const person = allContactsList.find(c => c.person_id === pid);

    try {
        const res = await fetch("/api/wishes/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                person_id: pid,
                lang: lang,
                style: currentSelectedStyle,
                variation: currentVariationIndex
            })
        });

        if (res.ok) {
            const data = await res.json();
            currentWishData = data;
            currentWishData.place_of_stay = (person && person.place_of_stay) ? person.place_of_stay : "";

            // Update contact details card
            if (wishPersonName) wishPersonName.textContent = data.person_name;
            if (wishPersonBadge) wishPersonBadge.textContent = data.relationship || "Contact";
            if (wishPersonBday) wishPersonBday.textContent = data.birthday_date || "--";
            if (wishPersonLocation) {
                wishPersonLocation.textContent = currentWishData.place_of_stay ? `Location: ${currentWishData.place_of_stay}` : "";
            }
            if (wishPersonInfo) wishPersonInfo.style.display = "block";

            // Update backwards compatibility elements
            const wishes = data.wishes || {};
            const elShort = document.getElementById("wish-short-text");
            if (elShort) elShort.textContent = wishes.short || "";
            const elFriendly = document.getElementById("wish-friendly-text");
            if (elFriendly) elFriendly.textContent = wishes.friendly || "";
            const elEmotional = document.getElementById("wish-emotional-text");
            if (elEmotional) elEmotional.textContent = wishes.emotional || "";

            updateWishStudioDisplay();

            if (wishPlaceholder) wishPlaceholder.style.display = "none";
            if (wishesResultsContainer) wishesResultsContainer.style.display = "flex";
        }
    } catch (err) {
        console.error("Error generating wishes:", err);
    }
}

function updateWishStudioDisplay() {
    if (!currentWishData) return;

    const styleName = currentSelectedStyle.charAt(0).toUpperCase() + currentSelectedStyle.slice(1);
    if (currentStyleLabel) currentStyleLabel.textContent = `${styleName} Style`;
    if (variationIndicator) variationIndicator.textContent = `Variation ${(currentVariationIndex % 3) + 1} of 3`;
    if (generatedWishText) generatedWishText.textContent = currentWishData.wish || "";

    // Update greeting card preview
    if (cardPreviewName) cardPreviewName.textContent = currentWishData.person_name;
    if (cardPreviewRel) cardPreviewRel.textContent = `To my wonderful ${currentWishData.relationship || 'Friend'}`;
    if (cardPreviewWish) cardPreviewWish.textContent = currentWishData.wish || "";
    if (cardPreviewDate) cardPreviewDate.textContent = `Birthday: ${currentWishData.birthday_date || 'Special Day'}`;

    // Highlight active style pill
    document.querySelectorAll(".style-pill").forEach(pill => {
        if (pill.getAttribute("data-style") === currentSelectedStyle) {
            pill.classList.add("active");
        } else {
            pill.classList.remove("active");
        }
    });
}

function copyCurrentWish() {
    const textToCopy = currentWishData ? currentWishData.wish : "";
    if (!textToCopy) return;

    navigator.clipboard.writeText(textToCopy).then(() => {
        showCopyFeedback();
    }).catch(() => {
        // Fallback for older browsers
        const textarea = document.createElement("textarea");
        textarea.value = textToCopy;
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand("copy");
            showCopyFeedback();
        } catch (e) {
            alert("Unable to copy to clipboard.");
        }
        document.body.removeChild(textarea);
    });
}

function showCopyFeedback() {
    const toast = document.getElementById("copy-feedback-toast");
    const copyBtn = document.getElementById("copy-wish-btn");

    if (toast) {
        toast.style.display = "block";
        setTimeout(() => { toast.style.display = "none"; }, 2000);
    }

    if (copyBtn) {
        const originalText = copyBtn.innerHTML;
        copyBtn.innerHTML = '<span class="btn-icon">&#x2713;</span> Copied!';
        setTimeout(() => { copyBtn.innerHTML = originalText; }, 1800);
    }
}

function shareWishOnWhatsApp() {
    const text = currentWishData ? currentWishData.wish : "";
    if (!text) return;
    const url = `https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`;
    window.open(url, "_blank");
}

function shareWishByEmail() {
    const text = currentWishData ? currentWishData.wish : "";
    if (!text) return;
    const name = currentWishData.person_name || "Friend";
    const subject = `Happy Birthday ${name}!`;
    const mailto = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;
    window.location.href = mailto;
}

function downloadGreetingCardPng() {
    if (!currentWishData) return;

    const canvas = document.getElementById("greeting-card-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = 1200;
    const H = 750;
    canvas.width = W;
    canvas.height = H;

    // 1. Soft pink-to-white background gradient
    const bgGrad = ctx.createLinearGradient(0, 0, W, H);
    bgGrad.addColorStop(0, "#ffffff");
    bgGrad.addColorStop(0.5, "#fdf6f8");
    bgGrad.addColorStop(1, "#fceed3");
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, W, H);

    // 2. Outer border
    ctx.strokeStyle = "#ebd0d9";
    ctx.lineWidth = 6;
    ctx.strokeRect(20, 20, W - 40, H - 40);

    // 3. Inner decorative frame with rounded corners
    ctx.strokeStyle = "#cb6d88";
    ctx.lineWidth = 2.5;
    const pad = 44;
    roundRect(ctx, pad, pad, W - (pad * 2), H - (pad * 2), 20);
    ctx.stroke();

    // 4. Header Badge: HAPPY BIRTHDAY
    ctx.font = "bold 18px 'Inter', Arial, sans-serif";
    ctx.fillStyle = "#cb6d88";
    ctx.textAlign = "center";
    ctx.fillText("★  H A P P Y   B I R T H D A Y  ★", W / 2, 110);

    // 5. Recipient Name
    ctx.font = "bold 50px 'Inter', Arial, sans-serif";
    ctx.fillStyle = "#2d3142";
    ctx.fillText(currentWishData.person_name || "", W / 2, 175);

    // 6. Relationship Subtitle
    ctx.font = "italic 24px 'Inter', Arial, sans-serif";
    ctx.fillStyle = "#8e5b6c";
    ctx.fillText(`To my wonderful ${currentWishData.relationship || "Friend"}`, W / 2, 218);

    // 7. Divider Line
    ctx.strokeStyle = "#eecfd7";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo((W / 2) - 80, 246);
    ctx.lineTo((W / 2) + 80, 246);
    ctx.stroke();

    // 8. Wish Text (wrapped & centered)
    ctx.font = "26px 'Inter', Arial, sans-serif";
    ctx.fillStyle = "#333745";
    const maxWidth = 980;
    const lineHeight = 42;
    const textLines = getCanvasWrappedLines(ctx, currentWishData.wish || "", maxWidth);

    // Center vertically in middle region
    const startY = 320;
    textLines.forEach((line, idx) => {
        ctx.fillText(line, W / 2, startY + (idx * lineHeight));
    });

    // 9. Footer Birthday Date Pill
    const bdayText = `Birthday Date: ${currentWishData.birthday_date || "Special Day"}`;
    ctx.font = "bold 18px 'Inter', Arial, sans-serif";
    const pillW = ctx.measureText(bdayText).width + 36;
    const pillH = 38;
    const pillX = (W / 2) - (pillW / 2);
    const pillY = 620;

    ctx.fillStyle = "#fdf2f5";
    roundRect(ctx, pillX, pillY, pillW, pillH, 10);
    ctx.fill();
    ctx.strokeStyle = "#ebd0d9";
    ctx.lineWidth = 1.5;
    roundRect(ctx, pillX, pillY, pillW, pillH, 10);
    ctx.stroke();

    ctx.fillStyle = "#cb6d88";
    ctx.fillText(bdayText, W / 2, pillY + 25);

    // 10. Subtle branding footer
    ctx.font = "14px 'Inter', Arial, sans-serif";
    ctx.fillStyle = "#9a8b92";
    ctx.fillText("Sent with warm wishes • Birthday Assistant", W / 2, 680);

    // Trigger PNG download
    const cleanName = (currentWishData.person_name || "Contact").replace(/[^a-zA-Z0-9]/g, "_");
    const filename = `Happy_Birthday_${cleanName}.png`;
    const dataUrl = canvas.toDataURL("image/png");

    const link = document.createElement("a");
    link.download = filename;
    link.href = dataUrl;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function roundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
}

function getCanvasWrappedLines(ctx, text, maxWidth) {
    const words = text.split(" ");
    const lines = [];
    let currentLine = "";

    words.forEach(word => {
        const testLine = currentLine ? `${currentLine} ${word}` : word;
        const testWidth = ctx.measureText(testLine).width;
        if (testWidth > maxWidth && currentLine) {
            lines.push(currentLine);
            currentLine = word;
        } else {
            currentLine = testLine;
        }
    });

    if (currentLine) {
        lines.push(currentLine);
    }
    return lines;
}

if (wishPersonSelect) {
    wishPersonSelect.addEventListener("change", () => {
        currentVariationIndex = 0;
        generateWishes();
    });
}

if (wishLangSelect) {
    wishLangSelect.addEventListener("change", () => {
        currentVariationIndex = 0;
        generateWishes();
    });
}

// Backwards compatibility for older copy function
window.copyWishText = function(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
        showCopyFeedback();
    }).catch(() => {
        alert("Unable to copy to clipboard.");
    });
};

window.selectWishStyle = selectWishStyle;
window.regenerateWish = regenerateWish;
window.copyCurrentWish = copyCurrentWish;
window.shareWishOnWhatsApp = shareWishOnWhatsApp;
window.shareWishByEmail = shareWishByEmail;
window.downloadGreetingCardPng = downloadGreetingCardPng;
window.closeWishesModal = closeWishesModal;


// --------------------------------------------------
// FEATURE: BIRTHDAY INSIGHTS
// --------------------------------------------------

const openInsightsBtn = document.getElementById("open-insights-btn");
const insightsModal = document.getElementById("insights-modal");

function openInsightsModal() {
    if (insightsModal) {
        insightsModal.style.display = "flex";
        loadBirthdayInsights();
    }
}

function closeInsightsModal() {
    if (insightsModal) insightsModal.style.display = "none";
}

if (openInsightsBtn) {
    openInsightsBtn.addEventListener("click", openInsightsModal);
}

async function loadBirthdayInsights() {
    try {
        const res = await fetch("/api/insights");
        if (res.ok) {
            const data = await res.json();
            document.getElementById("insight-total").textContent = data.total_birthdays || 0;
            document.getElementById("insight-this-month").textContent = data.this_month || 0;
            document.getElementById("insight-month-name").textContent = data.this_month_name || "";
            document.getElementById("insight-upcoming").textContent = data.upcoming_30_days || 0;

            const topMonth = data.most_common_month || {};
            document.getElementById("insight-top-month").textContent = topMonth.month ? `${topMonth.month} (${topMonth.count})` : "--";

            const relList = document.getElementById("insight-rel-list");
            if (relList) {
                relList.innerHTML = "";
                const counts = data.relationship_counts || [];
                if (counts.length === 0) {
                    relList.innerHTML = "<p class='text-muted'>No relationship data available.</p>";
                } else {
                    counts.forEach(item => {
                        const li = document.createElement("div");
                        li.className = "data-item";
                        li.innerHTML = `
                            <span class="item-label">
                                <span class="badge">${escapeHtml(item.relationship)}</span>
                            </span>
                            <span class="item-count">${item.count} birthdays</span>
                        `;
                        relList.appendChild(li);
                    });
                }
            }
        }
    } catch (err) {
        console.error("Error loading insights:", err);
    }
}

window.closeInsightsModal = closeInsightsModal;


// --------------------------------------------------
// FEATURE: SQLITE DATABASE AND CRUD (CONTACTS)
// --------------------------------------------------

const openContactsBtn = document.getElementById("open-contacts-btn");
const contactsModal = document.getElementById("contacts-modal");
const contactSearch = document.getElementById("contact-search");
const showAddContactBtn = document.getElementById("show-add-contact-btn");
const contactFormContainer = document.getElementById("contact-form-container");
const contactForm = document.getElementById("contact-form");
const contactsTbody = document.getElementById("contacts-tbody");
const formTitle = document.getElementById("form-title");

function openContactsModal() {
    if (contactsModal) {
        contactsModal.style.display = "flex";
        loadContactsTable();
    }
}

function closeContactsModal() {
    if (contactsModal) contactsModal.style.display = "none";
    hideContactForm();
}

if (openContactsBtn) {
    openContactsBtn.addEventListener("click", openContactsModal);
}

function showAddContactForm() {
    if (contactFormContainer) {
        formTitle.textContent = "Add Contact";
        contactForm.reset();
        document.getElementById("form-contact-id").value = "";
        contactFormContainer.style.display = "block";
    }
}

function hideContactForm() {
    if (contactFormContainer) {
        contactForm.reset();
        contactFormContainer.style.display = "none";
    }
}

if (showAddContactBtn) {
    showAddContactBtn.addEventListener("click", showAddContactForm);
}

async function loadContactsTable(searchQuery = "") {
    try {
        const res = await fetch("/api/contacts");
        if (res.ok) {
            allContactsList = await res.json();
            renderContacts(allContactsList, searchQuery);
            renderCalendar(calCurrentDate);
            renderUpcomingBirthdays(allContactsList);
            populateWishPersonSelect();
        }
    } catch (e) {
        console.error("Failed to load contacts:", e);
    }
}

function renderContacts(contacts, query = "") {
    if (!contactsTbody) return;
    contactsTbody.innerHTML = "";

    const filtered = contacts.filter(c => {
        if (!query) return true;
        const q = query.toLowerCase();
        return (c.name && c.name.toLowerCase().includes(q)) ||
               (c.place_of_stay && c.place_of_stay.toLowerCase().includes(q)) ||
               (c.relationship && c.relationship.toLowerCase().includes(q));
    });

    if (filtered.length === 0) {
        contactsTbody.innerHTML = "<tr><td colspan='7' style='text-align: center; color: #8c868f; padding: 20px;'>No contacts matching search.</td></tr>";
        return;
    }

    filtered.forEach(c => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${c.person_id}</strong></td>
            <td>${c.name}</td>
            <td>${c.nickname || '-'}</td>
            <td>${c.dob}</td>
            <td>${c.place_of_stay || '-'}</td>
            <td><span class="badge">${c.relationship || '-'}</span></td>
            <td>
                <button class="btn-action-sm" onclick="editContact(${c.id})">Edit</button>
                <button class="btn-action-sm btn-danger" onclick="deleteContactPrompt(${c.id}, '${escapeHtml(c.name)}')">Delete</button>
            </td>
        `;
        contactsTbody.appendChild(tr);
    });
}

function escapeHtml(text) {
    return text.replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

if (contactSearch) {
    contactSearch.addEventListener("input", (e) => {
        renderContacts(allContactsList, e.target.value.trim());
    });
}

// Save Contact (Create / Update)
if (contactForm) {
    contactForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const cid = document.getElementById("form-contact-id").value;
        const payload = {
            name: document.getElementById("form-name").value.trim(),
            nickname: document.getElementById("form-nickname").value.trim(),
            dob: document.getElementById("form-dob").value.trim(),
            place_of_stay: document.getElementById("form-city").value.trim(),
            relationship: document.getElementById("form-rel").value.trim(),
            relationship_group: document.getElementById("form-rel-grp").value.trim()
        };

        const url = cid ? `/api/contacts/${cid}` : "/api/contacts";
        const method = cid ? "PUT" : "POST";

        try {
            const res = await fetch(url, {
                method: method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                hideContactForm();
                await loadContactsTable();
            }
        } catch (err) {
            alert("Error saving contact. Please try again.");
        }
    });
}

window.editContact = function(cid) {
    const person = allContactsList.find(c => c.id === cid);
    if (!person) return;

    formTitle.textContent = "Edit Contact";
    document.getElementById("form-contact-id").value = person.id;
    document.getElementById("form-name").value = person.name;
    document.getElementById("form-nickname").value = person.nickname || "";
    document.getElementById("form-dob").value = person.dob ? person.dob.substring(0, 10) : "";
    document.getElementById("form-city").value = person.place_of_stay || "";
    document.getElementById("form-rel").value = person.relationship || "";
    document.getElementById("form-rel-grp").value = person.relationship_group || "";

    contactFormContainer.style.display = "block";
    contactFormContainer.scrollIntoView({ behavior: 'smooth' });
};

window.deleteContactPrompt = async function(cid, name) {
    if (confirm(`Confirmation required:\nAre you sure you want to delete ${name} from your contacts? This cannot be undone.`)) {
        try {
            const res = await fetch(`/api/contacts/${cid}`, { method: "DELETE" });
            const data = await res.json();
            if (data.success) {
                await loadContactsTable();
            } else {
                alert(data.error || "Failed to delete contact.");
            }
        } catch (err) {
            alert("Error deleting contact.");
        }
    }
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    initCalendar();
    fetchContactsData();
    checkReminderStatus();
});
