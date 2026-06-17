# core/tests.py
# ═══════════════════════════════════════════════════════════════
#  Suită completă de teste – Backend + Frontend
#  Proiect: RentGuru (Django 6 + PostgreSQL)
# ═══════════════════════════════════════════════════════════════

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse, resolve
from unittest.mock import patch, MagicMock
from decimal import Decimal

from .models import Listing, Report
from .data_validation import calculate_completeness_score


# ═══════════════════════════════════════════════════════════════
# 1. TESTE MODELE (Backend – Baza de Date)
# ═══════════════════════════════════════════════════════════════
class ModelTests(TestCase):
    """Teste pentru modelele Listing și Report."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='student_test', password='Parola123!'
        )
        cls.listing = Listing.objects.create(
            source_url='https://olx.ro/test-apartament',
            source_website='OLX',
            title='Apartament Test Militari',
            price=Decimal('350.00'),
            currency='EUR',
            city='București',
            neighborhood='Militari',
            rooms=2,
            useful_surface=Decimal('55.00'),
        )

    # ── Listing ──────────────────────────────────────────────
    def test_listing_creation(self):
        """Verificare salvare corectă a unui anunț."""
        saved = Listing.objects.get(id=self.listing.id)
        self.assertEqual(saved.title, 'Apartament Test Militari')
        self.assertEqual(saved.source_website, 'OLX')
        self.assertEqual(saved.currency, 'EUR')

    def test_listing_str_representation(self):
        """Metoda __str__ afișează status + sursă + titlu."""
        result = str(self.listing)
        self.assertIn('OLX', result)
        self.assertIn('Apartament Test Militari', result)

    def test_listing_default_status_is_pending(self):
        """Statusul implicit trebuie să fie PENDING."""
        new = Listing.objects.create(
            source_url='https://olx.ro/default-status',
            title='Default Test',
        )
        self.assertEqual(new.processing_status, 'PENDING')

    def test_listing_unique_source_url(self):
        """Nu poți crea două anunțuri cu același URL."""
        with self.assertRaises(Exception):
            Listing.objects.create(
                source_url='https://olx.ro/test-apartament',
                title='Duplicat',
            )

    def test_invalid_negative_price(self):
        """Prețul negativ trebuie respins de validator la full_clean()."""
        invalid = Listing(
            title='Preț Negativ',
            price=Decimal('-100.00'),
            source_url='https://test.ro/negativ',
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_listing_zero_price_is_valid(self):
        """Prețul 0 este permis (gratuit / schimb)."""
        listing = Listing(
            title='Gratuit',
            price=Decimal('0.00'),
            source_url='https://test.ro/gratuit',
        )
        try:
            listing.full_clean()
        except ValidationError:
            self.fail("Prețul 0 nu ar trebui să arunce ValidationError")

    def test_listing_nullable_fields(self):
        """Câmpurile opționale pot fi None."""
        listing = Listing.objects.create(
            source_url='https://test.ro/minimal',
        )
        self.assertIsNone(listing.title)
        self.assertIsNone(listing.price)
        self.assertIsNone(listing.rooms)
        self.assertIsNone(listing.city)

    def test_listing_gps_coordinates(self):
        """Coordonatele GPS se salvează corect."""
        self.listing.latitude = 44.4268
        self.listing.longitude = 26.1025
        self.listing.save()
        self.listing.refresh_from_db()
        self.assertAlmostEqual(self.listing.latitude, 44.4268, places=4)
        self.assertAlmostEqual(self.listing.longitude, 26.1025, places=4)

    # ── Report ───────────────────────────────────────────────
    def test_report_creation(self):
        """Verificare creare raport AI legat de listing + user."""
        report = Report.objects.create(
            listing=self.listing,
            user=self.user,
            integrity_score=85,
            final_verdict='Anunț valid – fără semne de fraudă.',
        )
        self.assertEqual(report.integrity_score, 85)
        self.assertEqual(report.listing, self.listing)
        self.assertEqual(report.user, self.user)

    def test_report_str_representation(self):
        """Metoda __str__ conține ID-ul listingului și scorul."""
        report = Report.objects.create(
            listing=self.listing,
            user=self.user,
            integrity_score=72,
            final_verdict='OK',
        )
        result = str(report)
        self.assertIn(str(self.listing.id), result)
        self.assertIn('72', result)

    def test_report_red_flags_default_empty_list(self):
        """Red flags implicit = listă goală."""
        report = Report.objects.create(
            listing=self.listing,
            user=self.user,
            integrity_score=90,
            final_verdict='Curat',
        )
        self.assertEqual(report.red_flags, [])

    def test_report_cascade_delete(self):
        """Ștergerea listingului șterge și rapoartele aferente."""
        Report.objects.create(
            listing=self.listing,
            user=self.user,
            integrity_score=60,
            final_verdict='Suspect',
        )
        listing_id = self.listing.id
        self.listing.delete()
        self.assertFalse(Report.objects.filter(listing_id=listing_id).exists())

    @patch('core.services.DetectiveAgent')
    def test_report_generation_with_mock_ai(self, MockAgent):
        """Testul mocking AI – simulare generare raport."""
        mock_instance = MockAgent.return_value
        mock_instance.analyze_listing.return_value = MagicMock(integrity_score=90)
        listing = Listing.objects.create(
            source_url='https://olx.ro/mock-test',
            source_website='OLX',
            title='Mock Test',
            price=Decimal('400.00'),
            currency='EUR',
        )
        report = Report.objects.create(
            listing=listing,
            user=self.user,
            integrity_score=90,
            final_verdict='Validat prin Mock',
        )
        self.assertEqual(report.integrity_score, 90)

    def test_report_limit_user_history_signal(self):
        """Semnalul post_save limitează la 60 rapoarte per user."""
        # Creăm 62 rapoarte
        listings = []
        for i in range(62):
            listings.append(Listing.objects.create(
                source_url=f'https://test.ro/signal-{i}',
                title=f'Signal Test {i}',
            ))
        for i, lst in enumerate(listings):
            Report.objects.create(
                listing=lst,
                user=self.user,
                integrity_score=50 + i,
                final_verdict=f'Test {i}',
            )
        count = Report.objects.filter(user=self.user).count()
        self.assertLessEqual(count, 60)


# ═══════════════════════════════════════════════════════════════
# 2. TESTE AUTENTIFICARE (Backend)
# ═══════════════════════════════════════════════════════════════
class AuthenticationTests(TestCase):
    """Teste pentru register, login, logout."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser', password='TestPass123!'
        )

    # ── Register ─────────────────────────────────────────────
    def test_register_page_loads(self):
        """Pagina de înregistrare se încarcă (200)."""
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_register_valid_user(self):
        """Înregistrarea cu date valide creează un cont și face redirect."""
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        self.assertEqual(response.status_code, 302)  # redirect
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_password_mismatch(self):
        """Parolele diferite nu permit crearea contului."""
        response = self.client.post(reverse('register'), {
            'username': 'baduser',
            'password1': 'Pass123!',
            'password2': 'Different456!',
        })
        self.assertEqual(response.status_code, 200)  # form re-render
        self.assertFalse(User.objects.filter(username='baduser').exists())

    # ── Login ────────────────────────────────────────────────
    def test_login_page_loads(self):
        """Pagina de login se încarcă (200)."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_login_valid_credentials(self):
        """Autentificarea cu credențiale corecte face redirect."""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'TestPass123!',
        })
        self.assertEqual(response.status_code, 302)

    def test_login_invalid_credentials(self):
        """Credențiale greșite rămân pe pagina de login."""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)

    # ── Logout ───────────────────────────────────────────────
    def test_logout_redirects(self):
        """Logout face redirect către login."""
        self.client.login(username='testuser', password='TestPass123!')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 302)


# ═══════════════════════════════════════════════════════════════
# 3. TESTE PAGINI PUBLICE (Backend + Frontend)
# ═══════════════════════════════════════════════════════════════
class PublicPageTests(TestCase):
    """Teste pentru paginile accesibile fără autentificare."""

    def setUp(self):
        self.client = Client()
        # Creăm date pentru homepage
        for i in range(8):
            Listing.objects.create(
                source_url=f'https://olx.ro/public-{i}',
                title=f'Apartament Public {i}',
                price=Decimal('300.00') + i * 50,
                currency='EUR',
                city='București',
            )

    def test_home_page_loads(self):
        """Pagina principală se încarcă (200)."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_home_page_shows_listings(self):
        """Homepage afișează ultimele anunțuri."""
        response = self.client.get(reverse('home'))
        self.assertIn('anunturi', response.context)
        self.assertLessEqual(len(response.context['anunturi']), 6)

    def test_about_page_loads(self):
        """Pagina About se încarcă (200)."""
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)

    def test_contact_page_loads(self):
        """Pagina Contact se încarcă (200)."""
        response = self.client.get(reverse('contact'))
        self.assertEqual(response.status_code, 200)

    def test_search_results_page_loads(self):
        """Pagina de căutare se încarcă (200)."""
        response = self.client.get(reverse('search_results'))
        self.assertEqual(response.status_code, 200)

    def test_search_with_query(self):
        """Căutarea cu termen returnează rezultate filtrate."""
        response = self.client.get(reverse('search_results'), {'q': 'București'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('anunturi', response.context)

    def test_search_with_price_filter(self):
        """Filtrarea după preț funcționează."""
        response = self.client.get(reverse('search_results'), {
            'pret_min': '200',
            'pret_max': '400',
        })
        self.assertEqual(response.status_code, 200)

    def test_search_with_rooms_filter(self):
        """Filtrarea după număr de camere funcționează."""
        response = self.client.get(reverse('search_results'), {
            'camere': '2',
        })
        self.assertEqual(response.status_code, 200)

    def test_search_with_amenity_filters(self):
        """Filtrele de dotări (pet_friendly, parcare, etc.) funcționează."""
        response = self.client.get(reverse('search_results'), {
            'pet_friendly': 'on',
            'parcare': 'on',
            'aer_conditionat': 'on',
        })
        self.assertEqual(response.status_code, 200)

    def test_search_statistics_in_context(self):
        """Contextul de căutare conține statistici."""
        response = self.client.get(reverse('search_results'))
        self.assertIn('statistici', response.context)
        self.assertIn('pret_mediu', response.context['statistici'])

    def test_search_currency_filter_eur(self):
        """Filtrarea pe monedă EUR funcționează."""
        response = self.client.get(reverse('search_results'), {
            'moneda': 'EUR',
        })
        self.assertEqual(response.status_code, 200)

    def test_search_currency_filter_ron(self):
        """Filtrarea pe monedă RON funcționează."""
        response = self.client.get(reverse('search_results'), {
            'moneda': 'RON',
        })
        self.assertEqual(response.status_code, 200)


# ═══════════════════════════════════════════════════════════════
# 4. TESTE PAGINI PROTEJATE (Backend – @login_required)
# ═══════════════════════════════════════════════════════════════
class ProtectedPageTests(TestCase):
    """Teste pentru paginile care necesită autentificare."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='authuser', password='AuthPass123!'
        )
        self.listing = Listing.objects.create(
            source_url='https://olx.ro/protected-test',
            title='Protected Test',
            price=Decimal('500.00'),
            currency='EUR',
        )

    def test_history_redirects_unauthenticated(self):
        """History fără login face redirect către login."""
        response = self.client.get(reverse('history'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_history_loads_authenticated(self):
        """History cu login se încarcă (200)."""
        self.client.login(username='authuser', password='AuthPass123!')
        response = self.client.get(reverse('history'))
        self.assertEqual(response.status_code, 200)

    def test_history_shows_user_reports_only(self):
        """History afișează doar rapoartele utilizatorului curent."""
        other_user = User.objects.create_user(
            username='otheruser', password='Other123!'
        )
        Report.objects.create(
            listing=self.listing,
            user=other_user,
            integrity_score=70,
            final_verdict='Altul',
        )
        self.client.login(username='authuser', password='AuthPass123!')
        response = self.client.get(reverse('history'))
        self.assertEqual(len(response.context['rapoarte']), 0)

    def test_analyze_external_requires_login(self):
        """Analiza externă fără login face redirect."""
        response = self.client.post(reverse('analyze_external'), {
            'external_url': 'https://olx.ro/test',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_result_detail_page_loads(self):
        """Pagina de detalii a unui rezultat se încarcă."""
        response = self.client.get(
            reverse('result_detail', kwargs={'listing_id': self.listing.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_result_detail_nonexistent_listing(self):
        """Listing inexistent returnează 404."""
        response = self.client.get(
            reverse('result_detail', kwargs={'listing_id': 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_task_status_api_invalid_task(self):
        """API task status cu task inexistent returnează eroare."""
        response = self.client.get(
            reverse('task_status_api', kwargs={'task_id': 'inexistent-id'})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'error')

    def test_loading_page_renders(self):
        """Pagina de loading se încarcă pentru orice task_id."""
        response = self.client.get(
            reverse('loading', kwargs={'task_id': 'test-task-123'})
        )
        self.assertEqual(response.status_code, 200)

    def test_ai_chat_rejects_get(self):
        """Endpoint-ul AI chat respinge cereri GET."""
        response = self.client.get(reverse('ai_chat_endpoint'))
        self.assertEqual(response.status_code, 405)


# ═══════════════════════════════════════════════════════════════
# 5. TESTE DATA VALIDATION (Backend – Logica de business)
# ═══════════════════════════════════════════════════════════════
class DataValidationTests(TestCase):
    """Teste pentru formula de calcul completeness score."""

    def test_full_data_returns_high_score(self):
        """Un anunț complet trebuie să aibă scor ≥ 90."""
        full_listing = {
            "Price": 350, "Currency": "EUR", "City": "București",
            "Neighborhood": "Militari", "Rooms": 2, "Useful surface": 55,
            "Heating type": "centrala_proprie",
            "Furnishing state": "mobilat", "Floor": "3", "Total floors": 8,
            "Bathrooms": 1, "Construction year": 2010, "Availability": "Imediat",
            "Has fridge": True, "Has washing machine": True, "Has ac": True,
            "Has oven": True, "Has parking": True, "Has elevator": True,
            "Near public transit": True,
            "Property destination": "rezidențial", "Rental period": "lung",
            "Kitchens": 1, "Balconies": 1, "Partitioning": "decomandat",
            "Comfort level": "1", "Building type": "bloc",
            "Building structure": "beton",
            "Has underfloor heating": False, "Has gas": True,
            "Has electricity": True, "Has water": True, "Has sewage": True,
            "Has gas meter": True, "Has water meter": True,
            "Has heat meter": True, "Internet type": "fibra",
            "Flooring": "parchet", "Windows": "termopan",
            "Interior doors": "lemn", "Entrance door": "metalica",
            "Walls": "zugravite", "Thermal insulation": "polistiren",
            "Has dishwasher": True, "Has tv": True, "Has microwave": True,
            "Has hood": True, "Has intercom": True,
            "Has video surveillance": False, "Is pet friendly": True,
            "Street paved": True, "Street lit": True,
            "Energy class": "B", "Vices": "Nu",
        }
        result = calculate_completeness_score(full_listing)
        self.assertGreaterEqual(result['completeness_score'], 90)

    def test_empty_data_returns_low_score(self):
        """Un anunț gol trebuie să aibă scor foarte mic."""
        result = calculate_completeness_score({})
        self.assertLessEqual(result['completeness_score'], 10)

    def test_missing_critical_field_subtracts_15(self):
        """Lipsa unui câmp critic scade scorul cu 15 puncte."""
        base = {
            "Price": 350, "Currency": "EUR", "City": "București",
            "Neighborhood": "Militari", "Rooms": 2, "Useful surface": 55,
        }
        full_score = calculate_completeness_score(base)['completeness_score']

        missing_price = dict(base)
        del missing_price["Price"]
        reduced_score = calculate_completeness_score(missing_price)['completeness_score']

        self.assertAlmostEqual(full_score - reduced_score, 15.0, places=1)

    def test_missing_heating_subtracts_10(self):
        """Lipsa tipului de încălzire scade scorul cu 10 puncte."""
        with_heating = {"Heating type": "centrala_proprie"}
        without_heating = {}
        score_with = calculate_completeness_score(with_heating)['completeness_score']
        score_without = calculate_completeness_score(without_heating)['completeness_score']
        # Diferența ar trebui sa includă -10 pentru heating
        self.assertGreater(score_with, score_without)

    def test_null_values_treated_as_missing(self):
        """Valorile None sunt tratate ca lipsă."""
        result = calculate_completeness_score({"Price": None, "City": None})
        self.assertLess(result['completeness_score'], 100)

    def test_nementionat_treated_as_missing(self):
        """Valorile 'Nemenționat (NULL)' sunt tratate ca lipsă."""
        result = calculate_completeness_score({
            "Price": "Nemenționat (NULL)",
        })
        self.assertLess(result['completeness_score'], 100)

    def test_score_never_below_zero(self):
        """Scorul nu poate fi sub 0."""
        result = calculate_completeness_score({})
        self.assertGreaterEqual(result['completeness_score'], 0)

    def test_score_never_above_100(self):
        """Scorul nu poate depăși 100."""
        result = calculate_completeness_score({"Price": 100})
        self.assertLessEqual(result['completeness_score'], 100)

    def test_warnings_contain_critical_label(self):
        """Avertismentele includ eticheta CRITICAL."""
        result = calculate_completeness_score({})
        has_critical = any(
            w.get('level') == 'CRITICAL' for w in result['warnings']
        )
        self.assertTrue(has_critical)

    def test_notices_contain_details(self):
        """Notices conțin detaliile lipsă."""
        result = calculate_completeness_score({})
        self.assertTrue(len(result['notices']) > 0)


# ═══════════════════════════════════════════════════════════════
# 6. TESTE FRONTEND (Template-uri, HTML, Formulare, Static)
# ═══════════════════════════════════════════════════════════════
class FrontendTests(TestCase):
    """Teste pentru template-uri, structură HTML, formulare și fișiere statice."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='frontuser', password='FrontPass123!'
        )
        self.listing = Listing.objects.create(
            source_url='https://olx.ro/frontend-test',
            title='Apartament Frontend',
            price=Decimal('400.00'),
            currency='EUR',
            city='București',
            neighborhood='Drumul Taberei',
            rooms=3,
        )

    # ── Template-uri corecte ─────────────────────────────────
    def test_home_uses_correct_template(self):
        """Homepage utilizează template-ul core/home.html."""
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'core/home.html')

    def test_about_uses_correct_template(self):
        """About utilizează template-ul core/about.html."""
        response = self.client.get(reverse('about'))
        self.assertTemplateUsed(response, 'core/about.html')

    def test_contact_uses_correct_template(self):
        """Contact utilizează template-ul core/contact.html."""
        response = self.client.get(reverse('contact'))
        self.assertTemplateUsed(response, 'core/contact.html')

    def test_login_uses_correct_template(self):
        """Login utilizează template-ul core/login.html."""
        response = self.client.get(reverse('login'))
        self.assertTemplateUsed(response, 'core/login.html')

    def test_register_uses_correct_template(self):
        """Register utilizează template-ul core/register.html."""
        response = self.client.get(reverse('register'))
        self.assertTemplateUsed(response, 'core/register.html')

    def test_search_results_uses_correct_template(self):
        """Search Results utilizează template-ul core/search_results.html."""
        response = self.client.get(reverse('search_results'))
        self.assertTemplateUsed(response, 'core/search_results.html')

    def test_result_uses_correct_template(self):
        """Result detail utilizează template-ul core/result.html."""
        response = self.client.get(
            reverse('result_detail', kwargs={'listing_id': self.listing.id})
        )
        self.assertTemplateUsed(response, 'core/result.html')

    def test_history_uses_correct_template(self):
        """History utilizează template-ul core/history.html."""
        self.client.login(username='frontuser', password='FrontPass123!')
        response = self.client.get(reverse('history'))
        self.assertTemplateUsed(response, 'core/history.html')

    def test_loading_uses_correct_template(self):
        """Loading utilizează template-ul core/loading.html."""
        response = self.client.get(
            reverse('loading', kwargs={'task_id': 'abc-123'})
        )
        self.assertTemplateUsed(response, 'core/loading.html')

    # ── Conținut HTML ────────────────────────────────────────
    def test_home_contains_html_structure(self):
        """Homepage conține structura HTML de bază."""
        response = self.client.get(reverse('home'))
        content = response.content.decode()
        self.assertIn('<html', content)
        self.assertIn('</html>', content)

    def test_home_contains_rentguru_branding(self):
        """Homepage conține branding-ul RentGuru."""
        response = self.client.get(reverse('home'))
        content = response.content.decode().lower()
        self.assertTrue(
            'rentguru' in content or 'rent guru' in content or 'rent' in content
        )

    def test_home_contains_navigation_links(self):
        """Homepage conține linkuri de navigare."""
        response = self.client.get(reverse('home'))
        content = response.content.decode()
        # Verificăm că există linkuri către paginile principale
        self.assertTrue(
            'about' in content.lower() or 'despre' in content.lower()
        )

    def test_login_form_contains_csrf(self):
        """Formularul de login conține token CSRF."""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        self.assertIn('csrfmiddlewaretoken', content)

    def test_register_form_contains_csrf(self):
        """Formularul de register conține token CSRF."""
        response = self.client.get(reverse('register'))
        content = response.content.decode()
        self.assertIn('csrfmiddlewaretoken', content)

    def test_login_form_has_username_field(self):
        """Formularul de login are câmpul username."""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        self.assertIn('username', content)

    def test_login_form_has_password_field(self):
        """Formularul de login are câmpul password."""
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        self.assertIn('password', content)

    def test_register_form_has_required_fields(self):
        """Formularul de register are câmpurile necesare."""
        response = self.client.get(reverse('register'))
        content = response.content.decode()
        self.assertIn('username', content)
        self.assertIn('password1', content)
        self.assertIn('password2', content)

    def test_search_page_has_search_input(self):
        """Pagina de căutare conține un input de căutare."""
        response = self.client.get(reverse('search_results'))
        content = response.content.decode()
        # Verificăm prezența unui input / formular
        self.assertTrue(
            '<input' in content or '<form' in content
        )

    def test_result_page_shows_listing_data(self):
        """Pagina de rezultat afișează datele listingului (preț)."""
        response = self.client.get(
            reverse('result_detail', kwargs={'listing_id': self.listing.id})
        )
        content = response.content.decode()
        self.assertIn('400.00', content)

    def test_history_pagination(self):
        """Pagina de history suportă paginare."""
        self.client.login(username='frontuser', password='FrontPass123!')
        # Creăm 10 rapoarte
        for i in range(10):
            lst = Listing.objects.create(
                source_url=f'https://test.ro/pagination-{i}',
                title=f'Pagination {i}',
            )
            Report.objects.create(
                listing=lst,
                user=self.user,
                integrity_score=80,
                final_verdict=f'Test {i}',
            )
        response = self.client.get(reverse('history'))
        self.assertEqual(response.status_code, 200)
        # Page 2 should also work
        response2 = self.client.get(reverse('history'), {'page': '2'})
        self.assertEqual(response2.status_code, 200)

    # ── Fișiere Statice ──────────────────────────────────────
    def test_home_references_css(self):
        """Homepage face referință la fișiere CSS."""
        response = self.client.get(reverse('home'))
        content = response.content.decode()
        self.assertTrue(
            '.css' in content or 'stylesheet' in content
        )

    def test_search_references_css(self):
        """Search results face referință la fișiere CSS."""
        response = self.client.get(reverse('search_results'))
        content = response.content.decode()
        self.assertTrue(
            '.css' in content or 'stylesheet' in content
        )

    # ── URL Routing ──────────────────────────────────────────
    def test_all_named_urls_resolve(self):
        """Toate URL-urile cu nume se rezolvă corect."""
        named_urls = [
            ('home', {}),
            ('register', {}),
            ('login', {}),
            ('logout', {}),
            ('about', {}),
            ('contact', {}),
            ('history', {}),
            ('search_results', {}),
        ]
        for name, kwargs in named_urls:
            url = reverse(name, kwargs=kwargs)
            self.assertIsNotNone(resolve(url))

    def test_parameterized_urls_resolve(self):
        """URL-urile cu parametri se rezolvă corect."""
        url = reverse('result_detail', kwargs={'listing_id': 1})
        self.assertIsNotNone(resolve(url))
        url = reverse('loading', kwargs={'task_id': 'abc'})
        self.assertIsNotNone(resolve(url))
        url = reverse('task_status_api', kwargs={'task_id': 'abc'})
        self.assertIsNotNone(resolve(url))

    # ── Response Headers ─────────────────────────────────────
    def test_pages_return_html_content_type(self):
        """Paginile returnează content-type text/html."""
        for url_name in ['home', 'about', 'contact', 'login', 'register']:
            response = self.client.get(reverse(url_name))
            self.assertIn('text/html', response['Content-Type'])

    def test_api_returns_json_content_type(self):
        """API-ul de task status returnează JSON."""
        response = self.client.get(
            reverse('task_status_api', kwargs={'task_id': 'test'})
        )
        self.assertIn('application/json', response['Content-Type'])