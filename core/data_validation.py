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

    missing_critical_important = []

    # 1. CÂMPURI CRITICE (-15 puncte)
    critical_fields = {
        "Price": "Preț", "Currency": "Monedă", "City": "Oraș",
        "Neighborhood": "Cartier/Zonă", "Rooms": "Număr de camere",
        "Useful surface": "Suprafață utilă"
    }
    for field, label in critical_fields.items():
        if is_missing(listing.get(field)):
            score -= 15.0
            missing_critical_important.append(label)

    # 2. CÂMPURI IMPORTANTE
    if is_missing(listing.get("Heating type")):
        score -= 10.0
        missing_critical_important.append("Tip încălzire")

    important_fields = {
        "Furnishing state": "Stare mobilier", "Floor": "Etaj", "Total floors": "Total etaje",
        "Bathrooms": "Număr băi", "Construction year": "An construcție", "Availability": "Disponibilitate"
    }
    for field, label in important_fields.items():
        if is_missing(listing.get(field)):
            score -= 4.0
            missing_critical_important.append(label)

    if missing_critical_important:
        warnings.append({"level": "CRITICAL", "message": f"BAZA:{','.join(missing_critical_important)}"})

    # 3. DOTĂRI ȘI UTILITĂȚI SPECIFICE (-1.5 puncte)
    specific_amenities = {
        "Has fridge": "Frigider", "Has washing machine": "Mașină de spălat",
        "Has ac": "AC", "Has oven": "Cuptor", "Has parking": "Parcare",
        "Has elevator": "Lift", "Near public transit": "Transport public"
    }
    missing_amenities = [label for field, label in specific_amenities.items() if is_missing(listing.get(field))]
    if missing_amenities:
        score -= 1.5 * len(missing_amenities)

    # 4. FINISAJE ȘI DETALII (-0.5 puncte)
    detail_fields = {
        "Property destination": "Destinație proprietate", "Rental period": "Perioadă închiriere", "Kitchens": "Bucătării", "Balconies": "Balcoane",
        "Partitioning": "Compartimentare", "Comfort level": "Confort", "Building type": "Tip clădire", "Building structure": "Structură clădire",
        "Has underfloor heating": "Încălzire în pardoseală", "Has gas": "Gaz", "Has electricity": "Curent electric", "Has water": "Apă",
        "Has sewage": "Canalizare", "Has gas meter": "Contor gaz", "Has water meter": "Apometre", "Has heat meter": "Repartitoare",
        "Internet type": "Internet", "Flooring": "Podele", "Windows": "Ferestre", "Interior doors": "Uși interior", "Entrance door": "Ușă intrare",
        "Walls": "Pereți", "Thermal insulation": "Izolație termică", "Has dishwasher": "Mașină de spălat vase", "Has tv": "TV", "Has microwave": "Microunde",
        "Has hood": "Hotă", "Has intercom": "Interfon", "Has video surveillance": "Supraveghere video", "Is pet friendly": "Pet friendly",
        "Street paved": "Stradă asfaltată", "Street lit": "Iluminat stradal", "Energy class": "Clasă energetică", "Vices": "Vicii"
    }

    missing_details = []
    for field, label in detail_fields.items():
        if is_missing(listing.get(field)):
            score -= 0.5
            missing_details.append(label)

    missing_secondary = missing_amenities + missing_details
    if missing_secondary:
        notices.append(f"DETALII:{', '.join(x.lower() for x in missing_secondary)}")

    return {
        "completeness_score": round(max(0.0, min(100.0, score)), 1),
        "warnings": warnings,
        "notices": notices
    }