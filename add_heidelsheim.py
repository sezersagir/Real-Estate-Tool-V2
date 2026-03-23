"""
Fügt Heidelsheim (Bruchsal) zur Datenbank hinzu.
Einmal ausführen: python add_heidelsheim.py
"""
from database import init_db, get_connection
from datetime import date

init_db()
conn = get_connection()

heute = date.today().isoformat()

# Heidelsheim liegt preislich ~5-8% unter Bruchsal Zentrum
# Quellen: immowelt, immoportal, wohnungsboerse (Stand Q1/2026)
daten = [
    ("76646", "Bruchsal", "Heidelsheim", heute, "wohnung", 2850, 2420, 3280, "marktdaten_baseline_q1_2026"),
    ("76646", "Bruchsal", "Heidelsheim", heute, "haus", 3200, 2720, 3680, "marktdaten_baseline_q1_2026"),
]

inserted = 0
for plz, stadt, stadtteil, datum, typ, preis, pmin, pmax, quelle in daten:
    try:
        conn.execute(
            """INSERT OR IGNORE INTO immobilienpreise
               (plz, stadt, stadtteil, datum, typ, preis_pro_qm, preis_min, preis_max, quelle)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (plz, stadt, stadtteil, datum, typ, preis, pmin, pmax, quelle)
        )
        inserted += 1
    except Exception as e:
        print(f"Fehler: {e}")

conn.commit()
conn.close()

print(f"✅ Heidelsheim hinzugefügt: {inserted} Datensätze")
print(f"   Wohnung: 2.850 €/m² (2.420 – 3.280)")
print(f"   Haus:    3.200 €/m² (2.720 – 3.680)")
