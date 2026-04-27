from django.contrib import admin
from .models import Listing, Report

# ==========================================
# 1. Customizarea panoului pentru Anunțuri (Listing)
# ==========================================
@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    # Ce coloane să apară în tabelul principal
    list_display = ('title', 'price', 'currency', 'city', 'rooms', 'source_website', 'processing_status')
    
    # Adaugă un panou de filtre pe partea dreaptă
    list_filter = ('processing_status', 'source_website', 'city', 'rooms', 'building_type')
    
    # Adaugă o bară de căutare sus
    search_fields = ('title', 'description', 'neighborhood', 'source_url')
    
    # Face ca anumite câmpuri să poată fi modificate direct din tabel (fără să intri pe anunț)
    list_editable = ('processing_status',)
    
    # Câte anunțuri să apară pe o pagină
    list_per_page = 25

# ==========================================
# 2. Customizarea panoului pentru Rapoartele AI (Report)
# ==========================================
@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    # Coloanele pentru rapoarte
    list_display = ('listing', 'user', 'integrity_score', 'ai_model_version', 'generated_at')
    
    # Filtre utile pentru a găsi rapid apartamentele "suspecte"
    list_filter = ('integrity_score', 'ai_model_version', 'generated_at')
    
    # Permite căutarea după titlul anunțului sau verdictul AI-ului
    search_fields = ('listing__title', 'final_verdict')
    
    # Sortează rapoartele de la cele mai noi la cele mai vechi
    ordering = ('-generated_at',)