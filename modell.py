"""
═══════════════════════════════════════════════════════════════
  System 2: Ensemble-Prognosemodell
  
  Kombination aus:
  1. PLZ-basierter Basispreis (aus Datenbank)
  2. Objektspezifische Multiplikatoren (Baujahr, Zustand, Größe)
  3. Makro-Trendkorrektur (Zinsen, Inflation, Bevölkerung)
  4. Regressionsschätzung (wenn genug historische Daten)
  
  Die finale Schätzung ist ein gewichteter Mix aus allen Methoden.
═══════════════════════════════════════════════════════════════
"""

import math
from datetime import datetime
from database import get_connection


# ═══════════════════════════════════════════════
# Konfiguration: Gewichte der Ensemble-Komponenten
# ═══════════════════════════════════════════════

ENSEMBLE_GEWICHTE = {
    "basispreis": 0.50,      # PLZ-Durchschnitt ist das Fundament
    "objekt_anpassung": 0.30, # Baujahr, Zustand, Größe
    "makro_korrektur": 0.20,  # Zinsen, Trend, Inflation
}


# ═══════════════════════════════════════════════
# 1. Basispreis aus Datenbank
# ═══════════════════════════════════════════════

def get_basispreis(plz: str, typ: str, stadtteil: str = "") -> dict:
    """
    Holt den Basispreis pro m² für eine PLZ + Stadtteil.
    Gibt Durchschnitt, Min und Max zurück.
    """
    conn = get_connection()
    
    # Exakten PLZ + Stadtteil Match versuchen
    if stadtteil:
        row = conn.execute("""
            SELECT preis_pro_qm, preis_min, preis_max, stadtteil, stadt
            FROM immobilienpreise
            WHERE plz = ? AND typ = ? AND stadtteil = ?
            AND quelle = 'marktdaten_baseline_q1_2026'
            ORDER BY datum DESC LIMIT 1
        """, (plz, typ, stadtteil)).fetchone()
        
        if row:
            conn.close()
            return {
                "preis_pro_qm": row["preis_pro_qm"],
                "preis_min": row["preis_min"],
                "preis_max": row["preis_max"],
                "stadtteil": row["stadtteil"],
                "stadt": row["stadt"],
                "methode": "exakt"
            }
    
    # Fallback: nur PLZ
    row = conn.execute("""
        SELECT preis_pro_qm, preis_min, preis_max, stadtteil, stadt
        FROM immobilienpreise
        WHERE plz = ? AND typ = ? AND quelle = 'marktdaten_baseline_q1_2026'
        ORDER BY datum DESC LIMIT 1
    """, (plz, typ)).fetchone()
    
    if row:
        conn.close()
        return {
            "preis_pro_qm": row["preis_pro_qm"],
            "preis_min": row["preis_min"],
            "preis_max": row["preis_max"],
            "stadtteil": row["stadtteil"],
            "stadt": row["stadt"],
            "methode": "exakt"
        }
    
    # Fallback: Karlsruhe-Durchschnitt
    avg = conn.execute("""
        SELECT AVG(preis_pro_qm) as avg_preis,
               MIN(preis_pro_qm) as min_preis,
               MAX(preis_pro_qm) as max_preis
        FROM immobilienpreise
        WHERE stadt = 'Karlsruhe' AND typ = ?
        AND quelle = 'marktdaten_baseline_q1_2026'
    """, (typ,)).fetchone()
    
    conn.close()
    
    if avg and avg["avg_preis"]:
        return {
            "preis_pro_qm": round(avg["avg_preis"]),
            "preis_min": round(avg["min_preis"]),
            "preis_max": round(avg["max_preis"]),
            "stadtteil": "Durchschnitt",
            "stadt": "Karlsruhe",
            "methode": "durchschnitt"
        }
    
    # Absoluter Fallback
    fallback = 4050 if typ == "wohnung" else 4200
    return {
        "preis_pro_qm": fallback,
        "preis_min": round(fallback * 0.85),
        "preis_max": round(fallback * 1.15),
        "stadtteil": "Unbekannt",
        "stadt": "Karlsruhe",
        "methode": "fallback"
    }


