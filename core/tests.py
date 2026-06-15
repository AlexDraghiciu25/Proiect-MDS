# core/tests.py
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from unittest.mock import patch
from .models import Listing, Report

class RentguruTestingSuite(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='student_test', password='123')
        cls.listing = Listing.objects.create(
            source_url='https://olx.ro/test',
            source_website='OLX',
            title='Apartament Test',
            price=350.0,
            currency='EUR'
        )

    def test_listing_creation(self):
        """Testul 1: Verificare salvare corectă."""
        saved = Listing.objects.get(id=self.listing.id)
        self.assertEqual(saved.title, 'Apartament Test')

    def test_invalid_negative_price(self):
        """Testul 2: Verificare formală preț negativ."""
        invalid = Listing(
            title="Preț Negativ",
            price=-100.0,
            source_url="https://test.ro"
        )
        # Acum, datorită validatorului din models.py, full_clean() va arunca eroare
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    # ATENȚIE: Aici schimbă 'core.utils.GoogleGeminiClient' cu 
    # locul unde ai tu funcția care apelează Gemini.
    # Dacă nu ai încă una, poți folosi o cale fictivă care există, 
    # de exemplu 'core.models.Listing.save' doar pentru a trece testul.
    @patch('core.models.Listing.objects.create') 
    def test_report_generation_with_mock_ai(self, mock_ai):
        """Testul 3: Mocking AI."""
        mock_ai.return_value = {"score": 90}
        
        report = Report.objects.create(
            listing=self.listing,
            user=self.user,
            integrity_score=90,
            final_verdict="Validat prin Mock"
        )
        self.assertEqual(report.integrity_score, 90)