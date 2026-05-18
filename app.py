"""
Polymarket Dashboard — application web locale (Streamlit).
Lancement : streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import json, pathlib, subprocess
import time as _time

from database import (
    initialiser,
    charger_positions,
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

# ─── Auto-sync Git + rechargement page toutes les 5 minutes ──────────────────

INTERVALLE_SYNC = 300  # secondes

def _sync_git():
    """Pull silencieux depuis GitHub pour récupérer la dernière DB."""
    subprocess.run(
        ["git", "pull", "--rebase", "origin", "main"],
        capture_output=True, cwd="."
    )

now = _time.time()
derniere_sync = st.session_state.get("derniere_sync_ts", 0)

if now - derniere_sync > INTERVALLE_SYNC:
    _sync_git()
    st.session_state["derniere_sync_ts"] = now
    st.session_state["derniere_actu_ts"] = 0  # force ré-actualisation des prix

# Timer JS : compte à rebours en temps réel + rechargement automatique
st.markdown(f"""
<script>
(function() {{
    var total = {INTERVALLE_SYNC};
    function tick() {{
        total--;
        if (total <= 0) {{ window.location.reload(); return; }}
        var m = Math.floor(total / 60);
        var s = total % 60;
        var el = document.getElementById('sync-countdown');
        if (el) el.innerText = '⏱ Sync auto dans ' + m + 'm' + (s < 10 ? '0' : '') + s + 's';
        setTimeout(tick, 1000);
    }}
    setTimeout(tick, 1000);
}})();
</script>
""", unsafe_allow_html=True)

# ─── Auto-actualisation des prix ─────────────────────────────────────────────

def _doit_actualiser() -> bool:
    derniere = st.session_state.get("derniere_actu_ts", 0)
    return (_time.time() - derniere) > INTERVALLE_SYNC

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
  .kpi-card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
    border: 1px solid #2a2a3e;
  }
  .kpi-label { color: #888; font-size: 0.78em; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .kpi-value { font-size: 2em; font-weight: 700; line-height: 1.1; }
  .kpi-sub   { font-size: 0.78em; color: #666; margin-top: 4px; }
  .green  { color: #00d4aa; }
  .red    { color: #ff4b4b; }
  .blue   { color: #4b8bff; }
  .yellow { color: #ffd700; }
  .white  { color: #ffffff; }
  .kpi-divider { border-top: 2px solid #2a2a3e; margin: 16px 0 24px 0; }

  .pos-card {
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 14px;
  }
  .pos-card.alerte  { border-color: #00d4aa; }
  .pos-card.stop    { border-color: #ff4b4b; }

  .dir-yes  { background:#0a3a0a; color:#00ff88; padding:3px 10px; border-radius:5px; font-weight:700; font-size:0.9em; }
  .dir-no   { background:#3a0a0a; color:#ff6666; padding:3px 10px; border-radius:5px; font-weight:700; font-size:0.9em; }
  .conf-haute   { background:#0a3a0a; color:#00ff88; padding:1px 7px; border-radius:3px; font-size:0.8em; }
  .conf-moyenne { background:#3a3a0a; color:#ffd700; padding:1px 7px; border-radius:3px; font-size:0.8em; }
  .conf-faible  { background:#2a2a2a; color:#888;    padding:1px 7px; border-radius:3px; font-size:0.8em; }
  .score-badge  { background:#1e1e3e; color:#aaaaff; padding:2px 8px; border-radius:4px; font-size:0.85em; font-weight:600; }

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
    cls = {"haute": "conf-haute", "moyenne": "conf-moyenne", "faible": "conf-faible"}.get(c or "", "conf-faible")
    return f'<span class="{cls}">{c or "—"}</span>'


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────

CONFIG_PATH = pathlib.Path("config.json")

def charger_config():
    defaults = {"mise_auto": 10.0, "score_min": 6, "max_positions": 50}
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
    mise_auto = st.number_input("💵 Mise par position (USDC)", min_value=1.0, max_value=500.0,
                                 value=float(cfg["mise_auto"]), step=1.0)
    score_min = st.slider("🎯 Score minimum", min_value=1, max_value=10, value=int(cfg["score_min"]))
    max_pos   = st.slider("📊 Positions max",  min_value=1, max_value=50,  value=int(cfg["max_positions"]))

    if st.button("💾 Enregistrer", use_container_width=True, type="primary"):
        sauvegarder_config({"mise_auto": mise_auto, "score_min": score_min, "max_positions": max_pos})
        st.success("Paramètres enregistrés ✓")

    st.divider()
    st.caption(f"Positions ouvertes : **{len(charger_positions('ouvert'))}** / {max_pos}")
    st.caption(f"Score min actif : **{score_min}/10**")
    st.caption(f"Mise auto : **{mise_auto:.0f} USDC**")


# ─── HEADER ───────────────────────────────────────────────────────────────────

h1, h2 = st.columns([5, 1])
h1.markdown("## 🎯 Polymarket Dashboard")

h2.markdown('<span id="sync-countdown" style="font-size:0.75em; color:#888;">⏱ Chargement...</span>', unsafe_allow_html=True)

if h2.button("☁️ Sync maintenant", use_container_width=True):
    _sync_git()
    st.session_state["derniere_sync_ts"] = _time.time()
    st.session_state["derniere_actu_ts"] = 0
    st.rerun()

stats    = stats_performance()
ouvertes = charger_positions("ouvert")

pnl      = stats["pnl"]
win_rate = stats["win_rate"]
gagnes   = stats["gagnes"]
perdus   = stats["perdus"]
total_cl = stats["total"]
nb_open  = len(ouvertes)
mise_open = sum(p["mise"] for p in ouvertes)

positions_actu   = st.session_state.get("positions_actualisees", [])
pnl_latent_total = sum(p.get("pnl_latent", 0) for p in positions_actu)
valeur_portfolio = sum((p["mise"] + p.get("pnl_latent", 0)) for p in positions_actu) if positions_actu else mise_open
portfolio_color  = "green" if pnl_latent_total >= 0 else "red"
portfolio_sub    = f"{'+' if pnl_latent_total >= 0 else ''}{pnl_latent_total:.2f} $ latent" if positions_actu else "actualise pour le P&L"

pnl_color = "green" if pnl >= 0 else "red"
pnl_sign  = "+" if pnl >= 0 else ""
wr_color  = "green" if win_rate >= 55 else ("yellow" if win_rate >= 45 else "red")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.markdown(kpi("Valeur Portefeuille", f"{valeur_portfolio:.2f} $", portfolio_color, portfolio_sub), unsafe_allow_html=True)
c2.markdown(kpi("P&L Réalisé",        f"{pnl_sign}{pnl:.2f} $",   pnl_color,       f"{total_cl} positions closes"), unsafe_allow_html=True)
c3.markdown(kpi("Win Rate",           f"{win_rate:.1f}%",          wr_color,        f"{gagnes}G / {perdus}P"), unsafe_allow_html=True)
c4.markdown(kpi("Victoires",          gagnes,   "green", "positions gagnées"), unsafe_allow_html=True)
c5.markdown(kpi("Défaites",           perdus,   "red",   "positions perdues"), unsafe_allow_html=True)
c6.markdown(kpi("Positions open",     nb_open,  "blue",  f"{mise_open:.0f} $ investis"), unsafe_allow_html=True)

st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)


# ─── ONGLETS ──────────────────────────────────────────────────────────────────

tab_positions, tab_historique, tab_performance = st.tabs([
    "💼 Positions ouvertes",
    "📋 Historique",
    "📈 Performance",
])


# ════════════════════════════════════════════════════════════════════════
# ONGLET 1 — POSITIONS OUVERTES
# ════════════════════════════════════════════════════════════════════════

with tab_positions:

    col_titre, col_actu = st.columns([3, 1])
    col_titre.subheader(f"Positions ouvertes — {nb_open}")

    if col_actu.button("🔄 Actualiser les prix", use_container_width=True, disabled=(nb_open == 0)):
        with st.spinner("Récupération des prix..."):
            st.session_state["positions_actualisees"] = actualiser_prix(ouvertes)
            st.session_state["derniere_actu_ts"] = _time.time()
        st.rerun()

    ouvertes_affich = st.session_state.get("positions_actualisees", ouvertes)

    if not ouvertes_affich:
        st.info("Aucune position ouverte. Le bot ouvrira automatiquement les prochaines opportunités.")
    else:
        for pos in ouvertes_affich:
            direction       = pos.get("direction", "YES")
            mise            = pos.get("mise", 0)
            prix_yes_entree = pos.get("prix_yes_entree") or 0.5
            prix_yes_cible  = pos.get("prix_yes_cible")  or prix_yes_entree
            prix_actuel     = pos.get("prix_actuel")
            pnl_l           = pos.get("pnl_latent", 0)
            progression     = pos.get("progression", 0)
            alerte          = pos.get("alerte", False)
            stop_loss       = pos.get("stop_loss", False)
            prix_stop       = pos.get("prix_stop")
            score           = pos.get("score")
            confiance       = pos.get("confiance")
            raisonnement    = pos.get("raisonnement", "")
            question        = pos.get("question", "")

            if direction == "YES":
                prix_part_entree = prix_yes_entree
                prix_part_cible  = prix_yes_cible
                prix_part_actuel = prix_actuel
                prix_part_stop   = prix_stop
            else:
                prix_part_entree = 1 - prix_yes_entree
                prix_part_cible  = 1 - prix_yes_cible
                prix_part_actuel = (1 - prix_actuel) if prix_actuel is not None else None
                prix_part_stop   = (1 - prix_stop)   if prix_stop   is not None else None

            nb_parts      = pos.get("nb_parts") or round(mise / max(prix_part_entree, 0.001), 1)
            pnl_signe     = "+" if pnl_l >= 0 else ""
            val_actuelle  = round(mise + pnl_l, 2) if prix_actuel is not None else None
            val_pct       = round(pnl_l / mise * 100, 1) if mise and prix_actuel is not None else None

            # En-tête de la carte
            if alerte:
                statut_icone = "🎯 OBJECTIF ATTEINT"
            elif stop_loss:
                statut_icone = "🛑 STOP-LOSS"
            elif prix_actuel is not None:
                couleur_pnl = "🟢" if pnl_l >= 0 else "🔴"
                statut_icone = f"{couleur_pnl} {pnl_signe}{val_pct:.1f}%"
            else:
                statut_icone = "⏳ Prix non actualisé"

            with st.expander(
                f"{statut_icone}  |  {'YES' if direction == 'YES' else 'NO'}  |  {question[:70]}",
                expanded=(alerte or stop_loss)
            ):
                # Ligne score + confiance + date
                meta_parts = []
                if score is not None:
                    meta_parts.append(f"Score **{score}/10**")
                if confiance:
                    meta_parts.append(f"Confiance **{confiance}**")
                meta_parts.append(f"Ouvert le **{pos['date_ouverture'][:16].replace('T', ' ')}**")
                st.markdown("  ·  ".join(meta_parts))

                # Raisonnement IA
                if raisonnement:
                    st.markdown(f"> {raisonnement}")

                st.divider()

                # Métriques prix
                cols = st.columns(5)
                cols[0].metric("Mise",         f"{mise:.0f} $")
                cols[1].metric("Entrée",        f"{prix_part_entree*100:.1f}%")
                cols[2].metric("Objectif IA",   f"{prix_part_cible*100:.1f}%",
                               delta=f"{(prix_part_cible - prix_part_entree)*100:+.1f}pts")
                cols[3].metric("Stop-loss",
                               f"{prix_part_stop*100:.1f}%" if prix_part_stop else "—")
                if prix_actuel is not None:
                    cols[4].metric("Prix actuel",
                                   f"{(prix_part_actuel or 0)*100:.1f}%",
                                   delta=f"{pnl_signe}{pnl_l:.2f} $")
                else:
                    cols[4].metric("Prix actuel", "—")

                # P&L visuel
                if val_actuelle is not None:
                    couleur_bg  = "#0a3a0a" if pnl_l >= 0 else "#3a0a0a"
                    couleur_txt = "#00ff88" if pnl_l >= 0 else "#ff6666"
                    icone_pnl   = "📈" if pnl_l >= 0 else "📉"
                    st.markdown(
                        f"""<div style="background:{couleur_bg}; border-radius:8px; padding:12px 18px; margin:10px 0;">
                        <span style="color:#aaa; font-size:0.8em;">VALEUR ACTUELLE</span><br>
                        <span style="color:{couleur_txt}; font-size:1.8em; font-weight:700;">{icone_pnl} {val_actuelle:.2f} $</span>
                        <span style="color:{couleur_txt}; margin-left:10px;">({pnl_signe}{pnl_l:.2f} $ / {pnl_signe}{val_pct:.1f}%)</span>
                        </div>""",
                        unsafe_allow_html=True
                    )

                    # Barre de progression
                    prog_clamped = max(0.0, min(progression / 100, 1.0))
                    couleur_prog = "#00d4aa" if progression >= 0 else "#ff4b4b"
                    st.markdown(f"**Progression vers l'objectif : {progression:.1f}%**")
                    st.progress(prog_clamped)

                # Lien + clôture manuelle
                if pos.get("url"):
                    st.markdown(f"[🔗 Voir sur Polymarket]({pos['url']})")

                st.divider()
                cc1, cc2 = st.columns([2, 1])
                with cc1:
                    val_defaut = round(prix_actuel * 100, 1) if prix_actuel else round(prix_part_cible * 100, 1)
                    val_defaut = max(val_defaut, 0.1)
                    prix_sortie_pct = st.number_input(
                        "Prix de sortie YES (%)", min_value=0.1, max_value=99.0,
                        value=float(val_defaut), step=0.5,
                        key=f"sortie_{pos['id']}",
                        help="Prix YES actuel sur Polymarket"
                    )
                with cc2:
                    st.write("")
                    st.write("")
                    if st.button("💸 Clôturer", key=f"sell_{pos['id']}", type="primary"):
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


# ════════════════════════════════════════════════════════════════════════
# ONGLET 2 — HISTORIQUE
# ════════════════════════════════════════════════════════════════════════

with tab_historique:

    closes = sorted(
        charger_positions("cloture"),
        key=lambda x: x.get("date_cloture", ""), reverse=True
    )
    st.subheader(f"Historique — {len(closes)} positions closes")

    if not closes:
        st.info("Aucune position clôturée pour l'instant.")
    else:
        rows = []
        for p in closes:
            direction = p.get("direction", "YES")
            entree    = p.get("prix_yes_entree") or 0
            sortie    = p.get("prix_yes_sortie") or 0
            pnl_val   = round(p.get("gain_perte") or 0, 2)
            score     = p.get("score")
            rows.append({
                "Résultat"  : "✅" if pnl_val > 0 else "❌",
                "Date"      : (p.get("date_cloture") or "")[:16].replace("T", " "),
                "Dir."      : direction,
                "Score"     : score if score is not None else "—",
                "Question"  : p["question"][:55] + "…",
                "Entrée"    : f"{entree*100:.1f}%",
                "Sortie"    : f"{sortie*100:.1f}%",
                "Mise ($)"  : round(p["mise"], 2),
                "P&L ($)"   : pnl_val,
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


# ════════════════════════════════════════════════════════════════════════
# ONGLET 3 — PERFORMANCE
# ════════════════════════════════════════════════════════════════════════

with tab_performance:

    closes = sorted(
        charger_positions("cloture"),
        key=lambda x: x.get("date_cloture", "")
    )

    if not closes:
        st.info("Aucune position clôturée pour l'instant.")
    else:
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
            xaxis_title=None, yaxis_title="P&L ($)",
            template="plotly_dark", height=320,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        col_pie, col_bar = st.columns(2)

        with col_pie:
            fig2 = go.Figure(go.Pie(
                labels=["Victoires", "Défaites"],
                values=[stats["gagnes"], stats["perdus"]],
                marker_colors=["#00d4aa", "#ff4b4b"],
                hole=0.5, textinfo="label+percent",
            ))
            fig2.update_layout(title="Répartition", template="plotly_dark",
                               height=280, margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        with col_bar:
            df_bar = pd.DataFrame([{
                "Position" : p["question"][:30] + "…",
                "P&L"      : round(p.get("gain_perte") or 0, 2),
                "Résultat" : "gagne" if (p.get("gain_perte") or 0) > 0 else "perdu",
            } for p in closes])

            fig3 = px.bar(
                df_bar, x="P&L", y="Position",
                color="Résultat",
                color_discrete_map={"gagne": "#00d4aa", "perdu": "#ff4b4b"},
                orientation="h", template="plotly_dark",
                title="P&L par position", height=280,
            )
            fig3.update_layout(margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)
