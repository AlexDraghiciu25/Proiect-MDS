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
from google import genai
from django.conf import settings
import requests

# Importăm ambele comenzi de scraping pentru a le putea rula instant la cerere manuală
from core.management.commands.scrape_olx import Command as OlxScraper
# Ajustează calea de mai jos dacă fișierul tău de Storia are altă denumire sau locație
try:
    from core.management.commands.scrape_storia import Command as StoriaScraper
except ImportError:
    StoriaScraper = None

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
# 3. LOGICA DE CĂUTARE AVANSATĂ CU AI
# ==========================================
def search_results(request):
    rezultate = Listing.objects.all().prefetch_related('reports')

    query = request.GET.get('q', '').strip()
    if query:
        rezultate = rezultate.filter(
            Q(city__icontains=query) | 
            Q(neighborhood__icontains=query) | 
            Q(title__icontains=query) |
            Q(description__icontains=query)
        )

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

    statistici = rezultate.aggregate(
        pret_mediu=Avg('price'),
        suprafata_medie=Avg('useful_surface')
    )
    
    pret_per_mp = 0
    if statistici['pret_mediu'] and statistici['suprafata_medie']:
        pret_per_mp = statistici['pret_mediu'] / statistici['suprafata_medie']

    rezultate = rezultate.order_by('-id')
    moneda_selectata = request.GET.get('moneda', 'Toate').strip()
    CURS_EUR_RON = 5.0

    for anunt in rezultate:
        moneda_reala = str(anunt.currency).upper()
        pret_brut = float(anunt.price) if anunt.price else 0.0
        
        if "EUR" in moneda_reala or "€" in moneda_reala or pret_brut < 1500:
            valuta_originala = "EUR"
        else:
            valuta_originala = "RON"

        if moneda_selectata == "EUR":
            if valuta_originala == "RON":
                anunt.pret_afisat = pret_brut / CURS_EUR_RON
            else:
                anunt.pret_afisat = pret_brut
            anunt.moneda_afisata = "€"
        elif moneda_selectata == "RON":
            if valuta_originala == "EUR":
                anunt.pret_afisat = pret_brut * CURS_EUR_RON
            else:
                anunt.pret_afisat = pret_brut
            anunt.moneda_afisata = "RON"
        else:
            anunt.pret_afisat = pret_brut
            anunt.moneda_afisata = "€" if valuta_originala == "EUR" else "RON"

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
        'filtru_moneda': moneda_selectata,
    }
    return render(request, 'core/search_results.html', context)

# ==========================================
# 4. PAGINA DE DETALII ȘI ANALIZĂ AI
# ==========================================
def result_detail_view(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id)
    report = Report.objects.filter(listing=listing).first()
    return render(request, 'core/result.html', {
        'listing': listing,
        'report': report
    })

@login_required
def run_analysis_view(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id)
    existing_report = Report.objects.filter(listing=listing).first()
    
    if existing_report:
        return redirect('result_detail', listing_id=listing.id)

    agent = DetectiveAgent()
    report = agent.analyze_listing(listing_id, request.user)
    
    if report:
        return redirect('result_detail', listing_id=listing.id)
    else:
        messages.error(request, "Analiza AI a eșuat. Verifică cheia API.")
        return redirect('home')

