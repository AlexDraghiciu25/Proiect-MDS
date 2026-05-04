import json
from google import genai
from google.genai import types
from django.conf import settings
from .models import Listing, Report
from django.utils import timezone

class DetectiveAgent:
    def __init__(self):
        # Inițializarea noului client Google GenAI
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        # Folosim noul model de generație Flash (2.5) care este activ
        self.model_id = 'gemini-2.5-flash'

    def analyze_listing(self, listing_id, user):
        data_azi = timezone.now().strftime('%d.%m.%Y')
        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            print("Eroare: Anunțul nu a fost găsit.")
            return None
        
        scor_baza = listing.data_completeness_score or 85

        prompt = f"""
            Ești un consultant imobiliar senior din România, specializat în analiza de piață. 
            Analizează acest anunț pornind de la un Index de Încredere de bază de {scor_baza}%.

            DATE ANUNȚ:
            Locație: {listing.city}, {listing.neighborhood}
            Titlu: {listing.title} 
            Preț: {listing.price} {listing.currency}
            Descriere: {listing.description}
            Specificații tehnice: {listing.raw_data.get('site_specs', 'N/A')}

            INSTRUCȚIUNI CRITICE PENTRU SCOR ȘI FLAGS:
            1. Scorul final trebuie să reflecte acuratețea și completitudinea datelor. 
            2. Dacă scorul final este sub 90%, ești OBLIGAT să incluzi în lista "flags" motivele pentru care s-au pierdut puncte (ex: "Număr de camere nespecificat", "Lipsă detalii etaj", "Descriere sumară").
            3. NU scădea puncte pentru lipsa contactului telefonic (e gestionat de platformă).
            4. Scade din scorul de {scor_baza}% DOAR dacă identifici contradicții (ex: etaj greșit) sau preț suspect (peste 50% sub medie).
            5. Dacă prețul este cu 10-20% sub medie, etichetează-l ca "Ofertă competitivă" în verdict, nu ca risc.
            6. Data curentă: {data_azi}. Ignoră eroarea "dată în viitor" pentru ziua de azi.

            Returnează DOAR un JSON valid:
            {{
                "score": <int_scor_ajustat_pornind_de_la_{scor_baza}>,
                "flags": ["listă_cu_riscuri_SAU_lipsuri_tehnice_care_justifică_scorul"],
                "proximity": "analiză_facilități_și_zgomot",
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