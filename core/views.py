from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Avg
from .models import Listing, Report 
from .services import DetectiveAgent
from .utils import scrape_single_url
from django.utils import timezone
from django.core.paginator import Paginator
import json
from django.views.decorators.csrf import csrf_exempt
import re
import google.generativeai as genai
from .services import DetectiveAgent
from django.conf import settings
import requests

# ==========================================
# 1. AUTENTIFICARE
# ==========================================
def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Cont creat cu succes!")
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'core/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

# ==========================================
# 2. PAGINI SIMPLE / STATICE
# ==========================================
def home_view(request):
    ultimele_anunturi = Listing.objects.all().order_by('-id')[:6]
    return render(request, 'core/home.html', {'anunturi': ultimele_anunturi})

def about(request):
    return render(request, 'core/about.html')

def contact(request):
    return render(request, 'core/contact.html')

# core/views.py

def history(request):
    if not request.user.is_authenticated:
        return redirect('login')
    rapoarte_list = Report.objects.filter(user=request.user).select_related('listing').order_by('-generated_at')
    
    paginator = Paginator(rapoarte_list, 6) 
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'core/history.html', {
        'rapoarte': page_obj,
    })

# ==========================================
# 3. LOGICA DE CĂUTARE AVANSATĂ CU AI (Cea optimizată)
# ==========================================
def search_results(request):
    # 1. Inițializăm query-ul de bază cu prefetch_related pentru a evita interogări multiple în baza de date
    rezultate = Listing.objects.all().prefetch_related('reports')

    # 2. FILTRU TEXT (Căutare universală: Zonă, Oraș, Titlu)
    query = request.GET.get('q', '').strip()
    if query:
        rezultate = rezultate.filter(
            Q(city__icontains=query) | 
            Q(neighborhood__icontains=query) | 
            Q(title__icontains=query) |
            Q(description__icontains=query)
        )

    # 3. FILTRE NUMERICE (Preț, Camere, Suprafață)
    pret_min = request.GET.get('pret_min')
    pret_max = request.GET.get('pret_max')
    if pret_min:
        rezultate = rezultate.filter(price__gte=pret_min)
    if pret_max:
        rezultate = rezultate.filter(price__lte=pret_max)

    camere = request.GET.get('camere')
    if camere and camere != "Toate":
        rezultate = rezultate.filter(rooms=camere)

    suprafata_min = request.GET.get('suprafata_min')
    if suprafata_min:
        rezultate = rezultate.filter(useful_surface__gte=suprafata_min)

    partitionare = request.GET.get('partitionare')
    if partitionare and partitionare != "Toate":
        rezultate = rezultate.filter(partitioning=partitionare)

    # 5. FILTRE FACILITĂȚI (Boolean - se activează dacă checkbox-ul e bifat)
    if request.GET.get('pet_friendly') == 'on':
        rezultate = rezultate.filter(is_pet_friendly=True)
    if request.GET.get('parcare') == 'on':
        rezultate = rezultate.filter(has_parking=True)
    if request.GET.get('aer_conditionat') == 'on':
        rezultate = rezultate.filter(has_ac=True)
    if request.GET.get('lift') == 'on':
        rezultate = rezultate.filter(has_elevator=True)
    if request.GET.get('centrala') == 'on':
        rezultate = rezultate.filter(heating_type__icontains='central')

    # 6. ANALIZA DATELOR (Statistici rapide pentru rezultatele afișate)
    # Calculăm media de preț a anunțurilor filtrate pentru a ajuta utilizatorul
    statistici = rezultate.aggregate(
        pret_mediu=Avg('price'),
        suprafata_medie=Avg('useful_surface')
    )
    
    # Adăugăm și prețul per metru pătrat mediu dacă există date
    pret_per_mp = 0
    if statistici['pret_mediu'] and statistici['suprafata_medie']:
        pret_per_mp = statistici['pret_mediu'] / statistici['suprafata_medie']

    # 7. ORDONARE (Cele mai noi la început)
    rezultate = rezultate.order_by('-id')

    # 1. Preluăm opțiunea selectată din filtre (implicit 'Toate' - adică așa cum au fost publicate)
    moneda_selectata = request.GET.get('moneda', 'Toate').strip()
    
    # Rata de schimb stabilă pentru simulare
    CURS_EUR_RON = 5.0

    # 2. PROCESARE ȘI CONVERSIE DINAMICĂ (Arhitectură de date curată)
    for anunt in rezultate:
        # Determină valuta reală (Corecție euristică pentru erorile de scraper)
        moneda_reala = str(anunt.currency).upper()
        pret_brut = float(anunt.price) if anunt.price else 0.0
        
        # Dacă prețul e mic (sub 1500) dar scraperul a pus RON, e clar o eroare; e de fapt EUR
        if "EUR" in moneda_reala or "€" in moneda_reala or pret_brut < 1500:
            valuta_originala = "EUR"
        else:
            valuta_originala = "RON"

        # Aplicăm conversia în funcție de butonul selectat de utilizator
        if moneda_selectata == "EUR":
            if valuta_originala == "RON":
                anunt.pret_afisat = pret_brut / CURS_EUR_RON  # Convertim RON -> EUR
            else:
                anunt.pret_afisat = pret_brut
            anunt.moneda_afisata = "€"

        elif moneda_selectata == "RON":
            if valuta_originala == "EUR":
                anunt.pret_afisat = pret_brut * CURS_EUR_RON  # Convertim EUR -> RON
            else:
                anunt.pret_afisat = pret_brut
            anunt.moneda_afisata = "RON"

        else:  # Opțiunea "Toate" (Așa cum au fost publicate original)
            anunt.pret_afisat = pret_brut
            anunt.moneda_afisata = "€" if valuta_originala == "EUR" else "RON"

    # 8. CONTEXT PENTRU TEMPLATE
    context = {
        'anunturi': rezultate,
        'nr_rezultate': rezultate.count(),
        'cuvant_cautat': query,
        'statistici': {
            'pret_mediu': round(statistici['pret_mediu'], 2) if statistici['pret_mediu'] else 0,
            'suprafata_medie': round(statistici['suprafata_medie'], 1) if statistici['suprafata_medie'] else 0,
            'pret_per_mp': round(pret_per_mp, 2)
        },
        'filtru_camere': camere,
        'filtru_pret_max': pret_max,
        'filtru_moneda': moneda_selectata,  # Returnăm starea butonului
    }

    return render(request, 'core/search_results.html', context)

