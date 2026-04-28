import re
import unicodedata
from datetime import datetime
from django.utils import timezone
from django.core.management.base import BaseCommand
from core.models import Listing

class Command(BaseCommand):
    help = 'Motor avansat de normalizare ELT'

    def handle(self, *args, **options):
        pending_listings = Listing.objects.filter(processing_status='PENDING')
        count = pending_listings.count()
        
        if count == 0:
            self.stdout.write(self.style.WARNING(" Nu exista anunturi PENDING."))
            return
            
        self.stdout.write(self.style.WARNING(f" Normalizam {count} anunturi..."))

        for anunt in pending_listings:
            raw = anunt.raw_data
            if not raw: 
                continue
            
            # --- CURATARE TEXT ---
            def strip_accents(text):
                try:
                    text = str(text)
                    return str(unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode("utf-8"))
                except: 
                    return str(text)

            titlu = str(raw.get("site_title", ""))
            specs = str(raw.get("site_specs", ""))
            descriere = str(raw.get("site_description", ""))
            
            # Eliminăm pipe-ul (|)
            specs_curat = specs.replace(" | ", " ")
            text_brut = f"{titlu} {specs_curat} {descriere}"
            text_total = strip_accents(text_brut).lower()

            # --- FUNCȚII CĂUTARE ---
            def has_keyword(keywords):
                return any(re.search(r'\b' + re.escape(kw) + r'\b', text_total) for kw in keywords)

            def extract_choice(mapping_dict):
                for db_value, keywords in mapping_dict.items():
                    if has_keyword(keywords): 
                        return db_value
                return None

            # --- FUNCȚII BOOLEENE ---
            def extrage_facilitate(keywords):
                if has_keyword(keywords):
                    return True
                return False 
                
            def extrage_utilitate_esentiala(negative_keywords):
                if has_keyword(negative_keywords):
                    return False
                return True

            # --- FUNCȚIE NUMERE ---
            def extrage_numar_sau_standard(keywords, is_balcon=False):
                kw_pattern = r'(?:' + '|'.join(keywords) + r')'
                if is_balcon:
                    regex_str = rf'(?:{kw_pattern}[\s:]*(\d+)(?!\s*(?:mp|m2|metri))|(\d+)\s*{kw_pattern})'
                else:
                    regex_str = rf'(?:{kw_pattern}[\s:]*(\d+)|(\d+)\s*{kw_pattern})'

                match_cifra = re.search(regex_str, text_total)
                if match_cifra:
                    val = match_cifra.group(1) or match_cifra.group(2)
                    if val: return int(val)
                        
                if re.search(rf'\b{kw_pattern}\b', text_total):
                    return 1
                return None

            # --- EXTRAGERE NUMERICĂ COMPLEXĂ ---
            
            pret_curat = None
            pret_brut = raw.get("site_price", "").replace(" ", "")
            match_pret = re.search(r'(\d+[\.,]?\d*)', pret_brut)
            if match_pret:
                try: pret_curat = float(match_pret.group(1).replace('.', '').replace(',', ''))
                except ValueError: pass

            camere_curat = None
            match_camere = re.search(r'(?:camere|dormitoare|numarul\s+de\s+camere)[\s:]*(\d+)|(\d+)\s*(?:camere|dormitoare)', text_total)
            if match_camere:
                val = match_camere.group(1) or match_camere.group(2)
                if val: camere_curat = int(val)
            elif 'garsoniera' in text_total: 
                camere_curat = 1
            elif '2 camere' in titlu.lower(): 
                camere_curat = 2 

            bai_curat = extrage_numar_sau_standard(['baie', 'bai', 'grup sanitar'])
            balcoane_curat = extrage_numar_sau_standard(['balcon', 'balcoane', 'terasa', 'terase'], is_balcon=True)
            bucatarii_curat = extrage_numar_sau_standard(['bucatarie', 'bucatarii'])

            suprafata_curata = None
            match_suprafata = re.search(r'(?:suprafata utila|suprafata)[\s:]*(\d+)\s*(?:mp|m2)|(\d+)\s*(?:mp|m2)', text_total)
            if match_suprafata:
                val = match_suprafata.group(1) or match_suprafata.group(2)
                if val: suprafata_curata = float(val)

            # --- ETAJ (Actualizat pentru 10/15, 10 din 15, etc) ---
            etaj_curat = None
            etaje_totale = None
            
            # Pas 1: Căutăm format cu numitor (ex: 10/15, 10 din 15)
            match_etaj_complex = re.search(r'etaj(?:ul)?[\s:\-]*(\d+|parter|demisol)[\s]*(?:/|din)[\s]*(\d+)', text_total)
            if match_etaj_complex:
                etaj_val = match_etaj_complex.group(1)
                etaj_curat = "0" if etaj_val == 'parter' else ("-1" if etaj_val == 'demisol' else etaj_val)
                etaje_totale = int(match_etaj_complex.group(2))
            else:
                # Pas 2: Fallback pentru etaj simplu (ex: etaj 5)
                match_etaj_simplu = re.search(r'etaj(?:ul)?[\s:\-]*(\d+|parter|demisol)', text_total)
                if match_etaj_simplu:
                    etaj_val = match_etaj_simplu.group(1)
                    etaj_curat = "0" if etaj_val == 'parter' else ("-1" if etaj_val == 'demisol' else etaj_val)

            an_constructie = None
            match_an = re.search(r'(?:an\s+constructie|anul\s+constructiei|construit\s+in|dupa)[\s:]*([12][0-9]{3})', text_total)
            if match_an: 
                an_constructie = int(match_an.group(1))

            disponibilitate = None
            match_disp = re.search(r'liber\s+de\s+la[\s:]*(\d{4}-\d{2}-\d{2})', text_total)
            if match_disp:
                disponibilitate = match_disp.group(1)
            else:
                disponibilitate = timezone.now().strftime('%Y-%m-%d')

            # --- MAPARE CHOICES ---
            partitioning_map = {'decomandat': ['decomandat'], 'semidecomandat': ['semidecomandat'], 'circular': ['circular'], 'nedecomandat': ['nedecomandat']}
            heating_map = {'centrala_proprie': ['centrala proprie', 'centrala pe gaz', 'centrala de apartament'], 'centrala_imobil': ['centrala bloc', 'centrala imobil'], 'termoficare': ['termoficare', 'centralizata', 'radet'], 'incalzire_electrica': ['incalzire electrica']}
            comfort_map = { 'lux': ['lux', 'premium'], '1': ['confort 1'], '2': ['confort 2'] }
            furnishing_map = {'nemobilat': ['nemobilat'], 'partial': ['partial mobilat'], 'mobilat': ['mobilat complet', 'mobilier', 'complet mobilat']}
            structure_map = {'beton': ['beton'], 'caramida': ['caramida'], 'bca': ['bca'], 'lemn': ['lemn']}
            building_map = {'bloc': ['bloc', 'ansamblu de apartamente'], 'casa': ['casa', 'vila']}

            geamuri = "Aluminiu" if has_keyword(['aluminiu']) else ("Termopan/PVC" if has_keyword(['termopan', 'pvc']) else None)
            
            energy_class = None
            match_energy = re.search(r'(?:clasa\s+energetica|certificat\s+energetic)[\s:\-]*([a-g])\b', text_total)
            if match_energy:
                energy_class = match_energy.group(1).upper()

            # --- EXTRAGERE LOCAȚIE (RECUPERATĂ!) ---
            oras_curat = None
            zona_curata = None
            loc_brut = str(raw.get("site_location", ""))
            
            if loc_brut and loc_brut.lower() != "n/a":
                # Sparge pe virgulă (ex: "Nicolae Caramfil, Aviatiei, Sectorul 1, Bucuresti")
                parti = [p.strip() for p in loc_brut.split(',')]
                
                # Caută București
                for p in parti:
                    if 'bucuresti' in strip_accents(p.lower()):
                        oras_curat = "Bucuresti"
                
                # Elimină București și România pentru a lăsa doar strada/cartierul/sectorul
                parti_utile = [p for p in parti if 'bucuresti' not in strip_accents(p.lower()) and 'romania' not in strip_accents(p.lower())]
                
                if len(parti_utile) > 0:
                    # Unește ultimele 2 informații (de obicei Cartier + Sector)
                    zona_curata = ", ".join(parti_utile[-2:])

            # --- POPULARE MODEL ---
            anunt.title = titlu[:255] if titlu else "Fără titlu"
            anunt.description = descriere
            anunt.price = pret_curat
            anunt.rooms = camere_curat
            anunt.bathrooms = bai_curat
            anunt.kitchens = bucatarii_curat
            anunt.balconies = balcoane_curat
            anunt.useful_surface = suprafata_curata
            anunt.floor = etaj_curat[:50] if etaj_curat else None
            anunt.total_floors = etaje_totale
            anunt.construction_year = an_constructie
            anunt.availability = disponibilitate
            
            anunt.city = oras_curat
            anunt.neighborhood = zona_curata
            
            anunt.partitioning = extract_choice(partitioning_map)
            anunt.comfort_level = extract_choice(comfort_map)
            anunt.building_structure = extract_choice(structure_map)
            anunt.furnishing_state = extract_choice(furnishing_map)
            anunt.heating_type = extract_choice(heating_map)
            anunt.building_type = extract_choice(building_map)
            anunt.windows = geamuri
            anunt.energy_class = energy_class
            
            anunt.has_electricity = extrage_utilitate_esentiala(['fara curent', 'nebransat la curent'])
            anunt.has_water = extrage_utilitate_esentiala(['fara apa', 'nebransat la apa'])
            anunt.has_gas = extrage_utilitate_esentiala(['fara gaz', 'fara gaze']) 

            anunt.has_underfloor_heating = extrage_facilitate(['incalzire in pardoseala'])
            anunt.has_sewage = extrage_facilitate(['canalizare'])
            anunt.has_fridge = extrage_facilitate(['frigider', 'combina frigorifica'])
            anunt.has_washing_machine = extrage_facilitate(['masina de spalat rufe', 'masina de spalat'])
            anunt.has_dishwasher = extrage_facilitate(['masina de spalat vase', 'masina de spalat vasele'])
            anunt.has_tv = extrage_facilitate(['tv', 'televizor'])
            anunt.has_oven = extrage_facilitate(['cuptor'])
            anunt.has_microwave = extrage_facilitate(['microunde'])
            anunt.has_hood = extrage_facilitate(['hota'])
            anunt.has_ac = extrage_facilitate(['aer conditionat', 'ac', 'clima'])
            
            anunt.has_intercom = extrage_facilitate(['interfon', 'videointerfon'])
            anunt.has_elevator = extrage_facilitate(['lift', 'ascensor'])
            anunt.has_video_surveillance = extrage_facilitate(['supraveghere', 'alarma', 'camere video'])
            anunt.has_parking = extrage_facilitate(['parcare', 'garaj', 'loc de parcare'])
            anunt.is_pet_friendly = extrage_facilitate(['animale de companie', 'pet friendly'])

            fields_to_check = [
                anunt.price, anunt.rooms, anunt.useful_surface, anunt.floor, 
                anunt.partitioning, anunt.heating_type, anunt.building_type, anunt.construction_year
            ]
            score = sum(1 for field in fields_to_check if field is not None)
            anunt.data_completeness_score = int((score / len(fields_to_check)) * 100)

            anunt.processing_status = 'PROCESSED'
            
            try:
                anunt.save()
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Normalizat: {anunt.title[:15]}.. | Etaj: {anunt.floor}/{anunt.total_floors} | Zona: {anunt.neighborhood} | Scor: {anunt.data_completeness_score}%"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f" Eroare la salvare pt ID {anunt.id}: {e}"))
                anunt.processing_status = 'ERROR'
                anunt.save()

        self.stdout.write(self.style.SUCCESS(" Normalizare finalizată!"))