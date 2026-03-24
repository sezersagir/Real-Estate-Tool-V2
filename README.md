# Real Estate Tool v2.0

KI-gestützte Immobilienbewertung und 10-Jahres-Prognose für die Region Karlsruhe/Bruchsal.

## Was macht das Tool?

Das Tool schätzt den aktuellen Marktwert einer Immobilie und prognostiziert die Wertentwicklung über 10 Jahre — basierend auf einem Ensemble-Modell aus lokalen Marktdaten, Makro-Indikatoren und KI-Freitextanalyse.

**Alleinstellungsmerkmal:** Der User kann in natürlicher Sprache Objektmerkmale beschreiben ("Garage nicht gestrichen, Dach 2023 neu, Keller feucht") — eine KI (Groq Llama 3.3) analysiert den Text und übersetzt ihn in eine prozentuale Preisanpassung. Das kann kein anderes Tool auf dem Markt.

## Architektur

Das Tool besteht aus zwei Systemen:

### System 1: Data Collector

Sammelt 8 Datenkategorien aus verschiedenen Quellen in eine SQLite-Datenbank:

| Daten | Quelle | Datenpunkte |
|---|---|---|
| EZB-Leitzins | ECB Data API (live) | ~15 |
| Hypothekenzinsen 10J/15J/20J | Dr. Klein (Scraping) + Marktdaten | ~50 |
| Immobilienpreise pro Stadtteil | Engel & Völkers, ImmoScout24, Immoportal | ~48 |
| Historische Preisentwicklung | Aggregiert (2018-2026) | ~18 |
| Bevölkerungsdaten | DESTATIS (Fallback) | ~16 |
| Baupreisindex | DESTATIS (Fallback) | ~8 |
| Inflationsrate | DESTATIS (verifiziert) | ~23 |
| Arbeitsmarktdaten | Bundesagentur für Arbeit | ~24 |

Gesamt: ~250 Datensätze, abdeckend 14 PLZ-Gebiete (13x Karlsruhe + Bruchsal/Heidelsheim).

### System 2: Ensemble-Modell + Prognose

**Aktuelle Bewertung (4 Schichten):**

1. **Basispreis** — PLZ + Stadtteil → Durchschnittspreis/m² aus der Datenbank
2. **Objekt-Multiplikator** — 10 Faktoren multipliziert: Baujahr, Zustand, Heizung, Energieausweis, Bauart, Fassade, Keller, Solar/PV, Wohnfläche, Raumeffizienz. Asymmetrisch gewichtet: schlechte Merkmale bestrafen stärker als gute belohnen (weil Premium bereits im Startwert steckt).
3. **Makro-Trendkorrektur** — Live aus der DB: Hypothekenzins-Trend, historischer Preistrend, Bevölkerungsentwicklung, Inflation, Baukosten.
4. **LLM-Freitext-Bewertung** — Groq Llama 3.3 analysiert natürlichsprachliche Beschreibungen und gibt eine strukturierte Preiskorrektur (-30% bis +20%) zurück.

**10-Jahres-Prognose (Zinspfad-basiert):**

Nicht pauschal "3% pro Jahr", sondern dynamisch pro Jahr berechnet:

```
Wachstum(Jahr X) = Basis-Trend + (Zins-Delta x Sensitivität) + Objekt-Korrektur
```

- **Basis-Trend:** CAGR aus historischen Daten, gedämpft (x0.75), gedeckelt 1-3.5%
- **Zins-Delta:** Differenz zwischen aktuellem Hypothekenzins und prognostiziertem Zins für Jahr X
- **Sensitivität:** 0.5 (1% Zinssenkung → +0.5% mehr Preiswachstum p.a.)
- **Objekt-Korrektur:** Energieeffizienz beeinflusst langfristige Wertentwicklung (GEG-Regulierung)

3 Szenarien mit unterschiedlichen Zinspfaden basierend auf gewichtetem Consensus aus 8 Institutionen:

| Institution | Gewicht |
|---|---|
| EZB Survey of Monetary Analysts | Hoch |
| Bloomberg Consensus | Hoch |
| Bundesbank | Hoch |
| Dr. Klein Expertenrat | Mittel |
| Interhyp Bankenpanel | Mittel |
| ING | Niedrig |
| Commerzbank | Niedrig |
| BlackRock | Niedrig |

## Projektstruktur

```
real_estate_tool/
├── app.py                        # Flask Web-Interface
├── modell.py                     # Ensemble-Bewertungsmodell (10 Faktoren)
├── prognose.py                   # 10-Jahres-Prognose (Zinspfad-basiert)
├── llm_bewertung.py              # Groq LLM Freitext → Preiskorrektur
├── database.py                   # SQLite Schema & Verbindung
├── run_collector.py              # Hauptpipeline (alle 8 Collectors)
├── collector_ezb.py              # EZB-Zinssätze
├── collector_immobilienpreise.py # Immobilienpreise + Scraping
├── collector_destatis.py         # Bevölkerung + Baupreisindex
├── collector_makro.py            # Hypothekenzinsen, Inflation, Arbeitsmarkt
├── real_estate.db                # SQLite Datenbank (~250 Datensätze)
├── templates/
│   └── index.html                # Frontend (Chart.js, responsive)
├── requirements.txt              # Python-Abhängigkeiten
├── Procfile                      # Railway Deployment
└── README.md
```

