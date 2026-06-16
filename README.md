# AutoTrans - Bus Fleet Manager

AutoTrans este o aplicație web Django pentru administrarea unei flote de autobuze, căutarea rutelor, rezervarea biletelor și asistarea utilizatorilor prin agenți AI.

Proiect realizat pentru disciplina **Metode de Dezvoltare Software**.

## Documentație proces

Pentru detalii despre backlog, Sprint Backlog, arhitectură, diagrame UML, Git workflow, teste, bug reports, pull request-uri, design patterns și folosirea instrumentelor AI, vezi:

[PROCES_DE_DEZVOLTARE.md](PROCES_DE_DEZVOLTARE.md)

## Funcționalități principale

- Căutare rute directe și rute cu transfer
- Filtrare după stație de plecare, destinație, dată și oră
- Rezervare bilete pentru unul sau mai mulți pasageri
- Generare bilet PDF cu cod QR
- Pagina „Rezervările mele”
- Dashboard pentru șofer și scanare QR la îmbarcare
- Panou Django Admin personalizat pentru gestionarea datelor
- Hartă interactivă cu stații și trasee
- Formular de contact
- Date demo realiste pentru testare

## Agenți AI

Proiectul include doi agenți AI cu roluri diferite:

### 1. Asistent AI pentru călători

Chatbot integrat în interfața publică a site-ului. Ajută utilizatorul să:

- găsească rute între două orașe
- caute curse la o anumită dată sau oră
- primească variante cu transfer
- afle prețul estimat al biletului
- înțeleagă pașii pentru rezervare, plată, bilet PDF și îmbarcare

Agentul folosește un model local prin Ollama pentru extragerea intenției, iar informațiile despre rute sunt calculate determinist din baza de date.

### 2. Agent AI pentru managementul flotei

Agent disponibil în zona de administrare. Analizează cursele, autobuzele și șoferii pentru a detecta probleme operaționale:

- autobuze indisponibile alocate pe curse
- conflicte de alocare autobuz
- șoferi indisponibili sau suprapuși
- șoferi care depășesc 8 ore de condus
- curse cu ocupare foarte mică sau foarte mare
- oportunități de combinare a curselor slab ocupate

Agentul poate genera planuri de realocare și poate aplica modificări controlate în baza de date, cu log în `AIActionLog`.

## Tehnologii folosite

- Python
- Django
- SQLite
- Django Admin
- django-allauth
- Bootstrap
- Leaflet
- ReportLab
- qrcode
- Ollama / modele locale AI
- Gemini API, pentru experimente inițiale

Modele AI testate în dezvoltare:

- Qwen 2.5
- Llama
- Mistral Nemo
- Gemini

## Instalare

Clonează repository-ul:

```bash
git clone https://github.com/stematecatalin/Bus-Fleet-Manager.git
cd Bus-Fleet-Manager
```

Creează și activează mediul virtual:

```bash
python -m venv venv
```

Windows:

```bash
.\venv\Scripts\activate
```

Instalează dependențele:

```bash
pip install -r requirements.txt
```

Rulează migrațiile:

```bash
python manage.py migrate
```

## Configurare Ollama pentru agenții AI

Asistenții AI pot folosi modele locale prin Ollama. Dacă Ollama nu rulează, aplicația folosește fallback determinist pentru întrebările uzuale și pentru analiza flotei, dar răspunsurile AI sunt mai bune cu modelele pornite.

Instalează Ollama:

```text
https://ollama.com/download
```

Modele recomandate în proiect:

```bash
ollama pull qwen2.5
ollama pull mistral-nemo
```

Pentru asistentul de călători se poate porni Qwen:

```bash
ollama run qwen2.5
```

Pentru agentul AI de management al flotei se poate porni Mistral Nemo:

```bash
ollama run mistral-nemo
```

Modele testate în dezvoltare:

```text
qwen2.5
llama
mistral-nemo
```

Dacă folosești alt model, actualizează numele modelului în configurația chatbotului.

## Populare cu date demo

Pentru testare realistă, proiectul include o comandă de populare:

```bash
python manage.py seed_realistic_demo --admin-email admin@autotrans.ro --days 14
```

Comanda creează:

- stații
- rute
- orare
- autobuze
- șoferi
- curse
- bilete
- scenarii realiste pentru agentul AI de management

## Rulare aplicație

```bash
python manage.py runserver
```

Aplicația va fi disponibilă la:

```text
http://localhost:8000/
```

Panoul admin:

```text
http://localhost:8000/admin/
```

Agentul AI pentru flotă:

```text
http://localhost:8000/admin/agent-flota/
```

## Testare

Rulează testele aplicației:

```bash
python manage.py test core
```

Testele acoperă modele, căutare rute, chatbot, rezervări și logica agentului de management.

## Structură proiect

```text
Bus-Fleet-Manager/
├── Bus_Fleet_Manager/        # Configurația Django
├── core/                     # Aplicația principală
│   ├── models.py             # Modele: rute, curse, bilete, autobuze, AI logs
│   ├── views.py              # View-uri publice și API-uri
│   ├── chatbot.py            # Logica asistentului AI pentru călători
│   ├── fleet_optimizer.py    # Logica agentului AI de management
│   ├── templates/            # Template-uri HTML
│   ├── static/               # CSS și resurse statice
│   └── management/commands/  # Comenzi custom Django
├── manage.py
├── requirements.txt
└── README.md
```

## Conturi și autentificare

Aplicația folosește utilizator custom cu email ca identificator principal.

Pentru administrare se poate crea un superuser:

```bash
python manage.py createsuperuser
```

Sau se poate folosi comanda de seed pentru a păstra/crea contul admin demo.

## Observații

- Plata cu cardul este simulată pentru scop demonstrativ.
- Biletele PDF și codurile QR sunt generate local.
- Agentul AI nu inventează rute; rutele și orarele sunt calculate din baza de date.
- Pentru rezultate consistente între calculatoare, baza de date trebuie populată cu același seed.
