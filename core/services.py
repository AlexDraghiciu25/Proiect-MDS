import json
import requests
import re
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from django.db.models import Avg
from django.conf import settings
from .models import Listing, Report
from django.utils import timezone
from .data_validation import calculate_completeness_score

def extract_distance_claims(description: str) -> list[dict]:
    claims = []
    clauses = re.split(r'[.,;!|]|\bși\b|\bsi\b|\biar\b', description)
    
    patterns = [
        re.compile(r'(\d+)\s*(?:min(?:ute)?|\bmin\b)(.*)', re.IGNORECASE),
        re.compile(r'(?:faci|ajungi|mergi|durează|dureaza)\s*(?:cam|în|in|vreo)?\s*(\d+)(.*)', re.IGNORECASE),
        re.compile(r'(?:mers|pas)(?: relaxat| normal| lejer)?\s*(?:faci|ajungi)?\s*(?:cam|în|in|vreo)?\s*(\d+)(.*)', re.IGNORECASE)
    ]
    
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
            
        match = None
        for pattern in patterns:
            match = pattern.search(clause)
            if match:
                break
        
        if not match:
            continue
            
        claimed_time = int(match.group(1))
        tail = match.group(2).strip() 
        
        prep_regex = r'\b(până la|pana la|până în|pana in|spre|către|catre|de(?!\s+mers|\s+condus)|la(?!\s+pas|\s+mers))\b\s+(.*)'
        prep_match = re.search(prep_regex, tail, re.IGNORECASE)
        
        if prep_match:
            destination = prep_match.group(2).strip()
        else:
            destination = tail
            transport_keywords = r'\b(?:cu mașina|cu masina|auto|pe jos|la pas|cu autobuzul|cu metroul|cu tramvaiul|cu bicicleta|cu trotineta|în|in|cu)\b'
            destination = re.sub(transport_keywords, '', destination, flags=re.IGNORECASE).strip()

        destination = " ".join(destination.split())
        if not destination:
            destination = "Locație nespecificată"
    
        clause_lower = clause.lower()
        transport_mode = "walking" # Default
        
        if re.search(r'\b(mașină|masina|auto|condus)\b', clause_lower):
            transport_mode = "driving"
        elif re.search(r'\b(bicicletă|bicicleta|trotinetă|trotineta|scuter)\b', clause_lower):
            transport_mode = "bicycling"
        elif re.search(r'\bcu\s+(stb|autobuz|tramvai|troleibuz|metrou)\b', clause_lower):
            transport_mode = "transit"
            
        claims.append({
            "destination": destination,
            "claimed_time": claimed_time,
            "transport_mode": transport_mode,
            "raw_text": clause 
        })
        
    return claims

def get_real_travel_time(origin_lat, origin_lng, dest_lat, dest_lng, mode="walking") -> dict:
    endpoints = {
        "walking": "routed-foot/route/v1/driving",
        "driving": "routed-car/route/v1/driving",
        "bicycling": "routed-bike/route/v1/driving"
    }
    
    if mode == "transit" or mode not in endpoints:
        mode = "walking"
        
    endpoint = endpoints[mode]
    
    url = f"https://routing.openstreetmap.de/{endpoint}/{origin_lng},{origin_lat};{dest_lng},{dest_lat}?overview=false"
    
    headers = {'User-Agent': 'RentGuru/1.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return {
                "duration_minutes": round(route["duration"] / 60.0, 1),
                "distance_km": round(route["distance"] / 1000.0, 2)
            }
        return None
    except Exception as e:
        return f"Eroare: {e}"

