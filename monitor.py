"""
Monitor — vérifie les positions ouvertes et clôture automatiquement celles
dont l'objectif IA est atteint. Lancé toutes les 30 minutes par cron.
"""

from datetime import datetime
from database import initialiser
from auto_trader import auto_clore

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

    print(f"--- FIN MONITORING ---\n")

if __name__ == "__main__":
    main()