# ==========================================
# 4. PAGINA DE DETALII ȘI ANALIZĂ AI
# ==========================================

def result_detail_view(request, listing_id):
    # Folosim 'listing' peste tot pentru a se potrivi cu restul codului
    listing = get_object_or_404(Listing, id=listing_id)
    
    # Căutăm raportul
    report = Report.objects.filter(listing=listing).first()
    
    # DEBUG (opțional): Dacă vrei să vezi în terminal dacă găsește raportul
    if report:
        print(f"DEBUG: Scorul găsit este {report.integrity_score}")
    else:
        print("DEBUG: Nu există raport pentru acest listing!")

    return render(request, 'core/result.html', {
        'listing': listing,  # Schimbat din 'anunt' în 'listing'
        'report': report
    })
@login_required
def run_analysis_view(request, listing_id):
    if not request.user.is_authenticated:
        # Returnezi o eroare sau un mesaj că trebuie să fie logat
        return JsonResponse({'error': 'Trebuie să fii logat pentru analiză.'}, status=401)
    
    listing = get_object_or_404(Listing, id=listing_id)
    
    # Dacă există raport, redirecționăm la detalii
    existing_report = Report.objects.filter(listing=listing).first()
    if existing_report:
        return redirect('result_detail', listing_id=listing.id)

    # Dacă nu, rulăm AI-ul lui Alex
    agent = DetectiveAgent()
    report = agent.analyze_listing(listing_id, request.user)
    
    if report:
        # Redirecționăm către pagina de detalii unde va apărea noul raport
        return redirect('result_detail', listing_id=listing.id)
    else:
        messages.error(request, "Analiza AI a eșuat. Verifică cheia API.")
        return redirect('home')

