# core/data_validation.py

def calculate_completeness_score(listing: dict) -> dict:
    """
    Calculează Data Completeness Score pentru un anunț imobiliar pe o scară de la 0 la 100.
    Returnează un dicționar cu scorul, lista de avertismente și atenționări.
    """
    score = 100.0
    warnings = []
    notices = []

    def is_missing(val):
        if val is None:
            return True
        if isinstance(val, str):
            val_clean = val.strip()
            return val_clean == "" or "Nemenționat (NULL)" in val_clean or val_clean == "--------"
        return False

    # 1. CÂMPURI CRITICE (-15 puncte)
    critical_fields = {
        "Price": "Preț", "Currency": "Monedă", "City": "Oraș",
        "Neighborhood": "Cartier/Zonă", "Rooms": "Număr de camere",
        "Useful surface": "Suprafață utilă"
    }
    for field, label in critical_fields.items():
        if is_missing(listing.get(field)):
            score -= 15.0
            warnings.append({"level": "CRITICAL", "message": f"Lipsește câmpul critic: '{label}'."})

    # 2. CÂMPURI IMPORTANTE
    if is_missing(listing.get("Heating type")):
        score -= 10.0
        warnings.append({"level": "STRONG", "message": "Lipsește tipul de încălzire (Heating type)."})
        
    important_fields = {
        "Furnishing state": "Stare mobilier", "Floor": "Etaj", "Total floors": "Total etaje",
        "Bathrooms": "Număr băi", "Construction year": "An construcție", "Availability": "Disponibilitate"
    }
    for field, label in important_fields.items():
        if is_missing(listing.get(field)):
            score -= 4.0
            warnings.append({"level": "STRONG", "message": f"Lipsește informație importantă: '{label}'."})

    # 3. DOTĂRI ȘI UTILITĂȚI SPECIFICE (-1.5 puncte)
    specific_amenities = {
        "Has fridge": "Frigider", "Has washing machine": "Mașină de spălat",
        "Has ac": "AC", "Has oven": "Cuptor", "Has parking": "Parcare",
        "Has elevator": "Lift", "Near public transit": "Transport public"
    }
    missing_amenities = [label for field, label in specific_amenities.items() if is_missing(listing.get(field))]
    if missing_amenities:
        score -= 1.5 * len(missing_amenities)
        notices.append(f"Nu se menționează dotări standard: {', '.join(missing_amenities)}.")

    # 4. FINISAJE ȘI DETALII (-0.5 puncte)
    detail_fields = [
        "Property destination", "Rental period", "Kitchens", "Balconies", 
        "Partitioning", "Comfort level", "Building type", "Building structure", 
        "Has underfloor heating", "Has gas", "Has electricity", "Has water", 
        "Has sewage", "Has gas meter", "Has water meter", "Has heat meter", 
        "Internet type", "Flooring", "Windows", "Interior doors", "Entrance door", 
        "Walls", "Thermal insulation", "Has dishwasher", "Has tv", "Has microwave", 
        "Has hood", "Has intercom", "Has video surveillance", "Is pet friendly", 
        "Street paved", "Street lit", "Energy class", "Vices"
    ]
    for field in detail_fields:
        if is_missing(listing.get(field)):
            score -= 0.5

    return {
        "completeness_score": round(max(0.0, min(100.0, score)), 1),
        "warnings": warnings,
        "notices": notices
    }