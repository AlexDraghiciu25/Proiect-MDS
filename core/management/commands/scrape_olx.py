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
# Importăm MapsAgent pentru a genera coordonate GPS ca fallback automat
from core.services import MapsAgent 

class Command(BaseCommand):
    help = 'Scraper ultra-robust pentru OLX.ro cu extragere directă din JSON State, Imagini și Geocoding avansat'

    def handle(self, *args, **options):
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        self.stdout.write(self.style.WARNING(" Parser OLX.ro: Inițiere proces de scraping..."))

        # ====================================================
        # 🔥 INTERCEPTARE URL MANUAL (DASHBOARD RUN-GUARD)
        # ====================================================
        url_manual = options.get('url')

        with Stealth().use_sync(sync_playwright()) as p:
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

            # Dacă a fost pasat un URL din interfață, îl procesăm doar pe acesta și închidem instant
            if url_manual:
                self.stdout.write(self.style.WARNING(f" 🎯 [RentGuru Manual] Se procesează EXCLUSIV URL-ul cerut: {url_manual[:50]}..."))
                self.proceseaza_anunt_olx(context, url_manual)
                browser.close()
                self.stdout.write(" Gata scanarea rapidă pentru URL-ul introdus!")
                return  # 🛑 Oprim execuția aici ca să nu treacă la lista generală de 40 de anunțuri

            # ====================================================
            # RULARE ÎN FUNDAL (BATCH SCRAPING DE 40 DE ANUNȚURI)
            # ====================================================
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

                    img_data = ld_data.get("image", [])
                    if isinstance(img_data, list):
                        imagini_brute = img_data
                    elif isinstance(img_data, str):
                        imagini_brute = [img_data]

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
                    descriere = ld_data.get("description", "N/A")

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"   LD+JSON parse error: {e}"))

            if not titlu:
                try:
                    raw_title = page.title()
                    titlu = raw_title.split(" - OLX.ro")[0].strip()
                except:
                    titlu = None

            if not pret_curat and titlu:
                match_pret = re.search(r'(\d+[\.,]?\d*)\s*(?:€|eur|euro|lei)', titlu.lower())
                if match_pret:
                    try:
                        pret_curat = float(match_pret.group(1).replace(",", "."))
                        currency = "EUR" if any(c in titlu.lower() for c in ["€", "eur", "euro"]) else "RON"
                    except:
                        pass

            if not titlu or len(titlu) < 5:
                self.stdout.write(self.style.WARNING(f"   Skip: Titlu invalid pentru: {url[:50]}"))
                page.close()
                return False

            if descriere == "N/A":
                try:
                    descriere = page.locator('[data-testid="ad-description"]').inner_text(timeout=3000)
                except:
                    try:
                        descriere = page.evaluate("() => document.body.innerText").strip()[:1500]
                    except:
                        pass

            try:
                locatie_el = page.locator("a[href*='#map'], [data-cy='ad-location-popover'] p, [data-testid='map-anchor'] p").first
                if locatie_el.count() > 0:
                    locatie = locatie_el.inner_text().strip()
            except:
                pass

            # ====================================================
            # EXTRACTOR INTELIGENT DE CARTIER DIN TITLU ȘI DESCRIERE
            # ====================================================
            text_pentru_locatie = f"{titlu or ''} {descriere or ''}".lower()
            
            cartiere_bucuresti = {
                "Militari": [
                    "militari", "gorjului", "lujerului", "lujerul", "pacii", "păcii", "apusului", "uverturii", 
                    "chiajna", "avangarde", "virtutii", "virtuții", "preciziei", "politehnica", "bvd timisoara", 
                    "bulevardul timișoara", "veteranilor", "moinești", "moinesti", "militari residence", "apusului"
                ],
                "Drumul Taberei": [
                    "drumul taberei", "favorit", "orizont", "moghioros", "moghioroș", "chilia veche", "romancierilor", 
                    "valea ialomitei", "valea ialomiței", "plaza", "tudor arghezi", "brancusi", "brâncuși", "frații buzești",
                    "trivium", "valea argesului", "valea argeșului", "compozitorilor", "haiducului", "bucla", "razoare", "răzoare"
                ],
                "Ghencea": [
                    "ghencea", "prelungirea ghencea", "stadion ghencea", "antelia", "latin", "cartierul latin", "cooperativei"
                ],
                "Titan": [
                    "titan", "potcoava", "costin georgian", "billa titan", "auchan titan", "minis", "miniș", 
                    "parcul titan", "galeriile titan", "liviu rebreanu", "postavarului", "postăvarului"
                ],
                "Pallady / Theodor Pallady": [
                    "theodor pallady", "pallady", "nicolae teclu", "1 decembrie", "1 decembrie 1918", "auchan pallady", 
                    "ikea pallady", "astralis", "hils", "hils pallady"
                ],
                "Dristor": [
                    "dristor", "dristor 1", "dristor 2", "camil ressu", "ramnicu sarat", "râmnicu sărat", "fizicienilor", "baba novac"
                ],
                "Vitan": [
                    "vitan", "mall vitan", "baleanu", "băleanu", "real vitan", "mihai bravu vitan", "cazul vitan", 
                    "energeticienilor", "foz", "bărătiei", "olimpia"
                ],
                "Văcărești / Asmita": [
                    "vacaresti", "văcărești", "asmita", "asmita gardens", "delta vacaresti", "pridvorului"
                ],
                "Tineretului": [
                    "tineretului", "timpuri noi", "sincai", "șincai", "palatul copiiilor", "parcul tineretului", "piscului"
                ],
                "Berceni": [
                    "berceni", "aparatorii patriei", "apărătorii patriei", "piata sudului", "piața sudului", "brancoveanu", 
                    "brâncoveanu", "oltenitei", "olteniței", "nitu vasile", "nițu vasile", "secuilor", "huedin", "giurgiului",
                    "luică", "luica", "reșița", "resita", "cultural", "piața cultural"
                ],
                "Metalurgiei": [
                    "metalurgiei", "bulevardul metalurgiei", "grand arena", "turnu magurele", "turnu măgurele", 
                    "viva residence", "solar", "solaris"
                ],
                "Pantelimon": [
                    "pantelimon", "delfinului", "socului", "mega mall", "baicului", "spitalul pantelimon", "morarilor", "vergului"
                ],
                "Colentina": [
                    "colentina", "bucur obor", "obor", "doamna ghica", "fundeni", "mai0", "mai 10", "rose garden", "andronache"
                ],
                "Crângași": [
                    "crangasi", "crângași", "constructorilor", "virtutii", "virtuții", "piata crangasi", "piața crângași", "pod grant"
                ],
                "Giulești": [
                    "giulesti", "giulești", "constructorilor", "prunaru", "cimitirul giulesti"
                ],
                "Rahova": [
                    "rahova", "alexandriei", "margeanului", "mărgeanului", "sebastian", "mărgeanului", "piata rahova", 
                    "piața rahova", "vulcan", "vulcan value centre", "antena 1", "mărgeanului"
                ],
                "Ferentari": [
                    "ferentari", "salaj", "sălaj", "toporași", "toporasi", "iasomie", "prelungirea ferentari"
                ],
                "Aviatorilor / Herăstrău": [
                    "aviatorilor", "charles de gaulle", "herastrau", "herăstrău", "nordului", "șoseaua nordului", "soseaua nordului"
                ],
                "Băneasa": [
                    "baneasa", "băneasa", "aeroport baneasa", "baneasa shopping city", "jandarmeriei", "sisesti", "șișești", 
                    "vatra noua", "vatra nouă", "feeria", "pădurea băneasa", "padurea baneasa"
                ],
                "Aviației": [
                    "aviatiei", "aviației", "promenada", "promenada mall", "aurel vlaicu", "sirius", "elena vacarescu"
                ],
                "Floreasca": [
                    "floreasca", "barbu vacarescu", "barbu văcărescu", "tariverde", "ceaikovski", "radutulian"
                ],
                "Dorobanți": [
                    "dorobanti", "dorobanți", "perla", "beller", "radu beller", "piața dorobanți", "piata dorobanti", "capitale"
                ],
                "Cotroceni": [
                    "cotroceni", "academia militara", "academia militară", "carol davila", "grădina botanică", 
                    "gradina botanica", "dr herescu", "palatul cotroceni"
                ],
                "Grozăvești / Regie": [
                    "grozavesti", "grozăvești", "regie", "economu cezarescu", "caramfil", "petre popovat", "bvd regiei", "metrou grozavesti"
                ],
                "Unirii": [
                    "unirii", "piata unirii", "piața unirii", "alba iulia", "decebal", "coposu", "corneliu coposu", 
                    "zepter", "bulevardul unirii", "tribunalul bucuresti", "octavian goga", "sitari", "sfanta vineri", "sfânta vineri"
                ],
                "Universitate / Romană": [
                    "universitate", "piata romana", "piața romană", "romana", "română", "magheru", "calea victoriei", 
                    "sala palatului", "amzei", "piața amzei", "intercontinental", "marriott", "izvor", "parcul izvor", 
                    "cișmigiu", "cismigiu", "batistei", "batiștei", "armenească", "armeneasca", "rossetti", "rosetti"
                ],
                "Piața Victoriei": [
                    "piata victoriei", "piața victoriei", "guvern", "buzești", "buzesti", "ion mihalache", "titulescu", 
                    "nicolae titulescu", "banu manta"
                ],
                "Grivița / Gara de Nord": [
                    "grivita", "grivița", "gara de nord", "dinicu golescu", "witting", "basarab", "pod basarab", "calea griviței"
                ],
                "Tei": [
                    "lacul tei", "tei", "ghica tei", "facultatea de constructii", "parcul tei", "maica domnului"
                ],
                "Mosilor": [
                    "mosilor", "moșilor", "calea mosilor", "calea moșilor", "eminescu", "mihai eminescu", "dacia", "bulevardul dacia"
                ],
                "Ștefan cel Mare": [
                    "stefan cel mare", "ștefan cel mare", "circului", "parcul circului", "spitalul floreasca", "dinamo", "stadion dinamo"
                ],
                "Chitila": [
                    "chitila", "pod chitila", "șoseaua chitilei", "soseaua chitilei", "banatului"
                ],
                "Bucureștii Noi / Damaroaia": [
                    "bucurestii noi", "bucureștii noi", "damaroaia", "dămăroaia", "jiului", "parcul bazilescu", "bazilescu", 
                    "laminorului", "străulești", "straulesti", "chibrit", "piața chibrit"
                ],
                "Vila Olarilor / Foișor": [
                    "foisorul de foc", "foișorul de foc", "traian", "strada traian", "pache protopopescu", "matasari", "mătăsari"
                ],
                "13 Septembrie": [
                    "13 septembrie", "septembrie 13", "marriott", "catedrala mantuirii", "progresului", "trafic greu", "panduri"
                ]
            }

            cartier_detectat = None
            for cartier, cuvinte_cheie in cartiere_bucuresti.items():
                if any(re.search(r'\b' + re.escape(cuvant) + r'\b', text_pentru_locatie) for cuvant in cuvinte_cheie):
                    cartier_detectat = cartier
                    break

            if cartier_detectat:
                cartier_curat = cartier_detectat
            else:
                cartier_curat = locatie.replace("Bucuresti,", "").replace("București,", "").replace("Ilfov,", "").strip()
            # ====================================================

            # ====================================================
            # [CONECTARE REȚEA] GENRARE GPS PRIN MAPSAGENT PE CARTIERUL DETECTAT
            # ====================================================
            lat_extras = None
            lng_extras = None
            try:
                maps_agent = MapsAgent()
                query_gps = f"{cartier_curat}, Bucuresti"
                lat_extras, lng_extras = maps_agent.get_coordinates(query_gps)
            except Exception as e_gps:
                self.stdout.write(self.style.ERROR(f"   Eroare la generarea coordonatelor MapsAgent: {e_gps}"))

            # --- ALGORITM ALINIAT DE DETECTIE ȘI REGEX ---
            text_total_analiza = f"{titlu} {descriere} {specs_brute}".lower()

            camere_detectate = None
            if "garsonier" in text_total_analiza or "1 camer" in text_total_analiza:
                camere_detectate = 1
            elif "2 camer" in text_total_analiza or "doua camer" in text_total_analiza:
                camere_detectate = 2
            elif "3 camer" in text_total_analiza or "trei camer" in text_total_analiza:
                camere_detectate = 3
            elif "4 camer" in text_total_analiza or "patru camer" in text_total_analiza:
                camere_detectate = 4

            etaj_detectat = None
            if "etaj p" in text_total_analiza or "parter" in text_total_analiza:
                etaj_detectat = "P"
            else:
                match_etaj = re.search(r'etaj(?:ul)?\s*(\d+|p|m|mansarda)', text_total_analiza)
                if match_etaj:
                    etaj_detectat = match_etaj.group(1).upper()

            suprafata_detectata = None
            match_suprafata = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:mp|m\s*p[aă]trat|suprafata\s*utila)', text_total_analiza)
            if match_suprafata:
                try:
                    suprafata_detectata = float(match_suprafata.group(1).replace(',', '.'))
                except:
                    pass

            def detecteaza_dotare(cuvinte_cheie):
                return True if any(c in text_total_analiza for c in cuvinte_cheie) else None

            # ====================================================
            # [LOGICA TA] CURĂȚARE ȘI NORMALIZARE VALUTĂ ÎN MEMORIE
            # ====================================================
            moneda_finala = "RON"
            if "eur" in str(currency).lower() or "€" in str(currency) or (pret_curat and pret_curat < 1500):
                moneda_finala = "EUR"

            # ========================================================
            # BLOCUL DE LOGARE ALINIAT CU STORIA
            # ========================================================
            self.stdout.write("\n" + "="*60)
            self.stdout.write(f"🔗 OLX URL: {url[:50]}...")
            self.stdout.write(f"📌 TITLU: {titlu[:40]}...")
            self.stdout.write(f"💰 PRET CALCULAT: {pret_curat} {moneda_finala}")
            self.stdout.write(f"🌍 GPS (MapsAgent Hibrid): Lat {lat_extras} | Lng {lng_extras}")
            self.stdout.write(f"📍 CARTIER DETECTAT: {cartier_curat}")
            self.stdout.write("="*60 + "\n")

            # --- SALVARE ATOMICĂ IN DB ---
            with transaction.atomic():
                Listing.objects.create(
                    title=titlu[:255],
                    description=descriere if descriere else "",
                    price=pret_curat,
                    currency=moneda_finala,
                    city="Bucuresti",
                    neighborhood=cartier_curat,
                    source_url=url,
                    source_website="OLX.ro",
                    latitude=lat_extras,
                    longitude=lng_extras,
                    processing_status='PROCESSED',

                    rooms=camere_detectate,
                    floor=etaj_detectat,
                    useful_surface=suprafata_detectata,
                    partitioning="decomandat" if "decomandat" in text_total_analiza else "semidecomandat",
                    furnishing_state="mobilat" if detecteaza_dotare(["mobilat", "utilat"]) else "nemobilat",

                    has_fridge=detecteaza_dotare(["frigider", "combina frigorifica", "utilata"]),
                    has_washing_machine=detecteaza_dotare(["masina de spalat", "masina spalat rufe"]),
                    has_dishwasher=detecteaza_dotare(["masina de spalat vase", "dishwasher"]),
                    has_tv=detecteaza_dotare(["televizor", "tv", "smart tv"]),
                    has_ac=detecteaza_dotare(["aer conditionat", " ac ", "climatizare"]),
                    has_elevator=detecteaza_dotare(["lift", "elevator"]),
                    has_parking=detecteaza_dotare(["parcare", "loc parcare", "garaj", "loc de parcare"]),
                    is_pet_friendly=detecteaza_dotare(["accepta animale", "pet friendly"]),

                    raw_data={
                        "site_title": titlu,
                        "site_price": f"{pret_curat} {currency}" if pret_curat else "N/A",
                        "site_location": locatie,
                        "site_description": descriere,
                        "site_images": list(set(imagini_brute)),
                        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                )

            self.stdout.write(self.style.SUCCESS(f"   ✅ Aspirat și populat local de pe OLX: {titlu[:30]}..."))
            page.close()
            return True

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Eroare pe pagina {url[:40]}: {e}"))
            page.close()
            return False