# core/views.py

def analyze_external(request):
    if request.method == 'POST':
        url_extern = request.POST.get('external_url', '').strip()
        
        # 1. Căutăm dacă există deja
        listing = Listing.objects.filter(source_url=url_extern).first()
        
        # 2. Dacă NU există, facem SCRAPE + NORMALIZARE
        if not listing:
            messages.info(request, "Anunț nou detectat. Pornim scanarea...")
            # Această funcție (din utils.py) trebuie să returneze listing-ul GATA NORMALIZAT
            listing = scrape_single_url(url_extern)
            
            if not listing:
                messages.error(request, "Scraper-ul nu a putut accesa link-ul.")
                return redirect('home')

        # 3. Verificăm dacă are REPORT (Analiza AI)
        report = Report.objects.filter(listing=listing).first()
        
        # 4. Dacă nu are raport, sau dacă raportul existent are erori (opțional), rulăm AI
        if not report:
            # IMPORTANT: Reîncărcăm obiectul din DB pentru a ne asigura că avem 
            # prețul și descrierea populate de normalizator înainte de a le da la AI
            listing.refresh_from_db()
            
            messages.info(request, "Generăm raportul AI...")
            try:
                agent = DetectiveAgent()
                report = agent.analyze_listing(listing.id, request.user)
                
                if not report:
                    messages.error(request, "AI-ul a extras datele dar nu a putut genera concluzia.")
                    return redirect('home')
            except Exception as e:
                messages.error(request, f"Eroare la procesarea AI: {e}")
                return redirect('home')

        return redirect('result_detail', listing_id=listing.id)
        
    return redirect('home')

