"""
Récupère le prix YES actuel de chaque position ouverte sur Polymarket.
Détecte si l'objectif IA a été atteint (signal de revente).
"""

import json
import requests

POLYMARKET_API = "https://gamma-api.polymarket.com"
SEUIL_CIBLE    = 0.90   # on alerte si le prix a parcouru 90 % du chemin vers la cible


def extraire_slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def fetch_marches_event(slug: str) -> list:
    try:
        r = requests.get(
            f"{POLYMARKET_API}/events",
            params={"slug": slug},
            timeout=10,
        )
        r.raise_for_status()
        events = r.json()
        return events[0].get("markets", []) if events else []
    except Exception:
        return []


def prix_yes_actuel(marche: dict):
    """Retourne le prix YES actuel du marché (float) ou None."""
    try:
        prix_raw = marche.get("outcomePrices", "[]")
        prix     = json.loads(prix_raw) if isinstance(prix_raw, str) else prix_raw
        return float(prix[0])
    except (ValueError, TypeError, IndexError):
        return None


def actualiser_prix(positions_ouvertes: list) -> list:
    """
    Pour chaque position ouverte, récupère le prix YES actuel et calcule :
    - pnl_latent : P&L non réalisé
    - progression : % du chemin vers la cible (0 % = entrée, 100 % = cible atteinte)
    - alerte : True si la cible est atteinte ou dépassée

    Retourne une liste de dicts enrichis.
    """
    cache   = {}
    resultats = []

    for pos in positions_ouvertes:
        slug = extraire_slug(pos.get("url", ""))
        if not slug:
            resultats.append({**pos, "prix_actuel": None, "pnl_latent": 0, "progression": 0, "alerte": False})
            continue

        if slug not in cache:
            cache[slug] = fetch_marches_event(slug)

        prix_actuel = None
        for m in cache[slug]:
            if m.get("question", "").lower().strip() == pos.get("question", "").lower().strip():
                prix_actuel = prix_yes_actuel(m)
                break

        direction        = pos.get("direction", "YES")
        prix_yes_entree  = pos.get("prix_yes_entree") or 0.5
        prix_yes_cible   = pos.get("prix_yes_cible")  or prix_yes_entree
        nb_parts         = pos.get("nb_parts") or 0

        if prix_actuel is not None:
            # P&L latent
            if direction == "YES":
                pnl_l  = round((prix_actuel - prix_yes_entree) * nb_parts, 4)
                # progression vers la cible
                ecart_total = prix_yes_cible - prix_yes_entree
                ecart_fait  = prix_actuel   - prix_yes_entree
            else:
                pnl_l  = round(((1 - prix_actuel) - (1 - prix_yes_entree)) * nb_parts, 4)
                ecart_total = prix_yes_entree - prix_yes_cible   # on veut que YES baisse
                ecart_fait  = prix_yes_entree - prix_actuel

            if ecart_total and ecart_total > 0:
                progression = round(ecart_fait / ecart_total * 100, 1)
            else:
                progression = 0.0

            alerte = progression >= SEUIL_CIBLE * 100
        else:
            pnl_l       = 0.0
            progression = 0.0
            alerte      = False

        resultats.append({
            **pos,
            "prix_actuel" : prix_actuel,
            "pnl_latent"  : pnl_l,
            "progression" : progression,
            "alerte"      : alerte,
        })

    return resultats
