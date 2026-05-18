"""
Monitor — vérifie les positions ouvertes et clôture automatiquement celles
dont l'objectif IA est atteint. Lancé toutes les 30 minutes par cron.
"""

from datetime import datetime
from database import initialiser, charger_positions
from auto_trader import auto_clore
from sports_fetcher import get_matchs_live, trouver_match, get_incidents


def _log_incidents_sport(ouvertes):
    """Affiche dans les logs l'état live des positions sportives en cours."""
    if not ouvertes:
        return

    try:
        matchs_live = get_matchs_live()
    except Exception:
        return

    if not matchs_live:
        return

    for pos in ouvertes:
        question = pos.get("question", "")
        match = trouver_match(question, matchs_live)
        if not match:
            continue

        home    = match.get("homeTeam", {}).get("name", "?")
        away    = match.get("awayTeam", {}).get("name", "?")
        h_score = match.get("homeScore", {}).get("current", "?")
        a_score = match.get("awayScore", {}).get("current", "?")
        statut  = match.get("status", {}).get("description", "")
        event_id = match.get("id")

        print(f"\n   ⚽ {home} {h_score}-{a_score} {away}  [{statut}]")
        print(f"      Position : {question[:65]}")

        if event_id:
            incidents = get_incidents(event_id)
            for inc in incidents:
                typ    = inc.get("incidentType", "")
                joueur = inc.get("player", {}).get("name", "?")
                min_   = inc.get("time", "?")
                equipe = "dom." if inc.get("isHome") else "ext."
                if typ == "goal":
                    print(f"      ⚽ {min_}' {joueur} ({equipe})")
                elif typ == "card" and inc.get("incidentClass") == "red":
                    print(f"      🟥 {min_}' {joueur} ({equipe})")


def main():
    initialiser()
    print(f"--- {datetime.now().strftime('%Y-%m-%d %H:%M')} --- MONITORING ---")

    cloturees = auto_clore()

    if cloturees:
        print(f"✅ {len(cloturees)} position(s) clôturée(s) automatiquement :")
        for p in cloturees:
            pnl = p.get("pnl_latent", 0)
            print(f"   {'+' if pnl >= 0 else ''}{pnl:.2f} $  —  {p.get('question', '')[:60]}")
    else:
        print("   Aucun objectif atteint pour l'instant.")

    # Log des données live SofaScore pour les positions encore ouvertes
    ouvertes = charger_positions("ouvert")
    if ouvertes:
        print(f"\n⚽ Vérification SofaScore pour {len(ouvertes)} position(s) ouverte(s)...")
        _log_incidents_sport(ouvertes)

    print(f"\n--- FIN MONITORING ---\n")

if __name__ == "__main__":
    main()
