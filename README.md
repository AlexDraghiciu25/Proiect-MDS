# 🏠 RentGuru - AI-Powered Real Estate Integrity Auditor

**RentGuru** este un sistem expert de audit imobiliar conceput pentru a proteja utilizatorii de fraude și de omisiuni critice în anunțurile de închirieri. Sistemul utilizează o arhitectură bazată pe micro-agenți AI pentru analiză textuală și geospațială.

---

## 🛠 Tehnologii Utilizate (Stack Tehnologic)
* **Backend:** Python 3.x cu framework-ul **Django**.
* **Bază de date:** **MySQL** (pentru persistența utilizatorilor, istoricului și rapoartelor).
* **Frontend:** Django Templates + Bootstrap.
* **AI/ML:** OpenAI API (GPT-4) / LangChain pentru coordonarea agenților.
* **Geospatial:** Google Maps Platform API / OpenStreetMap.
* **Data Acquisition:** Beautiful Soup 4 / Selenium (Web Scraping).

---

## 🏗 Arhitectura Sistemului

Sistemul este structurat pe patru straturi logice:

1.  **Ingestion Layer:** Modulul de Web Scraping care extrage datele brute din link-uri externe.
2.  **AI Analysis Layer:** * **Detective Agent:** Validare integritate, detecție "red flags", analiză anomalii de preț.
    * **Oracle Agent:** Calcul scor proximitate, validare distanțe reale, analiză facilități zonale.
3.  **Persistence Layer:** Baza de date MySQL pentru stocarea profilurilor și a rapoartelor.
4.  **Presentation Layer:** Dashboard-ul web pentru vizualizarea scorului de onestitate.

---

## 📋 Backlog de Dezvoltare (Sprint-uri)

### 🔹 Sprint 1: Setup & Core
- [ ] Configurare proiect Django și conectare la instanța MySQL.
- [ ] Definirea Modelelor (User, Report, Listing).
- [ ] Implementare sistem de autentificare (Login/Register).

### 🔹 Sprint 2: Data & Scraper
- [ ] Implementare Parser pentru platformele imobiliare (OLX/Imobiliare.ro).
- [ ] Validare formală a datelor (Data Cleaning & Regex).

### 🔹 Sprint 3: AI Agents Integration
- [ ] **Detective Agent:** Integrare LLM pentru analiza semantică a descrierilor.
- [ ] **Oracle Agent:** Integrare API Hărți pentru calcularea punctelor de interes.

### 🔹 Sprint 4: Finalization & Testing
- [ ] Generarea raportului de încredere (Onestitate + Lifestyle).
- [ ] Testare unitară (Unit Testing) și documentație finală.

---

## 🧪 Verificări Formale & Calitate
* **Validare Date:** Verificarea integrității JSON-urilor returnate de agenți.
* **Cross-Check:** Compararea facilităților declarate în text cu datele geografice reale.
* **Design Patterns:** Utilizarea pattern-urilor *Strategy* (pentru profiluri utilizator) și *Singleton* (pentru conexiunea la DB).
