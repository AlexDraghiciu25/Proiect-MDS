# 🤝 Ghidul de Supraviețuire RentGuru (CONTRIBUTING)

Salutare! Dacă citești asta, înseamnă că faci parte din echipă. Respectăm cu sfințenie pașii de mai jos pentru a nu strica proiectul și a nu pierde nopțile reparând codul.

---

## 🛑 REGULA ZERO
Nu lucra niciodată pe ramura "main"! Toată munca se face pe ramuri (branch-uri) separate.

---

## 📥 Clonare
Comanda pentru a descărca proiectul pe calculatorul tău este:

> git clone https://github.com/AlexDraghiciu25/Proiect-MDS.git

---

## 🛠 1. Setup local (Cum începi)
Dacă tocmai ai clonat proiectul, trebuie să rulezi aceste două comenzi în terminal (Git Bash) pentru a te identifica. Astfel, colegii vor ști cine a scris codul:

> git config --global user.name "Numele Tau"
> git config --global user.email "email@exemplu.com"

---

## 🌿 2. Cum lucrăm pe Task-uri
Când vrei să lucrezi la o funcționalitate nouă, urmează acești pași exacți:

1. Asigură-te că ai ultimele noutăți:
> git checkout main
> git pull origin main

2. Creează-ți "crenguța" (ramura) ta de lucru:
> git checkout -b feature/numele-taskului-tau

3. Scrie codul tău, apoi salvează-l:
> git add .
> git commit -m "Am adaugat [descrierea modificarii]"

4. Trimite-l pe GitHub:
> git push origin feature/numele-taskului-tau

5. Deschide un Pull Request (Cere aprobarea colegilor):
Pentru a uni codul tău cu proiectul principal, ai două variante:

Varianta A (Din Browser - Recomandată):
Intră pe pagina de GitHub a proiectului și apasă pe butonul verde "Compare & pull request" care apare automat.

Varianta B (Din Terminal - Comanda directă):
Dacă ai instalat GitHub CLI pe calculator, poți scrie direct această comandă în Git Bash:

> gh pr create --web

Acest lucru va deschide automat fereastra de Pull Request pentru tine!
