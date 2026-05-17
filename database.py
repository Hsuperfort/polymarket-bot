"""
Base de données SQLite — scans, opportunités, news, positions de trading.
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/polymarket.db"


def connexion():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialiser():
    """Crée les tables et applique les migrations si nécessaire."""
    conn = connexion()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL,
            nb_marches INTEGER
        );

        CREATE TABLE IF NOT EXISTS opportunites (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id      INTEGER NOT NULL,
            event_title  TEXT,
            question     TEXT,
            prob_marche  REAL,
            prob_estimee REAL,
            direction    TEXT,
            score        INTEGER,
            confiance    TEXT,
            raisonnement TEXT,
            jours        REAL,
            liquidite    REAL,
            volume_24h   REAL,
            url          TEXT,
            FOREIGN KEY (scan_id) REFERENCES scans(id)
        );

        CREATE TABLE IF NOT EXISTS news (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunite_id INTEGER NOT NULL,
            titre          TEXT,
            source         TEXT,
            resume         TEXT,
            FOREIGN KEY (opportunite_id) REFERENCES opportunites(id)
        );

        -- Positions de trading (logique prix d'entrée / prix de sortie)
        CREATE TABLE IF NOT EXISTS positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunite_id  INTEGER,
            question        TEXT NOT NULL,
            event_title     TEXT,
            url             TEXT,
            direction       TEXT NOT NULL,      -- YES ou NO
            mise            REAL NOT NULL,      -- USDC investis
            prix_yes_entree REAL,               -- prix YES au moment de l'entrée
            prix_yes_cible  REAL,               -- objectif IA (prix YES visé)
            nb_parts        REAL,               -- nombre de parts achetées
            prix_yes_sortie REAL,               -- prix YES à la sortie (rempli à la clôture)
            statut          TEXT DEFAULT 'ouvert',
            gain_perte      REAL,
            date_ouverture  TEXT NOT NULL,
            date_cloture    TEXT
        );
    """)
    conn.commit()

    # Migration 1 : ajoute les nouvelles colonnes si absentes
    colonnes_existantes = {
        row[1] for row in conn.execute("PRAGMA table_info(positions)")
    }
    for col, typ in [
        ("prix_yes_entree", "REAL"),
        ("prix_yes_cible",  "REAL"),
        ("nb_parts",        "REAL"),
        ("prix_yes_sortie", "REAL"),
    ]:
        if col not in colonnes_existantes:
            conn.execute(f"ALTER TABLE positions ADD COLUMN {col} {typ}")
    conn.commit()

    # Migration 2 : remplit les valeurs manquantes depuis la table opportunites
    conn.execute("""
        UPDATE positions
        SET
            prix_yes_entree = (
                SELECT o.prob_marche FROM opportunites o WHERE o.id = positions.opportunite_id
            ),
            prix_yes_cible = (
                SELECT o.prob_estimee FROM opportunites o WHERE o.id = positions.opportunite_id
            ),
            nb_parts = CASE
                WHEN positions.direction = 'YES' THEN
                    positions.mise / NULLIF(
                        (SELECT o.prob_marche FROM opportunites o WHERE o.id = positions.opportunite_id), 0
                    )
                ELSE
                    positions.mise / NULLIF(
                        1.0 - (SELECT o.prob_marche FROM opportunites o WHERE o.id = positions.opportunite_id), 0
                    )
            END
        WHERE prix_yes_entree IS NULL AND opportunite_id IS NOT NULL
    """)
    conn.commit()
    conn.close()


# ─── Scans ────────────────────────────────────────────────────────────────────

