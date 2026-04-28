import os
import time
import random
from django.core.management.base import BaseCommand
from core.models import Listing
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from django.db import transaction

class Command(BaseCommand):
    help = 'Scraper robust pentru Storia.ro (Izolare pe Tab-uri, Heuristic Extraction, Lazy Loading)'

    def handle(self, *args, **options):
        # Permitem operatiunile asincrone in Django
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        self.stdout.write(self.style.WARNING(" Parser Storia.ro: Inițiere proces de scraping..."))

        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(
                headless=False, # Poti pune True cand il muti pe server
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
            # Mergem pe pagina
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # --- PASUL 1: SCROLL LENT ---
            # Dăm scroll ca să forțăm site-ul să descarce listele
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
            # Caută butoanele după text și dă click pe ele prin JS clasic
            page.evaluate("""function() {
                var butoane = document.querySelectorAll('button, div[role="button"]');
                for(var i=0; i<butoane.length; i++) {
                    var text = butoane[i].innerText ? butoane[i].innerText.toLowerCase() : '';
                    if(text.includes('facilități') || text.includes('clădire') || text.includes('mai mult')) {
                        try { butoane[i].click(); } catch(e) {}
                    }
                }
            }""")
            
            # Așteptăm 2 secunde pentru ca animația de la acordeon să se deschidă complet
            time.sleep(2)

            # --- PASUL 3: CITIREA DATELOR "LA SÂNGE" ---
            # Tragem tot textul din zona de specificații, rând cu rând
            specs_brute = page.evaluate("""function() {
                // Găsim cutia mare care ține toate datele
                var container = document.querySelector('[data-testid="ad-details"]') || 
                                document.querySelector('[data-cy="adPageAdFeatures"]');
                
                if(!container) {
                    // Dacă au schimbat clasele, căutăm ancora "Suprafață utilă:" și urcăm în structură
                    var divs = document.querySelectorAll('div');
                    for(var i=0; i<divs.length; i++) {
                        if(divs[i].innerText === 'Suprafață utilă:') {
                            container = divs[i].parentElement.parentElement.parentElement.parentElement;
                            break;
                        }
                    }
                }
                
                if(container) {
                    // container.innerText ia textul EXTRAT cum arată pe ecran (inclusiv "frigider" etc.)
                    // Folosim dublu backslash pentru Python
                    var linii = container.innerText.split('\\n'); 
                    var texte_valide = [];
                    
                    for(var i=0; i<linii.length; i++) {
                        var linie = linii[i].trim();
                        // Eliminăm gunoaiele și rândurile goale
                        if(linie.length > 1 && linie.length < 80) {
                            texte_valide.push(linie);
                        }
                    }
                    
                    // Eliminăm duplicatele
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

            # --- SALVAREA ---
            with transaction.atomic():
                Listing.objects.create(
                    title=f"BRUT: {titlu[:40]}",
                    source_url=url,
                    source_website="Storia.ro",
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

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Eroare pe pagina anuntului: {e}"))
        
        finally:
            page.close()