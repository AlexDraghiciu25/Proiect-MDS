document.addEventListener('DOMContentLoaded', function() {
    // --- 1. GESTIONARE SLIDER RAZĂ (HARTĂ) ---
    const radiusSlider = document.getElementById('radiusRange');
    const radiusDisplay = document.getElementById('radiusDisplay');

    if (radiusSlider && radiusDisplay) {
        radiusSlider.addEventListener('input', function() {
            radiusDisplay.textContent = this.value + ' km';
        });
    }

    // --- 2. GESTIONARE LOADING ASISTENT AI ---
    const analyzeForm = document.getElementById('analyze-form');
    const btnMagic = document.querySelector('#analyze-form button[type="submit"]');
    const normalState = document.getElementById('card-content-normal');
    const loadingState = document.getElementById('card-content-loading');
    const msgElement = document.getElementById('loading-msg');

    if (analyzeForm && btnMagic) {
        analyzeForm.addEventListener('submit', function(e) {
            // Verificăm dacă input-ul are un URL valid înainte de a porni animația
            const urlInput = analyzeForm.querySelector('input[name="external_url"]');
            if (!urlInput.value.includes('storia.ro')) {
                // Opțional: poți lăsa Django să dea eroarea, sau o poți opri aici
                // alert("Te rugăm să introduci un link valid de Storia.ro");
                // e.preventDefault();
                // return;
            }

            // Activăm starea de loading
            normalState.style.display = 'none';
            loadingState.style.display = 'block';
            btnMagic.disabled = true;

            // Mesaje dinamice pentru robotul AI
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

// --- 3. CONFIRMARE LOCAȚIE DIN MODAL ---
function confirmMapLocation() {
    const locationInput = document.getElementById('locationInput');
    const radiusSlider = document.getElementById('radiusRange');
    
    const selectedRadius = radiusSlider ? radiusSlider.value : "5";
    // Sfat: Am putea extrage locația reală dacă am folosi Google Maps API, 
    // momentan simulăm selecția pentru interfață
    const simulatedLocation = "București, Sector 1"; 
    
    if (locationInput) {
        locationInput.value = simulatedLocation;
        
        // Feedback vizual (Highlight)
        locationInput.classList.add('is-valid'); // Bootstrap class
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