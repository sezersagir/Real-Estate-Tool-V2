"""
Prognosemodell v2: Zinspfad-basierte Wertentwicklung

Formel: Wachstum(Jahr) = Basis-Trend + (Zins-Delta * Sensitivitaet) + Objekt-Korrektur

Zinspfade basieren auf gewichtetem Consensus aus:
- EZB Survey of Monetary Analysts (Gewicht: 3)
- Bloomberg Consensus (Gewicht: 3)
- Bundesbank (Gewicht: 3)
- Dr. Klein Expertenrat (Gewicht: 2)
- Interhyp Bankenpanel (Gewicht: 2)
- ING, Commerzbank, BlackRock (Gewicht: je 1)

Zins-Sensitivitaet: 1% Zinssenkung -> +0.5% Preiswachstum p.a.
"""

from database import get_connection

AKTUELLER_ZINS = 3.6

ZINSPFADE = {
    "optimistisch": {1:3.4, 2:3.1, 3:2.9, 4:2.7, 5:2.6, 6:2.5, 7:2.5, 8:2.5, 9:2.5, 10:2.5},
    "realistisch":  {1:3.5, 2:3.3, 3:3.2, 4:3.2, 5:3.1, 6:3.0, 7:3.0, 8:3.0, 9:3.0, 10:3.0},
    "pessimistisch":{1:3.8, 2:4.2, 3:4.5, 4:4.8, 5:4.8, 6:4.5, 7:4.3, 8:4.2, 9:4.2, 10:4.0},
}

ZINS_SENSITIVITAET = 0.5


def _get_basis_trend(typ="wohnung"):
    conn = get_connection()
    preise = conn.execute(
        "SELECT datum, preis_pro_qm FROM immobilienpreise "
        "WHERE quelle = 'historisch_aggregiert' AND typ = ? ORDER BY datum ASC", (typ,)
    ).fetchall()
    conn.close()
    if len(preise) < 2:
        return 0.025
    erster = preise[0]["preis_pro_qm"]
    letzter = preise[-1]["preis_pro_qm"]
    jahre = len(preise) - 1
    if erster <= 0 or jahre <= 0:
        return 0.025
    cagr = (letzter / erster) ** (1.0 / jahre) - 1.0
    gedaempft = cagr * 0.75
    return round(max(0.01, min(0.035, gedaempft)), 4)


def _get_objekt_korrektur(energieausweis, heizung, bauart, solarthermie, zustand):
    korrektur = 0.0
    energie_map = {"a+":0.003,"a":0.002,"b":0.001,"c":0.0,"d":-0.002,"e":-0.004,"f":-0.007,"g":-0.010,"h":-0.015}
    korrektur += energie_map.get(energieausweis.lower().strip(), 0.0)
    
    heizung_lower = heizung.lower().strip()
    h_map = {"wärmepumpe":0.002,"waermepumpe":0.002,"fernwärme":0.001,"fernwaerme":0.001,"pellets":0.001,
             "gas_neu":0.0,"gas neu":0.0,"gasbrennwert":0.0,"gas_alt":-0.003,"gas alt":-0.003,"gasheizung":-0.002,
             "öl":-0.006,"oel":-0.006,"ölheizung":-0.006,"nachtspeicher":-0.008}
    for k,v in h_map.items():
        if k in heizung_lower:
            korrektur += v
            break
    
    bauart_lower = bauart.lower().strip()
    b_map = {"massivbau":0.001,"massiv":0.001,"vollwärmedämmung":0.002,"vollwaermedaemmung":0.002,
             "wdvs":0.002,"gedämmt":0.001,"gedaemmt":0.001,"rahmenbauweise":-0.001,"holzrahmen":-0.001,"fertighaus":0.0}
    for k,v in b_map.items():
        if k in bauart_lower:
            korrektur += v
            break
    
    if solarthermie:
        korrektur += 0.001
    
    z_map = {"erstbezug":0.002,"renoviert":0.001,"normal":0.0,"teilsaniert":-0.002,"sanierungsbedürftig":-0.005}
    korrektur += z_map.get(zustand.lower().strip(), 0.0)
    return round(korrektur, 4)


