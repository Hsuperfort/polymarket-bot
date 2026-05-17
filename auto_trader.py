"""
Auto-trading : ouverture et fermeture automatiques des positions simulées.
"""

import os
import json
import pathlib
from dotenv import load_dotenv
from database import ouvrir_position, clore_position, charger_positions
from resolver import actualiser_prix
from notifier import envoyer_message

load_dotenv()

def _lire_config():
    p = pathlib.Path("config.json")
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}

_cfg = _lire_config()

MISE_AUTO        = float(_cfg.get("mise_auto",     os.getenv("MISE_AUTO", 10)))
SCORE_MIN_AUTO   = int(  _cfg.get("score_min",     os.getenv("SCORE_MIN_AUTO", 6)))
MAX_POSITIONS    = int(  _cfg.get("max_positions",  os.getenv("MAX_POSITIONS_OUVERTES", 8)))
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ─── Auto-ouverture ───────────────────────────────────────────────────────────

def auto_ouvrir(opportunites: list) -> list:
    """
    Ouvre automatiquement des positions pour les meilleures opportunités.
    Règles :
      - Score >= SCORE_MIN_AUTO
      - Pas déjà une position ouverte sur ce marché
      - Nombre total de positions < MAX_POSITIONS
    Retourne la liste des positions ouvertes.
    """
    ouvertes     = charger_positions("ouvert")
    questions_en_cours = {p["question"].lower().strip() for p in ouvertes}
    nb_ouvertes  = len(ouvertes)
    nouvelles    = []

    for opp in opportunites:
        if nb_ouvertes >= MAX_POSITIONS:
            break

        score     = opp.get("score", 0)
        question  = opp.get("question", "").lower().strip()
        direction = opp.get("direction", "SKIP")

        if score < SCORE_MIN_AUTO:
            continue
        if direction == "SKIP":
            continue
        if question in questions_en_cours:
            continue

        pos_id = ouvrir_position(opp, MISE_AUTO)
        nouvelles.append(opp)
        questions_en_cours.add(question)
        nb_ouvertes += 1

        # Notification Telegram
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            prob_m = (opp.get("prob_marche") or 0) * 100
            prob_e = (opp.get("prob_estimee") or 0) * 100
            envoyer_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, (
                f"🤖 *Position auto-ouverte*\n\n"
                f"{'✅ YES' if direction == 'YES' else '❌ NO'} — Score {score}/10\n"
                f"*{opp.get('question', '')[:80]}*\n\n"
                f"Marché : `{prob_m:.1f}%` → Objectif : `{prob_e:.1f}%`\n"
                f"Mise : `{MISE_AUTO:.0f} USDC`\n"
                f"[🔗 Polymarket]({opp.get('url', '')})"
            ))

    return nouvelles


# ─── Auto-fermeture ───────────────────────────────────────────────────────────

def auto_clore() -> list:
    """
    Vérifie toutes les positions ouvertes et ferme celles dont la cible est atteinte.
    Retourne la liste des positions clôturées.
    """
    ouvertes = charger_positions("ouvert")
    if not ouvertes:
        return []

    actualisees = actualiser_prix(ouvertes)
    clôturées   = []

    for pos in actualisees:
        if not pos.get("alerte"):
            continue

        prix_yes_actuel = pos.get("prix_actuel")
        if prix_yes_actuel is None:
            continue

        clore_position(pos["id"], prix_yes_actuel)
        clôturées.append(pos)

        # Notification Telegram
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            pnl        = pos.get("pnl_latent", 0)
            pnl_signe  = "+" if pnl >= 0 else ""
            direction  = pos.get("direction", "YES")
            mise       = pos.get("mise", 0)
            valeur     = round(mise + pnl, 2)
            icone      = "✅" if pnl >= 0 else "❌"

            envoyer_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, (
                f"{icone} *Objectif atteint — Position clôturée*\n\n"
                f"*{pos.get('question', '')[:80]}*\n\n"
                f"Direction : {'YES' if direction == 'YES' else 'NO'}\n"
                f"Mise : `{mise:.0f} $`  →  Valeur : `{valeur:.2f} $`\n"
                f"P&L : `{pnl_signe}{pnl:.2f} $`\n"
                f"[🔗 Polymarket]({pos.get('url', '')})"
            ))

    return clôturées
