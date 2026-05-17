"""
Récupère les actualités récentes via Google News RSS (gratuit, sans clé API).
Utilisé pour enrichir l'analyse des marchés court terme.
"""

import re
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta

# Mots vides à exclure pour construire la requête de recherche
STOP_WORDS = {
    "will", "the", "a", "an", "in", "by", "to", "of", "is", "are", "be",
    "has", "have", "do", "does", "for", "at", "on", "with", "from", "that",
    "this", "or", "and", "if", "it", "its", "was", "were", "had", "did",
    "there", "their", "they", "what", "which", "who", "how", "when", "where",
    "win", "lose", "reach", "hit", "get", "make", "post", "tweets", "out",
    "vs", "between", "against", "until", "before", "after", "during",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; newsbot/1.0)"}


def extraire_mots_cles(question: str, max_mots: int = 6) -> str:
    """Extrait les mots clés significatifs d'une question de marché."""
    mots = re.findall(r"\b[a-zA-Z][a-zA-Z0-9'.]*\b", question)
    filtres = [m for m in mots if m.lower() not in STOP_WORDS and len(m) > 2]
    return " ".join(filtres[:max_mots])


def nettoyer_titre(titre: str) -> str:
    """Retire le nom de la source souvent ajouté en fin de titre ('... - Reuters')."""
    return re.sub(r"\s*-\s*[^-]{2,40}$", "", titre).strip()


def est_recent(date_str: str, jours: int = 7) -> bool:
    """Vérifie si un article a été publié dans les N derniers jours."""
    try:
        pub = datetime(*date_str[:6], tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - pub) < timedelta(days=jours)
    except Exception:
        return True  # En cas de doute, on garde l'article


def chercher_news(question: str, max_articles: int = 5) -> list:
    """
    Cherche les actualités récentes sur Google News RSS.
    Retourne une liste de dicts {titre, source, resume}.
    """
    query = extraire_mots_cles(question)
    if not query:
        return []

    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}"
        f"&hl=en&gl=US&ceid=US:en"
    )

    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return []

        feed = feedparser.parse(r.content)
        articles = []

        for entry in feed.entries[:max_articles * 2]:  # marge pour filtrer
            # Filtre articles trop vieux
            if hasattr(entry, "published_parsed") and not est_recent(entry.published_parsed):
                continue

            titre = nettoyer_titre(entry.get("title", ""))
            source = entry.get("source", {}).get("title", "") if hasattr(entry.get("source", {}), "get") else ""

            # Résumé : nettoyage HTML et entités
            resume_brut = entry.get("summary", "")
            resume = re.sub(r"<[^>]+>", "", resume_brut)
            resume = re.sub(r"&[a-z]+;", " ", resume)
            resume = re.sub(r"\s+", " ", resume).strip()[:180]

            if titre:
                articles.append({
                    "titre"  : titre,
                    "source" : source,
                    "resume" : resume,
                })

            if len(articles) >= max_articles:
                break

        return articles

    except Exception:
        return []


def formater_pour_prompt(question: str, articles: list) -> str:
    """Formate les actualités pour injection dans un prompt LLM."""
    if not articles:
        return ""

    lignes = [f"Actualités récentes sur '{extraire_mots_cles(question, 4)}' :"]
    for a in articles:
        source = f"[{a['source']}] " if a["source"] else ""
        lignes.append(f"• {source}{a['titre']}")
        if a["resume"]:
            lignes.append(f"  → {a['resume']}")

    return "\n".join(lignes)


# ─── Test rapide ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    questions_test = [
        "Will Bitcoin reach $85,000 in May?",
        "Will Anthropic have the best AI model at the end of May 2026?",
        "Iran closes its airspace by May 31?",
    ]
    for q in questions_test:
        print(f"\n🔍 {q}")
        articles = chercher_news(q, max_articles=3)
        print(formater_pour_prompt(q, articles) if articles else "   Aucun résultat")
        time.sleep(1)
