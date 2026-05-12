import time
import requests 
from django.core.management.base import BaseCommand
from core.models import Listing
import re

class Command(BaseCommand):
    help = 'Bot asasin: Verifică valabilitatea și ȘTERGE instant anunțurile moarte'

    def handle(self, *args, **options):
        # Luăm absolut TOATE anunțurile din baza de date
        anunturi = Listing.objects.all()
        count = anunturi.count()
        
        if count == 0:
            self.stdout.write(self.style.WARNING("Nu există niciun anunț în baza de date de verificat."))
            return
            
        self.stdout.write(self.style.WARNING(f"Pornim verificarea și curățenia pentru {count} anunțuri..."))

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
        }

        anunturi_sterse = 0

        for anunt in anunturi:
            url = anunt.source_url
            
            try:
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
                este_valabil = True
                motiv = ""

                # STRATUL 1: Eroare 404 sau 410 clasică
                if response.status_code in [404, 410]:
                    este_valabil = False
                    motiv = "Eroare 404 (Hard)"
                
                # STRATUL 2: Redirect către altă pagină
                elif response.url != url and "/oferta/" not in response.url:
                    este_valabil = False
                    motiv = f"Redirect către: {response.url}"

                # STRATUL 3: Soft 404 (Pagina zice că e inactiv)
                elif response.status_code == 200:
                    text_pagina = response.text.lower()
                    
                    tipare_moarte = [
                        # Prinde: "acest anunt nu mai este valabil", "anunțul nu mai este disponibil"
                        r'anun[tț].{0,30}nu.{0,20}mai.{0,20}este.{0,20}(?:valabil|disponibil)',
                        
                        # Prinde: "anunt dezactivat", "anunț dezactivat"
                        r'anun[tț].{0,30}dezactivat',
                        
                        # Prinde: "pagina nu a fost gasita", "404 - pagina nu a fost gasita"
                        r'pagina.{0,30}nu.{0,20}a.{0,20}fost.{0,20}g[aă]sit[aă]',
                        
                        # Bonus (opțional, dar foarte util pentru Storia):
                        r'oferta.{0,30}inactiv[aă]'
                    ]
                    
                    for pattern in tipare_moarte:
                        if re.search(pattern, text_pagina):
                            este_valabil = False
                            # Opțional: Poți salva și tiparul exact în motiv ca să vezi în consolă ce a declanșat ștergerea
                            motiv = "Soft 404 (Anunț inactiv sau șters)" 
                            break

                # ACȚIUNEA DIRECTĂ: Dacă e mort, îl ștergem instant
                if not este_valabil:
                    url_sters = anunt.source_url 
                    anunt.delete() # ȘTERGERE DEFINITIVĂ DIN DB
                    anunturi_sterse += 1
                    self.stdout.write(self.style.ERROR(f" ȘTERS: {url_sters} | Motiv: {motiv}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f" VIU: {url}"))

                time.sleep(1)

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.WARNING(f" EROARE REȚEA la {url} (sare peste): {e}"))
                time.sleep(2)

        self.stdout.write(self.style.SUCCESS(f"Misiune îndeplinită! Baza de date a fost curățată. Am șters definitiv {anunturi_sterse} anunțuri."))