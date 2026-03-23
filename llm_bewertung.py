"""
═══════════════════════════════════════════════════════════════
  LLM-Bewertung: Freitext → Preiskorrektur
  
  Nutzt Groq API (Llama 3) um Freitext-Beschreibungen wie
  "Garage nicht gestrichen", "Dach neu 2023", "Keller feucht"
  in eine prozentuale Preisanpassung zu übersetzen.
═══════════════════════════════════════════════════════════════
"""

import os
import json

# Groq API Key aus Umgebungsvariable
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


SYSTEM_PROMPT = """Du bist ein deutscher Immobiliengutachter-Assistent.

Deine Aufgabe: Analysiere die Freitextbeschreibung einer Immobilie und berechne eine prozentuale Preisanpassung.

REGELN:
- Positive Eigenschaften erhöhen den Preis (z.B. "neues Dach", "Fußbodenheizung", "Südbalkon")
- Negative Eigenschaften senken den Preis (z.B. "Keller feucht", "Garage nicht gestrichen", "alte Heizung")
- Die Korrektur soll realistisch sein: meistens zwischen -15% und +15%
- Extreme Fälle (Schimmel, Asbest) können bis -30% gehen
- Premium-Ausstattung (Smart Home, Pool, Aufzug) kann bis +20% gehen

ANTWORTFORMAT: Du MUSST exakt dieses JSON-Format zurückgeben, NICHTS anderes:
{
  "korrektur_prozent": <Zahl zwischen -30 und +20>,
  "erklaerung": "<1-2 Sätze auf Deutsch>",
  "details": [
    {"merkmal": "<Eigenschaft>", "effekt": <Prozentzahl>}
  ]
}

Beispiel Input: "Garage nicht gestrichen, aber Dach 2023 neu gemacht"
Beispiel Output:
{
  "korrektur_prozent": 2.5,
  "erklaerung": "Das neue Dach (+5%) überwiegt die unrenovierte Garage (-2.5%), Nettoeffekt positiv.",
  "details": [
    {"merkmal": "Dach neu (2023)", "effekt": 5.0},
    {"merkmal": "Garage unrenoviert", "effekt": -2.5}
  ]
}"""


def bewerte_freitext(freitext: str) -> dict:
    """
    Sendet den Freitext an Groq und bekommt eine Preiskorrektur zurück.
    
    Returns:
        {
            "korrektur": float (-0.30 bis +0.20),
            "erklaerung": str,
            "details": list,
            "status": "erfolg" | "fehler" | "kein_text"
        }
    """
    # Kein Text eingegeben
    if not freitext or freitext.strip() == "":
        return {
            "korrektur": 0.0,
            "erklaerung": "Keine zusätzlichen Angaben gemacht.",
            "details": [],
            "status": "kein_text"
        }
    
    # Kein API Key
    if not GROQ_API_KEY:
        return {
            "korrektur": 0.0,
            "erklaerung": "Groq API Key nicht konfiguriert. Freitext-Bewertung deaktiviert.",
            "details": [],
            "status": "fehler"
        }
    
    try:
        from groq import Groq
        
        client = Groq(api_key=GROQ_API_KEY)
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Bewerte folgende Immobilienbeschreibung:\n\n{freitext}"}
            ],
            temperature=0.3,  # Niedrig für konsistente Bewertungen
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        
        antwort_text = response.choices[0].message.content
        
        # JSON parsen
        try:
            antwort = json.loads(antwort_text)
        except json.JSONDecodeError:
            # Versuche JSON aus dem Text zu extrahieren
            import re
            json_match = re.search(r'\{.*\}', antwort_text, re.DOTALL)
            if json_match:
                antwort = json.loads(json_match.group())
            else:
                return {
                    "korrektur": 0.0,
                    "erklaerung": f"LLM-Antwort konnte nicht geparst werden.",
                    "details": [],
                    "status": "fehler"
                }
        
        # Korrektur extrahieren und begrenzen
        korrektur_pct = antwort.get("korrektur_prozent", 0)
        korrektur_pct = max(-30, min(20, korrektur_pct))  # Clamp
        
        return {
            "korrektur": round(korrektur_pct / 100, 4),  # Prozent → Faktor
            "korrektur_prozent": korrektur_pct,
            "erklaerung": antwort.get("erklaerung", "Keine Erklärung verfügbar."),
            "details": antwort.get("details", []),
            "status": "erfolg"
        }
        
    except ImportError:
        return {
            "korrektur": 0.0,
            "erklaerung": "Groq Python-Paket nicht installiert. Bitte: pip install groq",
            "details": [],
            "status": "fehler"
        }
    except Exception as e:
        return {
            "korrektur": 0.0,
            "erklaerung": f"Groq API Fehler: {str(e)}",
            "details": [],
            "status": "fehler"
        }


if __name__ == "__main__":
    # Test
    test_texte = [
        "Garage nicht gestrichen, Dach aber 2023 komplett neu gemacht. Südbalkon vorhanden.",
        "Keller feucht, alte Gasheizung von 1990, einfache Verglasung",
        "Smart Home System, Fußbodenheizung, Einbauküche Bulthaup, Tiefgaragenstellplatz",
    ]
    
    for text in test_texte:
        print(f"\nInput: {text}")
        result = bewerte_freitext(text)
        print(f"Korrektur: {result.get('korrektur_prozent', result['korrektur']*100):+.1f}%")
        print(f"Erklärung: {result['erklaerung']}")
        print(f"Status: {result['status']}")
        if result["details"]:
            for d in result["details"]:
                print(f"  • {d['merkmal']}: {d['effekt']:+.1f}%")
