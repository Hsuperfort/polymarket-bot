"""
Notifier Telegram — envoie les opportunités détectées par le scanner.
"""

import requests


def envoyer_message(token: str, chat_id: str, texte: str) -> bool:
    """Envoie un message Telegram en Markdown."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id"    : chat_id,
        "text"       : texte,
        "parse_mode" : "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"   ⚠️  Erreur Telegram : {e}")
        return False


def get_chat_id(token: str):
    """Récupère automatiquement le chat_id après que l'utilisateur a écrit au bot."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        results = data.get("result", [])
        if results:
            return str(results[-1]["message"]["chat"]["id"])
        return None
    except Exception:
        return None


def formater_opportunite(opportunite: dict, rang: int) -> str:
    """Formate une opportunité en message Telegram lisible."""
    score     = opportunite.get("score", 0)
    direction = opportunite.get("direction", "?")
    prob_m    = opportunite.get("prob_marche", 0) * 100
    prob_e    = opportunite.get("prob_estimee", 0) * 100
    edge      = abs(prob_e - prob_m)
    confiance = opportunite.get("confiance", "?")
    question  = opportunite.get("question", "")[:80]
    analyse   = opportunite.get("raisonnement", "")[:200]
    url       = opportunite.get("url", "")
    liquidite = opportunite.get("liquidite", 0)

    if score >= 7:
        emoji = "🔥"
    elif score >= 5:
        emoji = "⚡"
    else:
        emoji = "💤"

    direction_label = "✅ YES" if direction == "YES" else "❌ NO"

    return (
        f"{emoji} *Opportunité #{rang} — Score {score}/10*\n"
        f"\n"
        f"📋 *{question}*\n"
        f"\n"
        f"🎯 Pari recommandé : *{direction_label}*\n"
        f"📊 Marché : `{prob_m:.1f}%` → IA estime : `{prob_e:.1f}%` *(écart {edge:.1f}pts)*\n"
        f"💧 Liquidité : `{liquidite:,.0f} USDC`\n"
        f"🧠 Confiance : `{confiance}`\n"
        f"\n"
        f"💬 _{analyse}_\n"
        f"\n"
        f"🔗 [Voir sur Polymarket]({url})"
    )


def envoyer_rapport(token: str, chat_id: str, opportunites: list, nb_analyses: int):
    """Envoie le rapport complet : résumé + chaque opportunité."""
    from datetime import datetime

    nb_opps = len(opportunites)
    heure   = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Message d'en-tête
    if nb_opps == 0:
        header = (
            f"🤖 *Polymarket Scanner*\n"
            f"📅 {heure}\n\n"
            f"Aucune opportunité détectée sur {nb_analyses} marchés analysés."
        )
        envoyer_message(token, chat_id, header)
        return

    header = (
        f"🤖 *Polymarket Scanner*\n"
        f"📅 {heure}\n\n"
        f"*{nb_opps} opportunité(s)* détectée(s) sur {nb_analyses} marchés analysés :"
    )
    envoyer_message(token, chat_id, header)

    # Une notification par opportunité (score >= 5 uniquement)
    rang = 1
    for opp in opportunites:
        if opp.get("score", 0) >= 5:
            texte = formater_opportunite(opp, rang)
            envoyer_message(token, chat_id, texte)
            rang += 1
