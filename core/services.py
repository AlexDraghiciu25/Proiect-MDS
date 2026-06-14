import json
import requests
import re
import math
import time
from google import genai
from google.genai import types
from django.conf import settings
from .models import Listing, Report
from django.utils import timezone

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
            
        time.sleep(1.2) 
        nom_url = "https://nominatim.openstreetmap.org/search"
        
        nom_params = {
            'q': f"{destination}, {city}",
            'format': 'json',
            'limit': 5,
            'viewbox': f"{listing_lng-0.05},{listing_lat+0.05},{listing_lng+0.05},{listing_lat-0.05}",
            'bounded': 0
        }
        
        try:
            nom_response = requests.get(nom_url, params=nom_params, headers=headers, timeout=5)
            nom_data = nom_response.json()
            
            if not nom_data:
                time.sleep(1.2)
                nom_params['q'] = destination
                nom_response = requests.get(nom_url, params=nom_params, headers=headers, timeout=5)
                nom_data = nom_response.json()
                
            if not nom_data:
                print(f"[-] Harta nu a putut geocoda: '{destination}'")
                continue
                
            closest_dest = None
            min_dist = float('inf')

            for place in nom_data:
                p_lat = float(place['lat'])
                p_lon = float(place['lon'])
                dist = (p_lat - listing_lat)**2 + (p_lon - listing_lng)**2
                if dist < min_dist:
                    min_dist = dist
                    closest_dest = (p_lat, p_lon)

            if not closest_dest:
                continue

            dest_lat, dest_lng = closest_dest
            real_data = get_real_travel_time(listing_lat, listing_lng, dest_lat, dest_lng, mode)
            
            if not real_data or isinstance(real_data, str):
                print(f"[-] Eroare de rutare către: '{destination}'")
                continue
                
            real_minutes = real_data["duration_minutes"]
            safe_claimed = claimed_time if claimed_time > 0 else 1 
            
            if real_minutes <= safe_claimed:
                if safe_claimed - real_minutes > 4:
                    diff_percent = round(((safe_claimed - real_minutes) / safe_claimed) * 100, 1)
                    verdict = "PIN FALS PE HARTĂ (MOMEALĂ)"
                else:
                    diff_percent = 0.0
                    verdict = "CONFIRMAT"
            else:
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
    
    def get_neighborhood_from_gps(self, lat, lng):
        """
        Reverse Geocoding: Trimite coordonatele GPS către Nominatim și extrage 
        numele oficial al cartierului (suburb / neighbourhood) pentru ORICE oraș.
        """
        if not lat or not lng:
            return "Zonă Nespecificată"

        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lng,
            'format': 'json',
            'addressdetails': 1
        }
        headers = {'User-Agent': 'RentGuru/1.0'}

        try:
            time.sleep(1.0)
            response = requests.get(url, params=params, headers=headers, timeout=5)
            data = response.json()
            
            address = data.get("address", {})
            cartier = address.get("suburb") or address.get("neighbourhood") or address.get("residential") or address.get("quarter")
            
            if cartier:
                return cartier.strip()
            if address.get("road"):
                return f"Zona {address.get('road')}"
                
        except Exception as e:
            print(f"MapsAgent [Reverse Geocoding Error]: {e}")
            
        return "Zonă Nespecificată"

    def _calculate_distance(self, lat1, lng1, lat2, lng2):
        R = 6371000  
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
            "transport": [], "supermarkets": [], "restaurants": [], "fitness": [],
            "pharmacies": [], "schools": [], "parks": [], "banks_atms": []
        }

        try:
            response = requests.post(self.overpass_url, data={'data': overpass_query}, headers=headers, timeout=15)
            data = response.json()
            elements = data.get("elements", [])

            for el in elements:
                tags = el.get("tags", {})
                el_lat = el["center"]["lat"] if "center" in el else el.get("lat")
                el_lng = el["center"]["lon"] if "center" in el else el.get("lng")

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
        self.model_id = 'gemini-2.5-flash'

    def analyze_listing(self, listing_id, user):
        if not self.client:
            print("Eroare: Agentul nu este inițializat.")
            return None

        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            print("Eroare: Anunțul nu a fost găsit.")
            return None

        pret_brut = float(listing.price) if listing.price else 0.0
        moneda_corectata = listing.currency

        text_complet = f"{listing.title or ''} {listing.description or ''}".lower()
        are_indicii_euro = any(c in text_complet for c in ["€", "eur", "euro"])

        if pret_brut < 1500 or are_indicii_euro:
            moneda_corectata = "EUR"
        else:
            moneda_corectata = "RON"

        scor_baza = listing.data_completeness_score or 85
        data_azi = timezone.now().strftime('%d.%m.%Y')

        maps_agent = MapsAgent()
        query_location = f"{listing.neighborhood}, {listing.city}"
        lat, lng = maps_agent.get_coordinates(query_location)
        
        verified_claims_text = "Nu au fost identificate afirmații legate de distanțe în descriere."
        poi_data = "Nu s-au putut obține date despre zonă (coordonate lipsă)."

        if lat and lng:
            claims = extract_distance_claims(listing.description)
            verified_claims = []
            if claims:
                verified_claims = verify_distance_claims(lat, lng, claims, city=listing.city)
            
            if verified_claims:
                verified_claims_text = ""
                for vc in verified_claims:
                    verified_claims_text += f"► {vc['raw_text']} -> DESTINAȚIE REALĂ: {vc['destination']} | TIMP REAL: {vc['real_minutes']} min | VERDICT: {vc['verdict']}\n"
            
            poi_raw_data = maps_agent.get_pois(lat, lng)
            poi_data = json.dumps(poi_raw_data, indent=2, ensure_ascii=False)
        else:
            poi_data = f"Sistemul GPS a eșuat să găsească adresa exactă. Te rog să analizezi zona '{listing.neighborhood}, {listing.city}' bazându-te pe cunoștințele tale generale."

        alerte_sistem = getattr(listing, 'validation_warnings', [])
        alerte_text = ", ".join([w.get('message', '') for w in alerte_sistem]) if alerte_sistem else "Nu sunt alerte critice."

        prompt = f"""
            Ești un consultant imobiliar senior din România, specializat în analiza de piață. 
            Analizează acest anunț pornind de la un Index de Încredere de bază de {scor_baza}%.

            DATE ANUNȚ:
            Locație: {listing.city}, {listing.neighborhood}
            Titlu: {listing.title} 
            Preț total: {listing.price} {moneda_corectata}
            Suprafață utilă: {getattr(listing, 'useful_surface', 'N/A')} mp
            Descriere: {listing.description}
            Specificații tehnice: {listing.raw_data.get('site_specs', 'N/A')}
            Alerte sistem (lipsă date): {alerte_text}
            
            Puncte de interes identificate de Maps Agent în zonă (Rază 1km):
            {poi_data}

            VERIFICARE AFIRMAȚII PROPRIETAR (RUTE REALE GPS):
            {verified_claims_text}

            INSTRUCȚIUNI CRITICE PENTRU SCOR ȘI FLAGS:
            1. Scorul final trebuie să reflecte acuratețea și completitudinea datelor. 
            2. Dacă scorul final este sub 90%, include în lista "flags" motivele.
            3. NU scădea puncte pentru lipsa contactului telefonic.
            4. Scade din scorul de {scor_baza}% DOAR dacă identifici contradicții mari sau preț suspect de mic/mare, dar dacă numărul de camere este deja cunoscut sau menționat în text (ex: '2 camere') nu penaliza.
            5. Dacă prețul este cu 10-20% sub medie, etichetează-l ca "Ofertă competitivă" în verdict.
            6. Data curentă: {data_azi}.
            7. Folosește Datele POI pentru a redacta o recenzie utilă în câmpul "proximity", incluzând distanțele exacte în metri.
            8. Dacă în VERIFICARE AFIRMAȚII PROPRIETAR există verdicte de "UȘOR EXAGERAT" sau "FALS / ÎNȘELĂTOR", PENALIZEAZĂ SCORUL și adaugă în flags.
            9. Dacă există verdictul "PIN FALS PE HARTĂ (MOMEALĂ)", penalizează drastic scorul de integritate.
            
            Returnează DOAR un JSON valid:
            {{
                "score": <int_scor_ajustat_porninn_de_la_{scor_baza}>,
                "flags": ["listă_cu_riscuri_SAU_lipsuri_tehnice"],
                "proximity": "Sinteză complexă a vieții în această zonă bazată pe datele POI...",
                "price_analysis": {{
                    "price_per_sqm": <float_calculat>,
                    "average_zone_price_sqm": <int_valoare_medie_estimată_pe_mp_în_{moneda_corectata}>,
                    "difference_percentage": <int_procent_pozitiv_sau_negativ>,
                    "label": "ex: Preț conform pieței / Ofertă excelentă"
                }},
                "distance_verification": [
                    {{
                        "claim": "textul afirmatiei, ex: 10 minute de metrou",
                        "real": "valoarea reală calculată, ex: 14 minute",
                        "verdict": "CONFIRMAT / UȘOR EXAGERAT / FALS / ÎNȘELĂTOR"
                    }}
                ],
                "verdict": "concluzie_echilibrată_care_explică_și_scorul"
            }}
            """

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                
                data = json.loads(response.text)
                
                return Report.objects.create(
                    listing=listing,
                    user=user,
                    integrity_score=data.get('score', 0),
                    red_flags=data.get('flags', []),
                    proximity_analysis=data.get('proximity', "Nu au fost identificate detalii despre zonă."),
                    final_verdict=data.get('verdict', ""),
                    price_analysis=data.get('price_analysis'),
                    distance_verification=data.get('distance_verification', [])
                )
                
            except Exception as e:
                eroare_str = str(e)
                print(f"[-] Eroare AI (Încercarea {attempt + 1}/{max_retries}): {eroare_str}")
                
                if "503" in eroare_str or "429" in eroare_str or "UNAVAILABLE" in eroare_str:
                    wait_time = 5 * (attempt + 1)
                    print(f"[*] Server supraîncărcat. Așteptăm {wait_time} secunde...")
                    time.sleep(wait_time)
                    continue 
                else:
                    break 

        print("[-] Analiza AI a eșuat definitiv după multiple încercări.")
        return None