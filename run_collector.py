"""
═══════════════════════════════════════════════════════════════
  REAL ESTATE TOOL — Collector Pipeline
  Hauptskript: Führt alle Collectors aus und gibt Status-Report.
═══════════════════════════════════════════════════════════════

Nutzung:
    python run_collector.py              # Alles sammeln
    python run_collector.py --status     # Datenbank-Status anzeigen
    python run_collector.py --export     # Daten als JSON exportieren
"""

import sys
import json
import time
from datetime import datetime

from database import init_db, get_connection
from collector_ezb import collect_ezb_zinssaetze
from collector_immobilienpreise import (
    collect_immobilienpreise_scraping,
    seed_historische_preise
)
from collector_destatis import (
    collect_bevoelkerung_genesis,
    collect_baupreisindex,
    seed_ezb_fallback,
)
from collector_makro import (
    collect_hypothekenzinsen,
    collect_inflation,
    collect_arbeitslosigkeit,
)


def run_all_collectors() -> dict:
    """Führt alle Collectors der Reihe nach aus."""
    
    print("╔══════════════════════════════════════════════╗")
    print("║   REAL ESTATE TOOL — Data Collection        ║")
    print("║   Region: Karlsruhe / Bruchsal              ║")
    print(f"║   Datum:  {datetime.now().strftime('%Y-%m-%d %H:%M')}                  ║")
    print("╚══════════════════════════════════════════════╝\n")
    
    results = {}
    gesamt_start = time.time()
    
    # ── 1. EZB-Zinssätze ──
    print("① EZB-Zinssätze laden...")
    result = collect_ezb_zinssaetze()
    if result["status"] == "fehler":
        print("   ⚠️ ECB API nicht erreichbar — lade Fallback-Daten...")
        result = seed_ezb_fallback()
    results["ezb"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── 2. Immobilienpreise ──
    print("② Immobilienpreise sammeln...")
    result = collect_immobilienpreise_scraping()
    results["immobilienpreise"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── 3. Historische Preise ──
    print("③ Historische Preisdaten laden...")
    result = seed_historische_preise()
    results["historisch"] = result
    print(f"   → {result.get('historische_datensaetze', 0)} historische Datensätze\n")
    
    # ── 4. Bevölkerungsdaten ──
    print("④ Bevölkerungsdaten laden...")
    result = collect_bevoelkerung_genesis()
    results["bevoelkerung"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── 5. Baupreisindex ──
    print("⑤ Baupreisindex laden...")
    result = collect_baupreisindex()
    results["baupreisindex"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── 6. Hypothekenzinsen ──
    print("⑥ Hypothekenzinsen laden...")
    result = collect_hypothekenzinsen()
    results["hypothekenzinsen"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── 7. Inflation ──
    print("⑦ Inflationsrate laden...")
    result = collect_inflation()
    results["inflation"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── 8. Arbeitsmarkt ──
    print("⑧ Arbeitslosenquote laden...")
    result = collect_arbeitslosigkeit()
    results["arbeitsmarkt"] = result
    print(f"   → {result['status']}: {result.get('datensaetze', 0)} Datensätze\n")
    
    # ── Zusammenfassung ──
    gesamt_dauer = time.time() - gesamt_start
    
    print("─" * 46)
    print(f"✅ Pipeline abgeschlossen in {gesamt_dauer:.1f}s")
    print(f"   Gesamte Datensätze: {sum(r.get('datensaetze', 0) + r.get('historische_datensaetze', 0) for r in results.values())}")
    print()
    
    return results


def show_status():
    """Zeigt den aktuellen Datenbank-Status."""
    conn = get_connection()
    
    print("\n📊 DATENBANK-STATUS")
    print("=" * 50)
    
    tabellen = [
        ("ezb_zinssaetze", "EZB-Zinssätze"),
        ("hypothekenzinsen", "Hypothekenzinsen"),
        ("immobilienpreise", "Immobilienpreise"),
        ("bevoelkerung", "Bevölkerungsdaten"),
        ("baupreisindex", "Baupreisindex"),
        ("inflation", "Inflationsrate"),
        ("arbeitslosigkeit", "Arbeitslosenquote"),
        ("collector_log", "Collector-Logs"),
    ]
    
    for tabelle, name in tabellen:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0]
            
            if tabelle == "ezb_zinssaetze" and count > 0:
                latest = conn.execute(
                    "SELECT datum, zinssatz FROM ezb_zinssaetze ORDER BY datum DESC LIMIT 1"
                ).fetchone()
                print(f"\n  {name}: {count} Einträge")
                print(f"    Letzter Eintrag: {latest['datum']} → {latest['zinssatz']}%")
                
            elif tabelle == "immobilienpreise" and count > 0:
                stats = conn.execute("""
                    SELECT typ, COUNT(*) as n, 
                           ROUND(AVG(preis_pro_qm)) as avg_preis,
                           MIN(preis_pro_qm) as min_preis,
                           MAX(preis_pro_qm) as max_preis
                    FROM immobilienpreise 
                    WHERE quelle != 'historisch_aggregiert'
                    GROUP BY typ
                """).fetchall()
                print(f"\n  {name}: {count} Einträge")
                for s in stats:
                    print(f"    {s['typ'].capitalize()}: Ø {s['avg_preis']:.0f} €/m²"
                          f" (min {s['min_preis']:.0f}, max {s['max_preis']:.0f})")
                    
            elif tabelle == "bevoelkerung" and count > 0:
                latest = conn.execute("""
                    SELECT stadt, MAX(jahr) as jahr, einwohner
                    FROM bevoelkerung GROUP BY stadt
                """).fetchall()
                print(f"\n  {name}: {count} Einträge")
                for row in latest:
                    print(f"    {row['stadt']} ({row['jahr']}): "
                          f"{row['einwohner']:,} Einwohner".replace(",", "."))
                    
            elif tabelle == "baupreisindex" and count > 0:
                latest = conn.execute(
                    "SELECT datum, index_wert, veraenderung_vj "
                    "FROM baupreisindex ORDER BY datum DESC LIMIT 1"
                ).fetchone()
                print(f"\n  {name}: {count} Einträge")
                print(f"    Letzter Index: {latest['index_wert']} "
                      f"(+{latest['veraenderung_vj']}% ggü. Vorjahr)")

            elif tabelle == "hypothekenzinsen" and count > 0:
                latest = conn.execute("""
                    SELECT zinsbindung_jahre, zinssatz
                    FROM hypothekenzinsen 
                    WHERE datum = (SELECT MAX(datum) FROM hypothekenzinsen)
                    ORDER BY zinsbindung_jahre
                """).fetchall()
                print(f"\n  {name}: {count} Einträge")
                for row in latest:
                    print(f"    {row['zinsbindung_jahre']}J: {row['zinssatz']}%")

            elif tabelle == "inflation" and count > 0:
                latest = conn.execute(
                    "SELECT datum, inflationsrate "
                    "FROM inflation ORDER BY datum DESC LIMIT 1"
                ).fetchone()
                print(f"\n  {name}: {count} Einträge")
                print(f"    Aktuell: {latest['inflationsrate']}% ({latest['datum']})")

            elif tabelle == "arbeitslosigkeit" and count > 0:
                latest = conn.execute("""
                    SELECT region, quote
                    FROM arbeitslosigkeit 
                    WHERE datum = (SELECT MAX(datum) FROM arbeitslosigkeit)
                    ORDER BY region
                """).fetchall()
                print(f"\n  {name}: {count} Einträge")
                for row in latest:
                    print(f"    {row['region']}: {row['quote']}%")
                
            else:
                print(f"\n  {name}: {count} Einträge")
                
        except Exception as e:
            print(f"\n  {name}: FEHLER — {e}")
    
    # Letzte Collector-Läufe
    print(f"\n{'─' * 50}")
    print("  Letzte Collector-Läufe:")
    logs = conn.execute("""
        SELECT collector_name, status, datensaetze, erstellt_am
        FROM collector_log ORDER BY erstellt_am DESC LIMIT 10
    """).fetchall()
    for log in logs:
        icon = "✅" if log["status"] == "erfolg" else "⚠️" if log["status"] == "teilweise" else "❌"
        print(f"    {icon} {log['collector_name']}: {log['status']} "
              f"({log['datensaetze']} Sätze) — {log['erstellt_am']}")
    
    conn.close()


def _table_exists(conn, name):
    """Prüft ob eine Tabelle existiert."""
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None


def export_data():
    """Exportiert alle Daten als JSON."""
    conn = get_connection()
    
    export = {
        "exportiert_am": datetime.now().isoformat(),
        "region": "Karlsruhe / Bruchsal",
        "ezb_zinssaetze": [dict(r) for r in conn.execute(
            "SELECT * FROM ezb_zinssaetze ORDER BY datum"
        ).fetchall()],
        "immobilienpreise": [dict(r) for r in conn.execute(
            "SELECT * FROM immobilienpreise ORDER BY datum, plz"
        ).fetchall()],
        "bevoelkerung": [dict(r) for r in conn.execute(
            "SELECT * FROM bevoelkerung ORDER BY stadt, jahr"
        ).fetchall()],
        "baupreisindex": [dict(r) for r in conn.execute(
            "SELECT * FROM baupreisindex ORDER BY datum"
        ).fetchall()],
        "hypothekenzinsen": [dict(r) for r in conn.execute(
            "SELECT * FROM hypothekenzinsen ORDER BY datum, zinsbindung_jahre"
        ).fetchall()] if _table_exists(conn, "hypothekenzinsen") else [],
        "inflation": [dict(r) for r in conn.execute(
            "SELECT * FROM inflation ORDER BY datum"
        ).fetchall()] if _table_exists(conn, "inflation") else [],
        "arbeitslosigkeit": [dict(r) for r in conn.execute(
            "SELECT * FROM arbeitslosigkeit ORDER BY region, datum"
        ).fetchall()] if _table_exists(conn, "arbeitslosigkeit") else [],
    }
    
    conn.close()
    
    export_path = "daten_export.json"
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"📁 Daten exportiert nach: {export_path}")
    return export_path


# ── Main ──
if __name__ == "__main__":
    init_db()
    
    if "--status" in sys.argv:
        show_status()
    elif "--export" in sys.argv:
        export_data()
    else:
        run_all_collectors()
        show_status()
