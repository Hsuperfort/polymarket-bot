"""
Polymarket Scanner - Phase 1 (court terme)
Cible les marchés se résolvant dans les 30 prochains jours.
"""

import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from groq import Groq
from notifier import envoyer_rapport
from news_fetcher import chercher_news, formater_pour_prompt
from database import initialiser, sauvegarder_scan
from auto_trader import auto_ouvrir, auto_clore
from sports_fetcher import formater_donnees_sport, get_matchs_live, get_matchs_du_jour

load_dotenv()

# ─── Configuration ────────────────────────────────────────────────────────────

GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
GROQ_MODEL       = "llama-3.3-70b-versatile"
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FILTRE_LIQUIDITE_MIN  = 2_000   # USDC (marchés standard)
FILTRE_LIQUIDITE_INTRADAY = 500 # USDC (marchés intraday, souvent moins liquides)
FILTRE_VOLUME_MIN     = 5_000   # USDC
FILTRE_PROB_MIN       = 0.05
FILTRE_PROB_MAX       = 0.95
FILTRE_JOURS_MIN      = 0.04    # ~1 heure minimum (évite les marchés en cours de résolution)
FILTRE_JOURS_MAX      = 14      # 14 jours max
NB_MARCHES_MAX        = 300

# Répartition par horizon
QUOTA_INTRADAY        = 60      # < 24h  (crypto, sport du jour, événements immédiats)
QUOTA_TRES_COURT      = 180     # 1-7j
QUOTA_COURT           = 60      # 7-14j

POLYMARKET_API = "https://gamma-api.polymarket.com"

# Tags sportifs à toujours inclure (garantit la présence de matchs intraday)
SPORTS_TAGS = [
    "soccer", "nba", "nfl", "mlb", "nhl", "tennis",
    "mls", "ufc", "cricket", "rugby", "formula-1",
]
QUOTA_PAR_SPORT = 30   # événements max par tag (avant filtre)

# ─── Récupération des événements (avec pagination) ────────────────────────────

def recuperer_evenements():
    """Récupère jusqu'à 300 événements actifs triés par volume24hr."""
    print("📡 Récupération des événements Polymarket (global)...")

    tous = []
    limite_par_page = 100

    for offset in range(0, 600, limite_par_page):
        params = {
            "active"    : "true",
            "closed"    : "false",
            "limit"     : limite_par_page,
            "offset"    : offset,
            "order"     : "volume24hr",
            "ascending" : "false",
        }
        try:
            r = requests.get(f"{POLYMARKET_API}/events", params=params, timeout=15)
            r.raise_for_status()
            page = r.json()
            if not page:
                break
            tous.extend(page)
            if len(page) < limite_par_page:
                break
        except Exception as e:
            print(f"   ⚠️  Erreur page offset={offset} : {e}")
            break

    print(f"   → {len(tous)} événements globaux récupérés")
    return tous


def recuperer_evenements_sport():
    """Récupère les événements sportifs par tag pour garantir leur présence."""
    print("⚽ Récupération des marchés sportifs par tag...")

    tous = []
    ids_vus = set()

    for tag in SPORTS_TAGS:
        params = {
            "active"     : "true",
            "closed"     : "false",
            "limit"      : QUOTA_PAR_SPORT,
            "tag_slug"   : tag,
            "order"      : "volume24hr",
            "ascending"  : "false",
        }
        try:
            r = requests.get(f"{POLYMARKET_API}/events", params=params, timeout=15)
            r.raise_for_status()
            page = r.json()
            if not page:
                continue
            nouveaux = 0
            for ev in page:
                eid = ev.get("id") or ev.get("slug")
                if eid and eid not in ids_vus:
                    ids_vus.add(eid)
                    tous.append(ev)
                    nouveaux += 1
            print(f"   [{tag}] → {nouveaux} événements")
        except Exception as e:
            print(f"   ⚠️  Erreur tag={tag} : {e}")

    print(f"   → {len(tous)} événements sportifs uniques")
    return tous


# ─── Filtrage et extraction des marchés ───────────────────────────────────────

def jours_restants(date_str):
    """Retourne le nombre de jours entre maintenant et la date de résolution."""
    if not date_str:
        return None
    try:
        # Normalise le format ISO
        date_str = date_str.replace("Z", "+00:00")
        fin = datetime.fromisoformat(date_str)
        maintenant = datetime.now(timezone.utc)
        delta = (fin - maintenant).total_seconds() / 86400
        return round(delta, 1)
    except Exception:
        return None


