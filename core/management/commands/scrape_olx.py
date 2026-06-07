import os
import time
import random
import re
import json
from django.core.management.base import BaseCommand
from core.models import Listing
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from django.db import transaction

class Command(BaseCommand):
    help = 'Scraper ultra-robust pentru OLX.ro cu extragere directă din JSON State și Imagini'

    def handle(self, *args, **options):
        # Permitem operatiunile asincrone in Django
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        self.stdout.write(self.style.WARNING(" Parser OLX.ro: Inițiere proces de scraping..."))

        with Stealth().use_sync(sync_playwright()) as p:
            # Lansăm browserul ascunzând amprenta de automatizare
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ]
            ) 
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            main_page = context.new_page()
            url_cautare = "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-inchiriat/bucuresti/"
            
            try:
                self.stdout.write(f" Navigam spre lista OLX: {url_cautare}")
                main_page.goto(url_cautare, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)
                
                try:
                    main_page.locator("#onetrust-accept-btn-handler, button:has-text('Accepta tot')").first.click(timeout=3000)
                except: 
                    pass

                self.stdout.write(" Generam scroll pentru a incarca lista...")
                for _ in range(3):
                    main_page.mouse.wheel(0, 1000)
                    time.sleep(1.2)

                hrefs = main_page.evaluate("""function() {
                    var links = document.querySelectorAll('a');
                    var urls = [];
                    links.forEach(function(a) {
                        if(a.href && (a.href.includes('/d/oferta/') || a.href.includes('/oferta/'))) {
                            urls.push(a.href);
                        }
                    });
                    return urls;
                }""")

                linkuri_valide = set()
                for href in hrefs:
                    if ".html" in href:
                        clean_url = href.split('#')[0].split('?')[0]
                        linkuri_valide.add(clean_url)

                if len(linkuri_valide) == 0:
                    self.stdout.write(self.style.ERROR(" Am gasit 0 anunturi in lista."))
                    return

                self.stdout.write(self.style.SUCCESS(f"Am gasit {len(linkuri_valide)} anunturi. Incepem procesarea..."))
                main_page.close()

                count = 0
                for url in list(linkuri_valide):
                    if count >= 40: break
                    
                    if self.proceseaza_anunt_olx(context, url):
                        count += 1
                        time.sleep(random.uniform(3, 6))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f" Eroare in handler-ul principal OLX: {e}"))
            finally:
                browser.close()
                self.stdout.write(" Gata scriptul de Scraping OLX!")

    def proceseaza_anunt_olx(self, context, url):
        if Listing.objects.filter(source_url=url).exists():
            self.stdout.write(self.style.WARNING(f"Skip: Exista in DB: {url[:40]}..."))
            return False

        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # --- EXTRACTOR PRINCIPAL: application/ld+json (Schema.org) ---
            ld_json_raw = page.evaluate("""function() {
                var scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (var i = 0; i < scripts.length; i++) {
                    var content = scripts[i].innerHTML;
                    if (content.includes('"name"') && content.includes('"offers"')) {
                        return content;
                    }
                }
                return null;
            }""")

            titlu = None
            pret_curat = None
            currency = "EUR"
            descriere = "N/A"
            locatie = "Bucuresti"
            imagini_brute = []
            specs_brute = ""

            if ld_json_raw:
                try:
                    ld_data = json.loads(ld_json_raw)

                    titlu = ld_data.get("name", "").strip()

                    # Extragere Imagini din LD+JSON
                    img_data = ld_data.get("image", [])
                    if isinstance(img_data, list):
                        imagini_brute = img_data
                    elif isinstance(img_data, str):
                        imagini_brute = [img_data]

                    # Preț din offers
                    offers = ld_data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    pret_raw = offers.get("price") or offers.get("lowPrice")
                    currency_raw = offers.get("priceCurrency", "EUR")
                    if pret_raw:
                        try:
                            pret_curat = float(str(pret_raw).replace(",", "."))
                        except:
                            pass
                    currency = currency_raw

                    # Descriere
                    descriere = ld_data.get("description", "N/A")

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"   LD+JSON parse error: {e}"))

            # --- FALLBACK: titlu din <title> tag dacă ld+json a eșuat ---
            if not titlu:
                try:
                    raw_title = page.title()
                    titlu = raw_title.split(" - OLX.ro")[0].strip()
                except:
                    titlu = None

            # --- FALLBACK preț: extrage din titlu cu regex ---
            if not pret_curat and titlu:
                match_pret = re.search(r'(\d+[\.,]?\d*)\s*(?:€|eur|euro|lei)', titlu.lower())
                if match_pret:
                    try:
                        pret_curat = float(match_pret.group(1).replace(",", "."))
                        currency = "EUR" if any(c in titlu.lower() for c in ["€", "eur", "euro"]) else "RON"
                    except:
                        pass

            # Validare titlu
            if not titlu or len(titlu) < 5:
                self.stdout.write(self.style.WARNING(f"   Skip: Titlu invalid pentru: {url[:50]}"))
                page.close()
                return False

            # --- FALLBACK descriere din DOM ---
            if descriere == "N/A":
                try:
                    descriere = page.locator('[data-testid="ad-description"]').inner_text(timeout=3000)
                except:
                    try:
                        descriere = page.evaluate("() => document.body.innerText").strip()[:1500]
                    except:
                        pass

            # Extragere locație din DOM (LD+JSON nu o conține mereu curată în format de cartier)
            try:
                locatie_el = page.locator("a[href*='#map'], [data-cy='ad-location-popover'] p, [data-testid='map-anchor'] p").first
                if locatie_el.count() > 0:
                    locatie = locatie_el.inner_text().strip()
            except:
                pass

            # --- ALGORITM DETECTIE ---
            text_total_analiza = f"{titlu} {descriere} {specs_brute}".lower()

            camere_detectate = None
            if "garsonier" in text_total_analiza or "1 camer" in text_total_analiza:
                camere_detectate = 1
            elif "2 camer" in text_total_analiza:
                camere_detectate = 2
            elif "3 camer" in text_total_analiza:
                camere_detectate = 3
            elif "4 camer" in text_total_analiza:
                camere_detectate = 4

            etaj_detectat = None
            if "parter" in text_total_analiza:
                etaj_detectat = "P"
            else:
                match_etaj = re.search(r'etaj(?:ul)?\s*(\d+)', text_total_analiza)
                if match_etaj:
                    etaj_detectat = match_etaj.group(1)

            suprafata_detectata = None
            match_suprafata = re.search(r'(\d+)\s*(?:mp|m\s*p[aă]trat)', text_total_analiza)
            if match_suprafata:
                try:
                    suprafata_detectata = float(match_suprafata.group(1))
                except:
                    pass

            def detecteaza_dotare(cuvinte_cheie):
                return True if any(c in text_total_analiza for c in cuvinte_cheie) else None

            # --- SALVARE IN DB CU MAPARE IMAGINI ---
            with transaction.atomic():
                Listing.objects.create(
                    title=titlu[:255],
                    description=descriere if descriere else "",
                    price=pret_curat,
                    currency="EUR" if "eur" in str(currency).lower() or "€" in str(currency) else "RON",
                    city="Bucuresti",
                    neighborhood=locatie.replace("Bucuresti,", "").replace("București,", "").strip(),
                    source_url=url,
                    source_website="OLX.ro",
                    processing_status='PROCESSED',

                    rooms=camere_detectate,
                    floor=etaj_detectat,
                    useful_surface=suprafata_detectata,
                    partitioning="decomandat" if "decomandat" in text_total_analiza else "semidecomandat",
                    furnishing_state="mobilat" if detecteaza_dotare(["mobilat", "utilat"]) else "nemobilat",

                    has_fridge=detecteaza_dotare(["frigider", "combina"]),
                    has_washing_machine=detecteaza_dotare(["masina de spalat", "masina spalat"]),
                    has_ac=detecteaza_dotare(["aer conditionat", " ac ", "climatizare"]),
                    has_elevator=detecteaza_dotare(["lift", "elevator"]),
                    has_parking=detecteaza_dotare(["parcare", "loc parcare", "garaj"]),

                    # INJECTĂM DESIGNUL DE DATE METADATA (pentru a fi citit în pagina de căutare/filtrare)
                    raw_data={
                        "site_title": titlu,
                        "site_price": f"{pret_curat} {currency}" if pret_curat else "N/A",
                        "site_location": locatie,
                        "site_description": descriere,
                        "site_images": list(set(imagini_brute)), # Salvează lista unică de URL-uri ale pozelor
                        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                )

            self.stdout.write(self.style.SUCCESS(f"   ✅ Salvat cu Imagini: {titlu[:50]}"))
            page.close()
            return True

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Eroare pe pagina {url[:40]}: {e}"))
            page.close()
            return False