def verify_distance_claims(listing_lat, listing_lng, claims: list[dict], city: str = "București") -> list[dict]:
    verified_results = []
    headers = {'User-Agent': 'RentGuru/1.0'}
    
    for claim in claims:
        destination = claim.get("destination")
        claimed_time = claim.get("claimed_time")
        mode = claim.get("transport_mode", "walking")
        
        if not destination or "nespecificată" in destination.lower():
            continue
            
        time.sleep(1.0) 
        
        # --- FIX 1: Ajutăm motorul de căutare să înțeleagă termenii generici ---
        search_term = destination
        dest_lower = destination.lower()
        if dest_lower in ['metrou', 'metroul', 'statie metrou', 'stație metrou']:
            search_term = "stație de metrou"
        elif dest_lower in ['parc', 'parcul']:
            search_term = "parc"
        elif dest_lower in ['stb', 'autobuz', 'tramvai']:
            search_term = f"stație de {dest_lower}"
        
        nom_url = "https://nominatim.openstreetmap.org/search"
        
        # --- FIX 2: Bounded=1 forțează harta să NU mai caute în alte sectoare ---
        nom_params = {
            'q': f"{search_term}, {city}",
            'format': 'json',
            'limit': 5,
            'viewbox': f"{listing_lng-0.03},{listing_lat+0.03},{listing_lng+0.03},{listing_lat-0.03}",
            'bounded': 1 
        }
        
        try:
            nom_response = requests.get(nom_url, params=nom_params, headers=headers, timeout=5)
            nom_data = nom_response.json()
            
            # Dacă nu găsește nimic strict în zonă, scoatem limitarea ca ultim resort
            if not nom_data:
                time.sleep(1.0)
                nom_params['q'] = search_term 
                nom_params['bounded'] = 0 
                nom_response = requests.get(nom_url, params=nom_params, headers=headers, timeout=5)
                nom_data = nom_response.json()
                
            if not nom_data:
                print(f"[-] Harta nu a putut geocoda: '{destination}'")
                continue
                
            # --- NOU: Calculăm distanța matematică pentru a găsi cel mai apropiat rezultat ---
            closest_dest = None
            min_dist = float('inf')

            for place in nom_data:
                p_lat = float(place['lat'])
                p_lon = float(place['lon'])
                
                # Distanță în linie dreaptă pentru triere rapidă
                dist = (p_lat - listing_lat)**2 + (p_lon - listing_lng)**2
                if dist < min_dist:
                    min_dist = dist
                    closest_dest = (p_lat, p_lon)

            if not closest_dest:
                continue

            dest_lat, dest_lng = closest_dest
            # --------------------------------------------------------------------------------

            # Rutăm doar către cel mai apropiat punct
            real_data = get_real_travel_time(listing_lat, listing_lng, dest_lat, dest_lng, mode)
            
            if not real_data or isinstance(real_data, str):
                print(f"[-] Eroare de rutare către: '{destination}'")
                continue
                
            real_minutes = real_data["duration_minutes"]

            safe_claimed = claimed_time if claimed_time > 0 else 1 
            
            if real_minutes <= safe_claimed:
                # NOU: Dacă e o diferență suspect de mare (mai mult de 4 minute), înseamnă că pin-ul GPS pus de agent e FALS (momeală)
                if safe_claimed - real_minutes > 4:
                    diff_percent = round(((safe_claimed - real_minutes) / safe_claimed) * 100, 1)
                    verdict = "PIN FALS PE HARTĂ (MOMEALĂ)"
                else:
                    diff_percent = 0.0
                    verdict = "CONFIRMAT"
            else:
                # Logica veche: dacă distanța reală e mai MARE decât ce a zis el (adică a mințit ca să pară mai aproape)
                diff_percent = round(((real_minutes - safe_claimed) / safe_claimed) * 100, 1)
                
                if diff_percent < 20:
                    verdict = "CONFIRMAT"
                elif 20 <= diff_percent <= 50:
                    verdict = "UȘOR EXAGERAT"
                else:
                    verdict = "FALS / ÎNȘELĂTOR"
                
            verified_results.append({
                "destination": destination,
                "claimed_minutes": claimed_time,
                "real_minutes": real_minutes,
                "difference_percent": diff_percent,
                "verdict": verdict,
                "transport_mode": mode,
                "raw_text": claim.get("raw_text", "Distanță afirmată")
            })
            
        except Exception as e:
            print(f"[-] Eroare la procesarea afirmației pentru '{destination}': {e}")
            
    return verified_results

