"""
Script de configuration Telegram.
Lance ce script après avoir créé ton bot et cliqué Start.
"""

import os
from dotenv import load_dotenv
from notifier import get_chat_id, envoyer_message

load_dotenv()

token = os.getenv("TELEGRAM_TOKEN", "").strip()

if not token or "REMPLACE" in token:
    print("❌ Configure TELEGRAM_TOKEN dans le fichier .env d'abord.")
    exit(1)

print("🔍 Recherche de ton chat_id...")
chat_id = get_chat_id(token)

if not chat_id:
    print("\n❌ Impossible de trouver le chat_id.")
    print("   → Assure-toi d'avoir cliqué 'Start' sur ton bot Telegram, puis relance ce script.")
    exit(1)

print(f"✅ Chat ID trouvé : {chat_id}")

# Envoie un message de test
ok = envoyer_message(token, chat_id, (
    "🤖 *Polymarket Scanner configuré !*\n\n"
    "Tu recevras tes alertes ici à chaque scan.\n"
    "_Bonne chance sur les marchés_ 🎯"
))

if ok:
    print("✅ Message de test envoyé sur Telegram !")
    print(f"\n👉 Ajoute cette ligne dans ton .env :")
    print(f"   TELEGRAM_CHAT_ID={chat_id}")
else:
    print("❌ Erreur lors de l'envoi — vérifie ton token.")