# ═══════════════════════════════════════════════
# 2. Objektspezifische Multiplikatoren
# ═══════════════════════════════════════════════

def berechne_objekt_multiplikator(
    baujahr: int,
    zustand: str,
    wohnflaeche: float,
    zimmer: int,
    typ: str,
    heizung: str = "",
    energieausweis: str = "",
    bauart: str = "",
    keller: str = "",
    fassade: str = "",
    solarthermie: bool = False,
) -> dict:
    """
    Berechnet einen Multiplikator basierend auf Objekteigenschaften.
    Asymmetrisch: Schlecht drückt stark, gut hebt kaum — weil der
    Basispreis in der DB bereits ein "normales" Objekt widerspiegelt.
    """
    faktoren = {}
    erklaerungen = []
    
    # ── Baujahr-Faktor ──
    aktuelles_jahr = datetime.now().year
    alter = aktuelles_jahr - baujahr
    
    if alter <= 3:
        faktoren["baujahr"] = 1.15
        erklaerungen.append(f"Neubau ({baujahr}): +15%")
    elif alter <= 10:
        faktoren["baujahr"] = 1.08
        erklaerungen.append(f"Neuwertig ({baujahr}): +8%")
    elif alter <= 20:
        faktoren["baujahr"] = 1.02
        erklaerungen.append(f"Modern ({baujahr}): +2%")
    elif alter <= 40:
        faktoren["baujahr"] = 0.97
        erklaerungen.append(f"Bestandsbau ({baujahr}): -3%")
    elif alter <= 60:
        faktoren["baujahr"] = 0.90
        erklaerungen.append(f"Altbau ({baujahr}): -10%")
    elif alter <= 80:
        faktoren["baujahr"] = 0.82
        erklaerungen.append(f"Historisch ({baujahr}): -18%")
    else:
        faktoren["baujahr"] = 0.75
        erklaerungen.append(f"Sehr alt ({baujahr}): -25%")
    
    # ── Zustand-Faktor ──
    zustand_map = {
        "renoviert": (1.12, "Renoviert: +12%"),
        "erstbezug": (1.18, "Erstbezug: +18%"),
        "normal": (1.00, "Normaler Zustand: ±0%"),
        "sanierungsbedürftig": (0.72, "Sanierungsbedürftig: -28%"),
        "teilsaniert": (0.88, "Teilsaniert: -12%"),
    }
    zustand_lower = zustand.lower().strip()
    z_faktor, z_text = zustand_map.get(zustand_lower, (1.00, f"Zustand '{zustand}': ±0%"))
    faktoren["zustand"] = z_faktor
    erklaerungen.append(z_text)
    
    # ── Heizung-Faktor (asymmetrisch) ──
    if heizung:
        heizung_lower = heizung.lower().strip()
        heizung_map = {
            "wärmepumpe": (1.00, "Wärmepumpe (Standard bei Neubau): ±0%"),
            "waermepumpe": (1.00, "Wärmepumpe (Standard bei Neubau): ±0%"),
            "fernwärme": (1.00, "Fernwärme: ±0%"),
            "fernwaerme": (1.00, "Fernwärme: ±0%"),
            "pellets": (1.00, "Pelletheizung: ±0%"),
            "gas_neu": (0.98, "Gas-Brennwert (nach 2015): -2%"),
            "gas neu": (0.98, "Gas-Brennwert (nach 2015): -2%"),
            "gas_alt": (0.92, "Alte Gasheizung (vor 2015): -8%"),
            "gas alt": (0.92, "Alte Gasheizung (vor 2015): -8%"),
            "öl": (0.88, "Ölheizung (GEG-Risiko): -12%"),
            "oel": (0.88, "Ölheizung (GEG-Risiko): -12%"),
            "nachtspeicher": (0.85, "Nachtspeicher (veraltet): -15%"),
        }
        for key, (faktor, text) in heizung_map.items():
            if key in heizung_lower:
                faktoren["heizung"] = faktor
                erklaerungen.append(text)
                break
    
    # ── Energieausweis-Faktor (asymmetrisch) ──
    if energieausweis:
        energie_map = {
            "a+": (1.02, "Energieausweis A+: +2%"),
            "a":  (1.01, "Energieausweis A: +1%"),
            "b":  (1.00, "Energieausweis B: ±0%"),
            "c":  (1.00, "Energieausweis C: ±0%"),
            "d":  (0.97, "Energieausweis D: -3%"),
            "e":  (0.94, "Energieausweis E: -6%"),
            "f":  (0.90, "Energieausweis F: -10%"),
            "g":  (0.86, "Energieausweis G: -14%"),
            "h":  (0.82, "Energieausweis H: -18%"),
        }
        e_key = energieausweis.lower().strip()
        if e_key in energie_map:
            faktoren["energieausweis"] = energie_map[e_key][0]
            erklaerungen.append(energie_map[e_key][1])
    
    # ── Bauart-Faktor ──
    if bauart:
        bauart_lower = bauart.lower().strip()
        if "massivbau_wdvs" in bauart_lower or "vollwärmedämmung" in bauart_lower:
            faktoren["bauart"] = 1.02
            erklaerungen.append("Massivbau + WDVS: +2%")
        elif "massivbau" in bauart_lower or "massiv" in bauart_lower:
            faktoren["bauart"] = 1.01
            erklaerungen.append("Massivbau: +1%")
        elif "rahmenbauweise" in bauart_lower or "fertighaus" in bauart_lower:
            faktoren["bauart"] = 0.97
            erklaerungen.append("Rahmenbauweise/Fertighaus: -3%")
    
    # ── Fassade-Faktor ──
    if fassade:
        fassade_lower = fassade.lower().strip()
        if "sichtmauerwerk" in fassade_lower or "klinker" in fassade_lower:
            faktoren["fassade"] = 1.02
            erklaerungen.append("Sichtmauerwerk/Klinker (wartungsarm): +2%")
        elif "wdvs" in fassade_lower:
            faktoren["fassade"] = 1.01
            erklaerungen.append("WDVS-Fassade: +1%")
        elif "rauputz" in fassade_lower:
            faktoren["fassade"] = 1.00
            erklaerungen.append("Rauputz (Standard): ±0%")
    
    # ── Keller-Faktor ──
    if keller:
        keller_lower = keller.lower().strip()
        if "vollkeller" in keller_lower:
            faktoren["keller"] = 1.02
            erklaerungen.append("Vollkeller: +2%")
        elif "teilkeller" in keller_lower:
            faktoren["keller"] = 1.00
            erklaerungen.append("Teilkeller: ±0%")
        elif "kein" in keller_lower:
            faktoren["keller"] = 0.96
            erklaerungen.append("Kein Keller: -4%")
    
    # ── Solar/PV ──
    if solarthermie:
        faktoren["solar"] = 1.03
        erklaerungen.append("Solar/PV-Anlage: +3%")
    
    # ── Wohnfläche-Faktor ──
    if typ == "wohnung":
        if wohnflaeche < 40:
            faktoren["flaeche"] = 1.08
            erklaerungen.append(f"Kleine Wohnung ({wohnflaeche}m²): +8%/m²")
        elif wohnflaeche < 60:
            faktoren["flaeche"] = 1.03
            erklaerungen.append(f"Kompakte Wohnung ({wohnflaeche}m²): +3%/m²")
        elif wohnflaeche < 100:
            faktoren["flaeche"] = 1.00
            erklaerungen.append(f"Standardgröße ({wohnflaeche}m²): ±0%")
        elif wohnflaeche < 140:
            faktoren["flaeche"] = 0.97
            erklaerungen.append(f"Große Wohnung ({wohnflaeche}m²): -3%/m²")
        else:
            faktoren["flaeche"] = 0.93
            erklaerungen.append(f"Sehr große Wohnung ({wohnflaeche}m²): -7%/m²")
    else:
        if wohnflaeche < 80:
            faktoren["flaeche"] = 1.05
            erklaerungen.append(f"Kleines Haus ({wohnflaeche}m²): +5%/m²")
        elif wohnflaeche < 150:
            faktoren["flaeche"] = 1.00
            erklaerungen.append(f"Standardgröße ({wohnflaeche}m²): ±0%")
        elif wohnflaeche < 220:
            faktoren["flaeche"] = 0.96
            erklaerungen.append(f"Großes Haus ({wohnflaeche}m²): -4%/m²")
        else:
            faktoren["flaeche"] = 0.91
            erklaerungen.append(f"Villa-Größe ({wohnflaeche}m²): -9%/m²")
    
    # ── Raumeffizienz-Faktor ──
    qm_pro_zimmer = wohnflaeche / max(zimmer, 1)
    if 18 <= qm_pro_zimmer <= 28:
        faktoren["effizienz"] = 1.03
        erklaerungen.append(f"Effiziente Aufteilung ({qm_pro_zimmer:.0f}m²/Zi): +3%")
    elif qm_pro_zimmer < 15:
        faktoren["effizienz"] = 0.95
        erklaerungen.append(f"Sehr kleine Zimmer ({qm_pro_zimmer:.0f}m²/Zi): -5%")
    elif qm_pro_zimmer > 40:
        faktoren["effizienz"] = 0.98
        erklaerungen.append(f"Wenige große Räume ({qm_pro_zimmer:.0f}m²/Zi): -2%")
    else:
        faktoren["effizienz"] = 1.00
    
    # Gesamtmultiplikator (alle Faktoren multiplizieren)
    gesamt = 1.0
    for f in faktoren.values():
        gesamt *= f
    
    return {
        "multiplikator": round(gesamt, 4),
        "faktoren": faktoren,
        "erklaerungen": erklaerungen
    }