def sauvegarder_scan(opportunites: list, articles_par_marche: dict) -> int:
    conn = connexion()
    cur  = conn.cursor()

    cur.execute(
        "INSERT INTO scans (timestamp, nb_marches) VALUES (?, ?)",
        (datetime.now().isoformat(), len(opportunites))
    )
    scan_id = cur.lastrowid

    for opp in opportunites:
        cur.execute("""
            INSERT INTO opportunites
              (scan_id, event_title, question, prob_marche, prob_estimee,
               direction, score, confiance, raisonnement, jours, liquidite, volume_24h, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_id,
            opp.get("event_title", ""),
            opp.get("question", ""),
            opp.get("prob_marche"),
            opp.get("prob_estimee"),
            opp.get("direction"),
            opp.get("score"),
            opp.get("confiance"),
            opp.get("raisonnement"),
            opp.get("jours"),
            opp.get("liquidite"),
            opp.get("volume_24h"),
            opp.get("url"),
        ))
        opp_id = cur.lastrowid

        for article in articles_par_marche.get(opp.get("question", ""), []):
            cur.execute(
                "INSERT INTO news (opportunite_id, titre, source, resume) VALUES (?, ?, ?, ?)",
                (opp_id, article.get("titre"), article.get("source"), article.get("resume"))
            )

    conn.commit()
    conn.close()
    return scan_id


def charger_dernier_scan():
    conn  = connexion()
    scan  = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        conn.close()
        return None, []

    opps = conn.execute(
        "SELECT * FROM opportunites WHERE scan_id = ? ORDER BY score DESC",
        (scan["id"],)
    ).fetchall()

    resultats = []
    for opp in opps:
        news = conn.execute(
            "SELECT * FROM news WHERE opportunite_id = ?", (opp["id"],)
        ).fetchall()
        resultats.append({"opp": dict(opp), "news": [dict(n) for n in news]})

    conn.close()
    return dict(scan), resultats


# ─── Positions ────────────────────────────────────────────────────────────────

def ouvrir_position(opp: dict, mise: float) -> int:
    """
    Ouvre une position.
    - Pour YES : on achète des parts YES à prob_marche
    - Pour NO  : on achète des parts NO à (1 - prob_marche)
    """
    direction       = opp.get("direction", "YES")
    prob_yes_entree = opp.get("prob_marche") or 0.5
    prob_yes_cible  = opp.get("prob_estimee") or prob_yes_entree

    if direction == "YES":
        prix_part = prob_yes_entree
    else:
        prix_part = 1.0 - prob_yes_entree

    nb_parts = round(mise / prix_part, 4) if prix_part > 0 else 0

    conn = connexion()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO positions
          (opportunite_id, question, event_title, url, direction,
           mise, prix_yes_entree, prix_yes_cible, nb_parts, date_ouverture)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        opp.get("id"),
        opp.get("question"),
        opp.get("event_title"),
        opp.get("url"),
        direction,
        mise,
        prob_yes_entree,
        prob_yes_cible,
        nb_parts,
        datetime.now().isoformat(),
    ))
    pos_id = cur.lastrowid
    conn.commit()
    conn.close()
    return pos_id


def clore_position(pos_id: int, prix_yes_sortie: float):
    """
    Clore une position au prix YES actuel fourni.
    P&L = (prix_sortie_part - prix_entree_part) × nb_parts
    """
    conn = connexion()
    pos  = conn.execute("SELECT * FROM positions WHERE id = ?", (pos_id,)).fetchone()
    if not pos:
        conn.close()
        return

    direction       = pos["direction"]
    prix_yes_entree = pos["prix_yes_entree"] or 0.5
    nb_parts        = pos["nb_parts"] or 0

    if direction == "YES":
        prix_entree_part = prix_yes_entree
        prix_sortie_part = prix_yes_sortie
    else:
        prix_entree_part = 1.0 - prix_yes_entree
        prix_sortie_part = 1.0 - prix_yes_sortie

    gain_perte = round((prix_sortie_part - prix_entree_part) * nb_parts, 4)

    conn.execute("""
        UPDATE positions
        SET statut = 'cloture', prix_yes_sortie = ?, gain_perte = ?, date_cloture = ?
        WHERE id = ?
    """, (prix_yes_sortie, gain_perte, datetime.now().isoformat(), pos_id))
    conn.commit()
    conn.close()


def charger_positions(statut: str = None):
    conn = connexion()
    if statut:
        rows = conn.execute(
            "SELECT * FROM positions WHERE statut = ? ORDER BY date_ouverture DESC", (statut,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM positions ORDER BY date_ouverture DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pnl_latent(pos: dict, prix_yes_actuel: float) -> float:
    """Calcule le P&L non réalisé pour une position ouverte."""
    direction        = pos.get("direction", "YES")
    prix_yes_entree  = pos.get("prix_yes_entree") or 0.5
    nb_parts         = pos.get("nb_parts") or 0

    if direction == "YES":
        return round((prix_yes_actuel - prix_yes_entree) * nb_parts, 4)
    else:
        return round(((1 - prix_yes_actuel) - (1 - prix_yes_entree)) * nb_parts, 4)


def stats_performance():
    conn   = connexion()
    closes = conn.execute(
        "SELECT gain_perte FROM positions WHERE statut = 'cloture'"
    ).fetchall()
    conn.close()

    if not closes:
        return {"total": 0, "gagnes": 0, "perdus": 0, "pnl": 0.0, "win_rate": 0.0}

    gains  = [r["gain_perte"] or 0 for r in closes]
    gagnes = sum(1 for g in gains if g > 0)
    perdus = sum(1 for g in gains if g <= 0)
    pnl    = round(sum(gains), 4)
    total  = len(closes)

    return {
        "total"   : total,
        "gagnes"  : gagnes,
        "perdus"  : perdus,
        "pnl"     : pnl,
        "win_rate": round(gagnes / total * 100, 1) if total else 0.0,
    }
