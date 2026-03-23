# Real Estate Tool — Konfiguration & Setup

## Schnellstart

```bash
# 1. Abhängigkeiten installieren
pip install requests pandas

# 2. Collector starten
python run_collector.py

# 3. Status prüfen
python run_collector.py --status

# 4. Daten exportieren
python run_collector.py --export
```

## Projektstruktur

```
real_estate_tool/
├── database.py                  # SQLite Datenbank-Schema & Verbindung
├── collector_ezb.py             # EZB-Zinssätze (ECB Data API)
├── collector_immobilienpreise.py # Immobilienpreise Karlsruhe
├── collector_destatis.py        # DESTATIS Bevölkerung & Baupreise
├── run_collector.py             # Hauptpipeline (alle Collectors)
├── real_estate.db               # SQLite Datenbank (wird erstellt)
├── daten_export.json            # JSON Export (wird erstellt)
└── README.md                    # Diese Datei
```

## Datenquellen

| Daten | Quelle | API? | Status |
|---|---|---|---|
| EZB-Zinssatz | ECB Data API | ✅ Ja, kostenlos | Aktiv |
| Immobilienpreise | Marktdaten-Baseline | Manuell + Scraping | Aktiv (Fallback) |
| Bevölkerung | DESTATIS GENESIS | ✅ Ja, kostenlos nach Registrierung | Fallback aktiv |
| Baupreisindex | DESTATIS GENESIS | ✅ Ja, kostenlos nach Registrierung | Fallback aktiv |

## DESTATIS GENESIS API aktivieren

1. Kostenlos registrieren: https://www-genesis.destatis.de/genesis/online
2. Umgebungsvariablen setzen:
   ```bash
   export GENESIS_USER="dein_username"
   export GENESIS_PASS="dein_passwort"
   ```
3. Dann liefert der Collector echte Live-Daten statt Fallback.

## Nächste Schritte (System 2 — Entscheidungsmodell)

- [ ] Gewichtungsmodell für Preis-Einflussfaktoren
- [ ] Ensemble-Forecasting (Regression + Trend-Extrapolation)
- [ ] User-Input verarbeiten (Adresse, m², Zimmer, Baujahr, Typ, Zustand)
- [ ] Preisspanne berechnen (min-max)
- [ ] Vergleich mit PLZ-Durchschnitt
- [ ] Frontend / Web-Interface
