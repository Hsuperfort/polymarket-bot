"""
Polymarket Dashboard — application web locale (Streamlit).
Lancement : streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from database import (
    initialiser,
    charger_dernier_scan,
    charger_positions,
    ouvrir_position,
    clore_position,
    stats_performance,
)
from resolver import actualiser_prix

st.set_page_config(
    page_title="Polymarket Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

initialiser()

# ─── Auto-actualisation des prix au chargement ────────────────────────────────

import time as _time

def _doit_actualiser() -> bool:
    derniere = st.session_state.get("derniere_actu_ts", 0)
    return (_time.time() - derniere) > 300  # rafraîchit si > 5 minutes

if _doit_actualiser():
    _ouvertes = charger_positions("ouvert")
    if _ouvertes:
        st.session_state["positions_actualisees"] = actualiser_prix(_ouvertes)
    else:
        st.session_state["positions_actualisees"] = []
    st.session_state["derniere_actu_ts"] = _time.time()

# ─── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  /* Carte KPI */
  .kpi-card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
    border: 1px solid #2a2a3e;
  }
  .kpi-label {
    color: #888;
    font-size: 0.78em;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
  }
  .kpi-value {
    font-size: 2em;
    font-weight: 700;
    line-height: 1.1;
  }
  .kpi-sub {
    font-size: 0.78em;
    color: #666;
    margin-top: 4px;
  }
  .green  { color: #00d4aa; }
  .red    { color: #ff4b4b; }
  .blue   { color: #4b8bff; }
  .yellow { color: #ffd700; }
  .white  { color: #ffffff; }

  /* Séparateur KPI */
  .kpi-divider { border-top: 2px solid #2a2a3e; margin: 16px 0 24px 0; }

  /* Badges direction */
  .dir-yes { background:#0a3a0a; color:#00ff88; padding:2px 10px; border-radius:4px; font-weight:700; }
  .dir-no  { background:#3a0a0a; color:#ff6666; padding:2px 10px; border-radius:4px; font-weight:700; }

  /* Badges confiance */
  .conf-haute   { background:#0a3a0a; color:#00ff88; padding:1px 7px; border-radius:3px; font-size:0.8em; }
  .conf-moyenne { background:#3a3a0a; color:#ffd700; padding:1px 7px; border-radius:3px; font-size:0.8em; }
  .conf-faible  { background:#2a2a2a; color:#888;    padding:1px 7px; border-radius:3px; font-size:0.8em; }

  /* Masquer le menu hamburger et footer Streamlit */
  #MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def kpi(label, value, color="white", sub=""):
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value {color}">{value}</div>
      {sub_html}
    </div>"""

def dir_badge(d):
    return f'<span class="dir-yes">YES</span>' if d == "YES" else f'<span class="dir-no">NO</span>'

def conf_badge(c):
    cls = {"haute": "conf-haute", "moyenne": "conf-moyenne", "faible": "conf-faible"}.get(c, "conf-faible")
    return f'<span class="{cls}">{c}</span>'

def score_icon(s):
    if s >= 7: return "🔥"
    if s >= 5: return "⚡"
    return "💤"


# ─── SIDEBAR — Paramètres du bot ─────────────────────────────────────────────

import json, pathlib

CONFIG_PATH = pathlib.Path("config.json")

def charger_config():
    defaults = {"mise_auto": 10.0, "score_min": 6, "max_positions": 8}
    if CONFIG_PATH.exists():
        try:
            return {**defaults, **json.loads(CONFIG_PATH.read_text())}
        except Exception:
            pass
    return defaults

def sauvegarder_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

cfg = charger_config()

