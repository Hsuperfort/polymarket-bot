"""
SofaScore — données sportives live et pré-match (API non officielle).
Fournit : matchs du jour, incidents live (buts, penaltys, cartons), forme équipe.
"""

import requests
import unicodedata
from datetime import datetime, timezone

API = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent"      : "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept"          : "application/json",
    "Accept-Language" : "fr-FR,fr;q=0.9",
    "Referer"         : "https://www.sofascore.com/",
    "Origin"          : "https://www.sofascore.com",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get(url, params=None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def _normaliser(texte: str) -> str:
    """Supprime accents et met en minuscules pour la comparaison."""
    return unicodedata.normalize("NFD", texte.lower()).encode("ascii", "ignore").decode()


# ─── Matchs ───────────────────────────────────────────────────────────────────

def get_matchs_live() -> list:
    """Retourne tous les matchs de football en direct."""
    data = _get(f"{API}/sport/football/events/live")
    return data.get("events", [])


def get_matchs_du_jour() -> list:
    """Retourne les matchs de football du jour."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data  = _get(f"{API}/sport/football/scheduled-events/{today}")
    return data.get("events", [])


def get_incidents(event_id: int) -> list:
    """Retourne les incidents d'un match (buts, cartons, penaltys, fin)."""
    data = _get(f"{API}/event/{event_id}/incidents")
    return data.get("incidents", [])


def get_forme_equipe(team_id: int) -> list:
    """Retourne les 5 derniers matchs d'une équipe."""
    data   = _get(f"{API}/team/{team_id}/events/last/0")
    events = data.get("events", [])
    return events[-5:] if len(events) >= 5 else events


# ─── Matching question → match ────────────────────────────────────────────────

def trouver_match(question: str, matchs: list) -> dict | None:
    """
    Essaie d'associer une question Polymarket à un match SofaScore
    via correspondance floue sur les noms d'équipes.
    """
    q = _normaliser(question)
    meilleur, meilleur_score = None, 0

    for m in matchs:
        home = _normaliser(m.get("homeTeam", {}).get("name", ""))
        away = _normaliser(m.get("awayTeam", {}).get("name", ""))

        # Compte combien de mots du nom d'équipe apparaissent dans la question
        score = 0
        for mot in home.split() + away.split():
            if len(mot) >= 4 and mot in q:
                score += 1

        if score > meilleur_score:
            meilleur_score = score
            meilleur = m

    return meilleur if meilleur_score >= 1 else None


# ─── Formatage pour le prompt IA ──────────────────────────────────────────────

def _resultat_forme(event, team_id: int) -> str:
    home_id = event.get("homeTeam", {}).get("id")
    home_score = event.get("homeScore", {}).get("current", 0)
    away_score = event.get("awayScore", {}).get("current", 0)

    if home_score == away_score:
        return "N"
    if home_id == team_id:
        return "V" if home_score > away_score else "D"
    return "V" if away_score > home_score else "D"


def formater_donnees_sport(question: str, tous_matchs: list) -> str:
    """
    Cherche le match correspondant et retourne un bloc texte pour le prompt IA.
    Inclut : statut live, score, incidents et forme des équipes.
    """
    match = trouver_match(question, tous_matchs)
    if not match:
        return ""

    home      = match.get("homeTeam", {}).get("name", "?")
    away      = match.get("awayTeam", {}).get("name", "?")
    home_id   = match.get("homeTeam", {}).get("id")
    away_id   = match.get("awayTeam", {}).get("id")
    event_id  = match.get("id")
    statut    = match.get("status", {}).get("description", "Inconnu")
    minute    = match.get("time", {}).get("currentPeriodStartTimestamp")
    h_score   = match.get("homeScore", {}).get("current", "?")
    a_score   = match.get("awayScore", {}).get("current", "?")
    compet    = match.get("tournament", {}).get("name", "")

    lignes = [f"⚽ DONNÉES SPORTIVES — {home} vs {away} ({compet})"]
    lignes.append(f"Statut : {statut}  |  Score : {h_score} - {a_score}")

    # Incidents live
    incidents = get_incidents(event_id)
    buts, cartons, penaltys = [], [], []
    for inc in incidents:
        typ    = inc.get("incidentType", "")
        equipe = "domicile" if inc.get("isHome") else "extérieur"
        joueur = inc.get("player", {}).get("name", "?")
        min_   = inc.get("time", "?")

        if typ == "goal":
            buts.append(f"  ⚽ {min_}' {joueur} ({equipe})")
        elif typ == "card":
            couleur = inc.get("incidentClass", "")
            if couleur == "red":
                cartons.append(f"  🟥 {min_}' {joueur} ({equipe})")
            elif couleur == "yellow":
                cartons.append(f"  🟨 {min_}' {joueur} ({equipe})")
        elif typ == "penalty":
            statut_pen = inc.get("incidentClass", "")
            buts.append(f"  🎯 PENALTY {min_}' {joueur} ({equipe}) — {statut_pen}")

    if buts:
        lignes.append("Buts :\n" + "\n".join(buts))
    if cartons:
        lignes.append("Cartons :\n" + "\n".join(cartons))

    # Forme des équipes (5 derniers matchs)
    for team_id, nom in [(home_id, home), (away_id, away)]:
        if not team_id:
            continue
        forme = get_forme_equipe(team_id)
        if forme:
            res = [_resultat_forme(e, team_id) for e in forme]
            lignes.append(f"Forme {nom} (5 derniers) : {' '.join(res)}")

    return "\n".join(lignes)