def extraire_marches(events):
    """Filtre et trie les marchés court terme les plus actifs."""
    candidats = []

    for event in events:
        try:
            liquidite_event = float(event.get("liquidity", 0) or 0)
            volume_event    = float(event.get("volume", 0) or 0)
            volume_24h      = float(event.get("volume24hr", 0) or 0)
        except (ValueError, TypeError):
            continue

        # Filtre liquidité pré-check (les events avec 0 liquidité sont écartés d'emblée)
        if liquidite_event <= 0:
            continue

        slug_event  = event.get("slug", "")
        titre_event = event.get("title", "")
        desc_event  = (event.get("description", "") or "")[:300]
        tags_event  = [t.get("slug", "") for t in (event.get("tags") or [])]
        is_sport    = any(t in SPORTS_TAGS for t in tags_event)

        for m in event.get("markets", []):
            # Probabilité YES
            prix_raw = m.get("outcomePrices", "[]")
            try:
                prix     = json.loads(prix_raw) if isinstance(prix_raw, str) else prix_raw
                prob_yes = float(prix[0])
            except (ValueError, TypeError, IndexError):
                continue

            if not (FILTRE_PROB_MIN <= prob_yes <= FILTRE_PROB_MAX):
                continue

            # Filtre temporel
            jours = jours_restants(m.get("endDate", ""))
            if jours is None or not (FILTRE_JOURS_MIN <= jours <= FILTRE_JOURS_MAX):
                continue

            # Seuils adaptés selon sport intraday vs reste
            if is_sport and jours < 1:
                liq_min = FILTRE_LIQUIDITE_INTRADAY   # 500 USDC
                vol_min = 500                          # volume minimal réduit pour sport
            elif jours < 1:
                liq_min = FILTRE_LIQUIDITE_INTRADAY
                vol_min = FILTRE_VOLUME_MIN
            else:
                liq_min = FILTRE_LIQUIDITE_MIN
                vol_min = FILTRE_VOLUME_MIN

            if liquidite_event < liq_min:
                continue
            if volume_event < vol_min:
                continue

            # Volume 24h spécifique au marché individuel
            try:
                vol_24h_m = float(m.get("volume24hr", 0) or 0)
            except (ValueError, TypeError):
                vol_24h_m = 0

            candidats.append({
                "event_title"  : titre_event,
                "question"     : m.get("question", ""),
                "description"  : desc_event,
                "prob_marche"  : round(prob_yes, 3),
                "liquidite"    : round(liquidite_event, 0),
                "volume_24h"   : round(volume_24h, 0),
                "vol_24h_m"    : round(vol_24h_m, 0),
                "jours"        : jours,
                "date_fin"     : m.get("endDate", ""),
                "url"          : f"https://polymarket.com/event/{slug_event}",
                "is_sport"     : is_sport,
            })

    # Répartition par horizon temporel
    intraday = sorted(
        [c for c in candidats if c["jours"] < 1],
        key=lambda x: (-x["volume_24h"], x["jours"])
    )[:QUOTA_INTRADAY]

    tres_court = sorted(
        [c for c in candidats if 1 <= c["jours"] < 7],
        key=lambda x: (-x["volume_24h"], x["jours"])
    )[:QUOTA_TRES_COURT]

    court = sorted(
        [c for c in candidats if 7 <= c["jours"] <= FILTRE_JOURS_MAX],
        key=lambda x: (-x["volume_24h"], x["jours"])
    )[:QUOTA_COURT]

    selection = intraday + tres_court + court

    nb_sport = sum(1 for c in selection if c.get("is_sport"))
    print(f"   → {len(candidats)} candidats  |  "
          f"{len(intraday)} intraday  +  {len(tres_court)} < 7j  +  {len(court)} 7-14j  "
          f"=  {len(selection)} sélectionnés  (dont {nb_sport} sportifs)")
    return selection


# ─── Analyse IA ───────────────────────────────────────────────────────────────

PROMPT_SYSTEME = """Tu es un analyste spécialisé en marchés prédictifs court terme (Polymarket).
Ces marchés se résolvent dans les 30 prochains jours. L'horizon court implique que :
- L'état ACTUEL des choses prime sur les tendances longues
- Un écart de 5+ points entre ta proba et le marché peut être exploitable

Barème du score (utilise TOUTE l'échelle) :
  0-2 : pas d'opinion, données insuffisantes
  3-4 : légère conviction, edge < 5 points
  5-6 : conviction réelle, edge 5-15 points, signal modéré
  7-8 : forte conviction, edge > 15 points OU signal clair dans les news/données live
  9-10 : certitude quasi-totale, marché manifestement mal pricé

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après.
"""

