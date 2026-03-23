"""
═══════════════════════════════════════════════════════════════
  Real Estate Tool — Web-Interface (Flask)
  
  Startet einen lokalen Webserver auf http://localhost:5000
  
  Nutzung:
    set GROQ_API_KEY=dein_key_hier
    python app.py
═══════════════════════════════════════════════════════════════
"""

from flask import Flask, render_template, request, jsonify
from database import init_db, get_connection
from modell import schaetze_preis, get_basispreis
from llm_bewertung import bewerte_freitext
import json

app = Flask(__name__)


@app.route("/")
def index():
    """Hauptseite mit Eingabeformular."""
    return render_template("index.html")


@app.route("/api/schaetzen", methods=["POST"])
def api_schaetzen():
    """API-Endpoint für die Preisschätzung."""
    try:
        data = request.get_json()
        
        plz = data.get("plz", "").strip()
        stadtteil = data.get("stadtteil", "").strip()
        wohnflaeche = float(data.get("wohnflaeche", 0))
        zimmer = int(data.get("zimmer", 0))
        baujahr = int(data.get("baujahr", 0))
        typ = data.get("typ", "wohnung").lower()
        zustand = data.get("zustand", "normal").lower()
        freitext = data.get("freitext", "").strip()
        
        # Neue Felder
        bauart = data.get("bauart", "").strip()
        fassade = data.get("fassade", "").strip()
        heizung = data.get("heizung", "").strip()
        energieausweis = data.get("energieausweis", "").strip()
        keller = data.get("keller", "").strip()
        solarthermie = data.get("solarthermie", False)
        
        # Validierung
        fehler = []
        if not plz:
            fehler.append("PLZ fehlt")
        if wohnflaeche <= 0:
            fehler.append("Wohnfläche muss > 0 sein")
        if zimmer <= 0:
            fehler.append("Zimmeranzahl muss > 0 sein")
        if baujahr < 1800 or baujahr > 2027:
            fehler.append("Baujahr ungültig")
        if typ not in ["wohnung", "haus"]:
            fehler.append("Typ muss 'wohnung' oder 'haus' sein")
        
        if fehler:
            return jsonify({"status": "fehler", "fehler": fehler}), 400
        
        # LLM-Bewertung (Freitext)
        llm = bewerte_freitext(freitext)
        
        # Ensemble-Prognose
        result = schaetze_preis(
            plz=plz,
            wohnflaeche=wohnflaeche,
            zimmer=zimmer,
            baujahr=baujahr,
            typ=typ,
            zustand=zustand,
            stadtteil=stadtteil,
            heizung=heizung,
            energieausweis=energieausweis,
            bauart=bauart,
            keller=keller,
            fassade=fassade,
            solarthermie=solarthermie,
            llm_korrektur=llm["korrektur"],
            llm_erklaerung=llm.get("erklaerung", "")
        )
        
        # 10-Jahres-Prognose
        from prognose import berechne_prognose
        prognose = berechne_prognose(
            aktueller_preis=result["geschaetzter_preis"],
            typ=typ,
            energieausweis=energieausweis,
            heizung=heizung,
            bauart=bauart,
            solarthermie=solarthermie,
            zustand=zustand,
        )
        result["prognose"] = prognose
        
        # LLM-Details anhängen
        result["llm"] = llm
        result["status"] = "erfolg"
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"status": "fehler", "fehler": [str(e)]}), 500


@app.route("/api/stadtteile")
def api_stadtteile():
    """Gibt alle verfügbaren PLZ/Stadtteile zurück."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT plz, stadt, stadtteil
        FROM immobilienpreise
        WHERE quelle = 'marktdaten_baseline_q1_2026'
        ORDER BY stadt, stadtteil
    """).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in rows])


@app.route("/api/historie/<plz>")
def api_historie(plz):
    """Gibt historische Preisentwicklung zurück."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT datum, typ, preis_pro_qm
        FROM immobilienpreise
        WHERE quelle = 'historisch_aggregiert'
        ORDER BY datum
    """).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in rows])


@app.route("/api/markt")
def api_markt():
    """Gibt aktuelle Marktdaten zurück."""
    conn = get_connection()
    
    # Letzter Hypothekenzins
    hypo = conn.execute("""
        SELECT zinssatz FROM hypothekenzinsen
        WHERE zinsbindung_jahre = 10
        ORDER BY datum DESC LIMIT 1
    """).fetchone()
    
    # Letzte Inflation
    infl = conn.execute("""
        SELECT inflationsrate FROM inflation
        ORDER BY datum DESC LIMIT 1
    """).fetchone()
    
    # EZB
    ezb = conn.execute("""
        SELECT zinssatz FROM ezb_zinssaetze
        ORDER BY datum DESC LIMIT 1
    """).fetchone()
    
    conn.close()
    
    return jsonify({
        "hypothekenzins_10j": hypo["zinssatz"] if hypo else None,
        "inflation": infl["inflationsrate"] if infl else None,
        "ezb_leitzins": ezb["zinssatz"] if ezb else None,
    })


if __name__ == "__main__":
    init_db()
    print("\n" + "=" * 50)
    print("  REAL ESTATE TOOL — Web-Interface")
    print("  http://localhost:5000")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)
