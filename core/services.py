import json
import requests
from google import genai
from google.genai import types
from django.conf import settings
from .models import Listing, Report
from django.utils import timezone

class MapsAgent:
    def __init__(self):
        self.geocode_url = "https://nominatim.openstreetmap.org/search"
        self.places_url = "https://overpass.kumi.systems/api/interpreter"

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

    def get_pois(self, city, neighborhood):
        if not city or not neighborhood:
            return "Locație insuficient definită."

        query_location = f"{neighborhood}, {city}"
        lat, lng = self.get_coordinates(query_location)

        if not lat or not lng:
            return f"Nu s-au putut obține coordonatele GPS pentru {query_location}."

        raza = 1500
        headers = {'User-Agent': 'RentGuru/1.0'}

        poi_categories = [
            {"nume": "Transport", "amenity": "bus_stop"},
            {"nume": "Comercial", "shop": "supermarket"},
            {"nume": "Educație", "amenity": "school"},
            {"nume": "Sănătate", "amenity": "pharmacy"},
            {"nume": "Recreere", "amenity": "park"},
            {"nume": "Bănci", "amenity": "bank"},
        ]

        rezultate_analiza = {}

        for cat in poi_categories:
            nume = cat.pop("nume")
            key, value = list(cat.items())[0]
            rezultate_analiza[nume] = []

            params = {
                'format': 'json',
                'limit': 4,
                'lat': lat,
                'lon': lng,
                'radius': raza,
                f'tag[{key}]': value,
                'q': value,
                'bounded': 1,
                'viewbox': f"{lng-0.02},{lat+0.02},{lng+0.02},{lat-0.02}",
            }

            try:
                response = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        'q': f"{value} near {neighborhood} {city}",
                        'format': 'json',
                        'limit': 4,
                        'bounded': 1,
                        'viewbox': f"{lng-0.02},{lat+0.02},{lng+0.02},{lat-0.02}",
                    },
                    headers=headers,
                    timeout=8
                )
                results = response.json()
                for r in results:
                    name = r.get('display_name', '').split(',')[0]
                    if name and name not in rezultate_analiza[nume]:
                        rezultate_analiza[nume].append(name)
            except Exception as e:
                print(f"MapsAgent [Nominatim Error] {nume}: {e}")

        rezultate_analiza = {k: v for k, v in rezultate_analiza.items() if v}

        if not rezultate_analiza:
            return f"Zona {query_location} ({lat:.4f}, {lng:.4f}) identificată, dar nu s-au găsit POI-uri specifice."

        raport = f"Analiza Hărții (Rază {raza}m) pentru {query_location} ({lat:.4f}, {lng:.4f}):\n"
        for categorie, locatii in rezultate_analiza.items():
            raport += f"► {categorie}:\n"
            for loc in locatii:
                raport += f"   - {loc}\n"

        return raport

class DetectiveAgent:
    def __init__(self):
        # Inițializarea noului client Google GenAI
        self.api_key = settings.GEMINI_API_KEY
        if not self.api_key:
            print("ATENȚIE: GEMINI_API_KEY nu este setată în fișierul .env sau în variabilele de mediu!")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        
        self.model_id = 'gemini-2.5-flash'

    def analyze_listing(self, listing_id, user):
        if not self.client:
            print("Eroare: Analiza AI nu poate rula deoarece clientul GenAI nu a fost inițializat (lipsește cheia API).")
            return None

        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            print("Eroare: Anunțul nu a fost găsit.")
            return None
        
        scor_baza = listing.data_completeness_score or 85
        data_azi = timezone.now().strftime('%d.%m.%Y')

        # 1. Obținem datele reale despre zonă de la MapsAgent
        maps_agent = MapsAgent()
        date_proximitate_reale = maps_agent.get_pois(listing.city, listing.neighborhood)

        prompt = f"""
            Ești un consultant imobiliar senior din România, specializat în analiza de piață. 
            Analizează acest anunț pornind de la un Index de Încredere de bază de {scor_baza}%.

            DATE ANUNȚ:
            Locație: {listing.city}, {listing.neighborhood}
            Titlu: {listing.title} 
            Preț: {listing.price} {listing.currency}
            Descriere: {listing.description}
            Specificații tehnice: {listing.raw_data.get('site_specs', 'N/A')}
            Puncte de interes identificate de Maps Agent în zonă (Rază 1.5km):
            {date_proximitate_reale}

            INSTRUCȚIUNI CRITICE PENTRU SCOR ȘI FLAGS:
            1. Scorul final trebuie să reflecte acuratețea și completitudinea datelor. 
            2. Dacă scorul final este sub 90%, ești OBLIGAT să incluzi în lista "flags" motivele pentru care s-au pierdut puncte (ex: "Număr de camere nespecificat", "Lipsă detalii etaj", "Descriere sumară").
            3. NU scădea puncte pentru lipsa contactului telefonic (e gestionat de platformă).
            4. Scade din scorul de {scor_baza}% DOAR dacă identifici contradicții (ex: etaj greșit) sau preț suspect (peste 50% sub medie).
            5. Dacă prețul este cu 10-20% sub medie, etichetează-l ca "Ofertă competitivă" în verdict, nu ca risc.
            6. Data curentă: {data_azi}. Ignoră eroarea "dată în viitor" pentru ziua de azi.
            7. Folosește Datele identificate de Maps Agent pentru a redacta o recenzie utilă a zonei în câmpul "proximity".

            Returnează DOAR un JSON valid:
            {{
                "score": <int_scor_ajustat_pornind_de_la_{scor_baza}>,
                "flags": ["listă_cu_riscuri_SAU_lipsuri_tehnice_care_justifică_scorul"],
                "proximity": "Sinteză complexă a vieții în această zonă bazată pe analizele Maps Agent (ex: 'Zona este excelentă pentru familii având școli (X, Y) și supermarketuri în apropiere...')",
                "price_analysis": {{
                    "average_zone_price": <int_valoare_medie_estimată_în_{listing.currency}>,
                    "difference_percentage": <int_procent_pozitiv_sau_negativ>,
                    "label": "ex: Preț conform pieței / Ofertă excelentă / Peste media zonei"
                }},
                "verdict": "concluzie_echilibrată_care_explică_și_scorul_dacă_e_mic"
            }}
            """

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
            )
        except Exception as e:
            print(f"Eroare AI: {e}")
            return None