# ==========================================
# 5. [UNIFICAT] ANALIZĂ DIRECTĂ PRIN URL MANUAL (DASHBOARD)
# ==========================================
@login_required
def analyze_external(request):
    if request.method == 'POST':
        url_extern = request.POST.get('external_url', '').strip()
        url_lower = url_extern.lower()
        
        # 1. Căutăm dacă anunțul există deja în baza de date
        listing = Listing.objects.filter(source_url=url_extern).first()
        
        # 2. Dacă NU există, executăm comanda de Django direct din cod
        if not listing:
            messages.info(request, "Anunț nou detectat. Pornim scanarea instatanee...")
            try:
                if "olx.ro" in url_lower:
                    print("-> [RentGuru Engine] Rulăm comanda nativă de scraping pentru OLX...")
                    scraper_olx = OlxScraper()
                    # Dacă în handle ai logica directă, o apelăm direct cu URL ca parametru custom
                    # Dacă scraperul tău vechi folosea o metodă internă, o poți lăsa pe aceea, 
                    # dar handle() apelat direct e cel mai sigur:
                    try:
                        scraper_olx.proceseaza_anunt_olx(None, url_extern)
                    except AttributeError:
                        # Fallback dacă logica e direct în handle
                        scraper_olx.handle(url=url_extern)
                    
                elif "storia.ro" in url_lower:
                    if StoriaScraper:
                        print("-> [RentGuru Engine] Rulăm comanda nativă de scraping pentru Storia...")
                        scraper_storia = StoriaScraper()
                        
                        # Încercăm să apelăm handle direct sau metode alternative flexibile
                        # pentru a nu mai crăpa indiferent de cum ai numit funcția în interior
                        try:
                            if hasattr(scraper_storia, 'proceseaza_anunt_storia'):
                                scraper_storia.proceseaza_anunt_storia(None, url_extern)
                            elif hasattr(scraper_storia, 'proceseaza_anunt_olx'):
                                # Uneori rămâne denumirea de la OLX din cauza copy-paste-ului
                                scraper_storia.proceseaza_anunt_olx(None, url_extern)
                            else:
                                # Dacă e scrisă direct în handle sau altă metodă generică
                                scraper_storia.handle(url=url_extern)
                        except Exception as e_inner:
                            print(f"-> Încercare fallback direct prin handle: {e_inner}")
                            # Execuție directă prin handle ca fail-safe suprem
                            scraper_storia.handle(url=url_extern)
                    else:
                        messages.error(request, "Modulul de scraping pentru Storia nu este configurat.")
                        return redirect('home')
                else:
                    messages.error(request, "RentGuru acceptă doar link-uri valide de pe OLX.ro sau Storia.ro.")
                    return redirect('home')

                # Re-extragem din DB anunțul proaspăt descărcat de scraper
                listing = Listing.objects.filter(source_url=url_extern).first()

            except Exception as e_scrape:
                print(f"❌ [Scrape Error] Eșec la descărcarea instantă: {e_scrape}")
                messages.error(request, "Nu s-a putut descărca anunțul. Asigură-te că link-ul este activ.")
                return redirect('home')

        if not listing:
            messages.error(request, "Scraper-ul nu a putut salva datele anunțului în baza de date.")
            return redirect('home')

        # 3. FLUXUL HIBRID UNIC: Rulăm imediat și AI-ul în aceeași încărcare!
        report = Report.objects.filter(listing=listing).first()
        
        if not report:
            listing.refresh_from_db()
            messages.info(request, "Generăm raportul AI...")
            try:
                agent = DetectiveAgent()
                report = agent.analyze_listing(listing.id, request.user)
                
                if not report:
                    messages.error(request, "AI-ul a extras datele brute dar nu a putut compila raportul.")
                    return redirect('home')
            except Exception as e_ai:
                print(f"❌ [Gemini Error] Analiza directă a eșuat:\n{e_ai}")
                messages.error(request, f"Eroare la procesarea AI instantanee: {e_ai}")
                return redirect('home')

        # Redirecționăm direct către raport dintr-o singură mișcare!
        return redirect('result_detail', listing_id=listing.id)
        
    return redirect('home')

