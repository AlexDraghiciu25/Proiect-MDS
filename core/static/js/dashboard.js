document.addEventListener('DOMContentLoaded', function() {
    const radiusSlider = document.getElementById('radiusRange');
    const radiusDisplay = document.getElementById('radiusDisplay');

    if (radiusSlider && radiusDisplay) {
        radiusSlider.addEventListener('input', function() {
            radiusDisplay.textContent = this.value + ' km';
        });
    }

    const analyzeForm = document.getElementById('analyze-form');
    const btnMagic = document.querySelector('#analyze-form button[type="submit"]');
    const normalState = document.getElementById('card-content-normal');
    const loadingState = document.getElementById('card-content-loading');
    const msgElement = document.getElementById('loading-msg');

    if (analyzeForm && btnMagic) {
        // Căutăm inputul din timp pentru a-i asculta schimbările
        const urlInput = analyzeForm.querySelector('input[name="external_url"]');

        // Resetăm starea de eroare imediat ce utilizatorul începe să rescrie în căsuță
        if (urlInput) {
            urlInput.addEventListener('input', function() {
                this.classList.remove('is-invalid');
            });
        }

        analyzeForm.addEventListener('submit', function(e) {
            const urlValue = urlInput ? urlInput.value.toLowerCase().strip : '';
            
            // ====================================================
            // 🛑 VALIDARE ROBUSTĂ ALINIATĂ CU DESIGNUL BOOTSTRAP 5
            // ====================================================
            if (!urlInput.value.includes('storia.ro') && !urlInput.value.includes('olx.ro')) {
                // Oprim trimiterea formularului către server
                e.preventDefault(); 
                
                // Aplicăm clasa vizuală de eroare de la Bootstrap (contur roșu)
                urlInput.classList.add('is-invalid');
                urlInput.focus();
                return; // Oprim funcția aici, blocând starea de loading
            }

            // Dacă link-ul este valid, curățăm eventualele erori anterioare și pornim magia AI
            urlInput.classList.remove('is-invalid');
            normalState.style.display = 'none';
            loadingState.style.display = 'block';
            btnMagic.disabled = true;

            const messages = [
                "Accesăm sursa externă...",
                "Extragem specificațiile...",
                "Analizăm prețul pieței...",
                "Verificăm scorul de încredere...",
                "Generăm raportul tău..."
            ];
            
            let i = 0;
            const messageInterval = setInterval(() => {
                if (i < messages.length - 1) {
                    i++;
                    msgElement.innerText = '"' + messages[i] + '"';
                } else {
                    clearInterval(messageInterval);
                }
            }, 3000);
        });
    }
});

function confirmMapLocation() {
    const locationInput = document.getElementById('locationInput');
    const radiusSlider = document.getElementById('radiusRange');
    
    const selectedRadius = radiusSlider ? radiusSlider.value : "5";
    const simulatedLocation = "București, Sector 1"; 
    
    if (locationInput) {
        locationInput.value = simulatedLocation;
        
        locationInput.classList.add('is-valid');
        locationInput.style.transition = "all 0.3s ease";
        locationInput.style.borderColor = "var(--mds-green)";
        locationInput.style.boxShadow = "0 0 0 0.25rem rgba(45, 74, 34, 0.25)";
        
        setTimeout(() => {
            locationInput.style.borderColor = "";
            locationInput.style.boxShadow = "";
            locationInput.classList.remove('is-valid');
        }, 1500);
    }
}