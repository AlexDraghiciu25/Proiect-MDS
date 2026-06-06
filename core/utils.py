import os
from playwright.sync_api import sync_playwright
from core.management.commands.scrape_storia import Command as StoriaScraper
from core.management.commands.normalize_listings import Command as Normalizer

# Importăm funcția noastră de calcul a scorului
# (Asigură-te că fisierul data_validation.py este în același director 'core' 
# sau ajustează path-ul importului corespunzător)
from core.data_validation import calculate_completeness_score 

def scrape_single_url(url):
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    
    scraper = StoriaScraper()
    normalizer = Normalizer()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        try:
            # 1. SCRAPING: Luăm datele brute
            listing = scraper.proceseaza_anunt(context, url)
            
            if listing:
                # 2. NORMALIZARE: Traducem datele brute în câmpuri
                normalizer.handle(listing_id=listing.id) 
                
                # Reîncărcăm obiectul din baza de date
                listing.refresh_from_db()
                
                # 3. CALCUL COMPLETENESS SCORE
                # Mapăm atributele modelului tău Django către dicționarul pe care îl așteaptă formula.
                # Dacă normalizatorul tău a salvat acele zeci de detalii într-un câmp JSON (ex. 'site_specs' sau 'raw_data'),
                # trebuie să le extragi de acolo. 
                
                # Exemplu de asamblare a datelor (ajustează numele variabilelor dacă diferă în models.py):
                date_pentru_formula = {
                    # 1. CÂMPURI CRITICE (-15)
                    "Price": listing.price,
                    "Currency": listing.currency,
                    "City": listing.city,
                    "Neighborhood": listing.neighborhood,
                    "Rooms": listing.rooms,
                    "Useful surface": listing.useful_surface,

                    # 2. CÂMPURI IMPORTANTE (-10 / -4)
                    "Heating type": listing.heating_type,
                    "Furnishing state": listing.furnishing_state,
                    "Floor": listing.floor,
                    "Total floors": listing.total_floors,
                    "Bathrooms": listing.bathrooms,
                    "Construction year": listing.construction_year,
                    "Availability": listing.availability,

                    # 3. DOTĂRI ȘI UTILITĂȚI SPECIFICE (-1.5)
                    "Has fridge": listing.has_fridge,
                    "Has washing machine": listing.has_washing_machine,
                    "Has ac": listing.has_ac,
                    "Has oven": listing.has_oven,
                    "Has parking": listing.has_parking,
                    "Has elevator": listing.has_elevator,
                    "Near public transit": listing.near_public_transit,

                    # 4. FINISAJE, DETALII ȘI UTILITĂȚI IMPLICITE (-0.5)
                    "Property destination": listing.property_destination,
                    "Rental period": listing.rental_period,
                    "Kitchens": listing.kitchens,
                    "Balconies": listing.balconies,
                    "Partitioning": listing.partitioning,
                    "Comfort level": listing.comfort_level,
                    "Building type": listing.building_type,
                    "Building structure": listing.building_structure,
                    "Has underfloor heating": listing.has_underfloor_heating,
                    "Has gas": listing.has_gas,
                    "Has electricity": listing.has_electricity,
                    "Has water": listing.has_water,
                    "Has sewage": listing.has_sewage,
                    "Has gas meter": listing.has_gas_meter,
                    "Has water meter": listing.has_water_meter,
                    "Has heat meter": listing.has_heat_meter,
                    "Internet type": listing.internet_type,
                    "Flooring": listing.flooring,
                    "Windows": listing.windows,
                    "Interior doors": listing.interior_doors,
                    "Entrance door": listing.entrance_door,
                    "Walls": listing.walls,
                    "Thermal insulation": listing.thermal_insulation,
                    "Has dishwasher": listing.has_dishwasher,
                    "Has tv": listing.has_tv,
                    "Has microwave": listing.has_microwave,
                    "Has hood": listing.has_hood,
                    "Has intercom": listing.has_intercom,
                    "Has video surveillance": listing.has_video_surveillance,
                    "Is pet friendly": listing.is_pet_friendly,
                    "Street paved": listing.street_paved,
                    "Street lit": listing.street_lit,
                    "Energy class": listing.energy_class,
                    "Vices": listing.vices
                }

                # Rulăm formula matematică cu dicționarul complet
                evaluare = calculate_completeness_score(date_pentru_formula)

                # Salvăm rezultatul direct pe model
                listing.data_completeness_score = evaluare['completeness_score']
                listing.save()
                
                # Rulăm formula matematică
                evaluare = calculate_completeness_score(date_pentru_formula)
                
                # 4. SALVARE SCOR ÎN BAZA DE DATE
                # Presupunem că modelul Listing are un câmp IntegerField/FloatField pentru scor
                # și un JSONField pentru avertismente
                listing.data_completeness_score = evaluare['completeness_score']
                
                # Dacă ai un câmp de tip JSONField în model (ex: validation_warnings), e util să le salvezi
                # pentru a i le trimite agentului mai târziu, așa cum am stabilit.
                if hasattr(listing, 'validation_warnings'):
                    listing.validation_warnings = evaluare['warnings']
                    
                listing.save()
                
                print(f"Anunț procesat cu succes! Scor integritate date: {listing.data_completeness_score}%")
                
            return listing
            
        except Exception as e:
            print(f"Eroare Utils (Scrape/Normalize/Score): {e}")
            return None
        finally:
            context.close()
            browser.close()