with st.sidebar:
    st.markdown("## ⚙️ Paramètres du bot")
    st.divider()

    mise_auto = st.number_input(
        "💵 Mise par position (USDC)",
        min_value=1.0, max_value=500.0,
        value=float(cfg["mise_auto"]), step=1.0,
        help="Montant simulé investi automatiquement sur chaque opportunité détectée."
    )
    score_min = st.slider(
        "🎯 Score minimum pour entrer",
        min_value=1, max_value=10,
        value=int(cfg["score_min"]),
        help="Le bot n'ouvre une position que si le score IA est ≥ à cette valeur."
    )
    max_pos = st.slider(
        "📊 Positions ouvertes max",
        min_value=1, max_value=50,
        value=int(cfg["max_positions"]),
        help="Nombre maximum de positions simultanées. Au-delà, le bot n'ouvre plus."
    )

    if st.button("💾 Enregistrer", use_container_width=True, type="primary"):
        sauvegarder_config({"mise_auto": mise_auto, "score_min": score_min, "max_positions": max_pos})
        st.success("Paramètres enregistrés ✓")

    st.divider()
    st.caption(f"Positions ouvertes : **{len(charger_positions('ouvert'))}** / {max_pos}")
    st.caption(f"Score min actif : **{score_min}/10**")
    st.caption(f"Mise auto : **{mise_auto:.0f} USDC**")

# ─── DASHBOARD KPI (toujours visible en haut) ─────────────────────────────────

st.markdown("## 🎯 Polymarket Dashboard")

stats    = stats_performance()
ouvertes = charger_positions("ouvert")

pnl       = stats["pnl"]
win_rate  = stats["win_rate"]
gagnes    = stats["gagnes"]
perdus    = stats["perdus"]
total_cl  = stats["total"]
nb_open   = len(ouvertes)
mise_open = sum(p["mise"] for p in ouvertes)

# Valeur du portefeuille : utilise les prix actualisés si disponibles
positions_actu = st.session_state.get("positions_actualisees", [])
if positions_actu:
    valeur_portfolio = sum((p["mise"] + p.get("pnl_latent", 0)) for p in positions_actu)
    pnl_latent_total = sum(p.get("pnl_latent", 0) for p in positions_actu)
    portfolio_sub    = f"{'+' if pnl_latent_total >= 0 else ''}{pnl_latent_total:.2f} $ latent"
    portfolio_color  = "green" if pnl_latent_total >= 0 else "red"
    prix_ok          = True
else:
    valeur_portfolio = mise_open
    portfolio_sub    = "actualise les prix pour le P&L"
    portfolio_color  = "blue"
    prix_ok          = False

pnl_color  = "green" if pnl >= 0 else "red"
pnl_sign   = "+" if pnl >= 0 else ""
wr_color   = "green" if win_rate >= 55 else ("yellow" if win_rate >= 45 else "red")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.markdown(kpi("Valeur Portefeuille", f"{valeur_portfolio:.2f} $", portfolio_color, portfolio_sub), unsafe_allow_html=True)
c2.markdown(kpi("P&L Réalisé",        f"{pnl_sign}{pnl:.2f} $",   pnl_color,       f"{total_cl} positions closes"), unsafe_allow_html=True)
c3.markdown(kpi("Win Rate",           f"{win_rate:.1f}%",          wr_color,        f"{gagnes}G  /  {perdus}P"), unsafe_allow_html=True)
c4.markdown(kpi("Victoires",          gagnes,                      "green",         "positions gagnées"), unsafe_allow_html=True)
c5.markdown(kpi("Défaites",           perdus,                      "red",           "positions perdues"), unsafe_allow_html=True)
c6.markdown(kpi("Positions open",     nb_open,                     "blue",          f"{mise_open:.0f} $ investis"), unsafe_allow_html=True)

st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)


# ─── Onglets ──────────────────────────────────────────────────────────────────

tab_scanner, tab_portfolio, tab_performance = st.tabs([
    "🔍 Scanner",
    "💼 Portfolio",
    "📈 Performance",
])


# ════════════════════════════════════════════════════════════════════════
# ONGLET 1 — SCANNER
# ════════════════════════════════════════════════════════════════════════

