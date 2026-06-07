// Mapă globală și stări pentru Fluxul în Doi Pași
let proprietatiSelectate = new Set();
let asteaptaCriteriuUtilizator = false;
let iduriDeTrimisTemporar = [];

document.addEventListener('DOMContentLoaded', function() {
    // 1. Ascultăm checkbox-urile de comparare
    document.querySelectorAll('.compare-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const idAnunt = this.getAttribute('data-id');
            const label = document.querySelector(`label[for="${this.id}"]`);
            const icon = label.querySelector('.compare-icon');
            
            if (this.checked) {
                proprietatiSelectate.add(idAnunt);
                label.style.backgroundColor = '#002f34';
                label.style.color = '#fff';
                label.style.borderColor = '#002f34';
                if (icon) icon.className = 'bi bi-check-circle-fill compare-icon';
            } else {
                proprietatiSelectate.delete(idAnunt);
                label.style.backgroundColor = 'rgba(255, 255, 255, 0.95)';
                label.style.color = '#495057';
                label.style.borderColor = '#dee2e6';
                if (icon) icon.className = 'bi bi-plus-circle compare-icon';
            }
            actualizeazaPanouAi();
        });
    });

    // 2. [MODIFICAT] Click pe butonul de comparare - PASUL 1 DIN FLUX
    const btnCompare = document.getElementById('btnSubmitComparison');
    if (btnCompare) {
        btnCompare.addEventListener('click', function() {
            iduriDeTrimisTemporar = Array.from(proprietatiSelectate);
            asteaptaCriteriuUtilizator = true; // Activăm starea de așteptare filtru semantic

            const chatWindow = document.getElementById('chatWindow');
            
            // Agentul preia controlul și întreabă înainte de a procesa în backend
            const promptDiv = document.createElement('div');
            promptDiv.className = 'p-2 rounded-3 bg-white shadow-sm align-self-start small fw-medium';
            promptDiv.style.borderLeft = '4px solid #8b5e3c';
            promptDiv.style.borderTopLeftRadius = '0';
            promptDiv.innerHTML = `🤖 <strong>RentGuru Agent:</strong> Am blocat în memorie cele ${iduriDeTrimisTemporar.length} proprietăți!<br><br>
                                   Înainte de a rula matricea tehnică, te rog să îmi spui: <strong>ai un criteriu preferențial după care vrei să fac recomandarea?</strong> (Ex: <em>apropiere metrou, zonă liniștită, cel mai mic preț</em>).<br><br>
                                   Dacă vrei o analiză generală, scrie simplu: <strong>"general"</strong>.`;
            
            chatWindow.appendChild(promptDiv);
            chatWindow.scrollTop = chatWindow.scrollHeight;

            // Focalizăm automat căsuța de text ca utilizatorul să scrie criteriul
            const inputField = document.getElementById('aiUserInput');
            if (inputField) {
                inputField.placeholder = "Scrie criteriul tău aici (sau 'general')...";
                inputField.focus();
            }
        });
    }

    // 3. [MODIFICAT] Trimiterea formularului de text - PASUL 2 DIN FLUX
    const chatForm = document.getElementById('aiChatForm');
    if (chatForm) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const inputField = document.getElementById('aiUserInput');
            const text = inputField.value.trim();
            if (!text) return;
            
            if (asteaptaCriteriuUtilizator) {
                // Dacă suntem în fluxul în doi pași, trimitem textul drept criteriu + ID-urile salvate anterior
                trimiteMesajLaAgent(text, iduriDeTrimisTemporar);
                
                // Resetăm starea după trimitere, revenind la modul de chat liber
                asteaptaCriteriuUtilizator = false;
                inputField.placeholder = "Pune o întrebare suplimentară...";
            } else {
                // Modul normal de chat suplimentar
                trimiteMesajLaAgent(text, Array.from(proprietatiSelectate));
            }
            
            inputField.value = '';
        });
    }
});

function actualizeazaPanouAi() {
    const counter = document.getElementById('compareCounter');
    const btnCompare = document.getElementById('btnSubmitComparison');
    if (!counter) return;

    const nrElemente = proprietatiSelectate.size;
    counter.innerText = `${nrElemente} Proprietăți Selectate`;
    
    if (nrElemente >= 2) {
        counter.className = "badge bg-success w-100 py-2 fs-6 mb-2";
        if (btnCompare) btnCompare.classList.remove('d-none');
    } else {
        counter.className = "badge bg-secondary w-100 py-2 fs-6 mb-2";
        if (btnCompare) btnCompare.classList.add('d-none');
    }
}

function trimiteMesajLaAgent(mesajText, iduriProprietati) {
    const chatWindow = document.getElementById('chatWindow');
    if (!chatWindow) return;
    
    const userDiv = document.createElement('div');
    userDiv.className = 'p-2 rounded-3 text-white align-self-end small';
    userDiv.style.backgroundColor = '#a0714f';
    userDiv.style.maxWidth = '85%';
    userDiv.style.borderTopRightRadius = '0';
    userDiv.innerText = mesajText;
    chatWindow.appendChild(userDiv);
    
    chatWindow.scrollTop = chatWindow.scrollHeight;

    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'p-2 rounded-3 bg-white shadow-sm align-self-start small text-muted';
    thinkingDiv.innerHTML = '<i class="bi bi-cpu-fill spinning"></i> RentGuru procesează criteriile introduse...';
    chatWindow.appendChild(thinkingDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;

    const url = window.DjangoConfig ? window.DjangoConfig.chatEndpointUrl : '/ai-chat/';
    const token = window.DjangoConfig ? window.DjangoConfig.csrfToken : '';

    fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": token
        },
        body: JSON.stringify({
            message: mesajText, // Criteriul dat de utilizator la Pasul 2
            active_listings: iduriProprietati
        })
    })
    .then(response => response.json())
    .then(data => {
        thinkingDiv.remove();
        
        const agentDiv = document.createElement('div');
        agentDiv.className = 'p-2 rounded-3 bg-white shadow-sm align-self-start small';
        agentDiv.style.maxWidth = '85%';
        agentDiv.style.borderTopLeftRadius = '0';
        agentDiv.innerHTML = data.reply; 
        chatWindow.appendChild(agentDiv);
        
        chatWindow.scrollTop = chatWindow.scrollHeight;
    })
    .catch(error => {
        thinkingDiv.remove();
        console.error("Eroare comunicare Agent AI:", error);
    });
}