# 🏠 RentGuru - AI-Powered Real Estate Integrity Auditor

**RentGuru** este un sistem expert de audit imobiliar conceput pentru a proteja utilizatorii de fraude și de omisiuni critice în anunțurile de închirieri. Sistemul utilizează o arhitectură bazată pe micro-agenți AI pentru analiză textuală și geospațială.

---

## 🛠 Tehnologii Utilizate (Stack Tehnologic)
* **Backend:** Python 3.x cu framework-ul **Django**.
* **Bază de date:** **PostgreSQL** (pentru persistența utilizatorilor, istoricului și rapoartelor).
* **Frontend:** Django Templates + Bootstrap.
* **AI/ML:** OpenAI API (GPT-4) / LangChain pentru coordonarea agenților.
* **Geospatial:** Google Maps Platform API / OpenStreetMap.
* **Data Acquisition:** Playwright.

---

## 🏗 Arhitectura Sistemului

Sistemul este structurat pe patru straturi logice:

1.  **Ingestion Layer:** Modulul de Web Scraping care extrage datele brute din link-uri externe.
2.  **AI Analysis Layer:** * **Detective Agent:** Validare integritate, detecție "red flags", analiză anomalii de preț.
    * **Oracle Agent:** Calcul scor proximitate, validare distanțe reale, analiză facilități zonale.
3.  **Persistence Layer:** Baza de date PostgreSQL pentru stocarea profilurilor și a rapoartelor.
4.  **Presentation Layer:** Dashboard-ul web pentru vizualizarea scorului de onestitate.

---

## 📋 Backlog de Dezvoltare (Sprint-uri)

### 🔹 Sprint 1: Setup & Core
- [✓] Configurare proiect Django și conectare la instanța PostgreSQL.
- [✓] Definirea Modelelor (User, Report, Listing).
- [✓] Implementare sistem de autentificare (Login/Register).

### 🔹 Sprint 2: Data & Scraper
- [ ] Implementare Parser pentru platformele imobiliare (OLX/Imobiliare.ro).
- [ ] Validare formală a datelor (Data Cleaning & Regex).
- [✓] Creare diagrame UML.

### 🔹 Sprint 3: AI Agents Integration
- [✓] **Detective Agent:** Integrare LLM pentru analiza semantică a descrierilor.
- [ ] **Oracle Agent:** Integrare API Hărți pentru calcularea punctelor de interes.

### 🔹 Sprint 4: Finalization & Testing
- [✓] Generarea raportului de încredere (Onestitate + Lifestyle).
- [ ] Testare unitară (Unit Testing) și documentație finală.

---

## 📐 Arhitectură și Diagrame

### Diagrama 1: Arhitectura Componentelor
Acest grafic descrie interacțiunea dintre serverul Django, baza de date PostgreSQL și serviciile externe de AI și Scraping.

```mermaid
graph TD;
    UI[Frontend: Django Templates + Bootstrap] -- URL/Filtre --> Django[Backend: Django Framework];
    Django -- Persistență --> DB[(Database: PostgreSQL)];
    Django -- Web Scraping --> Web[Site-uri Imobiliare: OLX/Imobiliare.ro];
    Django -- Prompt Contextual --> AI[AI Layer: OpenAI GPT-4 / LangChain];
    Django -- Analiză Geospațială --> Maps[Geospatial: Google Maps API];
    AI -- Scor Integritate --> Django;
    Maps -- Validare Distanțe --> Django;
    Django -- Raport Final Audit --> UI;
```

### Diagrama 2: Fluxul de Audit Imobiliar (AI Agents)
Descrie procesul prin care un link de anunț este prelucrat de sistem pentru a genera un raport de încredere.

```mermaid
sequenceDiagram
    participant U as Utilizator
    participant D as Django (Core)
    participant S as Ingestion Layer (Scraper)
    participant AI as AI Layer (Detective Agent)
    participant DB as PostgreSQL

    U->>D: Introduce link anunț extern
    D->>S: Rulează Parser (BeautifulSoup/Requests)
    S-->>D: Returnează Date brute (Preț, Descriere, Dotări)
    D->>AI: Trimite date pentru audit (Detecție Red Flags)
    AI-->>D: Returnează Scor Integritate + Verdict
    D->>DB: Salvează Listing & Report
    DB-->>D: Confirmare salvare
    D-->>U: Afișează Dashboard Raport (Rezultat AI)
```

### Diagrama 3: Diagrama de Clase (Modele de Date)
Această diagramă reflectă structura bazei de date definită în modelele proiectului.

```mermaid
classDiagram
    class User {
        +String username
        +String email
    }
    class Listing {
        +URL source_url
        +String source_website
        +Json raw data
        +String processing_status
        +String title
        +Text description
        +Decimal price
        +String currency
        +String property_destination
        +String rental_period
        +String availability
        +String city
        +String neighborhood
        +Integer rooms
        +Integer bathrooms
        +Integer kitchen
        +Integer balconys
        +Decimal useful_surface
        +String floor
        +Integer total_floors
        +Integer construction_year
        +String partitioning
        +String comfort_level
        +String building_type
        +String building_structure
        +String furnishing_state
        +String heating_type
        +Boolean has_underfloor_heating
        +Boolean has_gas
        +Boolean has_electricity
        +Boolean has_water
        +Boolean has_sewage
        +Boolean has_gas_meter
        +Boolean has_water_meter
        +Boolean has_heat_meter
        +String internet_type
        +String flooring
        +String windows
        +String interior_doors
        +String entrance_door
        +String walls
        +String thermal_insulation
        +Boolean has_fridge
        +Boolean has_washing_machine
        +Boolean has_dishwasher
        +Boolean has_tv
        +Boolean has_oven
        +Boolean has_microwave
        +Boolean has_hood
        +Boolean has_ac
        +Boolean has_intercom
        +Boolean has_elevator
        +Boolean has_video_surveillance
        +Boolean has_parking
        +Boolean is_pet_friendly
        +Boolean street_paved
        +Boolean street_lit
        +Boolean near_public_transit
        +String energy_class
        +Text vices
        +Integer data_completeness_score
        +DateTime created_at
        +DateTime updated_at
        +String processing_status
    }
    class Report {
        +Integer integrity_score
        +JSON red_flags
        +String proximity_analysis
        +Text final_verdict
        +DateTime generated_at
        +Integer token_usage
    }

    User "1" -- "*" Report : vizualizează
    Listing "1" -- "*" Report : generează
```
---

## 🧪 Verificări Formale & Calitate
* **Validare Date:** Verificarea integrității JSON-urilor returnate de agenți.
* **Cross-Check:** Compararea facilităților declarate în text cu datele geografice reale.
* **Design Patterns:** Utilizarea pattern-urilor *Strategy* (pentru profiluri utilizator) și *Singleton* (pentru conexiunea la DB).
