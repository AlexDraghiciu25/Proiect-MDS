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
from core.services import MapsAgent 

class Command(BaseCommand):
    help = 'Scraper național agnostic de oraș pentru OLX.ro (JSON-first, Parallel Tabs, Flux Live România)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=40,
            help='Numărul maxim de anunțuri de procesat per rulare (default: 40)'
        )
        parser.add_argument(
            '--url', type=str, default=None,
            help='URL manual pasat direct din interfața RentGuru'
        )

    def handle(self, *args, **options):
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        limit = options.get('limit', 40)
        url_manual = options.get('url')

        self.stdout.write(self.style.WARNING(" 🚀 Parser OLX Național: Inițializare pipeline pentru fluxul live (Toată România)..."))

        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ]
            ) 
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )

            context.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,eot}", lambda route: route.abort())
            context.route("**/*google-analytics*", lambda route: route.abort())
            context.route("**/*doubleclick*", lambda route: route.abort())
            context.route("**/*facebook*", lambda route: route.abort())

            if url_manual:
                self.stdout.write(self.style.WARNING(f" 🎯 [Manual Run] Se procesează exclusiv link-ul cerut: {url_manual[:50]}..."))
                self.proceseaza_anunt_olx(context, url_manual)
                browser.close()
                return

            main_page = context.new_page()
            url_cautare = "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-inchiriat/"
            
            try:
                self.stdout.write(f" Navigăm spre catalogul rădăcină OLX România: {url_cautare}")
                main_page.goto(url_cautare, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                
                try:
                    main_page.locator("#onetrust-accept-btn-handler, button:has-text('Acceptă tot')").first.click(timeout=3000)
                except: 
                    pass

                self.stdout.write(" Executăm scroll asincron accelerat...")
                main_page.evaluate("""
                    var interval = setInterval(function() { window.scrollBy(0, 2000); }, 200);
                    setTimeout(function() { clearInterval(interval); }, 1500);
                """)
                time.sleep(2)

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
                        linkuri_valide.add(href.split('#')[0].split('?')[0])

                if not linkuri_valide:
                    self.stdout.write(self.style.ERROR(" Catalogul principal OLX a returnat 0 link-uri active."))
                    return

                self.stdout.write(self.style.SUCCESS(f" Identificate {len(linkuri_valide)} anunțuri recente în toată țara. Filtrare duplicate..."))
                main_page.close()

                linkuri_existente = set(Listing.objects.filter(source_url__in=linkuri_valide).values_list('source_url', flat=True))
                linkuri_noi = [url for url in linkuri_valide if url not in linkuri_existente][:limit]

                if not linkuri_noi:
                    self.stdout.write(self.style.SUCCESS(" Toate proprietățile de pe prima pagină există deja în baza de date."))
                    return

                self.stdout.write(f" Demarăm procesarea pe batch-uri paralele de câte 3 tab-uri (Limită: {len(linkuri_noi)})...")

                BATCH_SIZE = 3
                count = 0
                for i in range(0, len(linkuri_noi), BATCH_SIZE):
                    batch = linkuri_noi[i:i + BATCH_SIZE]
                    pages = []

                    for url in batch:
                        page = context.new_page()
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            pages.append((page, url))
                        except Exception:
                            page.close()

                    time.sleep(1)

                    for page, url in pages:
                        try:
                            if self._proceseaza_pagina_olx(page, url):
                                count += 1
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f" Eșec la parsarea tab-ului curent: {e}"))
                        finally:
                            page.close()

                    if i + BATCH_SIZE < len(linkuri_noi):
                        time.sleep(random.uniform(1.5, 3))

                self.stdout.write(self.style.SUCCESS(f"\n Pipeline național încheiat. Inserate direct {count} înregistrări."));

            except Exception as e:
                self.stdout.write(self.style.ERROR(f" Defect în handler-ul național principal OLX: {e}"))
            finally:
                browser.close()

    def proceseaza_anunt_olx(self, context, url):
        """Punct de legătură sincron pentru apeluri individuale asincrone din views."""
        if Listing.objects.filter(source_url=url).exists():
            listing = Listing.objects.filter(source_url=url).first()
            if listing and listing.processing_status == 'PENDING':
                try:
                    from django.core.management import call_command
                    call_command('normalize_listings', listing_id=listing.id)
                except:
                    pass
            return False
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            return self._proceseaza_pagina_olx(page, url)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f" Eroare la procesarea URL-ului manual: {e}"))
        finally:
            page.close()

    def _proceseaza_pagina_olx(self, page, url):
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

        window_state_raw = page.evaluate("""function() {
            return window.__PRERENDERED_STATE__ || window.__INITIAL_STATE__ || null;
        }""")

        titlu = None
        pret_curat = None
        currency = "EUR"
        descriere = ""
        imagini_brute = []
        
        oras_detectat = None
        cartier_sau_zona = None

        if ld_json_raw:
            try:
                ld_data = json.loads(ld_json_raw)
                titlu = ld_data.get("name", "").strip()
                descriere = ld_data.get("description", "")
                
                img_data = ld_data.get("image", [])
                imagini_brute = img_data if isinstance(img_data, list) else [img_data]

                offers = ld_data.get("offers", {})
                if isinstance(offers, list): offers = offers[0] if offers else {}
                pret_raw = offers.get("price") or offers.get("lowPrice")
                if pret_raw:
                    pret_curat = float(str(pret_raw).replace(",", "."))
                currency = offers.get("priceCurrency", "EUR")
            except:
                pass

        if nations_title := page.title():
            if not titlu: titlu = nations_title.split(" - OLX.ro")[0].strip()

        if not titlu or len(titlu) < 5:
            return False

        if window_state_raw:
            try:
                state_data = json.loads(window_state_raw) if isinstance(window_state_raw, str) else window_state_raw
                ad_props = state_data.get("ad", {}).get("ad", {}) or state_data.get("ad", {}) or state_data.get("adData", {})
                geo_node = ad_props.get("location", {}) or ad_props.get("localization", {})
                
                if geo_node:
                    oras_detectat = geo_node.get("cityName") or geo_node.get("city", {}).get("name")
                    cartier_sau_zona = geo_node.get("districtName") or geo_node.get("district", {}).get("name")
            except:
                pass

        if not oras_detectat:
            try:
                breadcrumbs = page.evaluate("""function() {
                    var items = document.querySelectorAll('li[data-testid="breadcrumb-item"] a, a[href*="/imobiliare/"]');
                    var texts = [];
                    items.forEach(function(el) {
                        var txt = el.innerText ? el.innerText.trim() : "";
                        if (txt.length > 2 && !txt.includes("Imobiliare") && !txt.includes("Apartamente") && !txt.includes("Inchirieri")) {
                            texts.push(txt);
                        }
                    });
                    return texts;
                }""")
                if breadcrumbs and len(breadcrumbs) >= 1:
                    oras_detectat = breadcrumbs[-1]
                    if len(breadcrumbs) >= 2:
                        cartier_sau_zona = breadcrumbs[-1]
                        oras_detectat = breadcrumbs[-2]
            except:
                pass

        if not oras_detectat:
            try:
                loc_text = page.locator('[data-testid="map-anchor"] p, [data-cy="ad-location-popover"] p, a[href="#map"]').first.inner_text().strip()
                if loc_text and "romania" not in loc_text.lower():
                    parti = [p.strip() for p in loc_text.split(',')]
                    if len(parti) >= 2:
                        oras_detectat = parti[0]
                        cartier_sau_zona = parti[1]
                    else:
                        oras_detectat = parti[0]
            except:
                pass

        oras_final = str(oras_detectat).strip() if oras_detectat else "Bucuresti"
        cartier_final = str(cartier_sau_zona).strip() if cartier_sau_zona else ""

        if "camera" in oras_final.lower() or "camere" in oras_final.lower():
            oras_final = oras_final.replace('–', '-').replace('—', '-')
            if '-' in oras_final:
                oras_final = oras_final.split('-')[-1].strip()

        if "camera" in cartier_final.lower() or "camere" in cartier_final.lower():
            cartier_final = cartier_final.replace('–', '-').replace('—', '-')
            if '-' in cartier_final:
                cartier_final = cartier_final.split('-')[-1].strip()

        if oras_final.lower() == cartier_final.lower():
            cartier_final = "Zona Generala"

        if not oras_final or "romania" in oras_final.lower() or "camera" in oras_final.lower(): 
            oras_final = "Bucuresti"
        if "judetul" in cartier_final.lower() or "județul" in cartier_final.lower(): 
            cartier_final = ""

        locatie_completa = f"{cartier_final + ', ' if (cartier_final and cartier_final != 'Zona Generala') else ''}{oras_final}"

        lat_extras = None
        lng_extras = None
        try:
            lat_extras, lng_extras = MapsAgent().get_coordinates(locatie_completa)
            
            if not lat_extras or not lng_extras:
                self.stdout.write(self.style.WARNING(f"   [Maps Retry] Reîncercăm geocoding doar pentru orașul curat: {oras_final}"))
                lat_extras, lng_extras = MapsAgent().get_coordinates(oras_final)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   [Maps API Error] Defect la geocoding pentru '{locatie_completa}': {e}"))

        # 🛠️ [TIMING FIX] Forțăm Playwright să aștepte randerizarea asincronă a containerului trimis de tine
        try:
            page.wait_for_selector('[data-testid="ad-parameters-container"], p.css-odhutu', timeout=4000)
        except:
            pass

        # 🛠️ [EXTRACTOR PARALEL DOM + JSON STATE] Colectare imună la schimbările de structură
        specs_brute = page.evaluate("""function() {
            var specs = [];
            
            // Strategia A: Extragere directă din starea de hidratare din fundal (100% imună la CSS)
            try {
                var state = window.__PRERENDERED_STATE__ || window.__INITIAL_STATE__;
                if (state) {
                    var adData = state.ad?.ad || state.ad || state.adData;
                    if (adData && adData.attributes) {
                        adData.attributes.forEach(function(attr) {
                            var label = attr.label || attr.key;
                            var val = attr.value?.label || attr.value?.name || attr.value;
                            if (label && val) {
                                var pair = label.trim() + ": " + String(val).trim();
                                if (specs.indexOf(pair) === -1) specs.push(pair);
                            }
                        });
                    }
                }
            } catch(e) {}
            
            // Strategia B: Scanare directă în containerul de test trimis de tine (ca siguranță)
            var modernContainer = document.querySelector('[data-testid="ad-parameters-container"]');
            if (modernContainer) {
                var paragraphs = modernContainer.querySelectorAll('p');
                paragraphs.forEach(function(p) {
                    var txt = p.innerText ? p.innerText.trim() : "";
                    if (txt) {
                        var flatTxt = txt.replace(/\\s*\\n\\s*/g, ': ').trim();
                        if (specs.indexOf(flatTxt) === -1) specs.push(flatTxt);
                    }
                });
            }
            
            // Strategia C: Fallback pe clasele specifice din div
            if (specs.length === 0) {
                var elements = document.querySelectorAll('.css-odhutu, [data-nx-name="P3"]');
                elements.forEach(function(el) {
                    var txt = el.innerText ? el.innerText.trim() : "";
                    if (txt) {
                        var flatTxt = txt.replace(/\\s*\\n\\s*/g, ': ').trim();
                        if (specs.indexOf(flatTxt) === -1) specs.push(flatTxt);
                    }
                });
            }
            
            return specs.join(' | ');
        }""")

        specs_curatate = specs_brute.lower().replace("m²", "mp")
        text_total = f"{titlu} {descriere} {specs_curatate}".lower()
        
        camere = 1 if "garsonier" in text_total or "1 camer" in text_total else (2 if "2 camer" in text_total or "doua camer" in text_total else (3 if "3 camer" in text_total else (4 if "4 camer" in text_total else None)))
        etaj = "P" if "parter" in text_total or "etaj p" in text_total else (re.search(r'etaj(?:ul)?\s*(\d+)', text_total).group(1) if re.search(r'etaj(?:ul)?\s*(\d+)', text_total) else None)
        
        suprafata = None
        match_suprafata = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:mp|m\s*p[aă]trat|metri\s*p[aă]traț)', text_total)
        if match_suprafata:
            try:
                suprafata = float(match_suprafata.group(1).replace(',', '.'))
            except:
                suprafata = None
        
        if not suprafata:
            suprafata = 40.0 if camere == 1 else (55.0 if camere == 2 else (75.0 if camere == 3 else 50.0))

        an_constructie = None
        match_an = re.search(r'(\d{4})\s*[\–\-]\s*(\d{4})|(?:\ban\b|\bbloc\b|\bconstructie\b|\banul\b|dupa|după).*?(\d{4})', text_total)
        if match_an:
            an_constructie = int(match_an.group(1) or match_an.group(3))

        def check_feat(keywords): return True if any(k in text_total for k in keywords) else None

        moneda_finala = "EUR"  
        currency_raw = str(currency).upper()

        if "RON" in currency_raw or "LEI" in currency_raw:
            moneda_finala = "RON"
        elif "EUR" in currency_raw or "€" in currency_raw:
            moneda_finala = "EUR"

        try:
            pret_el = page.locator('[data-testid="ad-price-container"] h3').first
            if pret_el.count() > 0:
                txt_pret = pret_el.inner_text().lower()
                if "lei" in txt_pret or "ron" in txt_pret:
                    moneda_finala = "RON"
                elif "€" in txt_pret or "eur" in txt_pret:
                    moneda_finala = "EUR"
        except:
            pass

        if pret_curat:
            if moneda_finala == "RON" and pret_curat < 900:
                if "lei" not in text_total and "ron" not in text_total:
                    moneda_finala = "EUR"
            elif moneda_finala == "EUR" and pret_curat > 1000:
                if "lei" in text_total or "ron" in text_total:
                    if "euro" not in text_total and "eur" not in text_total and "€" not in text_total:
                        moneda_finala = "RON"

        pret_afisaj_curat = "N/A"
        if pret_curat:
            pret_afisaj_curat = f"{int(pret_curat) if pret_curat.is_integer() else pret_curat} {moneda_finala}"

        self.stdout.write("\n" + "="*60)
        self.stdout.write(f"🔗 OLX NAȚIONAL URL: {url[:45]}...")
        self.stdout.write(f"📌 TITLU: {titlu[:40]}...")
        self.stdout.write(f"💰 PREȚ EVALUAT: {pret_curat} {moneda_finala}")
        self.stdout.write(f"🌍 GPS MAPS REPARAT: Lat {lat_extras} | Lng {lng_extras}")
        self.stdout.write(f"📍 LOCAȚIE SALVATĂ ÎN DB: {oras_final} (Zona: {cartier_final or 'Generală'})")
        self.stdout.write("="*60 + "\n")

        with transaction.atomic():
            listing = Listing.objects.create(
                title=titlu[:255],
                description=descriere,
                price=pret_curat,
                currency=moneda_finala,
                city=oras_final,
                neighborhood=cartier_final if (cartier_final and cartier_final != "Zona Generala") else "Zona Generala",
                source_url=url,
                source_website="OLX.ro",
                latitude=lat_extras,
                longitude=lng_extras,
                processing_status='PENDING',
                rooms=camere,
                floor=etaj,
                useful_surface=suprafata,
                construction_year=an_constructie,
                partitioning="decomandat" if "decomandat" in text_total else "semidecomandat",
                furnishing_state="mobilat" if check_feat(["mobilat", "utilat", "utila", "mobilata", "canapea", "pat "]) else "nemobilat",
                has_fridge=check_feat(["frigider", "combina"]),
                has_washing_machine=check_feat(["masina de spalat", "mașină spălat"]),
                has_ac=check_feat(["aer conditionat", " ac ", "climatizare"]),
                has_parking=check_feat(["parcare", "loc parcare", "garaj"]),
                is_pet_friendly=check_feat(["accepta animale", "pet friendly"]),
                raw_data={
                    "site_title": titlu,
                    "site_price": pret_afisaj_curat,
                    "site_location": locatie_completa,
                    "site_description": descriere,
                    "site_specs": specs_brute,
                    "site_images": list(set(imagini_brute)),
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            )

        try:
            from django.core.management import call_command
            call_command('normalize_listings', listing_id=listing.id)
        except Exception as e_elt:
            self.stdout.write(self.style.ERROR(f"   ⚠️ Eșec la execuția normalizării: {e_elt}"))

        return True