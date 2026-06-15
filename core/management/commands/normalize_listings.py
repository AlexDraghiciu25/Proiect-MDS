import re
import unicodedata
from datetime import datetime
from dateutil import parser
from django.utils import timezone
from django.core.management.base import BaseCommand
from core.models import Listing

class Command(BaseCommand):
    help = 'Motor avansat de normalizare ELT'

    def add_arguments(self, parser):
        parser.add_argument('--listing_id', type=int, help='ID-ul unui singur anunt pentru normalizare on-the-fly')

    def handle(self, *args, **options):
        listing_id = options.get('listing_id')
    
        if listing_id:
            pending_listings = Listing.objects.filter(id=listing_id)
        else:
            pending_listings = Listing.objects.filter(processing_status='PENDING')
        #pending_listings = Listing.objects.filter(processing_status='PENDING')

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

            def este_negat(keywords, text_sursa):
                """
                Verifică dacă o listă de cuvinte cheie este precedată de o structură de negare.
                Returnează True dacă s-a găsit o negare (ex: "nu se acceptă animale").
                """
                negatii = [
                    r'fara',
                    r'nu\s+.{0,15}acc\w*',       # nu acceptam, nu se accepta
                    r'nu\s+.{0,15}permi\w*',     # nu permitem, nu e permis
                    r'nu\s+.{0,15}prim\w*',      # nu primim, nu se primesc
                    r'nu\s+exista',
                    r'nu\s+.{0,15}benefici\w*',  # nu beneficiaza
                    r'nu\s+dispune\w*(?:\s+de)?',# nu dispune de
                    r'nu\s+.{0,15}ofer\w*',      # nu oferim, nu se ofera
                    r'nu\s+.{0,15}are',          # nu are
                    r'nu\s+.{0,15}include',      # nu include
                    r'fara\s+posibilitatea\s+de',
                    r'exclus'
                ]
                
                grup_negatii = r'(?:' + '|'.join(negatii) + r')'
                grup_keywords = r'(?:' + '|'.join(keywords) + r')'
                
                # Construim regex-ul: Negație + "fereastră" de 20 caractere + Cuvânt Cheie
                regex_interzicere = rf'\b{grup_negatii}\b.{{0,20}}\b{grup_keywords}\b'
                
                return bool(re.search(regex_interzicere, text_sursa))

            def extrage_facilitate(keywords):
                # Verificăm mai întâi dacă este negat clar (ex: "fără parcare")
                if este_negat(keywords, text_total):
                    return False
                if has_keyword(keywords):
                    return True
                return None 

            def extrage_utilitate_esentiala(negative_keywords, keywords):
                if has_keyword(negative_keywords) or este_negat(keywords, text_total):
                    return False
                if has_keyword(keywords):
                    return True
                return None

            # --- FUNCȚIE NUMERE ---
            def extrage_numar_sau_standard(keywords, is_balcon=False):
                kw_pattern = r'(?:' + '|'.join(keywords) + r')'
                if is_balcon:
                    regex_str = rf'(?:{kw_pattern}[\s:]*(\d+)(?!.*(?:mp|m2|metri|m²|m)))|(\d+)\s*{kw_pattern}'
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
            if bai_curat is None:
                bai_curat = 1
                
            balcoane_curat = extrage_numar_sau_standard(['balcon', 'balcoane', 'terasa', 'terase'], is_balcon=True)
            
            bucatarii_curat = extrage_numar_sau_standard(['bucatarie', 'bucatarii'])
            if bucatarii_curat is None:
                bucatarii_curat = 1

            suprafata_curata = None
            match_suprafata = re.search(r'(?:suprafata utila|suprafata)[\s:\-]*(?:de\s+)?(\d+)\s*(?:mp|m2|m²|m|metri)', text_total)            
            if match_suprafata:
                val = match_suprafata.group(1)
                if val: suprafata_curata = float(val)
            else:
                match_suprafata = re.search(r'(?:suprafata utila|suprafata).{0,20}?(?:de\s+)?(\d+)\s*(?:mp|m2|m²|m|metri)', text_total) 
                if match_suprafata:
                    val = match_suprafata.group(1)
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

            geamuri = "Aluminiu" if has_keyword(['aluminiu']) else ("Termopan/PVC" if has_keyword(['termopan', 'pvc']) else ("Plastic" if has_keyword(['plastic']) else None))
            
            energy_class = None
            match_energy = re.search(r'(?:clasa\s+energetica|certificat\s+energetic)[\s:\-]*([a-g])\b', text_total)
            if match_energy:
                energy_class = match_energy.group(1).upper()

            # --- EXTRAGERE LOCAȚIE — STRATEGIE ÎN 3 NIVELURI ---

            # Lista completă a municipiilor din România + suburbii comune
            # Cheie = formă fără diacritice (lowercase), Valoare = formă corectă
            MUNICIPII_RO = {
                'alba iulia': 'Alba Iulia', 'arad': 'Arad', 'pitesti': 'Pitești',
                'bacau': 'Bacău', 'oradea': 'Oradea', 'bistrita': 'Bistrița',
                'botosani': 'Botoșani', 'brasov': 'Brașov', 'braila': 'Brăila',
                'buzau': 'Buzău', 'resita': 'Reșița', 'cluj-napoca': 'Cluj-Napoca',
                'cluj napoca': 'Cluj-Napoca', 'cluj': 'Cluj-Napoca',
                'constanta': 'Constanța', 'sfantu gheorghe': 'Sfântu Gheorghe',
                'targoviste': 'Târgoviște', 'craiova': 'Craiova',
                'drobeta-turnu severin': 'Drobeta-Turnu Severin',
                'galati': 'Galați', 'giurgiu': 'Giurgiu', 'targu jiu': 'Târgu Jiu',
                'miercurea ciuc': 'Miercurea Ciuc', 'deva': 'Deva',
                'slobozia': 'Slobozia', 'iasi': 'Iași', 'baia mare': 'Baia Mare',
                'targu mures': 'Târgu Mureș', 'targu-mures': 'Târgu Mureș',
                'piatra neamt': 'Piatra Neamț', 'piatra-neamt': 'Piatra Neamț',
                'slatina': 'Slatina', 'ploiesti': 'Ploiești', 'satu mare': 'Satu Mare',
                'zalau': 'Zalău', 'sibiu': 'Sibiu', 'suceava': 'Suceava',
                'alexandria': 'Alexandria', 'timisoara': 'Timișoara', 'timis': 'Timișoara',
                'tulcea': 'Tulcea', 'vaslui': 'Vaslui',
                'ramnicu valcea': 'Râmnicu Vâlcea', 'ramnicu-valcea': 'Râmnicu Vâlcea',
                'rm valcea': 'Râmnicu Vâlcea', 'focsani': 'Focșani',
                'bucuresti': 'București', 'bucharest': 'București',
                'medias': 'Mediaș', 'sebes': 'Sebeș', 'turda': 'Turda',
                'campina': 'Câmpina', 'fagaras': 'Făgăraș',
                'hunedoara': 'Hunedoara', 'petrosani': 'Petroșani',
                'roman': 'Roman', 'falticeni': 'Fălticeni',
                'pascani': 'Pașcani', 'mangalia': 'Mangalia',
                'medgidia': 'Medgidia', 'calarasi': 'Călărași',
                'lugoj': 'Lugoj', 'ilfov': 'Ilfov',
                'voluntari': 'Voluntari', 'pantelimon': 'Pantelimon',
                'popesti-leordeni': 'Popești-Leordeni', 'popesti leordeni': 'Popești-Leordeni',
                'bragadiru': 'Bragadiru', 'otopeni': 'Otopeni',
                'buftea': 'Buftea', 'chiajna': 'Chiajna',
                'magurele': 'Măgurele', 'chitila': 'Chitila',
                'floresti': 'Florești', 'baciu': 'Baciu', 'apahida': 'Apahida',
            }

            oras_curat = None
            zona_curata = None

            # === NIVEL 1: Câmpuri curate salvate direct de JSON scraper (cel mai fiabil) ===
            site_city = str(raw.get("site_city", "") or "").strip()
            site_district = str(raw.get("site_district", "") or "").strip()

            if site_city:
                city_clean = strip_accents(site_city.lower()).strip()
                # Normalizăm diacriticele dacă știm orașul, altfel păstrăm ce a venit din JSON
                oras_curat = MUNICIPII_RO.get(city_clean, site_city)
                zona_curata = site_district if site_district else None

            # === NIVEL 2: Parsare din `site_specs` (foarte curat) ===
            if not oras_curat:
                specs_brut = str(raw.get("site_specs", "") or "")
                if specs_brut:
                    # site_specs are forma: "... | 550 € | Carol I, Iasi, Iasi | Apartament..."
                    specs_parts = [p.strip() for p in specs_brut.split('|')]
                    for part in specs_parts:
                        sub_parts = [s.strip() for s in part.split(',')]
                        # Căutăm fragmente care conțin orașul
                        oras_index = -1
                        for i, s in enumerate(sub_parts):
                            s_clean = strip_accents(s.lower()).strip()
                            if s_clean in MUNICIPII_RO:
                                oras_curat = MUNICIPII_RO[s_clean]
                                oras_index = i
                                break  # ne oprim la primul oraș găsit în acest fragment
                        
                        if oras_index >= 0:
                            # Ce e înainte de oraș e cartierul (ex: "Carol I")
                            parti_inainte = sub_parts[:oras_index]
                            if parti_inainte:
                                zona_curata = ", ".join(parti_inainte[-2:])
                            break
                            
            # === NIVEL 3: Parsare string site_location (fallback extrem) ===
            if not oras_curat:
                loc_brut = str(raw.get("site_location", "") or "")
                if loc_brut and loc_brut.lower() != "n/a":
                    # Luăm ultimele 15 elemente pentru a evita fragmentele gigantice din DOM fallback
                    parti_toate = [p.strip() for p in loc_brut.split(',')]
                    parti = parti_toate[-15:]

                    # Scanăm de la coadă spre început (orașul e de obicei spre final)
                    BLACKLIST_NAV = {'inchiri', 'apartam', 'garsonier', 'camere',
                                     'terenuri', 'spatii', 'birouri', 'hale', 'garaje',
                                     'case noi', 'apartamente noi', 'camere de inchiriat'}
                    for i in range(len(parti) - 1, -1, -1):
                        p_clean = strip_accents(parti[i].lower()).strip()
                        if p_clean in MUNICIPII_RO:
                            oras_curat = MUNICIPII_RO[p_clean]
                            parti_inainte = parti[:i]
                            # Filtrăm resturi de navigare
                            parti_utile = [
                                p for p in parti_inainte
                                if 2 < len(p) < 50
                                and not any(b in strip_accents(p.lower()) for b in BLACKLIST_NAV)
                            ]
                            if parti_utile:
                                zona_curata = ", ".join(parti_utile[-2:])
                            break

            
            def extrage_reguli_vicii(text):
                vicii_gasite = []
                
                if re.search(r'(?:fara|interzis|exclus|nu\s+se\s+accepta)[\s\w]*(?:fumat|fumator)|nu\s+se\s+fumeaza', text, re.IGNORECASE) or re.search(r'(?:fumatul|fumat).{0,10}?(?:interzis|exclus|nepermis)', text, re.IGNORECASE):
                        vicii_gasite.append("Fumatul interzis")
                    
                elif re.search(r'(?:se\s+accepta|permis|ok)[\s\w]*(?:fumat|fumator)', text, re.IGNORECASE):
                    vicii_gasite.append("Fumat permis")

                if re.search(r'(?:fara|interzis|exclus)[\s\w]*(?:petreceri|party|evenimente)', text, re.IGNORECASE):
                    vicii_gasite.append("Fără petreceri")
                    
                if len(vicii_gasite) > 0:
                    return ", ".join(vicii_gasite)
                    
                return None

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
            
            anunt.has_electricity = extrage_utilitate_esentiala( ['fara curent', 'fara electricitate'],['curent','electricitate'])
            anunt.has_water = extrage_utilitate_esentiala(['fara apa', 'nebransat la apa'], ['apa', 'bransat la apa'])
            anunt.has_gas = extrage_utilitate_esentiala(['fara gaz', 'fara gaze'], ['gaz', 'gaze']) 
            anunt.has_sewage = extrage_utilitate_esentiala(['fara canalizare', 'nebransat la canalizare'], ['canalizare', 'bransat la canalizare'])

            anunt.has_underfloor_heating = extrage_facilitate(['incalzire in pardoseala'])
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
            anunt.street_paved = extrage_facilitate(['strada asfaltata', 'asfalt'])
            anunt.street_lit = extrage_facilitate(['iluminat'])
            anunt.near_public_transit = extrage_facilitate([
             'metrou', 'stb', 'ratb', 'statie de autobuz', 
            'transport in comun', 'statie de tramvai', 'troleibuz'
            ])
            anunt.vices = extrage_reguli_vicii(text_total)

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
                    f" Normalizat: {anunt.title[:15]}.. | Etaj: {anunt.floor}/{anunt.total_floors} | Zona: {anunt.neighborhood} | Scor: {anunt.data_completeness_score}%"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f" Eroare la salvare pt ID {anunt.id}: {e}"))
                anunt.processing_status = 'ERROR'
                anunt.save()

        self.stdout.write(self.style.SUCCESS(" Normalizare finalizată!"))