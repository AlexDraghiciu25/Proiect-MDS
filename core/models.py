from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator

# 1. MODELUL LISTING (Anunțul Imobiliar)
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

    # --- DEFINIREA STĂRILOR PENTRU BOOLEENE ---
    STARI_DOTARI = (
        (True, 'Da'),
        (False, 'Nu'),
        (None, 'Nemenționat (NULL)'),
    )

    # --- IDENTIFICATORI ---
    source_url = models.URLField(max_length=500, unique=True)
    source_website = models.CharField(max_length=50, default='Necunoscut')

    # --- ZONA TAMPON (JSON Data Lake) ---
    raw_data = models.JSONField(default=dict, blank=True, null=True)
    processing_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # --- DATE GENERALE ---
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0.0)])
    currency = models.CharField(max_length=10, default='EUR')
    property_destination = models.CharField(max_length=50, null=True, blank=True)
    rental_period = models.CharField(max_length=50, null=True, blank=True)
    availability = models.CharField(max_length=100, null=True, blank=True)
    
    # --- LOCATIE ---
    city = models.CharField(max_length=100, null=True, blank=True)
    neighborhood = models.CharField(max_length=100, null=True, blank=True) 

    # --- LOCATIE GPS (NOU) ---
    latitude = models.FloatField(null=True, blank=True, help_text="Latitudine extrasă din sursă")
    longitude = models.FloatField(null=True, blank=True, help_text="Longitudine extrasă din sursă")

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

    # --- UTILITATI SI CONTORIZARE ---
    heating_type = models.CharField(max_length=50, choices=HEATING_CHOICES, null=True, blank=True)
    has_underfloor_heating = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_gas = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_electricity = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_water = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_sewage = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_gas_meter = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_water_meter = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_heat_meter = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    internet_type = models.CharField(max_length=100, null=True, blank=True)

    # --- FINISAJE ---
    flooring = models.CharField(max_length=100, null=True, blank=True)
    windows = models.CharField(max_length=100, null=True, blank=True)
    interior_doors = models.CharField(max_length=50, null=True, blank=True)
    entrance_door = models.CharField(max_length=50, null=True, blank=True)
    walls = models.CharField(max_length=100, null=True, blank=True)
    thermal_insulation = models.CharField(max_length=100, null=True, blank=True)

    # --- ELECTROCASNICE ---
    has_fridge = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_washing_machine = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_dishwasher = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_tv = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_oven = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_microwave = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_hood = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_ac = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)

    # --- FACILITATI IMOBIL & EXTERIOR ---
    has_intercom = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_elevator = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_video_surveillance = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    has_parking = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    is_pet_friendly = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    street_paved = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    street_lit = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)
    near_public_transit = models.BooleanField(null=True, blank=True, choices=STARI_DOTARI, default=None)

    # --- DETALII TEHNICE ---
    energy_class = models.CharField(max_length=2, choices=ENERGY_CLASS_CHOICES, null=True, blank=True)
    vices = models.TextField(null=True, blank=True)

    # --- METADATE ---
    data_completeness_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        title_display = self.title if self.title else "Anunț neprocesat"
        return f"[{self.processing_status}] {self.source_website} - {title_display}"

# 2. MODELUL REPORT 
class Report(models.Model):
    # --- Relaii ---
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='reports')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_reports')
    
    # --- Analiză AI ---
    integrity_score = models.IntegerField(default=0) 
    red_flags = models.JSONField(default=list) 
    proximity_analysis = models.TextField(blank=True, null=True) 
    final_verdict = models.TextField()
    price_analysis = models.JSONField(null=True, blank=True)
    distance_verification = models.JSONField(default=list, blank=True, null=True)

    # --- Metadate Tehnice AI ---
    ai_model_version = models.CharField(max_length=100, null=True, blank=True, help_text="Ex: gpt-4-turbo-2024-04-09")
    token_usage = models.IntegerField(default=0, help_text="Numărul total de tokeni consumați pentru acest raport")
    
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for Listing ID {self.listing.id} | Score: {self.integrity_score} | User: {self.user.username}"
    
    @receiver(post_save, sender="core.Report") 
    def limit_user_history(sender, instance, created, **kwargs):
        if created:
            user = instance.user
            max_reports = 60
            
            # Importăm modelul aici, în interiorul funcției, pentru a evita "circular import"
            from .models import Report 
            
            old_reports_ids = Report.objects.filter(user=user) \
                                            .order_by('-generated_at')[max_reports:] \
                                            .values_list('id', flat=True)
            
            if old_reports_ids:
                Report.objects.filter(id__in=old_reports_ids).delete()