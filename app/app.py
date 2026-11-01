"""
Mumbai Monsoon Risk Calculator — Streamlit edition.

Monte Carlo cost and schedule contingency for construction projects exposed to
the south-west monsoon. Run with:  streamlit run app.py
"""
from __future__ import annotations

import io
import math
import textwrap
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as E
import rainfall_model as RF

# ----------------------------------------------------------------------
# page setup
# ----------------------------------------------------------------------
st.set_page_config(page_title="Monsoon Risk Calculator",
                   page_icon="🌧️", layout="wide",
                   initial_sidebar_state="expanded")

NAVY, ORANGE, RED, GREEN, MUT = "#1F3864", "#C55A11", "#B00020", "#2E7D32", "#6B7280"

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px;}
  h1, h2, h3 {color: #1F3864;}
  [data-testid="stMetricValue"] {font-size: 1.45rem;}
  [data-testid="stMetricLabel"] {font-size: .80rem; color: #6B7280;}
  .readnote {background:#F4F7FB; border-left:3px solid #1F3864; padding:.7rem .9rem;
             border-radius:4px; font-size:.86rem; color:#374151; margin-top:.4rem;}
  .plain {background:#FFF8E7; border-left:3px solid #C55A11; padding:.9rem 1.1rem;
          border-radius:4px; font-size:.95rem; line-height:1.55;}
  .stTabs [data-baseweb="tab"] {font-size: .93rem; padding: .35rem .85rem;}
  @media (prefers-color-scheme: dark) {
    .readnote {background:#1C2433; color:#D5DBE5;}
    .plain {background:#2A2317; color:#EADFC8;}
  }
</style>
""", unsafe_allow_html=True)

PLOT_LAYOUT = dict(
    template="plotly_white", height=340,
    margin=dict(l=55, r=20, t=48, b=48),
    font=dict(family="Georgia, serif", size=12),
    hoverlabel=dict(font_size=12),
)

DEFAULT_ROWS = [
    ("A1",  "Site clearance and enabling works",          18,  12,  "",        0,  1,  4,  0.0, 0.2, 1.0),
    ("A2",  "Excavation, shoring and dewatering",         35,  28,  "A1",      0,  2,  8,  0.0, 0.8, 4.5),
    ("A3",  "PCC, footing reinforcement and shuttering",  29,  55,  "A2",      0,  1,  5,  0.0, 0.8, 4.0),
    ("A4",  "Footing and column RCC up to plinth",        23,  65,  "A3",      0,  2,  6,  0.0, 1.0, 5.0),
    ("A5",  "Backfilling and plinth beam RCC",            21,  32,  "A4",      0,  1,  3,  0.1, 0.8, 4.0),
    ("A6",  "Superstructure RCC, ground to 2nd floor",    70, 150,  "A5",      5, 15, 41,  3.0, 10.0, 30.0),
    ("A7",  "Superstructure RCC, 3rd to 4th and terrace", 53,  95,  "A6",      2,  8, 22,  1.5, 6.0, 20.0),
    ("A8",  "Block masonry, all floors",                  47,  60,  "A7",      0,  1,  2,  0.0, 1.0, 5.0),
    ("A9",  "MEP services, rough-in and fit-out",         42, 110,  "A8",      0,  1,  4,  0.0, 1.0, 5.0),
    ("A10", "External plaster and waterproofing",         41,  65,  "A8",      0,  2,  6,  0.3, 3.0, 14.0),
    ("A11", "Internal plaster, flooring and painting",    64, 163,  "A9;A10",  0,  2,  6,  0.0, 1.5, 8.0),
    ("A12", "External development, paving and drainage",  29,  23,  "A10",     0,  1,  5,  0.0, 0.5, 3.0),
]
COLS = ["id", "name", "duration", "cost", "predecessors",
        "delay_O", "delay_M", "delay_P", "cost_O", "cost_M", "cost_P"]


def default_df() -> pd.DataFrame:
    return pd.DataFrame(DEFAULT_ROWS, columns=COLS)


# ----------------------------------------------------------------------
# state
# ----------------------------------------------------------------------
if "acts_df" not in st.session_state:
    st.session_state.acts_df = default_df()
for k, v in dict(result=None, scenario_label="Typical monsoon", rain_mult=None,
                 ran_once=False, scen=None, tests=None, stab=None).items():
    st.session_state.setdefault(k, v)


def df_to_activities(df: pd.DataFrame):
    acts, bad = [], []
    for i, row in df.reset_index(drop=True).iterrows():
        try:
            pre = str(row["predecessors"] or "").replace(",", ";")
            acts.append(E.Activity(
                id=str(row["id"]).strip(),
                name=str(row["name"] or "").strip(),
                dur=float(row["duration"]), cost=float(row["cost"]),
                pre=[p.strip() for p in pre.split(";") if p.strip()],
                dO=float(row["delay_O"]), dM=float(row["delay_M"]), dP=float(row["delay_P"]),
                cO=float(row["cost_O"]), cM=float(row["cost_M"]), cP=float(row["cost_P"])))
        except (TypeError, ValueError):
            bad.append(f"Row {i+1}: every numeric field must contain a number.")
    return acts, bad


def fmt(x, d=1):
    return f"{x:,.{d}f}"


# ======================================================================
# SIDEBAR — settings
# ======================================================================
with st.sidebar:
    st.markdown("### Project profile")
    start = st.date_input("Planned start date", value=date(2027, 2, 1),
                          help="Decides which stages fall inside June to September. "
                               "This one does change the result.")
    c1, c2 = st.columns(2)
    budget = c1.number_input("Budget (₹ lakh)", min_value=1.0, value=900.0, step=10.0)
    buf = c2.number_input("Time buffer (days)", min_value=0.0, value=30.0, step=5.0)
    area = st.number_input("Built-up area (sq ft)", min_value=0, value=60000, step=1000)
    site = st.selectbox("Site type", ["Normal", "Low-lying or reclaimed",
                                      "Near creek or sea", "Tight plot"], index=1)
    fnd = st.selectbox("Foundation", ["Footing or raft", "Piled"])
    bsmt = st.number_input("Basement levels", min_value=0, max_value=5, value=0)

    st.markdown("### Cost of each extra day")
    st.caption("Only PROJECT-LEVEL costs accruing for each additional completion day; avoid counting activity costs twice. Keep this separate from the activity marginal cost implied by cost_M and delay_M.")
    dc1 = st.number_input("Idle labour wages (₹ L/day)", value=0.2868, format="%.4f", step=0.01)
    dc2 = st.number_input("Equipment rent or standby", value=0.1400, format="%.4f", step=0.01)
    dc3 = st.number_input("Site staff and overheads", value=0.1400, format="%.4f", step=0.01)
    dc4 = st.number_input("Security, power, water, temp works", value=0.0400, format="%.4f", step=0.01)
    dc5 = st.number_input("Contract penalty (LD)", value=0.0000, format="%.4f", step=0.01)
    lc1, lc2 = st.columns(2)
    loan = lc1.number_input("Loan outstanding (₹ L)", min_value=0.0, value=200.0, step=10.0)
    lint = lc2.number_input("Interest (% p.a.)", min_value=0.0, value=9.0, step=0.5)
    interest_day = loan * lint / 100.0 / 365.0
    rate = dc1 + dc2 + dc3 + dc4 + dc5 + interest_day
    st.info(f"Interest works out to ₹{interest_day:.4f} L/day.  \n"
            f"**Total cost of one extra day: ₹{rate:.4f} lakh** (₹{rate*1e5:,.0f}).")

    st.markdown("### Model settings")
    rho = 0.5  # legacy compatibility only; not read by the production rainfall model
    with st.expander("Legacy reference controls (do not affect production simulation)"):
        st.caption("The original PERT engine is retained for historical compatibility tests only. These settings do not affect the rainfall-bootstrap results.")
        st.slider("Legacy correlation ρ (reference only)", 0.0, 0.9, 0.5, 0.05, disabled=True)
        st.radio("Legacy sampling engine (reference only)", ["legacy", "precise"], horizontal=True, disabled=True)
    
    n_iter = st.select_slider("Iterations", [1000, 2500, 5000, 10000, 25000, 50000, 100000],
                              value=10000)
    seed = st.number_input("Random seed", min_value=0, value=42, step=1)
    eng = "PCG64 historical-year bootstrap"  # display/config metadata only
    st.markdown("### Scenario multipliers")
    m1, m2, m3 = st.columns(3)
    m_mild = m1.number_input("Mild", min_value=0.0, value=float(
        st.session_state.rain_mult["mild"]) if st.session_state.rain_mult else 0.60,
        step=0.05, format="%.2f")
    m_typ = m2.number_input("Typical", min_value=0.0, value=1.00, step=0.05, format="%.2f")
    m_sev = m3.number_input("Severe", min_value=0.0, value=float(
        st.session_state.rain_mult["severe"]) if st.session_state.rain_mult else 1.50,
        step=0.05, format="%.2f")
    if st.session_state.rain_mult:
        st.success("Mild and severe were derived from your rainfall file.")

try:
    bundled_rainfall_df = RF.load_and_validate()
    rainfall_df = st.session_state.get("custom_rainfall", bundled_rainfall_df)
    rainfall_source_name = st.session_state.get("custom_rainfall_source", "Bundled historical rainfall CSV")
    historical_rainfall = RF.HistoricalRainfall(rainfall_df)
except Exception as rain_error:
    st.error(f"Historical rainfall dataset rejected: {rain_error}")
    st.stop()

cfg = E.Config(start=start.isoformat(), budget=budget, buf=buf, rate=rate, rho=rho,
               n=int(n_iter), seed=int(seed), m_mild=m_mild, m_typ=m_typ,
               m_sev=m_sev, engine=eng)

# ======================================================================
# HEADER
# ======================================================================
st.title("🌧️ Mumbai Monsoon Risk Calculator")
st.caption("Empirical historical-year rainfall bootstrap with assumption-based construction disruption and CPM Monte Carlo.")

tabs = st.tabs(["Inputs", "Results", "Scenarios", "Validation",
                "Rainfall", "Input guide", "Why rain delays", "Model and trust"])

# ======================================================================
# 1. INPUTS
# ======================================================================
with tabs[0]:
    st.subheader("Construction stages")
    st.markdown(
        "Durations are **positive whole calendar days**; costs are **₹ lakh**. "
        "`delay_M` sets activity sensitivity and `cost_M` sets marginal cost per lost activity day. "
        "O/P fields are retained for legacy reference and do not drive production rainfall results. Separate predecessors with `;`.")

    bc1, bc2, bc3 = st.columns([1, 1, 4])
    if bc1.button("Reset to example", width="stretch"):
        st.session_state.acts_df = default_df()
        st.session_state.result = None
        st.rerun()
    up = bc2.file_uploader("Load CSV", type="csv", label_visibility="collapsed")
    if up is not None:
        try:
            d = pd.read_csv(up)
            missing = [c for c in COLS if c not in d.columns]
            if missing:
                st.error("CSV is missing: " + ", ".join(missing))
            else:
                st.session_state.acts_df = d[COLS].copy()
                st.success(f"Loaded {len(d)} activities.")
        except Exception as ex:
            st.error(f"Could not read that CSV: {ex}")

    edited = st.data_editor(
        st.session_state.acts_df, num_rows="dynamic", width="stretch",
        key="editor", height=460,
        column_config={
            "id": st.column_config.TextColumn("ID", width="small"),
            "name": st.column_config.TextColumn("Activity", width="large"),
            "duration": st.column_config.NumberColumn("Duration (whole calendar days)", min_value=1, step=1, format="%d"),
            "cost": st.column_config.NumberColumn("Cost (₹L)", min_value=0.0, format="%.1f"),
            "predecessors": st.column_config.TextColumn("Predecessors", width="small"),
            "delay_O": st.column_config.NumberColumn("Delay O (legacy)", min_value=0.0, format="%.1f"),
            "delay_M": st.column_config.NumberColumn("Delay M", min_value=0.0, format="%.1f"),
            "delay_P": st.column_config.NumberColumn("Delay P (legacy)", min_value=0.0, format="%.1f"),
            "cost_O": st.column_config.NumberColumn("Cost O (legacy)", min_value=0.0, format="%.1f"),
            "cost_M": st.column_config.NumberColumn("Cost M", min_value=0.0, format="%.1f"),
            "cost_P": st.column_config.NumberColumn("Cost P (legacy)", min_value=0.0, format="%.1f"),
        })
    st.session_state.acts_df = edited

    acts, parse_errors = df_to_activities(edited)
    errors, warnings, order = ([], [], [])
    if parse_errors:
        errors = parse_errors
    elif acts:
        fractional_ids = [a.id for a in acts if not float(a.dur).is_integer() or a.dur <= 0]
        if fractional_ids:
            errors = ["Production rainfall simulation requires positive whole calendar-day durations. Correct: " + ", ".join(fractional_ids)]
        else:
            errors, warnings, order = E.validate(acts, cfg)

    for e in errors:
        st.error(e)
    for w in warnings:
        st.warning(w)

    if not errors and acts:
        fl, cp, base = E.floats_and_critical_path(acts, order)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Baseline duration", f"{base:,.0f} days")
        k2.metric("Baseline activity cost", f"₹{fmt(cfg.base)} L")
        k3.metric("Budget headroom", f"₹{fmt(cfg.head)} L",
                  delta=None if cfg.head >= 0 else "baseline already overruns",
                  delta_color="inverse")
        k4.metric("Critical path", f"{len(cp)} of {len(acts)} activities")

        with st.expander("Network, float and monsoon exposure", expanded=False):
            ex = pd.DataFrame([{
                "ID": a.id, "Activity": a.name,
                "Predecessors": "; ".join(a.pre) or "—",
                "Duration": a.dur, "Float (d)": fl[a.id],
                "On critical path": "Yes" if a.id in cp else "No",
                "Monsoon overlap": "—" if a.exposure is None else f"{a.exposure*100:.0f}%",
            } for a in acts])
            st.dataframe(ex, width="stretch", hide_index=True)
            st.markdown(
                f'<div class="readnote"><b>Critical path:</b> {" → ".join(cp)}. '
                "Activities with float can absorb some delay without moving the finish date. "
                "Where two branches reach a merge with similar float, neither is reliably "
                "critical and only the simulation gets the mean right — see the Validation tab."
                "</div>", unsafe_allow_html=True)

        # profile guidance (does not feed the simulation)
        hints = []
        if area > 0:
            hints.append(f"Baseline cost works out to about **₹{cfg.base*1e5/area:,.0f} per sq ft**. "
                         "Compare with current local rates; if it looks wrong, recheck costs or area.")
        if bsmt > 0 or fnd == "Piled":
            hints.append("Basement or piling: excavation and dewatering are more exposed, so "
                         "consider higher pessimistic values for excavation delay and pumping cost.")
        if site == "Low-lying or reclaimed":
            hints.append("Low-lying or reclaimed site: waterlogging and a high water table worsen "
                         "the pessimistic case. Raise pessimistic delay and dewatering cost.")
        if site == "Near creek or sea":
            hints.append("Near creek or sea: heavy rain at high tide drains slowly, so raise "
                         "pessimistic delay values.")
        if site == "Tight plot":
            hints.append("Tight plot: little room to store materials or divert water, so material "
                         "damage and access problems are more likely.")
        with st.expander("Guidance from the project profile", expanded=False):
            for h in hints:
                st.markdown("- " + h)
            st.caption("These profile fields do not change the simulation by themselves. They "
                       "document the job and help guide delay_M and cost_M assumptions. "
                       "The planned start date is the exception — it does change the result.")

        st.download_button("Download activities.csv",
                           edited.to_csv(index=False).encode(),
                           "activities.csv", "text/csv")

        st.divider()
        if st.button("▶  Run simulation", type="primary", width="stretch"):
            mult = {"Mild monsoon": cfg.m_mild, "Typical monsoon": cfg.m_typ,
                    "Severe monsoon": cfg.m_sev}[st.session_state.scenario_label]
            with st.spinner(f"Running {cfg.n:,} iterations…"):
                st.session_state.result = RF.simulate_rainfall(
                    acts, order, cfg, multiplier=mult, historical=historical_rainfall,
                    label=st.session_state.scenario_label)
            st.session_state.ran_once = True
            st.success("Done — open the **Results** tab.")
        st.session_state.scenario_label = st.radio(
            "Scenario to run", ["Mild monsoon", "Typical monsoon", "Severe monsoon"],
            index=["Mild monsoon", "Typical monsoon", "Severe monsoon"].index(
                st.session_state.scenario_label), horizontal=True)

# ======================================================================
# charts
# ======================================================================
def hist_chart(vals, title, unit, pcts):
    fig = go.Figure()
    fig.add_histogram(x=vals, nbinsx=48, marker_color=NAVY, opacity=.80,
                      name="Simulated", hovertemplate="%{x:.1f}<br>%{y} seasons<extra></extra>")
    for p, lbl in ((.5, "P50"), (.8, "P80"), (.9, "P90")):
        fig.add_vline(x=pcts[p], line=dict(color=RED, dash="dash", width=1.4),
                      annotation_text=f"{lbl} {pcts[p]:,.0f}",
                      annotation_position="top", annotation_font_size=11)
    fig.update_layout(title=title, xaxis_title=unit, yaxis_title="Number of seasons",
                      showlegend=False, bargap=.04, **PLOT_LAYOUT)
    return fig


def cdf_chart(sorted_vals, title, unit, pcts):
    q = np.linspace(0, 1, 301)
    xs = [E.percentile(sorted_vals, float(p)) for p in q]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=q * 100, mode="lines", line=dict(color=NAVY, width=2.4),
                    name="Cumulative", hovertemplate="%{x:.1f} → %{y:.0f}%<extra></extra>")
    for p, lbl in ((.5, "P50"), (.8, "P80"), (.9, "P90")):
        v = pcts[p]
        fig.add_shape(type="line", x0=v, x1=v, y0=0, y1=p * 100,
                      line=dict(color=RED, dash="dot", width=1.2))
        fig.add_shape(type="line", x0=xs[0], x1=v, y0=p * 100, y1=p * 100,
                      line=dict(color=RED, dash="dot", width=1.2))
        fig.add_annotation(x=v, y=p * 100, text=f"{lbl} = {v:,.0f}", showarrow=False,
                           xshift=46, yshift=-12, font=dict(size=11, color=RED))
    fig.update_layout(title=title, xaxis_title=unit,
                      yaxis_title="Chance of being at or below (%)",
                      yaxis_range=[0, 100], showlegend=False, **PLOT_LAYOUT)
    return fig


# ======================================================================
# 2. RESULTS
# ======================================================================
with tabs[1]:
    R = st.session_state.result
    if R is None:
        st.info("Set up the activities on the **Inputs** tab, then press "
                "**Run simulation**.")
    else:
        S = E.summarise(R)
        c = R.cfg
        st.caption(
            f"Scenario **{R.label}** (multiplier ×{R.dm:g}) · {R.n:,} iterations · seed {c.seed} "
            f"· PCG64 historical-year bootstrap · baseline {R.base:,.0f} days / ₹{fmt(c.base)} L "
            f"· budget ₹{fmt(c.budget)} L · headroom ₹{fmt(c.head)} L")

        st.markdown(f"""<div class="plain"><b>In plain words.</b>
        With the {R.label.lower()} assumptions there is an 80% chance the monsoon adds no more
        than <b>₹{fmt(S['cost_p'][.8])} lakh</b> ({S['cost_p'][.8]/c.budget*100:.1f}% of budget)
        and no more than <b>{fmt(S['delay_p'][.8])} days</b>. On average it adds
        ₹{fmt(S['mean_cost'])} lakh and {fmt(S['mean_delay'])} days. The budget holds
        ₹{fmt(max(0, c.head))} lakh of headroom over the activity costs, so the chance of
        exceeding the budget is <b>{S['p_over_budget']*100:.1f}%</b>, and the chance of finishing
        beyond the {c.buf:.0f}-day buffer is <b>{S['p_late']*100:.1f}%</b>.
        These are estimates under your inputs and assumptions, not forecasts.</div>""",
                    unsafe_allow_html=True)

        st.markdown("#### Additional monsoon cost and delay, above the baseline plan")
        g = st.columns(4)
        g[0].metric("P50 additional cost", f"₹{fmt(S['cost_p'][.5])} L")
        g[1].metric("P80 additional cost", f"₹{fmt(S['cost_p'][.8])} L",
                    f"{S['cost_p'][.8]/c.budget*100:.1f}% of budget", delta_color="off")
        g[2].metric("P90 additional cost", f"₹{fmt(S['cost_p'][.9])} L",
                    f"{S['cost_p'][.9]/c.budget*100:.1f}% of budget", delta_color="off")
        g[3].metric("Mean additional cost", f"₹{fmt(S['mean_cost'])} L",
                    f"± {fmt(S['se_cost'], 2)} standard error", delta_color="off")
        g = st.columns(4)
        g[0].metric("P50 additional delay", f"{fmt(S['delay_p'][.5])} d")
        g[1].metric("P80 additional delay", f"{fmt(S['delay_p'][.8])} d")
        g[2].metric("P90 additional delay", f"{fmt(S['delay_p'][.9])} d")
        g[3].metric("Mean additional delay", f"{fmt(S['mean_delay'])} d",
                    f"± {fmt(S['se_delay'], 2)} standard error", delta_color="off")
        g = st.columns(2)
        g[0].metric("Chance total cost exceeds budget", f"{S['p_over_budget']*100:.1f}%",
                    f"above ₹{fmt(max(0, c.head))} L headroom", delta_color="off")
        g[1].metric("Chance of finishing later than plan", f"{S['p_late']*100:.1f}%",
                    f"beyond the {c.buf:.0f}-day buffer", delta_color="off")

        st.markdown("#### Charts and how to read them")
        a, b = st.columns(2)
        with a:
            st.plotly_chart(hist_chart(R.extra, "Additional cost: histogram",
                                       "Additional cost (₹ lakh)", S["cost_p"]),
                            width="stretch")
            st.markdown(
                f'<div class="readnote"><b>How to read this.</b> Each bar counts how many of the '
                f'{R.n:,} simulated seasons ended with extra cost in that range. Half cost less '
                f'than ₹{fmt(S["cost_p"][.5])} L, 80% less than ₹{fmt(S["cost_p"][.8])} L, 90% '
                f'less than ₹{fmt(S["cost_p"][.9])} L. The long right tail is the bad-luck '
                f'seasons, which is why budgeting for the average (₹{fmt(S["mean_cost"])} L) '
                "leaves you exposed: pessimistic estimates sit far above most-likely ones, and "
                "all stages share one monsoon, so a bad season hurts several at once.</div>",
                unsafe_allow_html=True)
        with b:
            st.plotly_chart(cdf_chart(S["e"], "Additional cost: cumulative",
                                      "Additional cost (₹ lakh)", S["cost_p"]),
                            width="stretch")
            st.markdown(
                '<div class="readnote"><b>How to read this.</b> Pick an amount on the bottom '
                "axis, go up to the curve, read the height: that is the chance the extra cost "
                f'lands at or below it. At ₹{fmt(S["cost_p"][.8])} L the curve reads 80%. Steep '
                "sections hold many outcomes, flat sections few. To set a contingency, choose "
                "the confidence you want and read off the amount.</div>",
                unsafe_allow_html=True)

        a, b = st.columns(2)
        with a:
            st.plotly_chart(hist_chart(R.delay, "Additional delay: histogram",
                                       "Additional delay (days)", S["delay_p"]),
                            width="stretch")
            st.markdown(
                '<div class="readnote"><b>How to read this.</b> The same idea for time. A tall '
                "bar near zero would mean the delay is often absorbed by float: a late stage "
                "that is not holding up the finish date does not move completion. Gaps or "
                "bunching come from that schedule logic, not from errors.</div>",
                unsafe_allow_html=True)
        with b:
            st.plotly_chart(cdf_chart(S["d"], "Additional delay: cumulative",
                                      "Additional delay (days)", S["delay_p"]),
                            width="stretch")
            st.markdown(
                f'<div class="readnote"><b>How to read this.</b> The chance of finishing within '
                f'{c.buf:.0f} days of plan is {(1-S["p_late"])*100:.1f}%. To be 80% confident of '
                f'finishing on time, add {fmt(S["delay_p"][.8])} days to the programme.</div>',
                unsafe_allow_html=True)

        st.markdown("#### Contingency at different confidence levels")
        lv = pd.DataFrame([{
            "Confidence": f"P{int(p*100)}",
            "Cost contingency (₹L)": round(S["cost_p"][p], 1),
            "% of budget": f"{S['cost_p'][p]/c.budget*100:.1f}%",
            "Total cost at that level (₹L)": round(c.base + S["cost_p"][p], 1),
            "Time contingency (days)": round(S["delay_p"][p], 1),
        } for p in (.5, .7, .8, .9, .95)])
        st.dataframe(lv, width="stretch", hide_index=True)
        st.caption("Total cost = baseline activity cost + the additional-cost percentile. "
                   "Each row is a percentile of the additional amount, not of the total.")

        st.markdown("#### Test your own contingency")
        t1, t2 = st.columns(2)
        tx = t1.number_input("Cost contingency (₹ lakh)",
                             value=float(round(S["cost_p"][.8], 1)), step=1.0)
        ty = t2.number_input("Time contingency (days)",
                             value=float(round(S["delay_p"][.8])), step=1.0)
        pc_ = float(np.mean(R.extra > tx)) * 100
        pd_ = float(np.mean(R.delay > ty)) * 100
        t1.markdown(f"Chance extra cost exceeds ₹{tx:,.0f} L: **{pc_:.1f}%**")
        t2.markdown(f"Chance delay exceeds {ty:,.0f} days: **{pd_:.1f}%**")

        st.markdown("#### Which activities drive the risk?")
        tot_cost = sum(float(R.act_cost[i].mean()) for i in range(len(R.acts)))
        drv = pd.DataFrame([{
            "Activity": f"{a.id} — {a.name}",
            "Monsoon overlap": "—" if a.exposure is None else f"{a.exposure*100:.0f}%",
            "Mean extra cost (₹L)": round(float(R.act_cost[i].mean()), 2),
            "Share of extra cost": f"{float(R.act_cost[i].mean())/max(tot_cost,1e-9)*100:.1f}%",
            "Mean delay (d)": round(float(R.act_delay[i].mean()), 2),
            "Corr. with project delay": round(float(np.corrcoef(
                R.act_delay[i], R.delay)[0, 1]), 2),
        } for i, a in enumerate(R.acts)]).sort_values(
            "Mean extra cost (₹L)", ascending=False)
        st.dataframe(drv, width="stretch", hide_index=True)

        share = [float(R.act_cost[i].mean()) for i in range(len(R.acts))]
        o = np.argsort(share)
        fig = go.Figure(go.Bar(x=[share[i] for i in o],
                               y=[R.acts[i].id for i in o], orientation="h",
                               marker_color=ORANGE,
                               hovertemplate="%{y}: ₹%{x:.2f} L<extra></extra>"))
        fig.update_layout(title="Mean extra cost by activity (₹ lakh)",
                          xaxis_title="₹ lakh", **PLOT_LAYOUT)
        st.plotly_chart(fig, width="stretch")
        st.markdown(
            '<div class="readnote">Low association with project delay can indicate available schedule float. '
            "It is an indicator, not a full criticality analysis. Concentrate review on activities "
            "with the largest simulated lost days and marginal cost. Production sensitivity uses delay_M; O/P fields are reference-only.</div>", unsafe_allow_html=True)

        buf_out = io.StringIO()
        pd.DataFrame({"additional_cost_lakh": R.extra,
                      "additional_delay_days": R.delay}).to_csv(buf_out, index=False)
        st.download_button("Download the simulated draws (CSV)",
                           buf_out.getvalue().encode(), "simulation_draws.csv", "text/csv")

# ======================================================================
# 3. SCENARIOS
# ======================================================================
with tabs[2]:
    st.subheader("Mild, typical and severe side by side")
    st.caption("Same historical-year bootstrap and activity assumptions at three configurable disruption sensitivity levels.")
    acts2, bad2 = df_to_activities(st.session_state.acts_df)
    if bad2:
        st.error("Fix the input errors on the Inputs tab first.")
    else:
        err2, _, ord2 = E.validate(acts2, cfg)
        if err2:
            st.error("Fix the input errors on the Inputs tab first.")
        elif st.button("Run all three scenarios", type="primary"):
            rows, store = [], {}
            prog = st.progress(0.0)
            for j, (nm, m) in enumerate([("Mild", cfg.m_mild), ("Typical", cfg.m_typ),
                                         ("Severe", cfg.m_sev)]):
                r = RF.simulate_rainfall(acts2, ord2, cfg, multiplier=m, historical=historical_rainfall, label=nm)
                s = E.summarise(r)
                store[nm] = s
                rows.append({
                    "Scenario": f"{nm} (×{m:g})",
                    "Mean cost": round(s["mean_cost"], 1),
                    "P50 cost": round(s["cost_p"][.5], 1),
                    "P80 cost": round(s["cost_p"][.8], 1),
                    "P90 cost": round(s["cost_p"][.9], 1),
                    "Mean delay": round(s["mean_delay"], 1),
                    "P50 delay": round(s["delay_p"][.5], 1),
                    "P80 delay": round(s["delay_p"][.8], 1),
                    "P90 delay": round(s["delay_p"][.9], 1),
                    "P(over budget)": f"{s['p_over_budget']*100:.1f}%",
                    "P(late)": f"{s['p_late']*100:.1f}%",
                })
                prog.progress((j + 1) / 3)
            prog.empty()
            st.session_state.scen = (rows, {k: {"cost_p": v["cost_p"]} for k, v in store.items()})
        if st.session_state.scen:
            rows, store = st.session_state.scen
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.caption("Additional cost in ₹ lakh, additional delay in days.")

            fig = go.Figure()
            for nm, col in (("Mild", "#7FA6D9"), ("Typical", NAVY), ("Severe", ORANGE)):
                fig.add_scatter(
                    x=[store[nm]["cost_p"][p] for p in (.5, .7, .8, .9, .95)],
                    y=[50, 70, 80, 90, 95], mode="lines+markers", name=nm,
                    line=dict(color=col, width=2.2))
            fig.update_layout(title="Cost contingency by confidence level",
                              xaxis_title="Additional cost (₹ lakh)",
                              yaxis_title="Confidence (%)", **PLOT_LAYOUT)
            st.plotly_chart(fig, width="stretch")
            st.markdown(
                '<div class="readnote">Read across at the confidence you need. The gap between '
                "the mild and severe lines is the price of not knowing what kind of monsoon you "
                "will get — often wider than the gap between percentiles within one scenario, "
                "which is why deriving the multipliers from real rainfall matters.</div>",
                unsafe_allow_html=True)

# ======================================================================
# 4. VALIDATION
# ======================================================================
with tabs[3]:
    st.subheader("Does the tool compute what the mathematics says it should?")
    R = st.session_state.result
    if R is None:
        st.info("Run a simulation first, then come back.")
    else:
        st.info("The historical rainfall bootstrap is NOT a PERT-beta draw. The earlier PERT versus hand-calculation comparisons are retained in test_engine.py exclusively for legacy regression; they are not valid checks for the rainfall-driven production model.")
        st.markdown("##### Rainfall-driven model verification")
        st.json({"rainfall_observations":len(rainfall_df), "year_bootstrap": "whole historical year", "mean_delay_days":round(float(R.delay.mean()),3),"mean_cost_lakh":round(float(R.extra.mean()),3), "recomputed_cost_identity": bool(np.allclose(R.extra,R.act_cost.sum(axis=0)+R.delay*R.cfg.rate)), "seed":R.cfg.seed})
        st.caption("Run pytest -q test_rainfall_model.py to execute rainfall-specific invariance and sensitivity checks. Values here are Monte Carlo estimates conditional on assumed activity sensitivity.")
        st.markdown("##### Self-tests")
        st.caption("Legacy PERT/CPM engine compatibility checks only. Production model tests are in test_rainfall_model.py.")
        if st.button("Run self-tests"):
            acts3, _ = df_to_activities(st.session_state.acts_df)
            _, _, ord3 = E.validate(acts3, cfg)
            with st.spinner("Testing…"):
                st.session_state.tests = E.self_tests(acts3, ord3, cfg)
        if st.session_state.tests:
            res = st.session_state.tests
            for t in res:
                (st.success if t["ok"] else st.error)(
                    ("✓ " if t["ok"] else "✗ ") + t["name"])
                if t["detail"]:
                    st.caption("   " + t["detail"])
            nfail = sum(1 for t in res if not t["ok"])
            if nfail:
                st.error(f"{nfail} test(s) failed — do not trust the output until fixed.")
            else:
                st.success(f"All {len(res)} legacy compatibility tests passed (not a validation of the rainfall bootstrap).")

        st.markdown("##### Convergence and seed stability")
        if st.button("Check stability"):
            acts4, _ = df_to_activities(st.session_state.acts_df)
            _, _, ord4 = E.validate(acts4, cfg)
            m = float(R.dm)  # same disruption multiplier as the active result being validated
            rows = []
            for n in (1000, 5000, 10000, 50000):
                s = E.summarise(RF.simulate_rainfall(acts4, ord4, cfg, n=n, seed=7, multiplier=m, historical=historical_rainfall))
                rows.append({"Test": f"n = {n:,}", "P80 cost": round(s["cost_p"][.8], 1),
                             "P80 delay": round(s["delay_p"][.8], 1),
                             "Mean delay": round(s["mean_delay"], 2)})
            for sd in (1, 2, 3, 4, 5):
                s = E.summarise(RF.simulate_rainfall(acts4, ord4, cfg, seed=sd, multiplier=m, historical=historical_rainfall))
                rows.append({"Test": f"seed {sd}", "P80 cost": round(s["cost_p"][.8], 1),
                             "P80 delay": round(s["delay_p"][.8], 1),
                             "Mean delay": round(s["mean_delay"], 2)})
            st.session_state.stab = rows
        if st.session_state.stab:
            sdf = pd.DataFrame(st.session_state.stab)
            st.dataframe(sdf, width="stretch", hide_index=True)
            seeds = sdf[sdf["Test"].str.startswith("seed")]
            st.caption(
                f"Across five seeds, P80 cost spans {seeds['P80 cost'].min():.1f} to "
                f"{seeds['P80 cost'].max():.1f} ₹L and P80 delay "
                f"{seeds['P80 delay'].min():.1f} to {seeds['P80 delay'].max():.1f} days. "
                "Choose iterations so that spread is small next to the decision you are making.")

        st.markdown("##### Three-point (PERT) hand cross-check — course brief, Topic 5")
        st.caption("The course brief asks for simulated means to be compared with hand PERT means. This runs the O/M/P (three-point) engine on the delay_O/M/P and cost_O/M/P columns and compares it with (O + 4M + P) / 6. It checks the three-point engine only; it is separate from the rainfall-driven production result above.")
        if st.button("Run PERT cross-check"):
            acts5, _ = df_to_activities(st.session_state.acts_df)
            _, _, ord5 = E.validate(acts5, cfg)
            sim5 = E.simulate(acts5, ord5, cfg, n=20000, engine="legacy")
            _, cp5, _ = E.floats_and_critical_path(acts5, ord5)
            hand5 = E.hand_pert_project(acts5, cp5, cfg.rho, cfg.rate)
            rows5 = []
            for i, a in enumerate(acts5):
                hd, hc = E.pert_mean(a.dO, a.dM, a.dP), E.pert_mean(a.cO, a.cM, a.cP)
                rows5.append({"Activity": a.id, "Hand PERT delay (d)": round(hd, 3),
                              "Simulated delay (d)": round(float(sim5.act_delay[i].mean()), 3),
                              "Hand PERT cost (₹L)": round(hc, 3),
                              "Simulated cost (₹L)": round(float(sim5.act_cost[i].mean()), 3)})
            st.session_state.pert5 = (rows5, hand5, float(sim5.delay.mean()), float(sim5.extra.mean()))
        if st.session_state.get("pert5"):
            rows5, hand5, sd5, se5 = st.session_state.pert5
            st.dataframe(pd.DataFrame(rows5), width="stretch", hide_index=True)
            st.markdown(f"Project (critical chain hand sum): delay **{hand5['mean_delay']:.2f} d** vs simulated **{sd5:.2f} d**; "
                        f"cost **₹{hand5['mean_cost']:.2f} L** vs simulated **₹{se5:.2f} L**.")
            st.caption("Per-activity means should agree within Monte Carlo noise. The project-level hand sum is a lower bound: parallel branches raise the simulated mean (the maximum of random paths exceeds any single path).")

# ======================================================================
# 5. RAINFALL
# ======================================================================
with tabs[4]:
    st.subheader("Historical IMD rainfall — source and scenario calibration")
    st.caption(f"Production simulation source currently selected: **{rainfall_source_name}**. An uploaded valid replacement is used automatically after upload; otherwise the bundled series is used.")
    diag = RF.diagnostics(rainfall_df, rainfall_source_name)
    diag["selected_source"] = rainfall_source_name
    st.json(diag)
    st.markdown(
        "Upload **complete daily calendar-year** rainfall, not June–September-only extracts. "
        "The CSV must contain exactly `date,rainfall_mm`, use ISO dates (`YYYY-MM-DD`), "
        "include every date from 1 January through 31 December for each year, and contain "
        "at least one complete year. Rainfall is in mm/day. The validator rejects gaps and partial years.")
    thr = st.number_input("Heavy-rain threshold (mm/day)", value=64.5, step=5.0,
                          help="64.5 mm is the IMD 'heavy rainfall' threshold.")
    rf = st.file_uploader("Daily rainfall CSV", type=["csv", "txt"], key="rfup")
    if rf is not None:
        try:
            raw = RF.load_and_validate(rf)
            uploaded_name = getattr(rf, "name", "Uploaded rainfall CSV")
            is_new_upload = (st.session_state.get("custom_rainfall_source") != uploaded_name
                             or not st.session_state.get("custom_rainfall", pd.DataFrame()).equals(raw))
            st.session_state.custom_rainfall = raw
            st.session_state.custom_rainfall_source = uploaded_name
            if is_new_upload:
                st.success(f"Validated custom rainfall selected for production: {uploaded_name}")
                st.rerun()
            g, info = E.rainfall_multipliers(raw, thr)
            if g is not None:
                show = g.copy()
                show["total_mm"] = show["total_mm"].round(0)
                st.dataframe(show.rename(columns={
                    "year": "Year", "total_mm": "Jun–Sep rain (mm)",
                    "heavy_days": f"Days ≥ {thr:g} mm",
                    "days_with_data": "Days with data (of 122)"}),
                    width="stretch", hide_index=True)
                thin = g[g["days_with_data"] < 120]
                if len(thin):
                    st.warning("Years with missing days: "
                               + ", ".join(str(y) for y in thin["year"])
                               + ". Their totals understate the season.")
                fig = go.Figure(go.Bar(x=g["year"].astype(str), y=g["total_mm"],
                                       marker_color=NAVY))
                if isinstance(info, dict):
                    fig.add_hline(y=info["median_mm"], line=dict(color=RED, dash="dash"),
                                  annotation_text="median year")
                fig.update_layout(title="Seasonal rainfall by year",
                                  xaxis_title="Year", yaxis_title="Jun–Sep total (mm)",
                                  **PLOT_LAYOUT)
                st.plotly_chart(fig, width="stretch")
            if isinstance(info, str):
                st.error(info)
            elif isinstance(info, dict):
                st.success(
                    f"Median seasonal total **{info['median_mm']:,.0f} mm** over "
                    f"{info['years']} years. Mild (20th-percentile year) = "
                    f"**×{info['mild']:.2f}**, severe (90th-percentile year) = "
                    f"**×{info['severe']:.2f}**.")
                if st.button("Use these as scenario multipliers", type="primary"):
                    st.session_state.rain_mult = {"mild": info["mild"],
                                                  "severe": info["severe"]}
                    st.rerun()
                st.markdown(
                    '<div class="readnote"><b>Assumption, not a measurement.</b> This takes '
                    "delay and extra cost to scale in proportion to the seasonal total relative "
                    "to the median year. That is a modelling choice, not an observed "
                    "relationship — a season with the same total but concentrated in fewer, "
                    "heavier events would disrupt a site more. With only a handful of years the "
                    "percentiles are rough.</div>", unsafe_allow_html=True)
        except Exception as ex:
            st.error(f"Could not read that file: {ex}")
    else:
        st.info("No new file selected in this interaction. The active source shown above continues to drive the production simulation. Mild/severe multipliers remain explicit scenario assumptions unless derived from a complete historical series.")

# ======================================================================
# 6-8. GUIDANCE
# ======================================================================
with tabs[5]:
    st.subheader("How to set active production inputs")
    st.markdown(textwrap.dedent("""
    **Production inputs.** `delay_M` is the activity's assumed most-likely monsoon delay input
    and is converted into an activity sensitivity factor by the production model. `cost_M` is
    the assumed activity-level additional cost associated with that delay input; the model
    converts it into a marginal cost per simulated lost day. Neither value is trained from
    site data. O/P delay and cost fields remain in the activity editor for legacy/reference
    compatibility and do not influence production rainfall results.

    **A defensible way to choose delay_M**

    1. Work out which calendar months each activity spans, from the planned start date and
       the baseline durations.
    2. Review historical daily rainfall over the actual months the activity is expected to run.
    3. Choose `delay_M` as a transparent, project-specific sensitivity input. The model maps
       it to `min(1, delay_M / (0.35 × duration))`; it is not a measured stoppage probability.
       Higher values increase the activity's assumed response to rainy days.
    4. Choose `cost_M` as the assumed activity-level additional cost associated with the
       delay_M input. The production model converts this to a marginal cost per lost activity
       day using `cost_M / delay_M` when delay_M is positive.

    **Avoid double counting.** Use the sidebar daily rate for project-wide costs accruing
    per additional completion day. `cost_M` is for activity-level marginal cost; do not put
    the same labour, equipment or overhead expense in both places.

    Review higher sensitivity assumptions for excavation and dewatering, concrete pours,
    external plaster and waterproofing, and activities involving a tower crane. Internal
    finishes under a completed slab may warrant lower sensitivity, depending on site conditions.
    """))

with tabs[6]:
    st.subheader("Why rain turns into delay and cost")
    st.markdown(textwrap.dedent("""
    Rain does not stop a site uniformly, which is why a flat percentage fits so badly.

    **Direct stoppage.** Concrete cannot be placed or finished in active rain without risking
    the water–cement ratio and the surface. Excavation in a flooded pit is unsafe and
    unproductive. Crane lifts stop in high wind and poor visibility.

    **Recovery time after the rain stops.** This is the part flat percentages miss. A pit has
    to be pumped out and the softened bottom re-levelled. Compacted backfill that got
    saturated fails density tests and has to be reworked. Access roads churn up. A two-hour
    shower can cost most of a day.

    **Cost that accrues whether or not work happens.** Labour on site still gets paid, or
    worse, migrant crews leave and have to be re-recruited at a premium. Plant hired by the
    month is paid for rain-stopped days. Site staff, security and overheads run on. Interest
    on drawn finance accrues daily.

    **Damage and rework.** Cement sets hard in damp storage. Rebar surface-corrodes. Plywood
    shuttering delaminates. External plaster applied before a wet spell fails and comes off.

    **Why the tail is long.** Two reinforcing effects. Within an activity, pessimistic
    estimates sit far above most-likely ones because bad outcomes compound — a washed-out
    pour needs breaking out, not just redoing. Across activities, every stage shares a single
    monsoon, so a wet historical sequence can affect several activities. In the production
    model this dependence comes from replaying a shared historical rainfall sequence, not from
    the legacy correlation-ρ control.

    **Why float matters.** A stage that is delayed but not holding up the finish date does
    not move completion. That is why the delay distribution can bunch near zero, and why
    activities with large float show weak correlation with project delay in the drivers table.
    """))

with tabs[7]:
    st.subheader("What this model does, and what it cannot do")
    st.markdown(textwrap.dedent("""
    **Production methodology.** The production path uses an empirical historical whole-year
    rainfall bootstrap. Each Monte Carlo replicate samples a historical calendar year with
    PCG64 and replays its observed daily rainfall sequence aligned to the project calendar.
    The supplied historical observations are resampled; no synthetic rainfall distribution
    is fitted and no supervised construction-delay model is trained.

    **Rainfall-to-disruption assumptions.** For activity *i*, sensitivity is
    `min(1, delay_M / (0.35 × duration))`. On each active calendar day, assumed stoppage
    probability is `min(1, rainfall_mm / 64.5 × sensitivity × scenario_multiplier)`.
    A Bernoulli draw determines whether that day is lost. This response curve, its constants,
    and the relationship between `delay_M` and sensitivity are assumptions, not estimates
    learned from construction site records. `delay_M` determines activity sensitivity;
    `cost_M` determines marginal activity cost per lost day. O/P fields are legacy/reference
    inputs and do not drive production rainfall simulation.

    **Schedule and cost propagation.** Activity start dates are dynamically propagated from
    predecessor finish dates. Each activity consumes its positive whole-calendar-day baseline
    duration plus simulated lost days. CPM project completion is the maximum terminal activity
    finish. Additional project delay is simulated completion minus baseline CPM completion.
    Activity-level additional cost is lost activity days multiplied by the assumed marginal
    activity cost (`cost_M / delay_M` where `delay_M > 0`); project-level additional cost is
    project delay multiplied by the configured daily project cost rate. P50, P80 and P90 are
    empirical percentiles of the resulting Monte Carlo outcome distributions.

    **Scenario interpretation.** Mild and severe multipliers are currently calculated from
    historical June–September seasonal rainfall-total quantiles relative to the median seasonal
    total, then applied as scalar multipliers to daily stoppage probabilities. They are not
    direct replays of actual 20th- or 90th-percentile rainfall years and do not preserve the
    corresponding year's daily sequence. This is a transparent scenario scaling assumption;
    the typical case uses multiplier 1.0. No scenario methodology has been silently changed.

    **Randomness and validation.** PCG64 is used for random draws. Fixed seeds make runs
    reproducible for identical inputs, software versions and execution paths. Tests verify
    implementation properties such as zero-rain behaviour, schedule propagation, source
    selection and arithmetic identities. They do not validate the assumed disruption curve
    against real construction outcomes.

    **What this model does not establish.** No supervised construction-delay model has been
    trained; no verified site-level rainfall-to-delay labels were supplied. Construction
    disruption probabilities, sensitivity constants, activity marginal costs and recovery
    behaviour remain assumptions. Monte Carlo percentiles describe the simulated outcome
    distribution under those assumptions, not validated predictive accuracy or confidence
    bounds on future performance. Historical resampling is not a weather forecast.

    **Data provenance.** The supplied processed CSV is structurally validated as a complete
    daily series. Original IMD source provenance, grid extraction and unit conversion have not
    been independently authenticated from the processed CSV alone.

    **Duration convention.** Production activities must use positive whole calendar days.
    This matches the daily rainfall time step and prevents baseline CPM and simulated schedule
    from using inconsistent fractional-day conventions.
    """))
