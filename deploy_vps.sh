#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Script de déploiement sur VPS Ubuntu/Debian
#  Usage : bash deploy_vps.sh <IP_VPS> <USER_VPS>
#  Exemple : bash deploy_vps.sh 51.210.12.34 ubuntu
# ─────────────────────────────────────────────────────────────

VPS_IP="${1:?Usage: $0 <IP_VPS> <USER_VPS>}"
VPS_USER="${2:-ubuntu}"
VPS_DIR="/home/$VPS_USER/polymarket"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Déploiement vers $VPS_USER@$VPS_IP:$VPS_DIR"

# ── 1. Créer le dossier distant ──────────────────────────────
ssh "$VPS_USER@$VPS_IP" "mkdir -p $VPS_DIR/logs $VPS_DIR/data"

# ── 2. Copier les fichiers (hors venv, data locale, logs) ────
rsync -avz --progress \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'venv/' \
  "$LOCAL_DIR/" "$VPS_USER@$VPS_IP:$VPS_DIR/"

# ── 3. Copier le .env séparément (contient les secrets) ──────
scp "$LOCAL_DIR/.env" "$VPS_USER@$VPS_IP:$VPS_DIR/.env"

# ── 4. Installation des dépendances sur le VPS ───────────────
ssh "$VPS_USER@$VPS_IP" << EOF
  cd $VPS_DIR
  python3 -m venv venv
  source venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
  echo "✅ Dépendances installées"
EOF

# ── 5. Installer le cron sur le VPS ─────────────────────────
ssh "$VPS_USER@$VPS_IP" << EOF
  # Rendre les scripts exécutables
  chmod +x $VPS_DIR/run_scanner.sh $VPS_DIR/run_monitor.sh

  # Ajouter les crons si pas déjà présents
  (crontab -l 2>/dev/null | grep -v 'polymarket'; \
   echo "*/30 * * * * $VPS_DIR/run_scanner.sh"; \
   echo "15,45 * * * * $VPS_DIR/run_monitor.sh") | crontab -

  echo "✅ Crons installés :"
  crontab -l | grep polymarket
EOF

echo ""
echo "✅ Déploiement terminé !"
echo ""
echo "Prochaines étapes :"
echo "  1. Connecte-toi : ssh $VPS_USER@$VPS_IP"
echo "  2. Teste le scanner : cd $VPS_DIR && source venv/bin/activate && python3 scanner.py"
echo "  3. Lance le dashboard : source venv/bin/activate && streamlit run app.py --server.port 8501 --server.headless true"
echo ""
echo "Pour accéder au dashboard depuis ton Mac :"
echo "  http://$VPS_IP:8501"
