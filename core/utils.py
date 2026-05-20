# core/utils.py
import os
from playwright.sync_api import sync_playwright
from core.management.commands.scrape_storia import Command as StoriaScraper
from core.management.commands.normalize_listings import Command as Normalizer # Importăm normalizatorul

def scrape_single_url(url):
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    
    scraper = StoriaScraper()
    normalizer = Normalizer() # Instanțiem motorul de normalizare
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        try:
            # 1. SCRAPING: Luăm datele brute
            listing = scraper.proceseaza_anunt(context, url)
            
            if listing:
                # 2. NORMALIZARE: Traducem datele brute în câmpuri (Price, Desc, etc.)
                # Normalizatorul tău caută anunțuri cu status 'PENDING'
                # Îl forțăm să ruleze acum pe obiectul proaspăt creat
                normalizer.handle() 
                
                # Reîncărcăm obiectul din baza de date pentru a vedea noile valori populate
                listing.refresh_from_db()
                
            return listing
        except Exception as e:
            print(f"Eroare Utils (Scrape/Normalize): {e}")
            return None
        finally:
            context.close()
            browser.close()