class MapsAgent:
    def __init__(self):
        self.geocode_url = "https://nominatim.openstreetmap.org/search"
        self.overpass_url = "https://overpass-api.de/api/interpreter"

    def get_coordinates(self, location_text):
        params = {
            'q': location_text,
            'format': 'json',
            'limit': 1
        }
        headers = {'User-Agent': 'RentGuru/1.0'}
        try:
            response = requests.get(self.geocode_url, params=params, headers=headers, timeout=5)
            results = response.json()
            if results:
                return float(results[0]['lat']), float(results[0]['lon'])
        except Exception as e:
            print(f"MapsAgent [Geocoding Error]: {e}")
        return None, None

    def _calculate_distance(self, lat1, lng1, lat2, lng2):
        """Calculul distanței în metri între două coordonate GPS folosind Haversine."""
        R = 6371000  # Raza Pământului în metri
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * \
            math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return int(R * c)

    def get_pois(self, lat, lng):
        """
        Caută puncte de interes în raza de 1000m față de coordonatele trimise.
        Returnează un dict structurat pe categorii cu denumirea și distanța în metri.
        """
        if not lat or not lng:
            return {}

        overpass_query = f"""
        [out:json][timeout:15];
        (
          node["highway"="bus_stop"](around:2000,{lat},{lng});
          node["railway"="station"](around:2000,{lat},{lng});
          node["station"="subway"](around:2000,{lat},{lng});
          node["shop"="supermarket"](around:2000,{lat},{lng});
          node["amenity"="restaurant"](around:2000,{lat},{lng});
          node["leisure"="fitness_centre"](around:2000,{lat},{lng});
          node["amenity"="pharmacy"](around:2000,{lat},{lng});
          node["amenity"="school"](around:2000,{lat},{lng});
          way["leisure"="park"](around:2000,{lat},{lng});
          node["amenity"="bank"](around:2000,{lat},{lng});
          node["amenity"="atm"](around:2000,{lat},{lng});
        );
        out center;
        """

        headers = {'User-Agent': 'RentGuru/1.0'}
        
        pois_data = {
            "transport": [],
            "supermarkets": [],
            "restaurants": [],
            "fitness": [],
            "pharmacies": [],
            "schools": [],
            "parks": [],
            "banks_atms": []
        }

        try:
            response = requests.post(self.overpass_url, data={'data': overpass_query}, headers=headers, timeout=15)
            data = response.json()
            elements = data.get("elements", [])

            for el in elements:
                tags = el.get("tags", {})
                
                if "center" in el:
                    el_lat = el["center"]["lat"]
                    el_lng = el["center"]["lon"]
                else:
                    el_lat = el.get("lat")
                    el_lng = el.get("lon")

                if not el_lat or not el_lng:
                    continue

                distance = self._calculate_distance(lat, lng, el_lat, el_lng)
                
                name = tags.get("name")

                if "highway" in tags and tags["highway"] == "bus_stop":
                    pois_data["transport"].append({"name": name or "Stație de Autobuz", "distance": distance})
                elif "railway" in tags and tags["railway"] == "station":
                    pois_data["transport"].append({"name": name or "Gară / Stație tren", "distance": distance})
                elif "station" in tags and tags["station"] == "subway":
                    pois_data["transport"].append({"name": name or f"Stația de Metrou {name if name else ''}".strip(), "distance": distance})
                
                elif "shop" in tags and tags["shop"] == "supermarket":
                    pois_data["supermarkets"].append({"name": name or "Supermarket", "distance": distance})
                
                elif "amenity" in tags and tags["amenity"] == "restaurant":
                    pois_data["restaurants"].append({"name": name or "Restaurant", "distance": distance})
                
                elif "leisure" in tags and tags["leisure"] == "fitness_centre":
                    pois_data["fitness"].append({"name": name or "Sală de Fitness", "distance": distance})
                
                elif "amenity" in tags and tags["amenity"] == "pharmacy":
                    pois_data["pharmacies"].append({"name": name or "Farmacie", "distance": distance})
                
                elif "amenity" in tags and tags["amenity"] == "school":
                    pois_data["schools"].append({"name": name or "Școală / Liceu", "distance": distance})
                
                elif "leisure" in tags and tags["leisure"] == "park":
                    pois_data["parks"].append({"name": name or "Parc", "distance": distance})
                
                elif "amenity" in tags and (tags["amenity"] == "bank" or tags["amenity"] == "atm"):
                    label = "Bancă" if tags["amenity"] == "bank" else "ATM"
                    pois_data["banks_atms"].append({"name": name or label, "distance": distance})

            for category in pois_data:
                pois_data[category] = sorted(pois_data[category], key=lambda x: x["distance"])

            pois_data["restaurants"] = pois_data["restaurants"][:5]

        except Exception as e:
            print(f"MapsAgent [Overpass Error]: {e}")
            
        return pois_data

