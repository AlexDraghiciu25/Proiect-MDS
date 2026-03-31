from django.contrib import admin
from .models import Listing, Report

# Înregistrăm modelele pentru a fi vizibile în Dashboard
admin.site.register(Listing)
admin.site.register(Report)