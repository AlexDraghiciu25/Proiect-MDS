document.addEventListener('DOMContentLoaded', function() {
    const radiusSlider = document.getElementById('radiusRange');
    const radiusDisplay = document.getElementById('radiusDisplay');

    if(radiusSlider && radiusDisplay) {
        radiusSlider.addEventListener('input', function() {
            radiusDisplay.textContent = this.value + ' km';
        });
    }
});

function confirmMapLocation() {
    const locationInput = document.getElementById('locationInput');
    const radiusSlider = document.getElementById('radiusRange');
    
    const selectedRadius = radiusSlider ? radiusSlider.value : "5";
    const simulatedLocation = "București, Sector 1 (+ " + selectedRadius + " km)";
    
    if(locationInput) {
        locationInput.value = simulatedLocation;
        
        locationInput.style.transition = "box-shadow 0.3s, border-color 0.3s";
        locationInput.style.borderColor = "var(--mds-green)";
        locationInput.style.boxShadow = "0 0 0 0.25rem rgba(45, 74, 34, 0.25)";
        
        setTimeout(() => {
            locationInput.style.borderColor = "#d4c5b9";
            locationInput.style.boxShadow = "none";
        }, 1000);
    }
}