def analyser_marche_avec_articles(marche, articles, client, tous_matchs=None):
    """Analyse un marché court terme avec Llama 3 + actualités récentes + données SofaScore."""

    jours = marche["jours"]
    if jours < 1:
        heures = round(jours * 24, 1)
        urgence = f"🚨 INTRADAY — résolution dans {heures:.0f} heures. L'état actuel prime sur tout."
    elif jours < 3:
        urgence = f"⚠️ URGENT — résolution dans {jours:.1f} jours"
    else:
        urgence = f"résolution dans {jours:.0f} jours"

    bloc_news = formater_pour_prompt(marche["question"], articles)
    section_news = f"\n{bloc_news}\n" if bloc_news else "\nAucune actualité récente trouvée.\n"

    # Données SofaScore pour les marchés sportifs
    section_sport = ""
    if marche.get("is_sport") and tous_matchs:
        bloc_sport = formater_donnees_sport(marche["question"], tous_matchs)
        if bloc_sport:
            section_sport = f"\n{bloc_sport}\n"

    prompt = f"""Analyse ce marché Polymarket court terme :

Événement : {marche['event_title']}
Question : {marche['question']}
Description : {marche['description']}
Probabilité actuelle (YES) : {marche['prob_marche'] * 100:.1f}%
Liquidité : {marche['liquidite']:,.0f} USDC
Volume 24h : {marche['volume_24h']:,.0f} USDC
Horizon : {urgence}
{section_sport}{section_news}
En intégrant les données sportives live, les actualités ET tes connaissances générales, estime la probabilité réelle.

Réponds en JSON avec exactement ces champs :
{{
  "prob_estimee": <float 0-1, ta meilleure estimation tenant compte des news>,
  "confiance": <"faible"|"moyenne"|"haute" — haute seulement si les news confirment clairement>,
  "direction": <"YES"|"NO"|"SKIP">,
  "edge": <float, différence absolue entre ta proba et celle du marché>,
  "score": <int 0-10, utilise le barème complet — un edge de 10 points avec signal modéré vaut 5-6, un edge de 20+ points vaut 7-8>,
  "raisonnement": <string, 2-3 phrases factuelles citant les news si pertinent>
}}

Si les news et tes connaissances ne permettent pas de trancher, mets direction="SKIP" et score=0.
Réponds UNIQUEMENT avec le JSON."""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=450,
            messages=[
                {"role": "system", "content": PROMPT_SYSTEME},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.15,
        )
        texte = response.choices[0].message.content.strip()
        debut = texte.find("{")
        fin   = texte.rfind("}") + 1
        texte = texte[debut:fin] if debut != -1 else texte
        analyse = json.loads(texte)

        # Validation cohérence direction / prob_estimee
        prob_m = marche["prob_marche"]
        prob_e = float(analyse.get("prob_estimee", prob_m))
        direction = analyse.get("direction", "SKIP")

        if direction == "YES" and prob_e <= prob_m:
            # LLM dit YES mais estime une proba plus basse → incohérent, forcer NO
            analyse["direction"] = "NO"
        elif direction == "NO" and prob_e >= prob_m:
            # LLM dit NO mais estime une proba plus haute → incohérent, forcer YES
            analyse["direction"] = "YES"

        analyse.update({
            "event_title" : marche["event_title"],
            "question"    : marche["question"],
            "prob_marche" : prob_m,
            "liquidite"   : marche["liquidite"],
            "volume_24h"  : marche["volume_24h"],
            "jours"       : marche["jours"],
            "url"         : marche["url"],
        })
        return analyse
    except json.JSONDecodeError:
        print(f"   ⚠️  JSON invalide pour : {marche['question'][:50]}")
        return None
    except Exception as e:
        print(f"   ⚠️  Erreur : {e}")
        return None


# ─── Affichage ────────────────────────────────────────────────────────────────