class DetectiveAgent:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = 'gemini-3.1-flash-lite'

    def analyze_listing(self, listing_id, user):
        if not self.client:
            print("Eroare: Analiza AI nu poate rula deoarece clientul GenAI nu a fost inițializat (lipsește cheia API).")
            return None

        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            print("Eroare: Anunțul nu a fost găsit.")
            return None
        
        t_start = time.time()
        scor_baza = listing.data_completeness_score or 85
        data_azi = timezone.now().strftime('%d.%m.%Y')
# --- AICI ÎNCEPE BUCATA NOUĂ PENTRU SPAȚIUL GOL ---
        listing_dict = {
            "Price": listing.price,
            "Currency": listing.currency,
            "City": listing.city,
            "Neighborhood": listing.neighborhood,
            "Rooms": listing.rooms,
            "Useful surface": listing.useful_surface,
            "Heating type": listing.heating_type,
            "Furnishing state": listing.furnishing_state,
            "Floor": listing.floor,
            "Total floors": listing.total_floors,
            "Bathrooms": listing.bathrooms,
            "Construction year": listing.construction_year,
            "Availability": listing.availability,
            "Has fridge": listing.has_fridge,
            "Has washing machine": listing.has_washing_machine,
            "Has ac": listing.has_ac,
            "Has oven": listing.has_oven,
            "Has parking": listing.has_parking,
            "Has elevator": listing.has_elevator,
            "Near public transit": listing.near_public_transit
        }
        
        validare_rezultate = calculate_completeness_score(listing_dict)
        
        lista_lipsuri = []  # va fi adăugată programatic în flags după răspunsul AI
        for warning in validare_rezultate.get('warnings', []):
            lista_lipsuri.append(warning['message'])
        for notice in validare_rezultate.get('notices', []):
            lista_lipsuri.append(notice)

        # Extragem categoriile deja acoperite de sistem (pentru a preveni duplicarea în AI flags)
        teme_sistem = []
        for lipsura in lista_lipsuri:
            if lipsura.startswith('BAZA:'):
                teme_sistem.append("câmpuri de bază (preț, camere, suprafață, etaj, mobilier, încălzire, etc.)")
            if lipsura.startswith('DETALII:'):
                teme_sistem.append("facilități și finisaje (dotări electrocasnice, parcare, lift, internet, etc.)")
        teme_sistem_str = ", ".join(set(teme_sistem)) if teme_sistem else "nicio temă"
            
        texte_penalizari = "\n".join([f"- {lipsa}" for lipsa in lista_lipsuri])
        if not texte_penalizari:
            texte_penalizari = "- Nicio penalizare tehnică din partea sistemului."

        # --- Preț mediu pe cartier din DB (preț/mp) ---
        pret_mediu_cartier = None
        context_pret = ""
        if listing.neighborhood and listing.city:
            from django.db.models import ExpressionWrapper, FloatField, F
            qs = Listing.objects.filter(
                neighborhood__iexact=listing.neighborhood,
                city__iexact=listing.city,
                processing_status='PROCESSED',
                price__isnull=False,
                useful_surface__isnull=False,
                useful_surface__gt=0,
            ).exclude(pk=listing.pk).annotate(
                pret_mp=ExpressionWrapper(
                    F('price') / F('useful_surface'),
                    output_field=FloatField()
                )
            )
            agg = qs.aggregate(avg=Avg('pret_mp'))
            pret_mediu_mp = round(float(agg['avg']), 2) if agg['avg'] else None
        else:
            pret_mediu_mp = None

        if pret_mediu_mp and listing.price and listing.useful_surface:
            pret_mp_curent = round(float(listing.price) / float(listing.useful_surface), 2)
            diff_pct = round(((pret_mp_curent - pret_mediu_mp) / pret_mediu_mp) * 100)
            semn = "+" if diff_pct >= 0 else ""
            context_pret = (f"\n            DATE REALE PREȚ/MP (din baza noastră de date pentru {listing.neighborhood}, {listing.city}): "
                           f"Prețul mediu/mp al anunțurilor similare procesate este {pret_mediu_mp} {listing.currency}/mp. "
                           f"Anunțul curent are {pret_mp_curent} {listing.currency}/mp, adică {semn}{diff_pct}% față de medie.")
            pret_mediu_cartier = round(pret_mediu_mp)  # pentru instrucțiunea PRICE ANALYSIS
        # --- Sfârșit calcul preț ---
        # --- AICI SE TERMINĂ BUCATA NOUĂ ---

        maps_agent = MapsAgent()
        
        # Folosim coordonatele GPS salvate de scraper (instant, fără Nominatim)
        lat, lng = listing.latitude, listing.longitude
        if not lat or not lng:
            query_location = f"{listing.neighborhood}, {listing.city}"
            lat, lng = maps_agent.get_coordinates(query_location)
        
        t_coords = time.time()
        print(f"[⏱] Coords: {t_coords - t_start:.1f}s")

        # ── FAZA 1: POI fetch (necesar pentru prompt-ul Gemini) ──
        poi_data = "Nu s-au putut obține date despre zonă (coordonate lipsă)."
        poi_raw_data = {}
        
        if lat and lng:
            try:
                poi_raw_data = maps_agent.get_pois(lat, lng)
                poi_data = json.dumps(poi_raw_data, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[-] Eroare Overpass POI: {e}")
        else:
            poi_data = "JSON GOl. Bazează-te pe cunoștințele generale pentru a face o scurtă recenzie a nivelului de trai și atmosferei din acest cartier."
        t_poi = time.time()
        print(f" POI fetch: {t_poi - t_coords:.1f}s")

        # ── FAZA 2: Gemini + Distance Verification IN PARALEL ──
        # Gemini primește datele de listing + POI (fără distance verification)
        # Distance verification rulează simultan pe alt thread
        # Penalizările pentru distanțe exagerate se aplică PROGRAMATIC după

        prompt = f"""Ești un consultant imobiliar senior din România, specializat în analiza de piață.

            DATE ANUNȚ:
            Locație: {listing.city}, {listing.neighborhood}
            Titlu: {listing.title}
            Preț: {listing.price} {listing.currency}
            Descriere: {listing.description}
            {context_pret}

            LIPSURI TEHNICE GĂSITE DE SISTEM (Motivele scorului de {scor_baza}%):
            {texte_penalizari}

            Puncte de interes identificate de Maps Agent în zonă (Rază 1km):
            {poi_data}

            INSTRUCȚIUNI CRITICE PENTRU RED FLAGS ȘI SCOR:
            1. SCOR: Scorul tău de pornire este {scor_baza}%. Scade puncte suplimentare DOAR dacă identifici tu contradicții între descriere și datele tehnice. Nu scadea tu puncte pentru detalii care lipsesc de la datele tehnice, pentru ca sistemul a facut deja asta. Nu scadea puncte nici pentru distante diferite fata de cele din descriere. 
            2. RED FLAGS: Adaugă în "flags" DOAR riscuri pe care le descoperi TU din analiza descrierii și a prețului. INTERZIS să menționezi în flags: {teme_sistem_str} — acestea sunt deja acoperite automat de sistem și vor apărea separat.
            3. PRICE ANALYSIS: {'Folosește datele reale din secțiunea DATE REALE PREȚ de mai sus pentru câmpul price_analysis. average_zone_price=' + str(pret_mediu_cartier) + ' (EUR/mp, medie din baza noastră de date)' if pret_mediu_cartier else 'Estimează prețul mediu/mp pe zona menționată conform cunoștințelor tale despre piața imobiliară din România. Câmpul average_zone_price va reprezenta EUR/mp.'}
            4. PROXIMITATE: Redactează câmpul "proximity" EXCLUSIV folosind atracțiile și distanțele din JSON-ul primit. Dacă nu ai date, descrie cartierul la modul general. Este absolut interzis să te plângi în text că îți lipsesc informațiile.

            Returnează DOAR un JSON valid:
            {{
                "score": <int_scor_final>,
                "flags": ["riscuri_descoperite_de_AI"],
                "proximity": "Sinteză a vieții în zonă...",
                "price_analysis": {{
                    "average_zone_price": <float_pret_mediu_pe_mp>,
                    "difference_percentage": <int_procent_diferenta>,
                    "label": "string_explicatie"
                }},
                "verdict": "concluzie_echilibrată"
            }}"""

        gemini_result = [None]
        gemini_error = [None]
        verified_claims = []

        def _call_gemini():
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_id,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            thinking_config=types.ThinkingConfig(thinking_budget=0)
                        )
                    )
                    gemini_result[0] = json.loads(response.text)
                    return
                except Exception as e:
                    eroare_str = str(e)
                    print(f"[-] Eroare AI (Încercarea {attempt + 1}/{max_retries}): {eroare_str}")
                    if "503" in eroare_str or "429" in eroare_str or "UNAVAILABLE" in eroare_str:
                        wait_time = 5 * (attempt + 1)
                        print(f"[*] Server supraîncărcat. Așteptăm {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        gemini_error[0] = eroare_str
                        return
            gemini_error[0] = "Eșuat după multiple încercări"

        def _verify_distances():
            nonlocal verified_claims
            if not lat or not lng or not listing.description:
                return
            claims = extract_distance_claims(listing.description)
            claims = claims[:3]  # Cap la max 3 claims
            if claims:
                verified_claims = verify_distance_claims(lat, lng, claims, listing.city or "București")

        # Lansăm ambele în paralel
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_gemini = executor.submit(_call_gemini)
            fut_distance = executor.submit(_verify_distances)
            
            fut_gemini.result(timeout=60)
            try:
                fut_distance.result(timeout=15)
            except Exception:
                pass

        t_parallel = time.time()
        print(f"[⏱] Gemini + Distance (paralel): {t_parallel - t_poi:.1f}s")

        if not gemini_result[0]:
            print(f"[-] Analiza AI a eșuat: {gemini_error[0]}")
            return None

        data = gemini_result[0]

        # ── Suprascriem difference_percentage cu valoarea calculată programatic ──
        # Gemini poate returna un procent care contrazice propriul label; folosim
        # valoarea reală calculată din DB (sau None dacă nu avem date).
        if data.get('price_analysis') and isinstance(data['price_analysis'], dict):
            if pret_mediu_mp and listing.price and listing.useful_surface:
                data['price_analysis']['difference_percentage'] = diff_pct
                data['price_analysis']['average_zone_price'] = pret_mediu_mp

        # ── FAZA 3: Aplicăm flag-uri pentru distanțe exagerate, DAR FĂRĂ SĂ SCĂDEM SCORUL ──
        distance_verification_results = []
        score_adjustment = 0
        
        for vc in verified_claims:
            verdict = vc.get('verdict', '')
            entry = {
                "claim": vc.get('raw_text', 'Distanță afirmată'),
                "real": f"{vc.get('real_minutes', '?')} minute ({vc.get('transport_mode', 'walking')})",
                "verdict": verdict
            }
            distance_verification_results.append(entry)
            
            # Adăugăm red flags bazate pe verdict, dar NU mai scădem scorul
            if verdict == "UȘOR EXAGERAT":
                data.setdefault('flags', []).append(
                    f"Distanța către {vc['destination']} e ușor exagerată (afirmat: {vc['claimed_minutes']}min, real: {vc['real_minutes']}min)"
                )
            elif verdict == "FALS / ÎNȘELĂTOR":
                data.setdefault('flags', []).append(
                    f"Distanța către {vc['destination']} e fals înșelătoare! (afirmat: {vc['claimed_minutes']}min, real: {vc['real_minutes']}min)"
                )
            elif "PIN FALS" in verdict:
                data.setdefault('flags', []).append(
                    f"PIN FALS PE HARTĂ: Agentul a plasat pinul GPS mai aproape de {vc['destination']} pentru a trișa căutările!"
                )

        final_score = max(0, min(100, data.get('score', scor_baza) + score_adjustment))

        # Adăugăm programatic flags-urile sistemului (BAZA: și DETALII:) la începutul listei
        ai_flags = data.get('flags', [])
        system_flags = lista_lipsuri  # conține deja "BAZA:..." și "DETALII:..."
        data['flags'] = system_flags + ai_flags

        t_end = time.time()
        print(f" TOTAL analyze_listing: {t_end - t_start:.1f}s (Gemini+Dist paralel: {t_parallel - t_poi:.1f}s, POI: {t_poi - t_coords:.1f}s)")

        try:
            return Report.objects.create(
                listing=listing,
                user=user,
                integrity_score=final_score,
                red_flags=data.get('flags', []),
                proximity_analysis=data.get('proximity', "Nu au fost identificate detalii despre zonă."),
                final_verdict=data.get('verdict', ""),
                price_analysis=data.get('price_analysis'),
                distance_verification=distance_verification_results
            )
        except Exception as e:
            print(f" Eroare la salvarea raportului: {e}")
            return None