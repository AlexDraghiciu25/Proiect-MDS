import json
from google import genai
from google.genai import types
from django.conf import settings
from .models import Listing, Report

class DetectiveAgent:
    def __init__(self):
        # Inițializarea noului client Google GenAI
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        # Folosim noul model de generație Flash (2.5) care este activ
        self.model_id = 'gemini-2.5-flash' 

    def analyze_listing(self, listing_id, user):
        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            print("Eroare: Anunțul nu a fost găsit.")
            return None
        
        prompt = f"""
            Ești un expert detectiv imobiliar din România. Analizează acest anunț:
            Locație: {listing.city}, {listing.neighborhood}
            Titlu: {listing.title} 
            Preț: {listing.price} {listing.currency}  # Transmiterea explicită a monedei (RON sau EUR)
            Descriere: {listing.description}

            SARCINĂ UNICĂ: 
            1. Evaluează riscul de fraudă și proximitatea (metrou/parcuri vs zgomot/cluburi).
            2. Compară prețul de {listing.price} {listing.currency} cu media pieței din {listing.neighborhood}. 
            3. Dacă moneda este RON, compară cu valori în RON. Dacă este EUR, compară cu valori în EUR.

            Returnează DOAR un JSON valid:
            {{
                "score": <int_0_100>,
                "flags": ["listă_scurtă_alerte"],
                "proximity": "analiză_facilități_și_zgomot",
                "price_analysis": {{
                    "average_zone_price": <int_valoare_medie_estimată_în_{listing.currency}>,
                    "difference_percentage": <int_procent_pozitiv_sau_negativ>,
                    "label": "ex: Preț corect / Mult sub media zonei"
                }},
                "verdict": "concluzie_finală_scurtă"
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