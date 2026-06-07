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
        self.model_id = 'gemini-2.5-flash'

    def analyze_listing(self, listing_id, user):
        data_azi = timezone.now().strftime('%d.%m.%Y')
        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            print("Eroare: Anunțul nu a fost găsit.")
            return None
        
        scor_baza = listing.data_completeness_score or 85
        
        # Presupunem că ai salvat avertismentele generate de tool-ul nostru 
        # într-un câmp de tip JSON (ex: validation_warnings) sau le recalculezi aici.
        # Dacă nu, poți lăsa doar scorul, dar e mai sigur să i le dai.
        alerte_sistem = getattr(listing, 'validation_warnings', [])
        alerte_text = ", ".join([w.get('message', '') for w in alerte_sistem]) if alerte_sistem else "Nu sunt alerte critice."

        prompt = f"""
            Ești un consultant imobiliar senior din România, specializat în analiza de piață. 
            Analizează acest anunț pornind de la un Index de Completitudine a Datelor de {scor_baza}%.

            DATE ANUNȚ:
            Locație: {listing.city}, {listing.neighborhood}
            Titlu: {listing.title} 
            Preț total: {listing.price} {listing.currency}
            Suprafață utilă: {getattr(listing, 'useful_surface', 'N/A')} mp
            Descriere: {listing.description}
            Specificații tehnice: {listing.raw_data.get('site_specs', 'N/A')}
            Alerte sistem (lipsă date): {alerte_text}

            INSTRUCȚIUNI CRITICE PENTRU SCOR ȘI FLAGS:
            1. Calculează mental prețul per metru pătrat (Preț total / Suprafață utilă). Bazează-ți TOATĂ analiza financiară pe această valoare.
            2. Scade din scorul de {scor_baza}% DOAR dacă identifici contradicții logice în text (ex: scrie etaj 1, dar în descriere e parter) sau un preț suspect/fals.
            3. Include în lista "flags" alertele de sistem primite mai sus, dar adaugă și propriile tale descoperiri (ex: "Descriere prea sumară", "Posibil apartament la demisol").
            4. NU scădea puncte pentru lipsa contactului telefonic.
            5. Dacă prețul per metru pătrat este cu 10-20% sub media zonei {listing.neighborhood}, etichetează-l ca "Ofertă competitivă" în verdict.
            6. Data curentă: {data_azi}.

            Returnează DOAR un JSON valid:
            {{
                "score": <int_scor_ajustat_pornind_de_la_{scor_baza}>,
                "flags": ["listă_cu_riscuri_SAU_lipsuri_tehnice"],
                "proximity": "analiză_facilități_și_zgomot_din_zona_{listing.neighborhood}",
                "price_analysis": {{
                    "price_per_sqm": <float_calculat>,
                    "average_zone_price_sqm": <int_valoare_medie_estimată_pe_mp_în_{listing.currency}>,
                    "difference_percentage": <int_procent_pozitiv_sau_negativ>,
                    "label": "ex: Preț conform pieței / Ofertă excelentă / Peste media zonei"
                }},
                "verdict": "concluzie_echilibrată_care_explică_și_scorul"
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