# ==========================================
# 6. UNIVERSAL AI CHAT ASSISTANT
# ==========================================
def ai_chat_endpoint(request):
    if request.method != "POST":
        return JsonResponse({"reply": "Metodă nepermisă"}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        id_uri_anunturi = data.get("active_listings", [])

        if not user_message:
            return JsonResponse({"reply": "⚠️ Te rog să introduci un mesaj sau o întrebare pentru RentGuru AI."})

        are_anunturi = len(id_uri_anunturi) >= 1
        tabel_html = ""
        context_proprietati_text = ""

        if are_anunturi:
            anunturi = Listing.objects.filter(id__in=id_uri_anunturi)
            rapoarte_context = []
            agent_real = DetectiveAgent()

            for anunt in anunturi:
                raport = Report.objects.filter(listing_id=anunt.id).first()
                if not raport:
                    try:
                        raport = agent_real.analyze_listing(anunt.id, request.user)
                    except Exception as ex_agent:
                        print(f"Eroare la apelarea DetectiveAgent: {ex_agent}")
                
                if hasattr(anunt, '_prefetched_objects_cache'):
                    anunt._prefetched_objects_cache = {}
                anunt.refresh_from_db()

                context_analiza_ta = ""
                if raport:
                    context_analiza_ta += f"Verdict Final: {getattr(raport, 'final_verdict', '')}\n"
                    context_analiza_ta += f"Analiză de Proximitate: {getattr(raport, 'proximity_analysis', '')}\n"
                    flags = getattr(raport, 'red_flags', [])
                    context_analiza_ta += f"Red Flags: {', '.join(flags) if isinstance(flags, list) else flags}\n"
                    context_analiza_ta += f"Analiză de Preț: {getattr(raport, 'price_analysis', '')}\n"

                rapoarte_context.append({
                    "anunt": anunt,
                    "scor": raport.integrity_score if raport else 70, 
                    "detalii_profunde": context_analiza_ta
                })

            tabel_html = """
            <div class="table-responsive mt-2">
                <table class="table table-sm table-bordered bg-white text-center align-middle" style="font-size: 0.8rem; border-radius: 6px; overflow: hidden;">
                    <thead class="table-dark">
                        <tr><th>Caracteristică</th>
            """
            for idx, ctx in enumerate(rapoarte_context, 1):
                tabel_html += f"<th>Proprietatea #{idx}</th>"
            tabel_html += "</tr></thead><tbody><tr><td class='fw-bold table-light text-start'>Titlu</td>"
            for ctx in rapoarte_context:
                tabel_html += f"<td class='text-truncate' style='max-width: 130px;' title='{ctx['anunt'].title}'>{ctx['anunt'].title}</td>"
            tabel_html += "</tr><tr><td class='fw-bold table-light text-start'>Preț</td>"
            for ctx in rapoarte_context:
                moneda = "€" if "EUR" in str(ctx['anunt'].currency).upper() or ctx['anunt'].price < 1500 else "RON"
                tabel_html += f"<td class='fw-bold text-success'>{int(ctx['anunt'].price) if ctx['anunt'].price else 'N/A'} {moneda}</td>"
            tabel_html += "</tr><tr><td class='fw-bold table-light text-start'>Suprafață</td>"
            for ctx in rapoarte_context:
                tabel_html += f"<td>{int(ctx['anunt'].useful_surface) if ctx['anunt'].useful_surface else '50'} mp</td>"
            tabel_html += "</tr><tr><td class='fw-bold table-light text-start'>Siguranță AI</td>"
            for ctx in rapoarte_context:
                scor = ctx['scor']
                badge = "bg-success" if scor > 70 else ("bg-warning text-dark" if scor > 45 else "bg-danger")
                tabel_html += f"<td><span class='badge {badge}'>{scor}%</span></td>"
            tabel_html += "</tr></tbody></table></div>"

            for idx, ctx in enumerate(rapoarte_context, 1):
                context_proprietati_text += f"\n--- PROPRIETATEA #{idx} ---\n"
                context_proprietati_text += f"Titlu: {ctx['anunt'].title}\n"
                context_proprietati_text += f"DATE AUDIT:\n{ctx['detalii_profunde']}\n"

        if are_anunturi:
            prompt_llm = f"""
            Ești RentGuru AI, un expert imobiliar din București de elită.
            Utilizatorul a selectat câteva proprietăți din listă și te întreabă următorul lucru: "{user_message}".
            
            Datele tehnice ale proprietăților selectate:
            {context_proprietati_text}
            
            Cerințe:
            1. Răspunde direct la întrebarea utilizatorului ("{user_message}") analizând proprietățile oferite.
            2. Formatează răspunsul exclusiv în HTML curat (folosește <strong>, <br>, <ul>, <li>). Fără markdown standard (fără ***, fără ```html).
            """
        else:
            prompt_llm = f"""
            Ești RentGuru AI, un asistent virtual inteligent, expert în piața imobiliară din România (în special București) și consultanță juridică/tehnică pentru chiriași.
            Utilizatorul nu are proprietăți selectate acum, ci îți adresează o întrebare generală de consultanță: "{user_message}".
            
            Cerințe:
            1. Oferă un răspuns profesionist, detaliat și extrem de util la întrebarea: "{user_message}".
            2. Dacă întrebarea nu are nicio legătură cu imobiliarele, chiriile, Bucureștiul sau aspectele conexe, redirecționează politicos discuția spre zona imobiliară.
            3. Formatează răspunsul exclusiv în HTML curat (folosește <strong>, <br>, <ul>, <li>). Fără markdown standard. Păstrează un ton prietenos dar avizat.
            """

        try:
            api_key = getattr(settings, "GEMINI_API_KEY", "CHEIA_TA_AICI")
            client = genai.Client(api_key=api_key)
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_llm,
            )
            opinie_ai = response.text
        except Exception as e_api:
            print(f"Eroare GenAI API: {e_api}")
            opinie_ai = f"🤖 Asistentul RentGuru întâmpină probleme tehnice. Detalii: {str(e_api)[:100]}"

        if are_anunturi:
            reply_final = (
                f"📊 <strong>Analiză Personalizată RentGuru AI pentru proprietățile selectate:</strong><br>"
                f"{tabel_html}"
                f"<div class='mt-3 border-top pt-2 text-dark' style='font-size: 0.85rem; line-height: 1.5;'>"
                f"{opinie_ai}"
                f"</div>"
            )
        else:
            reply_final = (
                f"🤖 <strong>RentGuru AI Consultant Imobiliar:</strong><br>"
                f"<div class='mt-2 text-dark' style='font-size: 0.85rem; line-height: 1.5;'>"
                f"{opinie_ai}"
                f"</div>"
            )

        return JsonResponse({"reply": reply_final})

    except Exception as e:
        return JsonResponse({"reply": f"❌ Eroare la procesarea chatului: {str(e)}"}, status=400)