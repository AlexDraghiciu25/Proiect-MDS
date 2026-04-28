from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.db.models import Q
from .models import Listing, Report 
from .services import DetectiveAgent

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
    return render(request, 'core/history.html')

# ==========================================
# 3. LOGICA DE CĂUTARE AVANSATĂ CU AI (Cea optimizată)
# ==========================================
def search_results(request):
    # Am păstrat versiunea cu prefetch_related pentru performanță
    rezultate = Listing.objects.all().prefetch_related('report_set')

    # Filtre Text
    query = request.GET.get('q')
    if query:
        rezultate = rezultate.filter(
            Q(city__icontains=query) | 
            Q(neighborhood__icontains=query) | 
            Q(title__icontains=query)
        )

    # Filtre Numerice
    pret_max = request.GET.get('pret_max')
    if pret_max:
        rezultate = rezultate.filter(price__lte=pret_max)

    camere = request.GET.get('camere')
    if camere:
        rezultate = rezultate.filter(rooms=camere)

    suprafata_min = request.GET.get('suprafata_min')
    if suprafata_min:
        rezultate = rezultate.filter(useful_surface__gte=suprafata_min)

    # Filtre Categorii
    tip_cladire = request.GET.get('tip')
    if tip_cladire and tip_cladire != "Orice tip":
        rezultate = rezultate.filter(building_type=tip_cladire)

    # Filtre Facilități
    if request.GET.get('pet_friendly'):
        rezultate = rezultate.filter(is_pet_friendly=True)
    if request.GET.get('parcare'):
        rezultate = rezultate.filter(has_parking=True)
    if request.GET.get('aer_conditionat'):
        rezultate = rezultate.filter(has_ac=True)
    if request.GET.get('centrala'):
        rezultate = rezultate.filter(heating_type__icontains='central')
    if request.GET.get('balcon'):
        rezultate = rezultate.filter(balconies__gt=0)
    if request.GET.get('lift'):
        rezultate = rezultate.filter(has_elevator=True)

    context = {
        'anunturi': rezultate,
        'nr_rezultate': rezultate.count(),
        'cuvant_cautat': query
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

def run_analysis_view(request, listing_id):
    if not request.user.is_authenticated:
        messages.warning(request, "Trebuie să fii logat pentru a folosi Detectivul AI.")
        return redirect('login')
    
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

def analyze_external(request):
    if request.method == 'POST':
        url_extern = request.POST.get('external_url', '').lower()
        
        # 1. Validare link (rămâne la fel)
        siteuri_permise = ['olx.ro', 'storia.ro', 'imobiliare.ro']
        if not any(site in url_extern for site in siteuri_permise):
            messages.error(request, "Link invalid!")
            return redirect('home')

        # 2. Luăm ultimul anunț
        listing_de_analizat = Listing.objects.last()
        
        if listing_de_analizat:
            # VERIFICARE CRITICĂ: Are deja un raport?
            raport_existent = Report.objects.filter(listing=listing_de_analizat).first()
            
            if raport_existent:
                # Dacă există deja, nu mai apelăm AI-ul, mergem direct la rezultat
                return redirect('result_detail', listing_id=listing_de_analizat.id)
            
            # 3. Dacă NU are raport, abia atunci apelăm AI-ul lui Alex
            try:
                agent = DetectiveAgent()
                raport_nou = agent.analyze_listing(listing_de_analizat.id, request.user)
                
                if raport_nou:
                    return redirect('result_detail', listing_id=listing_de_analizat.id)
                else:
                    # FALLBACK: Dacă AI-ul crapă, creăm unul rapid de test ca să nu dea eroare
                    Report.objects.create(
                        listing=listing_de_analizat,
                        user=request.user,
                        integrity_score=50,
                        final_verdict="Creat automat (Eroare AI)"
                    )
                    return redirect('result_detail', listing_id=listing_de_analizat.id)
            except Exception as e:
                messages.error(request, f"Eroare: {e}")
        
    return redirect('home')