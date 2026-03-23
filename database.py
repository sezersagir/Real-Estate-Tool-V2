"""
Datenbank-Modul für das Real Estate Tool.
SQLite-basiert — leichtgewichtig, kein Server nötig, perfekt für MVP.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "real_estate.db")


def get_connection():
    """Erstellt eine Verbindung zur SQLite-Datenbank."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Zugriff per Spaltenname
    conn.execute("PRAGMA journal_mode=WAL")  # Bessere Performance
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Erstellt alle Tabellen, falls sie noch nicht existieren."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── 1. EZB-Zinssätze ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ezb_zinssaetze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datum DATE NOT NULL,
            zinssatz REAL NOT NULL,
            typ TEXT DEFAULT 'hauptrefinanzierung',
            quelle TEXT DEFAULT 'ECB Data API',
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(datum, typ)
        )
    """)

    # ── 2. Immobilienpreise pro Region ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS immobilienpreise (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plz TEXT NOT NULL,
            stadt TEXT NOT NULL,
            stadtteil TEXT,
            datum DATE NOT NULL,
            typ TEXT NOT NULL CHECK(typ IN ('wohnung', 'haus')),
            preis_pro_qm REAL NOT NULL,
            preis_min REAL,
            preis_max REAL,
            quelle TEXT NOT NULL,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(plz, stadtteil, datum, typ, quelle)
        )
    """)

    # ── 3. Bevölkerungsdaten ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bevoelkerung (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plz TEXT,
            stadt TEXT NOT NULL,
            jahr INTEGER NOT NULL,
            einwohner INTEGER,
            einwohner_pro_qkm REAL,
            quelle TEXT DEFAULT 'DESTATIS',
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stadt, jahr)
        )
    """)

    # ── 4. Baupreisindex (bundesweit, DESTATIS) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS baupreisindex (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datum DATE NOT NULL,
            index_wert REAL NOT NULL,
            basisjahr TEXT DEFAULT '2015=100',
            veraenderung_vj REAL,
            quelle TEXT DEFAULT 'DESTATIS',
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(datum)
        )
    """)

    # ── 5. Collector-Log (Tracking aller Datensammlungen) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collector_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collector_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('erfolg', 'fehler', 'teilweise')),
            datensaetze INTEGER DEFAULT 0,
            fehlermeldung TEXT,
            dauer_sekunden REAL,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Datenbank initialisiert:", DB_PATH)


def log_collection(collector_name: str, status: str, datensaetze: int = 0,
                   fehlermeldung: str = None, dauer: float = None):
    """Loggt einen Collector-Durchlauf."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO collector_log 
           (collector_name, status, datensaetze, fehlermeldung, dauer_sekunden)
           VALUES (?, ?, ?, ?, ?)""",
        (collector_name, status, datensaetze, fehlermeldung, dauer)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
