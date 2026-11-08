"""PL Capital assessment workspace for the portfolio agent."""

import base64
import html
from pathlib import Path

import pandas as pd
import streamlit as st

from jeel_portfolio.agent import PortfolioAgent
from jeel_portfolio.exposure import calculate_exposure
from jeel_portfolio.presentation import LABELS, present_answer


st.set_page_config(page_title="PL Capital | Portfolio Intelligence", page_icon="◈", layout="wide")

# HERO: The official four-part PL Capital mark anchors an original research-desk
# masthead with live snapshot counts and a fine ledger grid.
st.markdown("""<style>
    :root {--blue:#243da8;--navy:#14223c;--ink:#1c2739;--muted:#566277;
           --paper:#f7f8fb;--line:#dbe1ec}
    [data-testid="stApp"] {background:var(--paper);color:var(--ink);
        font-family:"Trebuchet MS","Segoe UI",sans-serif}
    [data-testid="stHeader"] {background:transparent}
    .block-container {max-width:1200px;padding-top:1.5rem;padding-bottom:3rem}
    #MainMenu,footer,[data-testid="stToolbar"] {visibility:hidden}
    .desk-topline {display:flex;align-items:center;justify-content:space-between;
        border-bottom:1px solid var(--line);padding:.35rem 0 1rem;gap:1rem}
    .desk-brand {display:block;flex-shrink:0}
    .desk-brand img {display:block;width:154px;height:auto}
    .desk-topnote {font-size:.68rem;letter-spacing:.15em;font-weight:700;
        color:var(--muted);text-transform:uppercase;text-align:right}
    .desk-hero {margin:1.4rem 0 1.15rem;position:relative;overflow:hidden;
        background:var(--navy);color:#fff;padding:2rem 2.3rem 1.75rem;
        border-left:6px solid var(--blue);animation:desk-arrive .6s ease-out both}
    .desk-hero:after {content:"";position:absolute;inset:0 0 0 48%;opacity:.16;
        background:repeating-linear-gradient(90deg,transparent 0 28px,#c4d1ff 29px 30px),
                   repeating-linear-gradient(0deg,transparent 0 28px,#c4d1ff 29px 30px);
        transform:skewX(-14deg);pointer-events:none}
    .desk-hero > * {position:relative;z-index:1}
    .desk-kicker {font-size:.67rem;letter-spacing:.2em;font-weight:800;
        color:#bbc7ff;text-transform:uppercase;margin-bottom:.55rem}
    .desk-hero h1.desk-title {font-family:Georgia,"Times New Roman",serif!important;
        font-size:clamp(2rem,4vw,3.25rem)!important;line-height:1.08!important;
        letter-spacing:-.055em!important;font-weight:400!important;margin:0 0 .75rem!important}
    .desk-description {font-size:.98rem;line-height:1.6;color:#e0e6f4;max-width:58ch;margin:0}
    .desk-facts {display:flex;gap:2.4rem;flex-wrap:wrap;border-top:1px solid #53617a;
        margin-top:1.75rem;padding-top:1.05rem}
    .desk-fact strong {font-family:Consolas,monospace;font-size:1.25rem;color:#fff}
    .desk-fact span {display:block;color:#c3cce0;font-size:.65rem;text-transform:uppercase;
        letter-spacing:.12em;margin-top:.12rem}
    .desk-section {font-family:Georgia,"Times New Roman",serif;font-size:1.65rem;
        letter-spacing:-.035em;color:var(--navy);margin:.55rem 0 .25rem}
    .desk-subtitle {color:var(--muted);font-size:.88rem;line-height:1.5;margin-bottom:.9rem}
    .desk-rule {border-top:1px solid var(--line);margin:1.2rem 0}
    .desk-foot {border-top:1px solid var(--line);margin-top:2rem;padding-top:.8rem;
        color:var(--muted);font-size:.75rem;line-height:1.5}
    .desk-label {font-size:.66rem;font-weight:800;letter-spacing:.15em;
        text-transform:uppercase;color:var(--blue);margin:1rem 0 .35rem}
    [data-testid="stTabs"] [data-baseweb="tab-list"] {gap:1.5rem;border-bottom:1px solid var(--line)}
    [data-testid="stTabs"] [data-baseweb="tab"] {padding:.75rem .15rem;color:var(--muted)}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] {background:var(--blue);height:3px}
    [data-testid="stTabs"] [data-baseweb="tab-panel"] {padding-top:1.15rem}
    [data-testid="stTextInput"] input {background:#fff;border-radius:3px;min-height:49px;font-size:1rem}
    [data-testid="stButton"] button[kind="primary"] {background:var(--blue);border-radius:3px;
        min-height:45px;font-weight:700;padding:0 1.3rem}
    [data-testid="stButton"] button[kind="primary"]:hover {background:#1b3091}
    [data-testid="stButton"] button[kind="primary"]:disabled {
        background:#cdd6e9;color:#40516d;border-color:#cdd6e9}
    button:focus-visible,input:focus-visible,[role="tab"]:focus-visible,
    a:focus-visible,summary:focus-visible {outline:3px solid #8da5ff!important;outline-offset:2px}
    [data-testid="stMetric"] {background:#fff;border:1px solid var(--line);
        border-top:3px solid var(--blue);padding:.8rem 1rem;min-height:88px}
    [data-testid="stMetricLabel"] {font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}
    [data-testid="stMetricValue"] {font-family:Consolas,monospace;font-size:1.45rem}
    [data-testid="stDataFrame"] {border:1px solid var(--line)}
    [data-testid="stExpander"] {border:1px solid var(--line);border-radius:3px;background:#fff}
    [data-testid="stAlert"] {border-radius:3px}
    [data-testid="stMarkdownContainer"] p {line-height:1.6}
    .answer-panel {background:#fff;border:1px solid var(--line);border-left:5px solid var(--blue);
        padding:1.15rem 1.4rem;margin:.35rem 0 1.15rem;box-shadow:0 8px 24px rgba(20,34,60,.04)}
    .answer-eyebrow {color:var(--blue);font-size:.68rem;letter-spacing:.14em;
        font-weight:800;text-transform:uppercase;margin-bottom:.45rem}
    .answer-main {font-size:clamp(1.15rem,2.2vw,1.55rem);line-height:1.35;color:var(--navy)}
    .answer-context {font-size:.87rem;line-height:1.5;color:var(--muted);margin-top:.55rem}
    .comparison-bars {background:#fff;border:1px solid var(--line);padding:1rem 1.2rem;
        margin:.4rem 0 1.15rem}
    .comparison-title {font-size:.82rem;font-weight:800;color:var(--navy);margin-bottom:.75rem}
    .comparison-row {margin:.6rem 0 .9rem}
    .comparison-label {display:flex;justify-content:space-between;gap:1rem;
        font-size:.82rem;line-height:1.35;color:var(--ink);margin-bottom:.35rem}
    .comparison-label strong {font-variant-numeric:tabular-nums;white-space:nowrap}
    .comparison-track {height:.55rem;background:#e6ebf5;overflow:hidden;border-radius:1rem}
    .comparison-fill {height:100%;background:var(--blue);border-radius:1rem}
    .comparison-row.is-leading .comparison-fill {background:#117c85}
    .comparison-scale {display:flex;justify-content:space-between;font-size:.68rem;color:var(--muted)}
    @keyframes desk-arrive {from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
    @media (prefers-reduced-motion:reduce) {.desk-hero{animation:none}}
    @media (max-width:640px) {.block-container{padding-top:.6rem}
       .desk-hero{padding:1.4rem 1.2rem}.desk-facts{gap:1.2rem}
       .desk-topnote{font-size:.55rem}.desk-brand img{width:125px}}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_agent():
    return PortfolioAgent()


agent = get_agent()
logo_bytes = (Path(__file__).parent / "assets" / "pl-capital.svg").read_bytes()
logo_data = base64.b64encode(logo_bytes).decode("ascii")


def render_percentage_bars(rows, title):
    """Labelled horizontal comparison on a fixed 0–100% scale."""
    if len(rows) < 2:
        return
    parts = [f'<div class="comparison-bars" role="group" aria-label="{html.escape(title, quote=True)}">',
             f'<div class="comparison-title">{html.escape(title)}</div>']
    for index, (label, raw_percent) in enumerate(rows):
        percent = float(raw_percent)
        width = max(0.0, min(100.0, percent))
        parts.append(
            f'<div class="comparison-row{" is-leading" if index == 0 else ""}">'
            f'<div class="comparison-label"><span>{html.escape(str(label))}</span>'
            f'<strong>{percent:,.2f}%</strong></div>'
            f'<div class="comparison-track" aria-hidden="true"><div class="comparison-fill" style="width:{width:.2f}%"></div></div>'
            '</div>'
        )
    parts.append('<div class="comparison-scale" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


st.markdown(f"""
<div class="desk-topline">
  <div class="desk-brand"><img src="data:image/svg+xml;base64,{logo_data}" alt="PL Capital — Prabhudas Lilladher"></div>
  <div class="desk-topnote">AI Engineering Exercise · Portfolio Research</div>
</div>""", unsafe_allow_html=True)
st.markdown(f"""
<div class="desk-hero">
  <div class="desk-kicker">The holdings desk / sample data</div>
  <h1 class="desk-title">Portfolio intelligence,<br>with the workings shown.</h1>
  <p class="desk-description">Ask about holdings, risk, AUM and sector allocation.
     Every answer stays tied to the supplied portfolio snapshot.</p>
  <div class="desk-facts">
    <div class="desk-fact"><strong>{agent.db.counts['portfolios']}</strong><span>Portfolios</span></div>
    <div class="desk-fact"><strong>{agent.db.counts['holdings']}</strong><span>Holdings</span></div>
    <div class="desk-fact"><strong>{agent.db.counts['securities']}</strong><span>Securities</span></div>
    <div class="desk-fact"><strong>{len(agent.db.counts)}</strong><span>Linked tables</span></div>
  </div>
</div>""", unsafe_allow_html=True)

ask, explorer, method = st.tabs(["Ask the desk", "Portfolio explorer", "Method & data"])

with ask:
    st.markdown('<div class="desk-section">Ask a portfolio question</div>', unsafe_allow_html=True)
    st.markdown('<div class="desk-subtitle">Choose a prompt or type a new question. Figures are calculated from the supplied data.</div>', unsafe_allow_html=True)
    examples = [
        "What is the total AUM for portfolios with high target risk level?",
        "Show me the top 5 holdings by cost basis in the Growth Equity Fund",
        "What are the sector exposures for the Tech Innovation Fund?",
        "Which active high-risk portfolio has the highest Technology exposure?",
    ]
    selected = st.selectbox("Suggested question", ["Write my own question", *examples])
    question = st.text_input(
        "Your question", value="" if selected == "Write my own question" else selected,
        placeholder="For example: Which active portfolios hold Technology securities?",
    )
    if st.button("Run analysis", type="primary", disabled=not question.strip()):
        with st.spinner("Working through the portfolio snapshot…"):
            st.session_state.last_result = agent.answer(question)
    result = st.session_state.get("last_result")
    if result and result.get("question") == question:
        st.markdown('<div class="desk-rule"></div><div class="desk-label">Analysis result</div>', unsafe_allow_html=True)
        if result["status"] == "ok" and result.get("tool") == "glossary":
            st.info(result["message"])
        elif result["status"] == "ok":
            lead, context = present_answer(result)
            st.markdown(
                '<div class="answer-panel"><div class="answer-eyebrow">Answer from supplied data</div>'
                f'<div class="answer-main"><strong>{html.escape(lead)}</strong></div>'
                f'<div class="answer-context">{html.escape(context)}</div></div>',
                unsafe_allow_html=True,
            )
            rows = result["rows"]
            if result["tool"] == "hybrid":
                rows = result.get("evidence", {}).get("comparison_rows", rows)
                if len(rows) > 1:
                    sector = result.get("evidence", {}).get("sector", "Sector")
                    render_percentage_bars(rows, f"{sector} exposure across {len(rows)} portfolios · % of recorded weights")
            elif result["tool"] == "exposure_calculator" and len(rows) > 1:
                render_percentage_bars(rows, "Stock-sector allocation · % of recorded weights")
            frame = pd.DataFrame(rows, columns=result["columns"])
            if not frame.empty and not (len(frame) == len(frame.columns) == 1):
                if result["tool"] == "hybrid" and len(rows) > 1:
                    table_area = st.expander("View exact comparison table")
                else:
                    table_area = st.container()
                with table_area:
                    st.dataframe(frame.rename(columns=lambda name: LABELS.get(name, name.replace("_", " ").title())),
                                 width="stretch", hide_index=True)
            if not frame.empty:
                st.download_button("Download CSV", frame.to_csv(index=False), "portfolio_answer.csv", "text/csv")
            with st.expander("View calculation and evidence"):
                st.caption(f"{result['tool'].replace('_', ' ').title()} · {result['route'].replace('_', ' ').title()} · {result['elapsed_ms']:.3f} ms")
                st.json(result.get("evidence", {}))
            for warning in result.get("warnings", []):
                st.warning(warning)
        elif result["status"] == "clarify":
            st.info(result["message"])
        else:
            st.error(result["message"])

with explorer:
    st.markdown('<div class="desk-section">Portfolio explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="desk-subtitle">Move from the portfolio directory to sector allocation and the positions behind it.</div>', unsafe_allow_html=True)
    portfolios = agent.db.query(
        "SELECT portfolio_name,status,target_risk_level,total_aum FROM portfolios ORDER BY portfolio_name"
    )
    st.markdown('<div class="desk-label">Portfolio directory</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(portfolios.rows, columns=portfolios.columns), width="stretch", hide_index=True)
    control_a, control_b = st.columns([2, 1])
    with control_a:
        selected_portfolio = st.selectbox("Portfolio", agent.db.portfolios)
    with control_b:
        basis = st.radio(
            "Percentage basis", ["portfolio", "equity"], horizontal=True,
            help="Portfolio uses supplied weights. Equity renormalizes stock weights only.",
        )
    exposure = calculate_exposure(agent.db, selected_portfolio, basis)
    st.markdown('<div class="desk-label">Stock sector exposure</div>', unsafe_allow_html=True)
    exposure_frame = pd.DataFrame(exposure["rows"], columns=exposure["columns"])
    st.dataframe(exposure_frame.rename(columns={"sector": "Sector", "exposure_pct": "Exposure (%)"}),
                 width="stretch", hide_index=True)
    render_percentage_bars(exposure["rows"], "Stock-sector allocation · % of recorded weights")
    for warning in exposure["warnings"]:
        st.info(warning)
    st.markdown('<div class="desk-label">Positions behind the result</div>', unsafe_allow_html=True)
    holdings = agent.db.query("""SELECT s.symbol,s.company_name,s.asset_type,sec.sector_name,
        h.quantity,h.current_weight,h.cost_basis,s.current_price,
        ROUND(h.quantity*s.current_price,2) AS snapshot_market_value
        FROM holdings h JOIN portfolios p USING(portfolio_id)
        JOIN securities s USING(security_id) LEFT JOIN sectors sec USING(sector_id)
        WHERE p.portfolio_name=:name ORDER BY h.current_weight DESC""", {"name": selected_portfolio})
    st.dataframe(pd.DataFrame(holdings.rows, columns=holdings.columns), width="stretch", hide_index=True)
    st.caption("Snapshot market value = supplied quantity × supplied current price. The files do not provide holding and price timestamps.")

with method:
    st.markdown('<div class="desk-section">How to read the answer</div>', unsafe_allow_html=True)
    st.markdown("""The desk uses a local, parameterized route for common questions. Other questions ask Gemini to plan a guarded SQL or exposure calculation. The database is read only; query output is capped at 500 rows.

**AUM** is read from the supplied portfolio field. **Sector exposure** uses supplied `current_weight` for stocks and excludes bonds. The default percentage is of the whole portfolio; choose “equity” to renormalize stock weights.

This is an assessment snapshot, not live market data. Repeated questions may use the answer cache. Compute time shown beside an answer excludes Streamlit rendering. Inspect the evidence section to see the calculation route and supporting query details.""")
    st.caption(f"Dataset fingerprint: {agent.db.fingerprint[:12]} · Gemini model: {agent.model} · Tables: {len(agent.db.counts)}")

st.markdown('<div class="desk-foot">Independent AI Engineering exercise for PL Capital · Historical sample dataset · Not an official PL Capital service or investment advice.</div>', unsafe_allow_html=True)
