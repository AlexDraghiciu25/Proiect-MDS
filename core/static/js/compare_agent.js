document.addEventListener("DOMContentLoaded", function () {
    const chatForm = document.getElementById("aiChatForm");
    const inputField = document.getElementById("aiUserInput");
    const messagesContainer = document.getElementById("chatWindow");
    const counterBadge = document.getElementById("compareCounter");

    function updateSelectedBadge() {
        const checkedListings = document.querySelectorAll(".compare-checkbox:checked");
        
        if (counterBadge) {
            counterBadge.innerText = `${checkedListings.length} Anunțuri Selectate`;
            if (checkedListings.length > 0) {
                counterBadge.className = "badge bg-success w-100 py-2 fs-6";
            } else {
                counterBadge.className = "badge bg-secondary w-100 py-2 fs-6";
            }
        }
    }

    document.addEventListener("change", function (event) {
        if (event.target && event.target.classList.contains("compare-checkbox")) {
            const label = document.querySelector(`label[for="${event.target.id}"]`);
            
            if (label) {
                if (event.target.checked) {
                    label.style.background = "#198754"; 
                    label.style.color = "#ffffff";
                    label.style.borderColor = "#198754";
                    
                    const icon = label.querySelector(".compare-icon");
                    if (icon) {
                        icon.className = "bi bi-check-circle-fill compare-icon"; 
                    }
                } else {
                    label.style.background = "rgba(255, 255, 255, 0.95)";
                    label.style.color = "#495057";
                    label.style.borderColor = "#dee2e6";
                    
                    const icon = label.querySelector(".compare-icon");
                    if (icon) {
                        icon.className = "bi bi-plus-circle compare-icon"; 
                    }
                }
            }

            updateSelectedBadge();
        }
    });

    if (chatForm) {
        chatForm.addEventListener("submit", function (e) {
            e.preventDefault(); 

            const textMessage = inputField.value.trim();
            if (!textMessage) return;

            const userBubble = document.createElement("div");
            userBubble.className = "p-2 rounded-3 bg-primary text-white mb-2 text-end ms-5 shadow-sm small align-self-end";
            userBubble.style.maxWidth = "85%";
            userBubble.style.maxHeight = "fit-content";
            userBubble.style.borderRadius = "12px 12px 0 12px";
            userBubble.innerHTML = `<strong>Tu:</strong> ${textMessage}`;
            messagesContainer.appendChild(userBubble);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;

            inputField.value = "";

            const activeListings = [];
            document.querySelectorAll(".compare-checkbox:checked").forEach(cb => {
                activeListings.push(cb.getAttribute("data-id") || cb.value);
            });

            const loadingBubble = document.createElement("div");
            loadingBubble.className = "p-2 rounded-3 bg-white text-muted mb-2 border text-start me-5 shadow-xs align-self-start small";
            loadingBubble.id = "guru-typing-bubble";
            loadingBubble.style.maxWidth = "85%";
            loadingBubble.innerHTML = "🧠 RentGuru analizează...";
            messagesContainer.appendChild(loadingBubble);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;

            const endpointUrl = window.DjangoConfig?.chatEndpointUrl || "/ai-chat/";
            const csrfToken = window.DjangoConfig?.csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value || "";

            fetch(endpointUrl, {
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
                const typingElement = document.getElementById("guru-typing-bubble");
                if (typingElement) typingElement.remove();

                const aiBubble = document.createElement("div");
                aiBubble.className = "p-3 rounded-3 bg-white text-dark mb-2 text-start me-5 shadow-sm border-start border-4 small align-self-start";
                aiBubble.style.borderColor = "#8b5e3c";
                aiBubble.style.maxWidth = "85%";
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
                errorBubble.className = "p-2 rounded bg-danger text-white mb-2 text-start me-5 small align-self-start";
                errorBubble.innerText = "❌ S-a produs o eroare de rețea. Te rog reîncearcă.";
                messagesContainer.appendChild(errorBubble);
            });
        });
    }

    window.addEventListener('pageshow', function (event) {
        const butoaneAnaliza = document.querySelectorAll('.btn-view-report');

        butoaneAnaliza.forEach(buton => {
            if (buton.innerHTML.includes('încarcă') || buton.classList.contains('disabled')) {
                
                const matchId = buton.href.match(/\/(\d+)\/?$/);
                if (matchId && matchId[1]) {
                    const listingId = matchId[1];
                    
                    buton.href = `/result/${listingId}/`; 
                    buton.innerHTML = '<i class="bi bi-magic me-1"></i> Vezi Analiza Completă';
                    
                    buton.classList.remove('disabled', 'btn-trigger-analysis');
                    
                    buton.style.background = ''; 
                    buton.style.color = '';
                    buton.style.pointerEvents = 'auto';
                    buton.style.opacity = '1';
                }
            }
        });
    });

    updateSelectedBadge();
});