import os
import time
import random
import re
from django.core.management.base import BaseCommand
from core.models import Listing
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from django.db import transaction

class Command(BaseCommand):
    help = 'Scraper robust pentru Storia.ro (Izolare pe Tab-uri, Heuristic Extraction, Lazy Loading, Auto-Populare)'

    def handle(self, *args, **options):
        # Permitem operatiunile asincrone in Django
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        self.stdout.write(self.style.WARNING(" Parser Storia.ro: Inițiere proces de scraping..."))

        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(
                headless=True, # Poti pune True cand il muti pe server
                args=["--disable-blink-features=AutomationControlled"]
            ) 
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            # Deschidem un tab principal DOAR pentru a extrage lista de link-uri
            main_page = context.new_page()
            url_cautare = "https://www.storia.ro/ro/rezultate/inchiriere/apartament/bucuresti"
            
            try:
                self.stdout.write(f" Navigam spre: {url_cautare}")
                main_page.goto(url_cautare, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)
                
                try:
                    main_page.locator("button:has-text('Accept'), button:has-text('De acord'), #onetrust-accept-btn-handler").first.click(timeout=5000)
                    self.stdout.write(" Am scapat de cookie-uri.")
                except: 
                    pass

                self.stdout.write(" Generam scroll pentru a incarca anunturile...")
                for _ in range(4):
                    main_page.mouse.wheel(0, 1000)
                    time.sleep(1.5)

                toate_linkurile = main_page.locator("a").all()
                linkuri_valide = set()

                for link in toate_linkurile:
                    href = link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith('http') else f"https://www.storia.ro{href}"
                        if "/ro/oferta/" in full_url:
                            if "page=" not in full_url and "#" not in full_url:
                                linkuri_valide.add(full_url)

                if len(linkuri_valide) == 0:
                    self.stdout.write(self.style.ERROR(" Am gasit 0 anunturi."))
                    return

                self.stdout.write(self.style.SUCCESS(f"Am gasit {len(linkuri_valide)} anunturi pe pagina."))

                # Am terminat cu pagina de cautare, o inchidem pentru a elibera memoria
                main_page.close()

                count = 0
                for url in list(linkuri_valide):
                    if count >= 40: break # Seteaza numarul dorit de anunturi per rulare
                    
                    # ATENTIE: Trimitem 'context', nu 'page', pentru ca functia sa isi creeze propriul tab
                    self.proceseaza_anunt(context, url)
                    
                    count += 1
                    time.sleep(random.uniform(3, 6))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f" Eroare in misiune: {e}"))
            finally:
                browser.close()
                self.stdout.write(" Gata scriptul de Scraping!")

    def proceseaza_anunt(self, context, url):
        # 1. Verificam daca exista deja
        if Listing.objects.filter(source_url=url).exists():
            self.stdout.write(self.style.WARNING(f"Skip: Exista in DB: {url[:40]}..."))
            return

        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # --- VALIDARE TITLU ---
            h1_element = page.locator("h1").first
            if h1_element.count() == 0:
                self.stdout.write(self.style.WARNING(f"   Skip: Pagină invalidă/ștearsă (fără H1): {url[:40]}..."))
                page.close()
                return

            titlu = h1_element.inner_text().strip()
            
            if not titlu or len(titlu) < 5 or titlu.lower() == "fara titlu":
                self.stdout.write(self.style.WARNING(f"   Skip: Titlu invalid: '{titlu}' la {url[:40]}..."))
                page.close()
                return
            
            # --- PASUL 1: SCROLL LENT ---
            page.evaluate("""
                var interval = setInterval(function() { window.scrollBy(0, 400); }, 300);
                setTimeout(function() { clearInterval(interval); }, 2500);
            """)
            time.sleep(3) # Așteptăm scroll-ul
            
            titlu = page.locator("h1").first.inner_text().strip() if page.locator("h1").count() > 0 else "Fara titlu"
            
            pret = "N/A"
            pret_el = page.locator("strong:has-text('EUR'), strong:has-text('LEI'), [data-cy='adPageHeaderPrice']").first
            if pret_el.count() > 0:
                pret = pret_el.inner_text().strip()

            locatie = page.evaluate("""function() {
                var links = document.querySelectorAll('a');
                for(var i=0; i<links.length; i++) {
                    if(links[i].innerText.includes('Bucuresti') || links[i].innerText.includes('Sector')) {
                        return links[i].innerText.trim();
                    }
                }
                return 'N/A';
            }""")

            # --- PASUL 2: DESCHIDEREA ACORDEOANELOR ---
            page.evaluate("""function() {
                var butoane = document.querySelectorAll('button, div[role="button"]');
                for(var i=0; i<butoane.length; i++) {
                    var text = butoane[i].innerText ? butoane[i].innerText.toLowerCase() : '';
                    if(text.includes('facilități') || text.includes('clădire') || text.includes('mai mult')) {
                        try { butoane[i].click(); } catch(e) {}
                    }
                }
            }""")
            
            time.sleep(2)

            # --- PASUL 3: CITIREA DATELOR "LA SÂNGE" ---
            specs_brute = page.evaluate("""function() {
                var container = document.querySelector('[data-testid="ad-details"]') || 
                                document.querySelector('[data-cy="adPageAdFeatures"]');
                
                if(!container) {
                    var divs = document.querySelectorAll('div');
                    for(var i=0; i<divs.length; i++) {
                        if(divs[i].innerText === 'Suprafață utilă:') {
                            container = divs[i].parentElement.parentElement.parentElement.parentElement;
                            break;
                        }
                    }
                }
                
                if(container) {
                    var linii = container.innerText.split('\\n'); 
                    var texte_valide = [];
                    
                    for(var i=0; i<linii.length; i++) {
                        var linie = linii[i].trim();
                        if(linie.length > 1 && linie.length < 80) {
                            texte_valide.push(linie);
                        }
                    }
                    
                    var elemente_unice = [];
                    for(var j=0; j<texte_valide.length; j++) {
                        if(elemente_unice.indexOf(texte_valide[j]) === -1) {
                            elemente_unice.push(texte_valide[j]);
                        }
                    }
                    
                    return elemente_unice.join(' | ');
                }
                
                return '';
            }""")

            descriere = "N/A"
            desc_el = page.locator("[data-cy='adPageAdDescription']").first
            if desc_el.count() > 0:
                descriere = desc_el.inner_text().strip()

            imagini_brute = []
            img_elements = page.locator("img[src*='storiacdn.com'], img[src*='olxcdn.com']").all()
            for img in img_elements:
                src = img.get_attribute("src")
                if src and 'image;s=' in src and 's=314' not in src and 's=200' not in src:
                    if not any(bad in src.lower() for bad in ['logo', 'banner', 'avatar', 'admanager']):
                        imagini_brute.append(src)
                elif src and 'image;s=' not in src:
                    imagini_brute.append(src)

            # ====================================================
            # --- ALGORITM DE FILTRARE ȘI AUTO-POPULARE ---
            # ====================================================
            text_total_analiza = f"{titlu} {descriere} {specs_brute}".lower()

            # 1. Număr de camere
            camere_detectate = None
            if "garsonier" in text_total_analiza or "1 camer" in text_total_analiza:
                camere_detectate = 1
            elif "2 camer" in text_total_analiza or "doua camer" in text_total_analiza:
                camere_detectate = 2
            elif "3 camer" in text_total_analiza or "trei camer" in text_total_analiza:
                camere_detectate = 3
            elif "4 camer" in text_total_analiza or "patru camer" in text_total_analiza:
                camere_detectate = 4

            # 2. Etaj și Regim de înălțime (Total Etaje)
            etaj_detectat = None
            if "etaj p" in text_total_analiza or "parter" in text_total_analiza or "etaj parter" in text_total_analiza:
                etaj_detectat = "P"
            else:
                match_etaj = re.search(r'etaj(?:ul)?\s*(\d+|p|m|mansarda)', text_total_analiza)
                if match_etaj:
                    etaj_detectat = match_etaj.group(1).upper()

            total_etaje_detectat = None
            match_total_etaje = re.search(r'(?:p|etaj\s*\d+)\+(\d+)', text_total_analiza)
            if match_total_etaje:
                try: total_etaje_detectat = int(match_total_etaje.group(1))
                except: pass
            else:
                # Căutăm structuri de genul "bloc cu 4 etaje" sau "imobil p+4"
                match_regim = re.search(r'(?:regim\s*de\s*inaltime\s*|bloc\s*cu\s*|imobil\s*)(?:p\+)?(\d+)\s*etaj', text_total_analiza)
                if match_regim:
                    try: total_etaje_detectat = int(match_regim.group(1))
                    except: pass

            # 3. Suprafața Utilă
            suprafata_detectata = None
            match_suprafata = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:mp|m\s*patrati|metri\s*patrati|suprafata\s*utila)', text_total_analiza)
            if match_suprafata:
                try:
                    val_suprafata = match_suprafata.group(1).replace(',', '.')
                    suprafata_detectata = float(val_suprafata)
                except: pass

            # 4. Opțiuni predefinite conforme cu CHOICES din model
            compartimentare = None
            if "semidecomandat" in text_total_analiza: compartimentare = "semidecomandat"
            elif "decomandat" in text_total_analiza: compartimentare = "decomandat"
            elif "nedecomandat" in text_total_analiza: compartimentare = "nedecomandat"
            elif "circular" in text_total_analiza: compartimentare = "circular"

            stare_mobilier = None
            if "partial mobilat" in text_total_analiza: stare_mobilier = "partial"
            elif "nemobilat" in text_total_analiza: stare_mobilier = "nemobilat"
            elif "mobilat" in text_total_analiza or "utilat" in text_total_analiza: stare_mobilier = "mobilat"

            tip_incalzire = None
            if "centrala proprie" in text_total_analiza or "centrala termica" in text_total_analiza: tip_incalzire = "centrala_proprie"
            elif "termoficare" in text_total_analiza or "radet" in text_total_analiza: tip_incalzire = "termoficare"
            elif "centrala de imobil" in text_total_analiza or "centrala imobil" in text_total_analiza: tip_incalzire = "centrala_imobil"

            comfort = None
            if "lux" in text_total_analiza: comfort = "lux"
            elif "confort 1" in text_total_analiza or "conf 1" in text_total_analiza: comfort = "1"
            elif "confort 2" in text_total_analiza or "conf 2" in text_total_analiza: comfort = "2"

            # 5. Funcție ajutătoare pentru maparea stărilor booleene (True/None)
            def detecteaza_dotare(cuvinte_cheie):
                if any(cuvant in text_total_analiza for cuvant in cuvinte_cheie):
                    return True
                return None

            # --- CURĂȚARE PREȚ INAINTE DE SALVARE ---
            pret_curat = None
            if pret and pret != "N/A":
                cifre_pret = ''.join(c for c in pret if c.isdigit() or c == '.' or c == ',')
                if ',' in cifre_pret and '.' in cifre_pret:
                    cifre_pret = cifre_pret.replace('.', '').replace(',', '.')
                elif ',' in cifre_pret:
                    cifre_pret = cifre_pret.replace(',', '.')
                try: pret_curat = float(cifre_pret)
                except ValueError: pret_curat = None

            # --- SALVAREA CURATĂ ȘI POPULATĂ ÎN MODEL ---
            with transaction.atomic():
                listing = Listing.objects.create(
                    title=titlu[:255] if titlu and titlu != "Fara titlu" else "Anunț Storia",
                    description=descriere if descriere != "N/A" else "",
                    price=pret_curat,
                    currency="EUR" if "eur" in pret.lower() else "RON",
                    city="Bucuresti",
                    neighborhood=locatie.replace("Bucuresti,", "").strip() if locatie != "N/A" else "",
                    source_url=url,
                    source_website="Storia.ro",
                    processing_status='PROCESSED',
                    
                    # --- DATE GENERALE ȘI CARACTERISTICI ---
                    rooms=camere_detectate,
                    floor=etaj_detectat,
                    total_floors=total_etaje_detectat,
                    useful_surface=suprafata_detectata,
                    partitioning=compartimentare,
                    comfort_level=comfort,
                    furnishing_state=stare_mobilier,
                    heating_type=tip_incalzire,

                    # --- ELECTROCASNICE DETECTATE ---
                    has_fridge=detecteaza_dotare(["frigider", "combina frigorifica", "utilata", "utilat"]),
                    has_washing_machine=detecteaza_dotare(["masina de spalat", "masina spalat rufe", "utilata"]),
                    has_dishwasher=detecteaza_dotare(["masina de spalat vase", "masina spalat vase", "dishwasher"]),
                    has_tv=detecteaza_dotare(["televizor", "tv", "smart tv"]),
                    has_ac=detecteaza_dotare(["aer conditionat", "ac", "climatizare", "vortice"]),
                    has_oven=detecteaza_dotare(["cuptor", "aragaz", "plita"]),
                    has_microwave=detecteaza_dotare(["microunde", "cuptor microunde"]),

                    # --- FACILITĂȚI IMOBIL & EXTERIOR ---
                    has_elevator=detecteaza_dotare(["lift", "elevator"]),
                    has_intercom=detecteaza_dotare(["interfon", "videointerfon"]),
                    has_parking=detecteaza_dotare(["parcare", "loc parcare", "garaj", "loc de parcare"]),
                    is_pet_friendly=detecteaza_dotare(["accepta animale", "pet friendly", "animale de companie"]),
                    near_public_transit=detecteaza_dotare(["metrou", "stb", "autobuz", "tramvai", "statie"]),

                    raw_data={
                        "site_title": titlu,
                        "site_price": pret,
                        "site_location": locatie,
                        "site_specs": specs_brute,
                        "site_description": descriere,
                        "site_images": list(set(imagini_brute)),
                        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                )
            
            self.stdout.write(self.style.SUCCESS(f"   Aspirat și populat local: {titlu[:30]}..."))
            return listing

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Eroare pe pagina anuntului: {e}"))
        
        finally:
            page.close()