# ═══════════════════════════════════════════════
# 3. Makro-Trendkorrektur
# ═══════════════════════════════════════════════

def berechne_makro_korrektur() -> dict:
    """
    Berechnet eine Trendkorrektur basierend auf Makrodaten.
    Positiv = Markt stützt Preise, Negativ = Markt drückt Preise.
    """
    conn = get_connection()
    korrekturen = {}
    erklaerungen = []
    
    # ── Zinstrend ──
    try:
        zinsen = conn.execute("""
            SELECT zinssatz FROM hypothekenzinsen
            WHERE zinsbindung_jahre = 10
            ORDER BY datum DESC LIMIT 2
        """).fetchall()
        
        if len(zinsen) >= 2:
            aktuell = zinsen[0]["zinssatz"]
            vorher = zinsen[1]["zinssatz"]
            delta = aktuell - vorher
            
            if delta > 0.2:
                korrekturen["zinsen"] = -0.03
                erklaerungen.append(f"Hypothekenzinsen steigend ({aktuell}%): -3%")
            elif delta < -0.2:
                korrekturen["zinsen"] = 0.03
                erklaerungen.append(f"Hypothekenzinsen fallend ({aktuell}%): +3%")
            else:
                korrekturen["zinsen"] = 0.0
                erklaerungen.append(f"Hypothekenzinsen stabil ({aktuell}%): ±0%")
    except Exception:
        korrekturen["zinsen"] = 0.0
    
    # ── Preistrend (historisch) ──
    try:
        preise = conn.execute("""
            SELECT preis_pro_qm, datum FROM immobilienpreise
            WHERE quelle = 'historisch_aggregiert' AND typ = 'wohnung'
            ORDER BY datum DESC LIMIT 3
        """).fetchall()
        
        if len(preise) >= 2:
            trend = (preise[0]["preis_pro_qm"] - preise[1]["preis_pro_qm"]) / preise[1]["preis_pro_qm"]
            korrekturen["preistrend"] = round(trend * 0.5, 4)  # Halber Trend als Korrektur
            richtung = "steigend" if trend > 0 else "fallend"
            erklaerungen.append(
                f"Preistrend {richtung} ({trend*100:+.1f}%): "
                f"{korrekturen['preistrend']*100:+.1f}% Korrektur"
            )
    except Exception:
        korrekturen["preistrend"] = 0.0
    
    # ── Bevölkerungstrend ──
    try:
        bev = conn.execute("""
            SELECT einwohner, jahr FROM bevoelkerung
            WHERE stadt = 'Karlsruhe'
            ORDER BY jahr DESC LIMIT 2
        """).fetchall()
        
        if len(bev) >= 2:
            wachstum = (bev[0]["einwohner"] - bev[1]["einwohner"]) / bev[1]["einwohner"]
            if wachstum > 0.005:
                korrekturen["bevoelkerung"] = 0.01
                erklaerungen.append("Bevölkerung wachsend: +1%")
            elif wachstum < -0.005:
                korrekturen["bevoelkerung"] = -0.01
                erklaerungen.append("Bevölkerung schrumpfend: -1%")
            else:
                korrekturen["bevoelkerung"] = 0.0
                erklaerungen.append("Bevölkerung stabil: ±0%")
    except Exception:
        korrekturen["bevoelkerung"] = 0.0
    
    # ── Inflation ──
    try:
        infl = conn.execute("""
            SELECT inflationsrate FROM inflation
            ORDER BY datum DESC LIMIT 1
        """).fetchone()
        
        if infl:
            rate = infl["inflationsrate"]
            if rate > 3.0:
                korrekturen["inflation"] = -0.02
                erklaerungen.append(f"Hohe Inflation ({rate}%): -2%")
            elif rate < 1.5:
                korrekturen["inflation"] = 0.01
                erklaerungen.append(f"Niedrige Inflation ({rate}%): +1%")
            else:
                korrekturen["inflation"] = 0.0
                erklaerungen.append(f"Inflation im Zielbereich ({rate}%): ±0%")
    except Exception:
        korrekturen["inflation"] = 0.0
    
    # ── Baupreisindex ──
    try:
        bau = conn.execute("""
            SELECT veraenderung_vj FROM baupreisindex
            ORDER BY datum DESC LIMIT 1
        """).fetchone()
        
        if bau:
            vj = bau["veraenderung_vj"]
            if vj > 5.0:
                korrekturen["baukosten"] = 0.02
                erklaerungen.append(f"Baukosten stark steigend (+{vj}%): +2%")
            elif vj > 2.0:
                korrekturen["baukosten"] = 0.01
                erklaerungen.append(f"Baukosten steigend (+{vj}%): +1%")
            else:
                korrekturen["baukosten"] = 0.0
                erklaerungen.append(f"Baukosten stabil (+{vj}%): ±0%")
    except Exception:
        korrekturen["baukosten"] = 0.0
    
    conn.close()
    
    # Gesamtkorrektur (additiv)
    gesamt = sum(korrekturen.values())
    
    return {
        "korrektur": round(gesamt, 4),
        "korrekturen": korrekturen,
        "erklaerungen": erklaerungen
    }