def berechne_prognose(aktueller_preis, typ, energieausweis="", heizung="",
                       bauart="", solarthermie=False, zustand="normal"):
    erklaerungen = []
    
    basis_trend = _get_basis_trend(typ)
    erklaerungen.append(f"Basis-Trend Karlsruhe ({typ}): {basis_trend*100:.1f}% p.a. (historisch, gedaempft)")
    
    objekt_korr = _get_objekt_korrektur(energieausweis, heizung, bauart, solarthermie, zustand)
    if objekt_korr != 0:
        richtung = "stuetzt Wertentwicklung" if objekt_korr > 0 else "bremst Wertentwicklung"
        erklaerungen.append(f"Objektqualitaet: {objekt_korr*100:+.1f}% p.a. ({richtung})")
    
    aktueller_zins = AKTUELLER_ZINS
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT zinssatz FROM hypothekenzinsen WHERE zinsbindung_jahre = 10 ORDER BY datum DESC LIMIT 1"
        ).fetchone()
        if row:
            aktueller_zins = row["zinssatz"]
        conn.close()
    except Exception:
        pass
    
    erklaerungen.append(f"Aktueller Hypothekenzins 10J: {aktueller_zins}%")
    erklaerungen.append(f"Zins-Sensitivitaet: 1% Zinssenkung = +{ZINS_SENSITIVITAET}% Preiswachstum")
    
    szenarien = {}
    labels = {"optimistisch":"Optimistisch","realistisch":"Realistisch","pessimistisch":"Pessimistisch"}
    
    for szenario_name, zinspfad in ZINSPFADE.items():
        werte = []
        raten = []
        wert = aktueller_preis
        
        for jahr in range(1, 11):
            zins_prognose = zinspfad[jahr]
            zins_delta = aktueller_zins - zins_prognose
            zins_effekt = zins_delta * ZINS_SENSITIVITAET / 100
            jahres_rate = basis_trend + zins_effekt + objekt_korr
            jahres_rate = max(-0.03, min(0.05, jahres_rate))
            wert = wert * (1 + jahres_rate)
            werte.append(round(wert))
            raten.append(round(jahres_rate, 4))
        
        endwert = werte[-1]
        avg_rate = (endwert / aktueller_preis) ** (1.0/10) - 1.0
        
        annahmen = {
            "optimistisch": f"Zinsen fallen auf {zinspfad[10]}%, starke Nachfrage",
            "realistisch": f"Zinsen pendeln bei {zinspfad[10]}%, stabiler Markt",
            "pessimistisch": f"Zinsen steigen auf max. {max(zinspfad.values())}%, schwache Nachfrage",
        }
        
        szenarien[szenario_name] = {
            "rate": round(avg_rate, 4),
            "label": labels[szenario_name],
            "annahme": annahmen[szenario_name],
            "werte": werte,
            "raten_pro_jahr": raten,
            "zinspfad": [zinspfad[j] for j in range(1, 11)],
            "endwert": endwert,
            "gewinn": endwert - round(aktueller_preis),
            "gewinn_prozent": round(((endwert / aktueller_preis) - 1) * 100, 1),
        }
    
    for key in ["pessimistisch", "realistisch", "optimistisch"]:
        s = szenarien[key]
        erklaerungen.append(f"{s['label']}: Oe {s['rate']*100:+.1f}% p.a. -> {s['endwert']:,} EUR ({s['gewinn_prozent']:+.1f}%)".replace(",","."))
    
    erklaerungen.append("Hinweis: Alle Werte nominal. Bei ~2% Inflation p.a. liegt der reale Wertzuwachs ca. 20 Prozentpunkte niedriger.")
    
    return {
        "aktueller_preis": round(aktueller_preis),
        "szenarien": szenarien,
        "basis_trend": basis_trend,
        "objekt_korrektur": objekt_korr,
        "aktueller_zins": aktueller_zins,
        "zins_sensitivitaet": ZINS_SENSITIVITAET,
        "erklaerungen": erklaerungen,
    }


if __name__ == "__main__":
    from database import init_db
    init_db()
    
    print("=== GUTES OBJEKT ===")
    r = berechne_prognose(300000, "haus", "B", "Wärmepumpe", "Massivbau", True, "renoviert")
    for key in ["pessimistisch", "realistisch", "optimistisch"]:
        s = r["szenarien"][key]
        print(f"  {s['label']}: {s['rate']*100:+.1f}% p.a. -> {s['endwert']:,} EUR ({s['gewinn_prozent']:+.1f}%)")
        print(f"    Zinspfad: {s['zinspfad'][:5]} ...")
        print(f"    Raten:    {[f'{x*100:.1f}%' for x in s['raten_pro_jahr'][:5]]} ...")
    
    print()
    print("=== SCHLECHTES OBJEKT ===")
    r2 = berechne_prognose(300000, "haus", "G", "Ölheizung", "Rahmenbauweise", False, "sanierungsbedürftig")
    for key in ["pessimistisch", "realistisch", "optimistisch"]:
        s = r2["szenarien"][key]
        print(f"  {s['label']}: {s['rate']*100:+.1f}% p.a. -> {s['endwert']:,} EUR ({s['gewinn_prozent']:+.1f}%)")
    
    print()
    print("=== NORMAL (keine Extras) ===")
    r3 = berechne_prognose(300000, "haus")
    for key in ["pessimistisch", "realistisch", "optimistisch"]:
        s = r3["szenarien"][key]
        print(f"  {s['label']}: {s['rate']*100:+.1f}% p.a. -> {s['endwert']:,} EUR ({s['gewinn_prozent']:+.1f}%)")
    
    print()
    for e in r["erklaerungen"]:
        print(f"  {e}")
