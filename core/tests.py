from django.test import TestCase
from django.contrib.auth.models import User
from .models import Listing, Report

class RentguruDatabaseTests(TestCase):
    
    def setUp(self):
        """
        Această metodă rulează ÎNAINTE de fiecare test.
        Aici pregătim terenul: creăm un utilizator și un anunț fals.
        Aceste date trăiesc doar cât timp rulează testul, apoi sunt șterse.
        """
        # 1. Creăm un utilizator de test
        self.user = User.objects.create_user(
            username='agent_test', 
            password='parola_secreta'
        )
        
        # 2. Creăm un anunț imobiliar de test
        self.listing = Listing.objects.create(
            source_url='https://olx.ro/oferta/apartament-test-123.html',
            source_website='OLX',
            title='Apartament 2 camere Dristor',
            price=450.00,
            currency='EUR',
            city='București',
            rooms=2,
            has_ac=True
        )

    def test_listing_is_created_correctly(self):
        """
        TEST 1: Verificăm dacă anunțul s-a salvat corect în baza de date
        și dacă valorile 'default' funcționează.
        """
        # Căutăm anunțul în baza de date
        anunt_salvat = Listing.objects.get(id=self.listing.id)
        
        # Ne asigurăm că datele sunt exact cele pe care le-am introdus
        self.assertEqual(anunt_salvat.title, 'Apartament 2 camere Dristor')
        self.assertEqual(anunt_salvat.price, 450.00)
        self.assertTrue(anunt_salvat.has_ac)
        
        # Verificăm dacă valoarea default pentru status s-a pus automat
        self.assertEqual(anunt_salvat.processing_status, 'PENDING')

    def test_report_links_to_listing(self):
        """
        TEST 2: Verificăm relația complexă dintre tabele.
        Poate agentul AI să genereze un raport atașat acestui anunț?
        """
        # Creăm un raport pentru anunțul din setUp
        report = Report.objects.create(
            listing=self.listing,
            user=self.user,
            integrity_score=85,
            red_flags=["Preț ușor sub media zonei"],
            final_verdict='Anunț valid, dar necesită atenție la vizionare.',
            ai_model_version='gpt-4-turbo'
        )
        
        # Ne asigurăm că raportul este conectat corect la anunț
        self.assertEqual(report.listing.title, 'Apartament 2 camere Dristor')
        
        # Ne asigurăm că anunțul "știe" că are 1 raport atașat (folosind related_name='reports')
        self.assertEqual(self.listing.reports.count(), 1)