def ai_chat_endpoint(request):
    if request.method != "POST":
        return JsonResponse({"reply": "Metodă nepermisă"}, status=405)

    try:
        data = json.loads(request.body)
        user_criterion = data.get("message", "").strip() # Criteriul ales de Bianca (ex: apropiere mall)
        id_uri_anunturi = data.get("active_listings", [])

        if not id_uri_anunturi or len(id_uri_anunturi) < 2:
            return JsonResponse({
                "reply": "⚠️ Te rog să selectezi cel puțin 2 garsoniere/apartamente din pagină pentru a putea realiza o comparație relevantă."
            })

        anunturi = Listing.objects.filter(id__in=id_uri_anunturi)
        rapoarte_context = []
        
        # Instanțiem Agentul tău real din proiect
        agent_real = DetectiveAgent()

        for anunt in anunturi:
            # Căutăm raportul existent generat de DetectiveAgent
            raport = Report.objects.filter(listing=anunt).first()
            
            if not raport:
                try:
                    # Dacă nu a fost analizat, rulăm analiza ta profundă pe loc
                    raport = agent_real.analyze_listing(anunt.id, request.user)
                except Exception as ex_agent:
                    print(f"Eroare la apelarea DetectiveAgent: {ex_agent}")
            
            anunt.refresh_from_db()

            # --- EXTRACTOR EXCLUSIV PENTRU SCHEAMA TA DE REPORT ---
            # Reconstituim analiza ta profundă într-un format text structurat pe care să-l înțeleagă Gemini
            context_analiza_ta = ""
            if raport:
                context_analiza_ta += f"Verdict Final: {getattr(raport, 'final_verdict', '')}\n"
                context_analiza_ta += f"Analiză de Proximitate: {getattr(raport, 'proximity_analysis', '')}\n"
                
                # Extragere Red Flags (pentru că e salvat ca listă/JSON)
                flags = getattr(raport, 'red_flags', [])
                if isinstance(flags, list):
                    context_analiza_ta += f"Alerte de Integritate (Red Flags): {', '.join(flags)}\n"
                else:
                    context_analiza_ta += f"Alerte de Integritate (Red Flags): {flags}\n"
                
                # Extragere Price Analysis
                pret_analysis = getattr(raport, 'price_analysis', '')
                context_analiza_ta += f"Analiză de Preț Piață: {pret_analysis}\n"

            # Dacă din orice motiv nu avem raportul populat, punem descrierea de pe site ca rezervă
            if not context_analiza_ta:
                context_analiza_ta = anunt.description

            rapoarte_context.append({
                "anunt": anunt,
                "scor": raport.integrity_score if raport else 70, 
                "detalii_profunde": context_analiza_ta
            })

        # ====================================================
        # 2. CONSTRUIREA MATRICEI DINAMICE (TABELUL HTML)
        # ====================================================
        tabel_html = """
        <div class="table-responsive mt-2">
            <table class="table table-sm table-bordered bg-white text-center align-middle" style="font-size: 0.8rem; border-radius: 6px; overflow: hidden;">
                <thead class="table-dark">
                    <tr>
                        <th>Caracteristică</th>
        """
        for idx, ctx in enumerate(rapoarte_context, 1):
            tabel_html += f"<th>Proprietatea #{idx}</th>"
        tabel_html += "</tr></thead><tbody>"

        # Rând: Titlu
        tabel_html += "<tr><td class='fw-bold table-light text-start'>Titlu</td>"
        for ctx in rapoarte_context:
            tabel_html += f"<td class='text-truncate' style='max-width: 130px;' title='{ctx['anunt'].title}'>{ctx['anunt'].title}</td>"
        tabel_html += "</tr>"

        # Rând: Preț (Corectat structural Monedă)
        tabel_html += "<tr><td class='fw-bold table-light text-start'>Preț</td>"
        for ctx in rapoarte_context:
            pret_brut = ctx['anunt'].price or 0
            moneda_raw = str(ctx['anunt'].currency).upper()
            
            # Corecție inteligentă de interfață: 
            # Dacă prețul e sub 1500, în București e 100% vorba de EURO, chiar dacă scraperul a citit RON de pe OLX
            if "EUR" in moneda_raw or "€" in moneda_raw or pret_brut < 1500:
                moneda_simbol = "€"
            else:
                moneda_simbol = "RON"
                
            tabel_html += f"<td class='fw-bold text-success'>{int(pret_brut) if pret_brut else 'N/A'} {moneda_simbol}</td>"
        tabel_html += "</tr>"

        # Rând: Suprafață
        tabel_html += "<tr><td class='fw-bold table-light text-start'>Suprafață</td>"
        for ctx in rapoarte_context:
            suprafata = ctx['anunt'].useful_surface
            tabel_html += f"<td>{int(suprafata) if suprafata else '50'} mp</td>"
        tabel_html += "</tr>"

        # Rând: Siguranță AI
        tabel_html += "<tr><td class='fw-bold table-light text-start'>Siguranță AI</td>"
        for ctx in rapoarte_context:
            scor = ctx['scor']
            badge_class = "bg-success" if scor > 70 else ("bg-warning text-dark" if scor > 45 else "bg-danger")
            tabel_html += f"<td><span class='badge {badge_class}'>{scor}%</span></td>"
        tabel_html += "</tr>"

        tabel_html += "</tbody></table></div>"

        # ====================================================
        # 3. CONSTRUIREA CONTEXTULUI AVANSAT PENTRU LLM (GEMINI)
        # ====================================================
        context_proprietati_text = ""
        for idx, ctx in enumerate(rapoarte_context, 1):
            context_proprietati_text += f"\n--- PROPRIETATEA #{idx} ---\n"
            context_proprietati_text += f"Titlu: {ctx['anunt'].title}\n"
            context_proprietati_text += f"Pret în DB: {ctx['anunt'].price} {ctx['anunt'].currency}\n"
            context_proprietati_text += f"Suprafata utila: {ctx['anunt'].useful_surface} mp\n"
            context_proprietati_text += f"Scor de integritate: {ctx['scor']}%\n"
            context_proprietati_text += f"DATE STRUCURATE DIN DETECTIVEAGENT:\n{ctx['detalii_profunde']}\n"
            context_proprietati_text += f"Descriere text originala: {ctx['anunt'].description}\n"

        prompt_llm = f"""
        Ești RentGuru AI, un expert imobiliar din București de elită și un auditor tehnic avansat.
        Sarcina ta este să realizezi o analiză comparativă extrem de nuanțată a proprietăților transmise, punând accent STRICT pe următorul criteriu cerut de utilizator: "{user_criterion}".
        
        Iată datele complete de audit (inclusiv verdictele, alertele 'red flags' și analizele de proximitate extrase de partenerul tău, DetectiveAgent):
        {context_proprietati_text}
        
        Cerințe obligatorii pentru răspuns:
        1. Analizează datele în mod inteligent. Corelează criteriul utilizatorului ("{user_criterion}") cu informațiile din text. De exemplu, dacă cere 'apropiere mall', verifică în analizele de proximitate și descrieri ce mall-uri sau complexe (ex: Plaza, AFI) sunt menționate și explică care e mai aproape. Dacă cere 'zgomot' sau 'metrou', folosește datele specifice din rapoarte.
        2. Scoate în evidență problemele critice raportate în DetectiveAgent (cum ar fi contradicțiile legate de lipsa liftului la etaje superioare sau lipsa garanției) și explică cum influențează ele decizia finală pe baza criteriului ales.
        3. Dacă utilizatorul cere o analiză 'generală', oferă o sinteză echilibrată bazată pe raportul calitate-preț și siguranță.
        4. Răspunsul tău trebuie să fie formatat direct în HTML (folosește doar <strong>, <em>, <br>, <ul>, <li>). NU folosi formatare markdown (fără caractere de tipul asteriscuri sau hashtag-uri).
        """

        # ====================================================
        # 4. APEL LIVE CĂTRE GEMINI PRIN API v1
        # ====================================================
        try:
            api_key = getattr(settings, "GEMINI_API_KEY", "CHEIA_TA_GEMINI_AICI")
            url_gemini = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt_llm}]
                }]
            }
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url_gemini, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                res_data = response.json()
                opinie_ai = res_data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                # Backup stabil pe modelul 1.5-flash
                url_backup = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
                backup_resp = requests.post(url_backup, json=payload, headers=headers, timeout=30)
                if backup_resp.status_code == 200:
                    opinie_ai = backup_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    opinie_ai = "🤖 API Error: Modulul live imobiliar nu a putut returna concluzia din cauza unei erori de conexiune."
                
        except Exception as e_api:
            opinie_ai = f"🤖 Conexiunea live cu serverul AI a eșuat temporar: {e_api}"

        # Tritem rezultatul complet structurat în interfață
        reply_final = (
            f"📊 <strong>Comparație Inteligentă Generată de RentGuru AI:</strong><br>"
            f"Am procesat specificațiile complete în raport cu cerința ta. Iată matricea tehnică extrasă:<br>"
            f"{tabel_html}"
            f"<div class='mt-3 border-top pt-2 text-dark' style='font-size: 0.85rem; line-height: 1.5;'>"
            f"{opinie_ai}"
            f"</div>"
        )

        return JsonResponse({"reply": reply_final})

    except Exception as e:
        return JsonResponse({"reply": f"❌ Eroare la analiza comparativă: {str(e)}"}, status=400)