def afficher_resultats(analyses):
    opportunites = [a for a in analyses if a and a.get("direction") != "SKIP"]
    opportunites.sort(key=lambda x: x.get("score", 0), reverse=True)

    print("\n" + "═" * 72)
    print(f"  RAPPORT COURT TERME — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("═" * 72)

    if not opportunites:
        print("  Aucune opportunité court terme détectée.")
    else:
        for i, a in enumerate(opportunites, 1):
            score     = a.get("score", 0)
            direction = a.get("direction", "?")
            prob_m    = a.get("prob_marche", 0) * 100
            prob_e    = a.get("prob_estimee", 0) * 100
            edge      = abs(prob_e - prob_m)
            confiance = a.get("confiance", "?")
            jours     = a.get("jours", "?")
            vol24     = a.get("volume_24h", 0)

            indicateur = "🔥" if score >= 7 else ("⚡" if score >= 5 else "💤")
            urgence    = " ⏰" if isinstance(jours, float) and jours < 3 else ""

            print(f"\n{indicateur} #{i} — Score {score}/10  |  {direction}  |  Confiance: {confiance}  |  J-{jours:.0f}{urgence}")
            print(f"   Événement : {a.get('event_title', '')[:65]}")
            print(f"   Question  : {a['question'][:65]}")
            print(f"   Marché    : {prob_m:.1f}%  →  IA estime : {prob_e:.1f}%  (écart {edge:.1f}pts)")
            print(f"   Liquidité : {a['liquidite']:,.0f} USDC  |  Vol 24h : {vol24:,.0f} USDC")
            print(f"   Analyse   : {a.get('raisonnement', '')[:160]}")
            print(f"   Lien      : {a['url']}")

    print("\n" + "═" * 72)
    print(f"  {len(opportunites)} opportunité(s) sur {len(analyses)} marchés analysés")
    print("═" * 72 + "\n")

    chemin = f"logs/scan_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(opportunites, f, ensure_ascii=False, indent=2)
    print(f"📁 Résultats : {chemin}\n")

    return opportunites


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main():
    if not GROQ_API_KEY or "REMPLACE_MOI" in GROQ_API_KEY:
        print("❌ Configure GROQ_API_KEY dans .env")
        return

    client = Groq(api_key=GROQ_API_KEY)

    events_global = recuperer_evenements()
    events_sport  = recuperer_evenements_sport()

    # Fusion sans doublons (les événements sportifs complètent le pool global)
    ids_global = {ev.get("id") or ev.get("slug") for ev in events_global}
    events_sport_nouveaux = [
        ev for ev in events_sport
        if (ev.get("id") or ev.get("slug")) not in ids_global
    ]
    events = events_global + events_sport_nouveaux
    print(f"   → Pool total : {len(events)} événements "
          f"({len(events_sport_nouveaux)} sportifs supplémentaires)")

    if not events:
        return

    marches = extraire_marches(events)
    if not marches:
        print("Aucun marché court terme ne passe les filtres.")
        return

    # Charger les données SofaScore une seule fois pour tous les marchés sportifs
    print("\n⚽ Chargement données SofaScore (matchs live + jour)...")
    try:
        matchs_live = get_matchs_live()
        matchs_jour = get_matchs_du_jour()
        tous_matchs_sport = matchs_live + matchs_jour
        print(f"   → {len(matchs_live)} live + {len(matchs_jour)} programmés = {len(tous_matchs_sport)} matchs")
    except Exception as e:
        print(f"   ⚠️  SofaScore indisponible : {e}")
        tous_matchs_sport = []

    print(f"\n🤖 Analyse de {len(marches)} marchés (résolution < 30 jours)...")
    analyses = []
    articles_par_marche = {}
    for i, m in enumerate(marches, 1):
        print(f"   [{i}/{len(marches)}] J-{m['jours']:.0f}  {m['question'][:55]}...")
        articles = chercher_news(m["question"], max_articles=4)
        articles_par_marche[m["question"]] = articles
        analyse = analyser_marche_avec_articles(m, articles, client, tous_matchs=tous_matchs_sport)
        analyses.append(analyse)
        time.sleep(0.8)

    opportunites = afficher_resultats(analyses)

    # Sauvegarde en base de données
    initialiser()
    if opportunites:
        sauvegarder_scan(opportunites, articles_par_marche)
        print("💾 Scan sauvegardé en base de données")

    # ── 1. Vérifier si des positions existantes ont atteint leur objectif ──
    print("\n🔍 Vérification des positions ouvertes...")
    cloturees = auto_clore()
    if cloturees:
        print(f"   ✅ {len(cloturees)} position(s) clôturée(s) automatiquement")
    else:
        print("   Aucun objectif atteint")

    # ── 2. Ouvrir les nouvelles positions détectées ────────────────────────
    print("\n💰 Ouverture des nouvelles positions...")
    nouvelles = auto_ouvrir(opportunites)
    if nouvelles:
        print(f"   ✅ {len(nouvelles)} position(s) ouverte(s) automatiquement")
        for opp in nouvelles:
            print(f"      {opp['direction']} — {opp['question'][:55]}")
    else:
        print("   Aucune nouvelle position (max atteint ou score insuffisant)")

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        print("\n📨 Envoi rapport Telegram...")
        envoyer_rapport(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, opportunites, len(analyses))
        print("   → ✓")
    else:
        print("ℹ️  Telegram non configuré")


if __name__ == "__main__":
    main()