with tab_scanner:

    col_btn, col_meta = st.columns([1, 4])
    with col_btn:
        lancer = st.button("▶ Lancer un scan", type="primary", use_container_width=True)
    with col_meta:
        scan_meta, _ = charger_dernier_scan()
        if scan_meta:
            ts = scan_meta.get("timestamp", "")[:16].replace("T", " ")
            nb = scan_meta.get("nb_marches", 0)
            st.caption(f"Dernier scan : **{ts}** — {nb} marchés analysés")

    if lancer:
        with st.spinner("Scan en cours (≈ 45s)..."):
            import subprocess, sys
            result = subprocess.run(
                [sys.executable, "scanner.py"],
                capture_output=True, text=True, cwd="."
            )
        if result.returncode == 0:
            st.success("Scan terminé !")
        else:
            st.error(f"Erreur scanner : {result.stderr[-400:]}")
        st.rerun()

    # Filtres
    with st.expander("⚙️ Filtres", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        score_min  = fc1.slider("Score minimum", 0, 10, 0)
        directions = fc2.multiselect("Direction", ["YES", "NO"], default=["YES", "NO"])
        confiances = fc3.multiselect("Confiance", ["haute", "moyenne", "faible"],
                                     default=["haute", "moyenne", "faible"])

    # Résultats
    _, resultats = charger_dernier_scan()

    # Questions déjà en position ouverte → masquées dans le scanner
    positions_ouvertes = charger_positions("ouvert")
    questions_en_cours = {p["question"].lower().strip() for p in positions_ouvertes}

    filtres = [
        r for r in resultats
        if r["opp"]["score"] >= score_min
        and r["opp"]["direction"] in directions
        and r["opp"]["confiance"] in confiances
        and r["opp"]["question"].lower().strip() not in questions_en_cours
    ]

    if not filtres:
        st.info("Aucune opportunité disponible — toutes sont déjà en position ou le scan n'a rien détecté.")
    else:
        st.markdown(f"**{len(filtres)} opportunité(s)**")
        for item in filtres:
            opp  = item["opp"]
            news = item["news"]

            score     = opp.get("score", 0)
            direction = opp.get("direction", "?")
            prob_m    = (opp.get("prob_marche") or 0) * 100
            prob_e    = (opp.get("prob_estimee") or 0) * 100
            edge      = abs(prob_e - prob_m)
            jours     = opp.get("jours") or 0
            confiance = opp.get("confiance", "?")
            question  = opp.get("question", "")
            liquidite = opp.get("liquidite") or 0
            vol24     = opp.get("volume_24h") or 0
            urgence   = " ⏰" if jours < 3 else ""

            header = (
                f"{score_icon(score)} **Score {score}/10**  &nbsp;|&nbsp; "
                f"{dir_badge(direction)}  &nbsp;|&nbsp; "
                f"J‑{jours:.0f}{urgence}  &nbsp;|&nbsp; "
                f"{question[:65]}"
            )

            with st.expander(f"{score_icon(score)} Score {score}/10  |  J-{jours:.0f}{urgence}  —  {question[:65]}", expanded=(score >= 7)):

                # Métriques du marché
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Marché",     f"{prob_m:.1f}%")
                m2.metric("IA estime",  f"{prob_e:.1f}%", delta=f"{prob_e-prob_m:+.1f}pts")
                m3.metric("Edge",       f"{edge:.1f}pts")
                m4.metric("Liquidité",  f"{liquidite:,.0f} $")
                m5.metric("Vol 24h",    f"{vol24:,.0f} $")

                # Direction + confiance
                st.markdown(
                    f"Direction : {dir_badge(direction)} &nbsp;&nbsp; "
                    f"Confiance : {conf_badge(confiance)} &nbsp;&nbsp; "
                    f"Résolution : J‑{jours:.0f}",
                    unsafe_allow_html=True
                )

                # Raisonnement IA
                st.markdown(f"> {opp.get('raisonnement', '')}")

                # News
                if news:
                    st.markdown("**📰 Actualités récentes**")
                    for n in news:
                        src = f"`{n['source']}`  " if n.get("source") else ""
                        st.markdown(f"• {src}{n['titre']}")
                        if n.get("resume"):
                            st.caption(f"  {n['resume']}")

                st.markdown(f"[🔗 Voir sur Polymarket]({opp.get('url', '')})")

                # Ouvrir position
                st.divider()
                pc1, pc2 = st.columns([2, 1])
                with pc1:
                    mise = st.number_input(
                        "Mise simulée (USDC)", min_value=1.0, max_value=500.0,
                        value=10.0, step=1.0, key=f"mise_{opp['id']}"
                    )
                with pc2:
                    st.write("")
                    st.write("")
                    if st.button(f"💰 Ouvrir position {direction}", key=f"pos_{opp['id']}"):
                        ouvrir_position(opp, mise)
                        st.success(f"Position {direction} ouverte — {mise:.0f} USDC")
                        st.rerun()


# ════════════════════════════════════════════════════════════════════════
# ONGLET 2 — PORTFOLIO
# ════════════════════════════════════════════════════════════════════════

with tab_portfolio:

    ouvertes_brut = charger_positions("ouvert")

    col_titre, col_actu = st.columns([3, 1])
    col_titre.subheader(f"Positions ouvertes — {len(ouvertes_brut)}")

    if col_actu.button("🔄 Actualiser les prix", use_container_width=True, disabled=(len(ouvertes_brut) == 0)):
        with st.spinner("Récupération des prix Polymarket..."):
            st.session_state["positions_actualisees"] = actualiser_prix(ouvertes_brut)
        st.rerun()

    # Utilise les prix actualisés si disponibles, sinon les données brutes
    ouvertes = st.session_state.get("positions_actualisees", ouvertes_brut)

    if not ouvertes:
        st.info("Aucune position ouverte. Ouvre des positions depuis le Scanner.")
    else:
        for pos in ouvertes:
            direction       = pos.get("direction", "YES")
            mise            = pos.get("mise", 0)
            prix_entree_yes = pos.get("prix_yes_entree") or 0.5
            prix_cible_yes  = pos.get("prix_yes_cible")  or prix_entree_yes
            prix_actuel     = pos.get("prix_actuel")
            pnl_l           = pos.get("pnl_latent", 0)
            progression     = pos.get("progression", 0)
            alerte          = pos.get("alerte", False)

            # Prix de la part achetée (YES ou NO)
            if direction == "YES":
                prix_part_entree = prix_entree_yes
                prix_part_cible  = prix_cible_yes
                prix_part_actuel = prix_actuel
                label_cible      = f"YES → {prix_cible_yes*100:.1f}%"
            else:
                prix_part_entree = 1 - prix_entree_yes
                prix_part_cible  = 1 - prix_cible_yes
                prix_part_actuel = (1 - prix_actuel) if prix_actuel is not None else None
                label_cible      = f"NO → YES retombe à {prix_cible_yes*100:.1f}%"

            nb_parts      = pos.get("nb_parts") or round(mise / prix_part_entree, 1)
            gain_si_cible = round((prix_part_cible - prix_part_entree) * nb_parts, 2)
            pnl_signe     = "+" if pnl_l >= 0 else ""
            alerte_icone  = "🚨 OBJECTIF ATTEINT — " if alerte else ""

            # Valeur de revente immédiate
            if prix_actuel is not None:
                valeur_actuelle = round(mise + pnl_l, 2)
                val_signe       = "+" if pnl_l >= 0 else ""
                val_pct         = round(pnl_l / mise * 100, 1) if mise else 0
                tag_valeur      = f"  →  si vendu : {valeur_actuelle:.2f} $ ({val_signe}{val_pct:.1f}%)"
            else:
                tag_valeur = "  →  clique 'Actualiser' pour voir la valeur"

            dir_label = "✅ YES" if direction == "YES" else "❌ NO"
            header    = f"{alerte_icone}{dir_label}  |  Mise {mise:.0f} ${tag_valeur}  |  {pos['question'][:45]}"

            with st.expander(header, expanded=alerte):

                # Encadré "Si vendu maintenant" — priorité visuelle maximale
                if prix_actuel is not None:
                    couleur_bg  = "#0a3a0a" if pnl_l >= 0 else "#3a0a0a"
                    couleur_txt = "#00ff88" if pnl_l >= 0 else "#ff6666"
                    icone_pnl   = "📈" if pnl_l >= 0 else "📉"
                    st.markdown(
                        f"""<div style="background:{couleur_bg}; border-radius:8px; padding:14px 20px; margin-bottom:12px;">
                        <span style="color:#aaa; font-size:0.8em;">SI VENDU MAINTENANT</span><br>
                        <span style="color:{couleur_txt}; font-size:2em; font-weight:700;">{icone_pnl} {valeur_actuelle:.2f} $</span>
                        <span style="color:{couleur_txt}; font-size:1em; margin-left:10px;">({val_signe}{pnl_l:.2f} $ / {val_signe}{val_pct:.1f}%)</span>
                        </div>""",
                        unsafe_allow_html=True
                    )

                    # Barre de progression
                    st.markdown(
                        f"**Progression vers l'objectif : {progression:.1f}%**"
                        + ("  🎯 Objectif atteint !" if alerte else "")
                    )
                    st.progress(max(0.0, min(progression / 100, 1.0)))
                else:
                    st.info("💡 Clique **Actualiser les prix** pour voir la valeur de revente en temps réel.")

                # Métriques
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Mise investie",  f"{mise:.0f} $")
                c2.metric("Prix d'entrée",  f"{prix_part_entree*100:.1f}%")
                c3.metric("Objectif IA",    f"{prix_part_cible*100:.1f}%",
                          delta=f"{(prix_part_cible - prix_part_entree)*100:+.1f}pts")
                if prix_actuel is not None:
                    c4.metric("Prix actuel", f"{(prix_part_actuel or 0)*100:.1f}%",
                              delta=f"{pnl_signe}{pnl_l:.2f} $")
                else:
                    c4.metric("Prix actuel", "—")
                c5.metric("Gain si objectif", f"+{gain_si_cible:.2f} $")

                st.caption(
                    f"Direction : {direction}  |  {nb_parts:.1f} parts  |  "
                    f"Ouvert le {pos['date_ouverture'][:16].replace('T', ' ')}"
                )
                if pos.get("url"):
                    st.markdown(f"[🔗 Voir sur Polymarket]({pos['url']})")

                # Clôture manuelle au prix actuel ou personnalisé
                st.divider()
                st.markdown("**Clôturer la position**")
                cc1, cc2 = st.columns([2, 1])
                with cc1:
                    val_defaut = round(prix_actuel * 100, 1) if prix_actuel else round(prix_part_cible * 100, 1)
                    prix_sortie_pct = st.number_input(
                        "Prix de sortie YES (%)", min_value=1.0, max_value=99.0,
                        value=float(val_defaut), step=0.5,
                        key=f"sortie_{pos['id']}",
                        help="Entre le prix YES actuel affiché sur Polymarket"
                    )
                with cc2:
                    st.write("")
                    st.write("")
                    if st.button("💸 Vendre", key=f"sell_{pos['id']}", type="primary"):
                        clore_position(pos["id"], prix_sortie_pct / 100)
                        pnl_reel = round(
                            (prix_sortie_pct/100 - prix_part_entree if direction == "YES"
                             else (1 - prix_sortie_pct/100) - prix_part_entree) * nb_parts, 2
                        )
                        signe = "+" if pnl_reel >= 0 else ""
                        st.success(f"Position clôturée — P&L : {signe}{pnl_reel:.2f} $")
                        if "positions_actualisees" in st.session_state:
                            del st.session_state["positions_actualisees"]
                        st.rerun()

    st.divider()

    # Historique
    closes = sorted(
        charger_positions("gagne") + charger_positions("perdu"),
        key=lambda x: x.get("date_cloture", ""), reverse=True
    )
    st.subheader(f"Historique — {len(closes)} positions closes")

    if closes:
        rows = []
        for p in closes:
            direction = p.get("direction", "YES")
            entree    = p.get("prix_yes_entree") or 0
            sortie    = p.get("prix_yes_sortie") or 0
            pnl       = round(p.get("gain_perte") or 0, 2)
            rows.append({
                "Date"       : (p.get("date_cloture") or "")[:16].replace("T", " "),
                "Direction"  : direction,
                "Question"   : p["question"][:45] + "…",
                "Entrée"     : f"{entree*100:.1f}%",
                "Sortie"     : f"{sortie*100:.1f}%",
                "Mise ($)"   : round(p["mise"], 2),
                "P&L ($)"    : pnl,
                "Résultat"   : "✅" if pnl > 0 else "❌",
            })

        df = pd.DataFrame(rows)
        st.dataframe(
            df.style.applymap(
                lambda v: "color: #00d4aa" if isinstance(v, float) and v > 0
                          else ("color: #ff4b4b" if isinstance(v, float) and v < 0 else ""),
                subset=["P&L ($)"]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Aucune position clôturée.")


# ════════════════════════════════════════════════════════════════════════
# ONGLET 3 — PERFORMANCE
# ════════════════════════════════════════════════════════════════════════

with tab_performance:

    closes = sorted(
        charger_positions("gagne") + charger_positions("perdu"),
        key=lambda x: x.get("date_cloture", "")
    )

    if not closes:
        st.info("Aucune position clôturée pour l'instant.")
    else:
        # Courbe P&L cumulée
        dates, cumul, total = [], [], 0
        for pos in closes:
            total += pos.get("gain_perte") or 0
            dates.append((pos.get("date_cloture") or "")[:16].replace("T", " "))
            cumul.append(round(total, 2))

        couleur_ligne = "#00d4aa" if total >= 0 else "#ff4b4b"
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=cumul,
            mode="lines+markers",
            line=dict(color=couleur_ligne, width=2),
            marker=dict(size=7, color=couleur_ligne),
            fill="tozeroy",
            fillcolor=f"rgba({'0,212,170' if total >= 0 else '255,75,75'},0.12)",
            name="P&L cumulé",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="#444")
        fig.update_layout(
            title="Courbe P&L cumulée (USDC)",
            xaxis_title=None,
            yaxis_title="P&L ($)",
            template="plotly_dark",
            height=320,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Graphiques secondaires
        col_pie, col_bar = st.columns(2)

        with col_pie:
            fig2 = go.Figure(go.Pie(
                labels=["Victoires", "Défaites"],
                values=[stats["gagnes"], stats["perdus"]],
                marker_colors=["#00d4aa", "#ff4b4b"],
                hole=0.5,
                textinfo="label+percent",
            ))
            fig2.update_layout(
                title="Répartition",
                template="plotly_dark",
                height=280,
                margin=dict(l=0, r=0, t=40, b=0),
                showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True)

        with col_bar:
            df_bar = pd.DataFrame([{
                "Position" : p["question"][:28] + "…",
                "P&L"      : round(p.get("gain_perte") or 0, 2),
                "Résultat" : p.get("resultat", ""),
            } for p in closes])

            fig3 = px.bar(
                df_bar, x="P&L", y="Position",
                color="Résultat",
                color_discrete_map={"gagne": "#00d4aa", "perdu": "#ff4b4b"},
                orientation="h",
                template="plotly_dark",
                title="P&L par position",
                height=280,
            )
            fig3.update_layout(margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)
