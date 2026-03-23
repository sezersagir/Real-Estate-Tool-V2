"""
Collector 1: EZB-Zinssätze
Holt den aktuellen Hauptrefinanzierungssatz der Europäischen Zentralbank.
"""

import requests
import time
from datetime import datetime
from database import get_connection, log_collection


ECB_API_URL = (
    "https://data-api.ecb.europa.eu/service/data/FM/"
    "B.U2.EUR.4F.KR.MRR_FR.LEV"
    "?format=jsondata&lastNObservations=12"  # Letzte 12 Datenpunkte
)


def collect_ezb_zinssaetze() -> dict:
    """
    Holt EZB-Zinssätze und speichert sie in der Datenbank.
    Gibt ein Status-Dict zurück.
    """
    start = time.time()
    
    try:
        response = requests.get(ECB_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Zeitdimensionen extrahieren (Datum-Werte)
        time_periods = data["structure"]["dimensions"]["observation"][0]["values"]
        
        # Zinssatz-Werte extrahieren
        observations = data["dataSets"][0]["series"]["0:0:0:0:0:0:0"]["observations"]
        
        conn = get_connection()
        inserted = 0
        
        for obs_key, obs_value in observations.items():
            idx = int(obs_key)
            datum_str = time_periods[idx]["id"]  # Format: "2024-06"
            zinssatz = obs_value[0]
            
            # Monatsdatum -> Erster des Monats
            datum = f"{datum_str}-01"
            
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO ezb_zinssaetze (datum, zinssatz, typ)
                       VALUES (?, ?, 'hauptrefinanzierung')""",
                    (datum, zinssatz)
                )
                if conn.total_changes:
                    inserted += 1
            except Exception:
                pass  # Duplikate ignorieren
        
        conn.commit()
        conn.close()
        
        dauer = time.time() - start
        log_collection("ezb_zinssaetze", "erfolg", inserted, dauer=dauer)
        
        aktuellster = max(time_periods, key=lambda x: x["id"])
        aktueller_satz = list(observations.values())[-1][0]
        
        return {
            "status": "erfolg",
            "datensaetze": inserted,
            "aktueller_zinssatz": aktueller_satz,
            "aktuelles_datum": aktuellster["id"],
            "dauer_sekunden": round(dauer, 2)
        }
        
    except requests.RequestException as e:
        dauer = time.time() - start
        fehler = f"API-Fehler: {str(e)}"
        log_collection("ezb_zinssaetze", "fehler", fehlermeldung=fehler, dauer=dauer)
        return {"status": "fehler", "fehlermeldung": fehler}
    
    except (KeyError, IndexError) as e:
        dauer = time.time() - start
        fehler = f"Parsing-Fehler: {str(e)}"
        log_collection("ezb_zinssaetze", "fehler", fehlermeldung=fehler, dauer=dauer)
        return {"status": "fehler", "fehlermeldung": fehler}


if __name__ == "__main__":
    from database import init_db
    init_db()
    result = collect_ezb_zinssaetze()
    print(result)
