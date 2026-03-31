from django.db import models
from django.contrib.auth.models import User

# 1. Modelul pentru Anunțurile Imobiliare (Datele brute)
class Listing(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    location_text = models.CharField(max_length=255)
    source_url = models.URLField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

# 2. Modelul pentru Rapoartele generate de AI
class Report(models.Model):
    # Legăm raportul de un anunț specific și de utilizatorul care l-a generat
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='reports')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_reports')
    
    # Rezultatele de la Detective Agent
    integrity_score = models.IntegerField(default=0) # Scor 0-100
    red_flags = models.JSONField(default=list) # Listă de probleme: ["Preț suspect", "Poze ireale"]
    
    # Rezultatele de la Oracle Agent
    proximity_analysis = models.TextField(blank=True, null=True) # Analiza zonă/facilități
    
    # Verdictul final AI
    final_verdict = models.TextField()
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.listing.title} - Score: {self.integrity_score}"