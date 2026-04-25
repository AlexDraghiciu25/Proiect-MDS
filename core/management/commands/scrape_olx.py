import requests
import time
import re
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from core.models import Listing

class Command(BaseCommand):
    help = 'Extrage și standardizează datele (Tip, Cartier, Sumar)'

    def extrage_cartier(self, text):
        # O listă de cartiere comune (o poți extinde)
        cartiere = ['unirii', 'berceni', 'militari', 'drumul taberei', 'tineretului', 
                    'titan', 'dristor', 'floreasca', 'aviatiei', 'pipera', 'obor', 
                    'pantelimon', 'rahova', 'colentina', 'victoriei', 'dorobanti', 
                    'crangasi', 'lujerului', 'grozavesti', 'cotroceni', 'vitan']
        
        text_lower = text.lower()
        for c in cartiere:
            if c in text_lower:
                return c.title() # Returnează cu majusculă (ex: "Berceni")
        return "București (Zonă neprecizată)"

    def handle(self, *args, **options):
        url = "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-inchiriat/bucuresti/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }

        self.stdout.write("Preluăm lista de link-uri...")
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        toate_linkurile = soup.find_all('a', href=True)
        linkuri_oferte = set()
        
        for a in toate_linkurile:
            href = a['href']
            if '/d/oferta/' in href or 'storia.ro/ro/oferta/' in href:
                full_url = href if href.startswith('http') else f"https://www.olx.ro{href}"
                linkuri_oferte.add(full_url)

        self.stdout.write(self.style.SUCCESS(f"Am găsit {len(linkuri_oferte)} link-uri. Încep procesarea inteligentă..."))

        for source_url in linkuri_oferte:
            if Listing.objects.filter(source_url=source_url).exists():
                continue

            try:
                ad_response = requests.get(source_url, headers=headers)
                time.sleep(1.5)
                
                if ad_response.status_code != 200:
                    continue
                    
                ad_soup = BeautifulSoup(ad_response.text, 'html.parser')

                # 1. Extragem titlul brut pentru a-l analiza
                titlu_tag = ad_soup.find('h1')
                titlu_brut = titlu_tag.text.strip() if titlu_tag else ""

                # --- MAGIA NOUĂ: SMART TITLE ---
                # Detectăm tipul
                if 'garsonier' in titlu_brut.lower() or 'studio' in titlu_brut.lower():
                    tip_locuinta = "Garsonieră"
                else:
                    tip_locuinta = "Apartament"

                # Detectăm cartierul (căutăm în titlu și într-un tag de locație dacă există)
                locatie_tag = ad_soup.find('a', href=lambda href: href and 'map' in href)
                locatie_bruta = locatie_tag.text if locatie_tag else ""
                
                cartier = self.extrage_cartier(titlu_brut + " " + locatie_bruta)
                
                # Creăm noul titlu curat
                smart_title = f"{tip_locuinta} - {cartier}"

                # 2. PREȚUL (rămâne la fel)
                price = 0.00
                pret_tag = ad_soup.find(lambda tag: tag.name in ['h2', 'h3', 'div', 'strong'] and '€' in tag.text and len(tag.text.strip()) < 30)
                if pret_tag:
                    text_pret = pret_tag.text.replace(' ', '').replace('.', '')
                    cifre = re.findall(r'\d+', text_pret)
                    if cifre:
                        price = float(cifre[0])

                # --- MAGIA NOUĂ: SUMARIZAREA DESCRIERII ---
                divuri_text = ad_soup.find_all('div')
                raw_description = "Descriere indisponibilă."
                for div in divuri_text:
                    text_div = div.text.strip()
                    if len(text_div) > 150 and "Setări Cookies" not in text_div:
                        raw_description = text_div
                        break
                
                # Păstrăm doar primele 3 propoziții pentru un sumar curat
                propozitii = raw_description.split('.')
                # Evităm să luăm propoziții goale; adăugăm punct la final
                smart_description = '. '.join([p.strip() for p in propozitii[:3] if p.strip()]) + '.'

                # 4. SALVARE
                Listing.objects.create(
                    title=smart_title,
                    price=price,
                    description=smart_description,
                    location_text=cartier,
                    source_url=source_url
                )

                self.stdout.write(self.style.SUCCESS(f" => Salvat: {smart_title} | {price}€"))

            except Exception as e:
                pass

        self.stdout.write(self.style.SUCCESS("Baza de date a fost actualizată cu date structurate!"))