# ═══════════════════════════════════════════════
# 4. Ensemble: Alles zusammenführen
# ═══════════════════════════════════════════════

def schaetze_preis(
    plz: str,
    wohnflaeche: float,
    zimmer: int,
    baujahr: int,
    typ: str,
    zustand: str,
    stadtteil: str = "",
    heizung: str = "",
    energieausweis: str = "",
    bauart: str = "",
    keller: str = "",
    fassade: str = "",
    solarthermie: bool = False,
    llm_korrektur: float = 0.0,
    llm_erklaerung: str = ""
) -> dict:
    """
    Hauptfunktion: Schätzt den Immobilienpreis.
    """
    
    # ── Schritt 1: Basispreis ──
    basis = get_basispreis(plz, typ, stadtteil)
    basis_qm = basis["preis_pro_qm"]
    
    # ── Schritt 2: Objektanpassung ──
    objekt = berechne_objekt_multiplikator(
        baujahr, zustand, wohnflaeche, zimmer, typ,
        heizung=heizung, energieausweis=energieausweis,
        bauart=bauart, keller=keller, fassade=fassade,
        solarthermie=solarthermie
    )
    
    # ── Schritt 3: Makro-Korrektur ──
    makro = berechne_makro_korrektur()
    
    # ── Schritt 4: Ensemble-Berechnung ──
    # Angepasster m²-Preis
    angepasst_qm = basis_qm * objekt["multiplikator"]
    
    # Makro-Korrektur anwenden
    angepasst_qm *= (1 + makro["korrektur"])
    
    # LLM-Korrektur anwenden (Freitext-Bewertung)
    if llm_korrektur != 0:
        angepasst_qm *= (1 + llm_korrektur)
    
    # Gesamtpreis
    geschaetzter_preis = round(angepasst_qm * wohnflaeche)
    geschaetzter_qm = round(angepasst_qm)
    
    # ── Preisspanne berechnen ──
    # Unsicherheit basiert auf Datenqualität
    unsicherheit = 0.12  # Basis: ±12%
    if basis["methode"] == "fallback":
        unsicherheit = 0.20  # Weniger Daten = mehr Unsicherheit
    elif basis["methode"] == "durchschnitt":
        unsicherheit = 0.15
    
    preis_min = round(geschaetzter_preis * (1 - unsicherheit))
    preis_max = round(geschaetzter_preis * (1 + unsicherheit))
    qm_min = round(angepasst_qm * (1 - unsicherheit))
    qm_max = round(angepasst_qm * (1 + unsicherheit))
    
    # ── Vergleich mit PLZ-Durchschnitt ──
    abweichung_prozent = round(((angepasst_qm - basis_qm) / basis_qm) * 100, 1)
    
    # ── Erklärungen zusammenbauen ──
    alle_erklaerungen = []
    alle_erklaerungen.append(f"Basispreis {basis['stadt']} {basis['stadtteil']} ({basis['methode']}): {basis_qm} €/m²")
    alle_erklaerungen.extend(objekt["erklaerungen"])
    alle_erklaerungen.extend(makro["erklaerungen"])
    if llm_erklaerung:
        alle_erklaerungen.append(f"KI-Freitext-Bewertung: {llm_erklaerung}")
    
    return {
        # Hauptergebnis
        "geschaetzter_preis": geschaetzter_preis,
        "geschaetzter_qm_preis": geschaetzter_qm,
        "preis_min": preis_min,
        "preis_max": preis_max,
        "qm_min": qm_min,
        "qm_max": qm_max,
        
        # Details
        "plz": plz,
        "stadt": basis["stadt"],
        "stadtteil": basis["stadtteil"],
        "typ": typ,
        "wohnflaeche": wohnflaeche,
        "zimmer": zimmer,
        "baujahr": baujahr,
        "zustand": zustand,
        
        # Vergleich
        "basis_qm_preis": basis_qm,
        "abweichung_prozent": abweichung_prozent,
        
        # Transparenz
        "objekt_multiplikator": objekt["multiplikator"],
        "makro_korrektur": makro["korrektur"],
        "llm_korrektur": llm_korrektur,
        "erklaerungen": alle_erklaerungen,
        
        # Komponenten (für Debug)
        "basis": basis,
        "objekt": objekt,
        "makro": makro,
    }


