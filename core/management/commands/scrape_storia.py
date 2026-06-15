import os
import time
import random
import json
from django.core.management.base import BaseCommand
from core.models import Listing
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor, as_completed


class Command(BaseCommand):
    help = 'Scraper rapid pentru Storia.ro (JSON-first, Parallel Tabs, Resource Blocking)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--city', type=str, default='toata-romania',
            help='Slug-ul orașului pe Storia (ex: bucuresti, cluj-napoca, timisoara) sau "toata-romania" pentru toate'
        )
        parser.add_argument(
            '--limit', type=int, default=40,
            help='Numărul maxim de anunțuri de procesat per rulare (default: 40)'
        )

    def handle(self, *args, **options):
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        city_slug = options.get('city', 'toata-romania')
        limit = options.get('limit', 40)
        self.stdout.write(self.style.WARNING(f" Parser Storia.ro: Scraping '{city_slug}' (limită: {limit} anunțuri)..."))

        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )

            # Blocare resurse grele (imagini, fonturi, CSS) pentru pagina de listare
            context.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,eot}", lambda route: route.abort())
            context.route("**/*google-analytics*", lambda route: route.abort())
            context.route("**/*doubleclick*", lambda route: route.abort())
            context.route("**/*facebook*", lambda route: route.abort())

            main_page = context.new_page()
            url_cautare = f"https://www.storia.ro/ro/rezultate/inchiriere/apartament/{city_slug}"

            try:
                self.stdout.write(f" Navigam spre: {url_cautare}")
                main_page.goto(url_cautare, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)  # Redus de la 5s

                try:
                    main_page.locator("button:has-text('Accept'), button:has-text('De acord'), #onetrust-accept-btn-handler").first.click(timeout=3000)
                    self.stdout.write(" Am scapat de cookie-uri.")
                except:
                    pass

                # Scroll mai rapid — 2 iterații de scroll mare + un pic de așteptare
                self.stdout.write(" Generam scroll pentru a incarca anunturile...")
                main_page.evaluate("""
                    var interval = setInterval(function() { window.scrollBy(0, 2000); }, 200);
                    setTimeout(function() { clearInterval(interval); }, 1500);
                """)
                time.sleep(2)  # Redus de la 6s (4 x 1.5s)

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

                # Eliberăm memoria
                main_page.close()

                # Filtrăm URL-urile deja existente în DB (batch check)
                linkuri_existente = set(
                    Listing.objects.filter(source_url__in=linkuri_valide)
                    .values_list('source_url', flat=True)
                )
                linkuri_noi = [url for url in linkuri_valide if url not in linkuri_existente]

                if linkuri_existente:
                    self.stdout.write(self.style.WARNING(
                        f" Skip: {len(linkuri_existente)} anunturi deja existente in DB."
                    ))

                if not linkuri_noi:
                    self.stdout.write(self.style.SUCCESS(" Toate anunturile sunt deja in DB!"))
                    return

                # Limităm la 40 de anunțuri per rulare
                linkuri_noi = linkuri_noi[:limit]
                self.stdout.write(f" Procesăm {len(linkuri_noi)} anunțuri noi...")

                # Procesare în batch-uri paralele de câte 3 tab-uri
                BATCH_SIZE = 3
                count = 0
                for i in range(0, len(linkuri_noi), BATCH_SIZE):
                    batch = linkuri_noi[i:i + BATCH_SIZE]
                    pages = []

                    # Deschidem tab-urile în paralel
                    for url in batch:
                        page = context.new_page()
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            pages.append((page, url))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"   Timeout/Eroare la navigare: {url[:40]}... - {e}"))
                            page.close()

                    # Așteptăm un pic ca toate paginile să se stabilizeze
                    time.sleep(1)

                    # Procesăm fiecare pagină
                    for page, url in pages:
                        try:
                            self._proceseaza_pagina(page, url)
                            count += 1
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"   Eroare pe pagina anuntului: {e}"))
                        finally:
                            page.close()

                    # Pauză între batch-uri (anti-ban)
                    if i + BATCH_SIZE < len(linkuri_noi):
                        time.sleep(random.uniform(1.5, 3))

                self.stdout.write(self.style.SUCCESS(f"\n Procesat {count} anunturi noi!"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f" Eroare in misiune: {e}"))
            finally:
                browser.close()
                self.stdout.write(" Gata scriptul de Scraping!")

    def proceseaza_anunt(self, context, url):
        """Punct de intrare public (păstrat pentru compatibilitate cu utils.py)."""
        if Listing.objects.filter(source_url=url).exists():
            self.stdout.write(self.style.WARNING(f"Skip: Exista in DB: {url[:40]}..."))
            return

        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)
            return self._proceseaza_pagina(page, url)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Eroare pe pagina anuntului: {e}"))
        finally:
            page.close()

    def _proceseaza_pagina(self, page, url):
        """
        Logica principală de extragere.
        Încearcă mai întâi din __NEXT_DATA__ JSON (instantaneu),
        apoi fallback pe DOM (mai lent, dar sigur).
        """
        # === STRATEGIA 1: JSON-FIRST (RAPIDĂ) ===
        json_data = self._extract_next_data(page)

        if json_data:
            ad_data = json_data.get('props', {}).get('pageProps', {}).get('ad', {})

            if ad_data:
                result = self._parse_from_json(ad_data, url)
                if result:
                    return result

        # === STRATEGIA 2: FALLBACK DOM (dacă JSON-ul lipsește/e schimbat) ===
        self.stdout.write(self.style.WARNING(f"   JSON indisponibil, fallback DOM: {url[:40]}..."))
        return self._parse_from_dom(page, url)

    def _extract_next_data(self, page):
        """Extrage JSON-ul __NEXT_DATA__ dacă există."""
        try:
            script_locator = page.locator("script#__NEXT_DATA__").first
            if script_locator.count() > 0:
                json_text = script_locator.inner_text()
                return json.loads(json_text)
        except Exception:
            pass
        return None

    def _parse_from_json(self, ad_data, url):
        """Extrage toate datele dintr-un singur JSON parse — fără scroll, fără click, fără așteptare."""
        try:
            # Titlu
            titlu = ad_data.get('title', '').strip()
            if not titlu or len(titlu) < 5:
                self.stdout.write(self.style.WARNING(f"   Skip: Titlu invalid din JSON: '{titlu}'"))
                return None

            # Preț
            price_info = ad_data.get('target', {})
            pret_val = price_info.get('Price', '')
            currency = price_info.get('Currency', 'EUR')
            pret = f"{pret_val} {currency}" if pret_val else "N/A"

            # Locație
            location_data = ad_data.get('location', {})
            address = location_data.get('address', {})
            
            parti_locatie = []
            for key in ['street', 'district', 'city']:
                val = address.get(key, {}).get('name', '')
                if val:
                    parti_locatie.append(val)
            locatie = ', '.join(parti_locatie) if parti_locatie else 'N/A'

            # Coordonate GPS
            coords = location_data.get('coordinates', {})
            lat_extras = coords.get('latitude')
            lng_extras = coords.get('longitude')

            # Specificații — extragem din characteristics
            specs_parts = []
            characteristics = ad_data.get('characteristics', [])
            for char in characteristics:
                key = char.get('label', char.get('key', ''))
                value = char.get('localizedValue', char.get('value', ''))
                if key and value:
                    specs_parts.append(f"{key}: {value}")
            specs_brute = ' | '.join(specs_parts) if specs_parts else ''

            # Features / facilități — adăugăm la specs
            features = ad_data.get('features', [])
            if features:
                feat_labels = []
                for feat_category in features:
                    for item in feat_category if isinstance(feat_category, list) else [feat_category]:
                        if isinstance(item, dict):
                            feat_labels.extend(item.get('values', []))
                        elif isinstance(item, str):
                            feat_labels.append(item)
                if feat_labels:
                    if specs_brute:
                        specs_brute += ' | '
                    specs_brute += ' | '.join(feat_labels)

            # Descriere
            descriere = ad_data.get('description', 'N/A')

            # Imagini
            imagini_brute = []
            images = ad_data.get('images', [])
            for img in images:
                if isinstance(img, dict):
                    # Preferăm imaginea mare
                    src = img.get('large', img.get('medium', img.get('small', '')))
                    if src:
                        imagini_brute.append(src)
                elif isinstance(img, str):
                    imagini_brute.append(img)

            # Debug output
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(f"URL: {url}")
            self.stdout.write(f"TITLU EXTRAS (JSON): {titlu}")
            self.stdout.write(f"PRET EXTRAS: {pret}")
            self.stdout.write(self.style.WARNING(f"LOCAȚIE EXTRASĂ: {locatie}"))
            self.stdout.write(f"DESCRIERE (primele 100 char): {descriere[:100]}...")
            self.stdout.write(f"Sursa: __NEXT_DATA__ JSON (rapid)")
            self.stdout.write("=" * 60 + "\n")

            # Salvare
            with transaction.atomic():
                listing = Listing.objects.create(
                    title=f"BRUT: {titlu[:40]}",
                    source_url=url,
                    source_website="Storia.ro",
                    latitude=lat_extras,
                    longitude=lng_extras,
                    processing_status='PENDING',
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
            self.stdout.write(self.style.SUCCESS(f"   Aspirat complet: {titlu[:30]}..."))
            return listing

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Eroare la parsarea JSON: {e}"))
            return None

    def _parse_from_dom(self, page, url):
        """
        Fallback: extragere din DOM (versiunea originală, optimizată).
        Folosit doar dacă __NEXT_DATA__ nu e disponibil.
        """
        # Verificare titlu
        h1_element = page.locator("h1").first
        if h1_element.count() == 0:
            self.stdout.write(self.style.WARNING(f"   Skip: Pagină invalidă/ștearsă (fără H1): {url[:40]}..."))
            return None

        titlu = h1_element.inner_text().strip()
        if not titlu or len(titlu) < 5 or titlu.lower() == "fara titlu":
            self.stdout.write(self.style.WARNING(f"   Skip: Titlu invalid: '{titlu}' la {url[:40]}..."))
            return None

        # Scroll rapid + deschidere acordeoane (combinat, fără sleep separat)
        page.evaluate("""
            // Scroll rapid
            var interval = setInterval(function() { window.scrollBy(0, 800); }, 150);
            setTimeout(function() { clearInterval(interval); }, 1200);
            
            // Deschidere acordeoane
            setTimeout(function() {
                var butoane = document.querySelectorAll('button, div[role="button"]');
                for(var i=0; i<butoane.length; i++) {
                    var text = butoane[i].innerText ? butoane[i].innerText.toLowerCase() : '';
                    if(text.includes('facilități') || text.includes('clădire') || text.includes('mai mult')) {
                        try { butoane[i].click(); } catch(e) {}
                    }
                }
            }, 800);
        """)
        time.sleep(1.5)  # Redus de la 5s (3s scroll + 2s acordeon)

        pret = "N/A"
        pret_el = page.locator("strong:has-text('EUR'), strong:has-text('LEI'), [data-cy='adPageHeaderPrice']").first
        if pret_el.count() > 0:
            pret = pret_el.inner_text().strip()

        locatie = page.evaluate("""function() {
            // Strategia 1: Breadcrumb-uri Storia (link-uri cu /rezultate/ în href)
            var breadcrumbs = document.querySelectorAll('a[href*="/rezultate/"]');
            var parts = [];
            for(var i=0; i<breadcrumbs.length; i++) {
                var text = breadcrumbs[i].innerText.trim();
                if(text.length > 2 && text.length < 80) {
                    parts.push(text);
                }
            }
            if(parts.length > 0) {
                return parts.join(', ');
            }
            // Strategia 2: Căutăm orice link cu text de locație
            var links = document.querySelectorAll('a');
            for(var i=0; i<links.length; i++) {
                var href = links[i].getAttribute('href') || '';
                var text = links[i].innerText.trim();
                if(href.includes('/rezultate/') && text.length > 2 && text.length < 80) {
                    return text;
                }
            }
            return 'N/A';
        }""")

        # Curățăm locația de linii goale
        if locatie and '\n' in locatie:
            linii = [l.strip() for l in locatie.split('\n') if l.strip()]
            locatie = ', '.join(linii) if linii else 'N/A'

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
                    if(linie.length > 0 && linie.length < 80) {
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

        # Coordonate GPS din JSON (dacă __NEXT_DATA__ parțial funcțional)
        lat_extras = None
        lng_extras = None
        try:
            json_data = self._extract_next_data(page)
            if json_data:
                location_data = json_data.get('props', {}).get('pageProps', {}).get('ad', {}).get('location', {}).get('coordinates', {})
                if location_data:
                    lat_extras = location_data.get('latitude')
                    lng_extras = location_data.get('longitude')
        except Exception:
            pass

        # Debug
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(f"URL: {url}")
        self.stdout.write(f"TITLU EXTRAS (DOM): {titlu}")
        self.stdout.write(f"PRET EXTRAS: {pret}")
        self.stdout.write(self.style.WARNING(f"LOCAȚIE EXTRASĂ (BRUT): {locatie}"))
        self.stdout.write(f"DESCRIERE (primele 100 char): {descriere[:100]}...")
        self.stdout.write(f"Sursa: DOM fallback (mai lent)")
        self.stdout.write("=" * 60 + "\n")

        # Salvare
        with transaction.atomic():
            listing = Listing.objects.create(
                title=f"BRUT: {titlu[:40]}",
                source_url=url,
                source_website="Storia.ro",
                latitude=lat_extras,
                longitude=lng_extras,
                processing_status='PENDING',
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
        self.stdout.write(self.style.SUCCESS(f"   Aspirat complet: {titlu[:30]}..."))
        return listing