## Setup

### Lokal

```bash
# 1. Abhängigkeiten
pip install flask groq requests

# 2. Daten sammeln
python run_collector.py

# 3. Groq API Key setzen + starten
# Windows PowerShell:
$env:GROQ_API_KEY="dein_key"
python app.py

# Linux/Mac:
export GROQ_API_KEY="dein_key"
python app.py
```

Browser öffnen: http://localhost:5000

### Deployment (Railway)

1. GitHub Repo erstellen, Code pushen
2. railway.app → New Project → Deploy from GitHub
3. Variable setzen: `GROQ_API_KEY`
4. Builder: Nixpacks oder Dockerfile
5. Networking → Generate Domain

### Daten aktualisieren

```bash
python run_collector.py
git add real_estate.db
git commit -m "daten aktualisiert"
git push
```

Railway deployt automatisch neu.

## Eingabefelder

**Pflichtfelder:**
- PLZ / Stadtteil (Dropdown, 14 Optionen)
- Immobilientyp (Wohnung / Haus)
- Wohnfläche (m²)
- Zimmeranzahl
- Baujahr
- Zustand (Erstbezug / Renoviert / Normal / Teilsaniert / Sanierungsbedürftig)

**Gebäudedetails (optional — verbessern Bewertung + Prognose):**
- Bauart (Massivbau / Massivbau+WDVS / Rahmenbauweise)
- Außenfassade (Rauputz / Sichtmauerwerk / WDVS)
- Heizungsart (Wärmepumpe / Fernwärme / Pellets / Gas neu / Gas alt / Öl / Nachtspeicher)
- Energieausweis (A+ bis H)
- Keller (Vollkeller / Teilkeller / Kein Keller)
- Solar/PV-Anlage (Ja / Nein)

**Freitext (optional, KI-analysiert):**
Natürliche Sprache, z.B. "Dach 2023 neu, Keller feucht, Einbauküche Bulthaup, Südbalkon"

## Output

- Geschätzter Preis (Gesamtwert + pro m²)
- Preisspanne (+/-12-20%)
- Vergleich mit PLZ-Durchschnitt
- Aufschlüsselung aller Preisfaktoren
- KI-Freitext-Analyse (wenn eingegeben)
- 10-Jahres-Prognose: 3 Szenarien als Chart + Tabelle
- Inflations-Hinweis

## Wie der Preis berechnet wird

### Aktueller Wert

```
Preis = Basispreis/m² x Objekt-Multiplikator x (1 + Makro-Korrektur) x (1 + LLM-Korrektur) x Wohnfläche
```

Der Objekt-Multiplikator ist das Produkt aus 10 einzelnen Faktoren (Baujahr, Zustand, Heizung, Energieausweis, Bauart, Fassade, Keller, Solar, Wohnfläche, Raumeffizienz). Asymmetrisch: Ölheizung bestraft mit -12%, Wärmepumpe gibt +/-0% weil sie bei Neubauten Standard ist.

### 10-Jahres-Prognose

Jedes Jahr hat eine individuelle Wachstumsrate:

```
Rate(Jahr) = Basis-Trend + (Zins-Delta x 0.5 / 100) + Objekt-Korrektur
```

Drei Zinspfade (Optimistisch: Zinsen fallen auf 2.5%, Realistisch: pendeln bei 3.0%, Pessimistisch: steigen auf 4.8%) ergeben drei Szenarien. Die Rate ändert sich jedes Jahr — kein pauschaler Wert über 10 Jahre.

## Technologie

- **Backend:** Python 3, Flask, SQLite
- **Frontend:** HTML, CSS (DM Sans), Chart.js
- **KI:** Groq API (Llama 3.3 70B Versatile)
- **Deployment:** Railway (Gunicorn)
- **Datenquellen:** ECB Data API, DESTATIS, Dr. Klein, Interhyp, Immoportal, Wohnungsboerse

## Disclaimer

Dieses Tool liefert eine Orientierungshilfe basierend auf öffentlich verfügbaren Marktdaten und KI-Analyse. Es ersetzt keine professionelle Immobilienbewertung durch einen zertifizierten Sachverständigen. Alle Prognosen sind Schätzungen — Immobilienmärkte können sich anders entwickeln als prognostiziert. Alle Prognose-Werte sind nominal; bei ~2% Inflation p.a. liegt der reale Wertzuwachs ca. 20 Prozentpunkte niedriger.
