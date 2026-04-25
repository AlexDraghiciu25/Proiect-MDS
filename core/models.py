from django.db import models
from django.contrib.auth.models import User

# ==========================================
# 1. MODELUL LISTING (Anunțul Imobiliar)
# ==========================================
class Listing(models.Model):
    # --- ENUMS (Liste de opțiuni predefinite) ---
    STATUS_CHOICES = [('PENDING', 'Așteaptă curățare'), ('PROCESSED', 'Curățat'), ('ERROR', 'Eroare')]
    PARTITIONING_CHOICES = [('decomandat', 'Decomandat'), ('semidecomandat', 'Semidecomandat'), ('nedecomandat', 'Nedecomandat'), ('circular', 'Circular')]
    HEATING_CHOICES = [('centrala_proprie', 'Centrală proprie'), ('centrala_imobil', 'Centrală imobil/bloc'), ('termoficare', 'Termoficare (Radet)'), ('incalzire_electrica', 'Încălzire electrică'), ('calorifere', 'Calorifere')]
    COMFORT_CHOICES = [('1', 'Confort 1'), ('2', 'Confort 2'), ('3', 'Confort 3'), ('lux', 'Lux')]
    FURNISHED_CHOICES = [('mobilat', 'Mobilat (Complet)'), ('partial', 'Parțial mobilat'), ('nemobilat', 'Nemobilat')]
    BUILDING_TYPE_CHOICES = [('bloc', 'Bloc de apartamente'), ('casa', 'Casă/Vilă')]
    STRUCTURE_CHOICES = [('beton', 'Beton'), ('caramida', 'Cărămidă'), ('bca', 'BCA'), ('lemn', 'Lemn')]
    ENERGY_CLASS_CHOICES = [('A', 'Clasa A'), ('B', 'Clasa B'), ('C', 'Clasa C'), ('D', 'Clasa D'), ('E', 'Clasa E'), ('F', 'Clasa F'), ('G', 'Clasa G')]

    # --- IDENTIFICATORI ---
    source_url = models.URLField(max_length=500, unique=True)
    source_website = models.CharField(max_length=50, default='Necunoscut')

    # --- ZONA TAMPON (JSON Data Lake) ---
    raw_data = models.JSONField(default=dict, blank=True, null=True)
    processing_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # --- DATE GENERALE ---
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default='EUR')
    property_destination = models.CharField(max_length=50, null=True, blank=True)
    rental_period = models.CharField(max_length=50, null=True, blank=True)
    availability = models.CharField(max_length=100, null=True, blank=True)
    
    # --- LOCAȚIE ---
    city = models.CharField(max_length=100, null=True, blank=True)
    neighborhood = models.CharField(max_length=100, null=True, blank=True) 

    # --- CARACTERISTICI IMOBIL ---
    rooms = models.IntegerField(null=True, blank=True)
    bathrooms = models.IntegerField(null=True, blank=True)
    kitchens = models.IntegerField(null=True, blank=True, default=1)
    balconies = models.IntegerField(null=True, blank=True) 
    useful_surface = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    floor = models.CharField(max_length=50, null=True, blank=True)
    total_floors = models.IntegerField(null=True, blank=True)
    construction_year = models.IntegerField(null=True, blank=True)
    partitioning = models.CharField(max_length=50, choices=PARTITIONING_CHOICES, null=True, blank=True)
    comfort_level = models.CharField(max_length=50, choices=COMFORT_CHOICES, null=True, blank=True)
    building_type = models.CharField(max_length=50, choices=BUILDING_TYPE_CHOICES, null=True, blank=True)
    building_structure = models.CharField(max_length=50, choices=STRUCTURE_CHOICES, null=True, blank=True)
    furnishing_state = models.CharField(max_length=50, choices=FURNISHED_CHOICES, null=True, blank=True)

    # --- UTILITĂȚI ȘI CONTORIZARE ---
    heating_type = models.CharField(max_length=50, choices=HEATING_CHOICES, null=True, blank=True)
    has_underfloor_heating = models.BooleanField(default=False)
    has_gas = models.BooleanField(default=False)
    has_electricity = models.BooleanField(default=False)
    has_water = models.BooleanField(default=False)
    has_sewage = models.BooleanField(default=False)
    has_gas_meter = models.BooleanField(default=False)
    has_water_meter = models.BooleanField(default=False)
    has_heat_meter = models.BooleanField(default=False)
    internet_type = models.CharField(max_length=100, null=True, blank=True)

    # --- FINISAJE ---
    flooring = models.CharField(max_length=100, null=True, blank=True)
    windows = models.CharField(max_length=100, null=True, blank=True)
    interior_doors = models.CharField(max_length=50, null=True, blank=True)
    entrance_door = models.CharField(max_length=50, null=True, blank=True)
    walls = models.CharField(max_length=100, null=True, blank=True)
    thermal_insulation = models.CharField(max_length=100, null=True, blank=True)

    # --- ELECTROCASNICE ---
    has_fridge = models.BooleanField(default=False)
    has_washing_machine = models.BooleanField(default=False)
    has_dishwasher = models.BooleanField(default=False)
    has_tv = models.BooleanField(default=False)
    has_oven = models.BooleanField(default=False)
    has_microwave = models.BooleanField(default=False)
    has_hood = models.BooleanField(default=False)
    has_ac = models.BooleanField(default=False)

    # --- FACILITĂȚI IMOBIL & EXTERIOR ---
    has_intercom = models.BooleanField(default=False)
    has_elevator = models.BooleanField(default=False)
    has_video_surveillance = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    is_pet_friendly = models.BooleanField(default=False)
    street_paved = models.BooleanField(default=False)
    street_lit = models.BooleanField(default=False)
    near_public_transit = models.BooleanField(default=False)

    # --- DETALII TEHNICE ȘI JURIDICE ---
    energy_class = models.CharField(max_length=2, choices=ENERGY_CLASS_CHOICES, null=True, blank=True)
    vices = models.TextField(null=True, blank=True)

    # --- METADATE ---
    data_completeness_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        title_display = self.title if self.title else "Anunț neprocesat"
        return f"[{self.processing_status}] {self.source_website} - {title_display}"

# ==========================================
# 2. MODELUL REPORT (Creierul AI)
# ==========================================
class Report(models.Model):
    # --- Relații ---
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='reports')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_reports')
    
    # --- Analiză AI ---
    integrity_score = models.IntegerField(default=0) 
    red_flags = models.JSONField(default=list) 
    proximity_analysis = models.TextField(blank=True, null=True) 
    final_verdict = models.TextField()
    
    # --- Metadate Tehnice AI ---
    ai_model_version = models.CharField(max_length=100, null=True, blank=True, help_text="Ex: gpt-4-turbo-2024-04-09")
    token_usage = models.IntegerField(default=0, help_text="Numărul total de tokeni consumați pentru acest raport")
    
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for Listing ID {self.listing.id} | Score: {self.integrity_score} | User: {self.user.username}"