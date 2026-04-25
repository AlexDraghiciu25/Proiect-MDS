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
        Analizează acest anunț imobiliar pentru fraude:
        Titlu: {listing.title}
        Preț: {listing.price} EUR
        Descriere: {listing.description}

        Returnează DOAR un JSON (fără niciun alt text) cu structura:
        {{
            "score": 50,
            "flags": ["problema 1"],
            "verdict": "explicație"
        }}
        """

        try:
            # Apelăm AI-ul folosind noua sintaxă
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json" # Secretul pentru JSON perfect
                )
            )
            
            # Răspunsul este deja garantat a fi JSON, îl convertim direct
            data = json.loads(response.text)
            
            return Report.objects.create(
                listing=listing,
                user=user,
                integrity_score=data.get('score', 0),
                red_flags=data.get('flags', []),
                final_verdict=data.get('verdict', "Analizat cu succes.")
            )
        except Exception as e:
            print(f"Eroare AI: {e}")
            return None