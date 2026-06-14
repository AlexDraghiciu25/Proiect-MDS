document.addEventListener("DOMContentLoaded", function () {
    const inputField = document.getElementById("universal-chat-input");
    const sendButton = document.getElementById("universal-send-btn");
    const messagesContainer = document.getElementById("chat-messages-container");
    const counterBadge = document.getElementById("selected-counter-badge");

    // Funcție rapidă de actualizare a numărului de anunțuri selectate în timp real
    function updateSelectedBadge() {
        const checkedListings = document.querySelectorAll(".listing-checkbox:checked");
        if (counterBadge) {
            counterBadge.innerText = `${checkedListings.length} Anunțuri Selectate`;
            if (checkedListings.length > 0) {
                counterBadge.className = "badge bg-success text-white";
            } else {
                counterBadge.className = "badge bg-secondary text-white";
            }
        }
    }

    // Ascultăm schimbările pe checkbox-urile de anunțuri
    document.querySelectorAll(".listing-checkbox").forEach(box => {
        box.addEventListener("change", updateSelectedBadge);
    });

    // Logica principală de trimitere mesaj
    function handleSendMessage() {
        const textMessage = inputField.value.trim();
        if (!textMessage) return;

        // Afișăm instant mesajul utilizatorului în chatbox
        const userBubble = document.createElement("div");
        userBubble.className = "p-2 rounded bg-primary text-white mb-2 text-end ms-5 shadow-sm";
        userBubble.style.borderRadius = "12px 12px 0 12px";
        userBubble.innerHTML = `<strong>Tu:</strong> ${textMessage}`;
        messagesContainer.appendChild(userBubble);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Resetăm inputul text pentru a fi pregătit de următoarea întrebare
        inputField.value = "";

        // Colectăm id-urile anunțurilor bifate din grila html
        const activeListings = [];
        document.querySelectorAll(".listing-checkbox:checked").forEach(cb => {
            activeListings.push(cb.value);
        });

        // Afișăm un indicator de încărcare (typing status) animat pentru utilizator
        const loadingBubble = document.createElement("div");
        loadingBubble.className = "p-2 rounded bg-white text-muted mb-2 border text-start me-5 shadow-xs animate-pulse";
        loadingBubble.id = "guru-typing-bubble";
        loadingBubble.innerHTML = "Thinking... 🧠 RentGuru analizează...";
        messagesContainer.appendChild(loadingBubble);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Preluăm tokenul CSRF necesar securității Django din cookie sau tag
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || "";

        // Lansăm cererea hibridă către backend
        fetch("/ai-chat/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({
                message: textMessage,
                active_listings: activeListings
            })
        })
        .then(response => response.json())
        .then(data => {
            // Ștergem bubba de loading
            const typingElement = document.getElementById("guru-typing-bubble");
            if (typingElement) typingElement.remove();

            // Creăm bubba de răspuns cu stilul grafic din RentGuru
            const aiBubble = document.createElement("div");
            aiBubble.className = "p-3 rounded bg-white text-dark mb-2 text-start me-5 shadow-sm border-start border-4 border-primary";
            aiBubble.style.borderRadius = "0 12px 12px 12px";
            aiBubble.innerHTML = data.reply;
            
            messagesContainer.appendChild(aiBubble);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        })
        .catch(error => {
            console.error("Eroare Chat:", error);
            const typingElement = document.getElementById("guru-typing-bubble");
            if (typingElement) typingElement.remove();

            const errorBubble = document.createElement("div");
            errorBubble.className = "p-2 rounded bg-danger text-white mb-2 text-start me-5";
            errorBubble.innerText = "❌ S-a produs o eroare de rețea. Te rog reîncearcă.";
            messagesContainer.appendChild(errorBubble);
        });
    }

    // Atașăm evenimentele pe buton și pe tasta Enter pentru un UX fluid
    sendButton.addEventListener("click", handleSendMessage);
    inputField.addEventListener("keypress", function (e) {
        if (e.key === "Enter") {
            handleSendMessage();
        }
    });

    // Inițializare stare badge la încărcarea paginii
    updateSelectedBadge();
});