# ═══════════════════════════════════════════════
# CLI Test
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    from database import init_db
    init_db()
    
    # Testfall: 3-Zimmer-Wohnung in Durlach, 75m², Baujahr 1995, normal
    result = schaetze_preis(
        plz="76227",
        wohnflaeche=75,
        zimmer=3,
        baujahr=1995,
        typ="wohnung",
        zustand="normal"
    )
    
    print(f"\n{'='*50}")
    print(f"  PREISPROGNOSE")
    print(f"{'='*50}")
    print(f"  Objekt: {result['zimmer']}Zi-{result['typ'].capitalize()}, "
          f"{result['wohnflaeche']}m², BJ {result['baujahr']}")
    print(f"  Lage:   {result['stadt']} {result['stadtteil']} ({result['plz']})")
    print(f"  Zustand: {result['zustand']}")
    print(f"\n  Geschätzter Preis: {result['geschaetzter_preis']:,} €".replace(",", "."))
    print(f"  Pro m²:           {result['geschaetzter_qm_preis']:,} €/m²".replace(",", "."))
    print(f"  Spanne:           {result['preis_min']:,} – {result['preis_max']:,} €".replace(",", "."))
    print(f"  vs. PLZ-Schnitt:  {result['abweichung_prozent']:+.1f}%")
    print(f"\n  Faktoren:")
    for e in result["erklaerungen"]:
        print(f"    • {e}")
