from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Avg
from .models import Listing, Report 
from .services import DetectiveAgent
from .utils import scrape_single_url
from django.utils import timezone
from django.core.paginator import Paginator

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
        # Trimitem și filtrele înapoi pentru a rămâne selectate în interfață
        'filtru_camere': camere,
        'filtru_pret_max': pret_max,
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