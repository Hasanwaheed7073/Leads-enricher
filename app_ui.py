"""
================================================================================
LEAD SNIPER AI — WEB UI (The Clay Experience)
================================================================================
Responsibility:
    Provide a browser-based, spreadsheet-style interface for the Lead Sniper
    multi-agent pipeline. Users upload a CSV, configure their AI provider,
    and watch leads enrich row-by-row in real-time — exactly like Clay.

Architecture Reference:
    .antigravity_env/agents.md   — Multi-Agent system contract
    .antigravity_env/custom_rules.md — Core directives (Zero-Cost, Self-Healing)

Design Principles (per custom_rules.md):
    - ZERO-COST: Streamlit is free/OSS. No paid UI frameworks.
    - SELF-HEALING: All agent calls wrapped in try/except per-row.
    - SURGICAL: This file handles ONLY the UI layer. No business logic.
    - SELLABLE QUALITY: Premium light SaaS UI, live progress, downloadable output.

Usage:
    streamlit run app_ui.py

Dependencies:
    pip install streamlit pandas requests beautifulsoup4 lxml

Author:     Lead Architect via Antigravity Engine
Version:    3.0.0
================================================================================
"""

import streamlit as st
import pandas as pd
import time
import io
import logging
from datetime import datetime

# ── Agent Imports ─────────────────────────────────────────────────────────────
from agent1_ingestor import LeadIngestor
from agent2_scout import WebScout
from agent3_brain import LeadBrain

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("LEAD_SNIPER_UI")

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG — Must be the FIRST Streamlit call in the script.
# "wide" layout mimics a spreadsheet / Clay-style data table experience.
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lead Sniper AI",
    page_icon="LS",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS — Clean, modern SaaS light theme with navy blue accents.
# Overrides Streamlit's default styling for a professional, polished look.
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── Import premium font ─────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ── Global overrides ────────────────────────────────────────────────── */
    *, html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* ── Main background ─────────────────────────────────────────────────── */
    .stApp {
        background: #f5f7fa !important;
    }

    /* ── Sidebar ─────────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid #e8ecf0 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #0a1628 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown span,
    section[data-testid="stSidebar"] .stMarkdown label {
        color: #4b5563 !important;
    }

    /* ── Sidebar radio nav styling ───────────────────────────────────────── */
    section[data-testid="stSidebar"] .stRadio > div {
        gap: 0 !important;
    }
    section[data-testid="stSidebar"] .stRadio > div > label {
        padding: 0.65rem 1rem !important;
        border-radius: 8px !important;
        margin-bottom: 2px !important;
        font-weight: 500 !important;
        color: #6b7280 !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
    }
    section[data-testid="stSidebar"] .stRadio > div > label:hover {
        background: #f0f4f8 !important;
        color: #0a1628 !important;
    }
    section[data-testid="stSidebar"] .stRadio > div > label[data-checked="true"],
    section[data-testid="stSidebar"] .stRadio > div > label:has(input:checked) {
        background: #eef2f7 !important;
        color: #0a1628 !important;
        font-weight: 600 !important;
    }

    /* ── All headings ────────────────────────────────────────────────────── */
    h1, h2, h3, h4, h5, h6 {
        color: #0a1628 !important;
        font-weight: 700 !important;
    }

    /* ── Body text ───────────────────────────────────────────────────────── */
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        color: #374151 !important;
    }

    /* ── Form and Widget Labels ──────────────────────────────────────────── */
    label,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] span,
    .stTextInput label p,
    .stTextInput label span,
    .stSelectbox label p,
    .stSelectbox label span,
    .stSlider label p,
    .stSlider label span {
        color: #4b5563 !important;
        font-weight: 500 !important;
    }

    /* ── Metric cards (st.metric overrides) ──────────────────────────────── */
    [data-testid="stMetric"],
    [data-testid="metric-container"] {
        background: #ffffff !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
        padding: 20px !important;
        border: 1px solid #e8ecf0 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #6b7280 !important;
    }
    [data-testid="stMetricValue"] {
        color: #0a1628 !important;
        font-weight: 700 !important;
    }

    /* ── Custom metric cards (HTML) ──────────────────────────────────────── */
    .metric-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        flex: 1;
        background: #ffffff;
        border: 1px solid #e8ecf0;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        transition: all 0.25s ease;
    }
    .metric-card:hover {
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        transform: translateY(-2px);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #0a1628;
    }
    .metric-label {
        color: #6b7280;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-top: 0.25rem;
        font-weight: 600;
    }

    /* ── Status badge ────────────────────────────────────────────────────── */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .status-idle { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
    .status-running { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; animation: pulse 2s infinite; }
    .status-complete { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
    .status-error { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    /* ── Section headers ─────────────────────────────────────────────────── */
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #0a1628;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e8ecf0;
        letter-spacing: -0.01em;
    }

    /* ── White card wrapper ──────────────────────────────────────────────── */
    .ui-card {
        background: #ffffff;
        border: 1px solid #e8ecf0;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 1.5rem;
    }
    .ui-card-header {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0a1628;
        margin: 0 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #e8ecf0;
    }

    /* ── Dataframe styling ───────────────────────────────────────────────── */
    .stDataFrame, [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #e8ecf0;
        background: #ffffff;
    }
    /* Header row */
    .stDataFrame [data-testid="stDataFrameResizable"] thead tr th,
    .stDataFrame thead tr th,
    [data-testid="stDataFrame"] thead tr th {
        background: #0a1628 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    /* ── Buttons ─────────────────────────────────────────────────────────── */
    .stButton > button {
        background: #0a1628 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.65rem 2rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 2px 8px rgba(10,22,40,0.15) !important;
    }
    .stButton > button:hover {
        background: #162240 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(10,22,40,0.25) !important;
    }

    /* ── Download button ─────────────────────────────────────────────────── */
    .stDownloadButton > button {
        background: #0a1628 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 8px rgba(10,22,40,0.15) !important;
    }
    .stDownloadButton > button:hover {
        background: #162240 !important;
    }

    /* ── Progress bar ────────────────────────────────────────────────────── */
    .stProgress > div > div {
        background: linear-gradient(90deg, #0a1628 0%, #1e3a5f 50%, #2563eb 100%) !important;
        border-radius: 999px;
    }

    /* ── Input fields ────────────────────────────────────────────────────── */
    .stTextInput input, .stSelectbox select {
        background: #ffffff !important;
        border: 1px solid #d1d5db !important;
        border-radius: 8px !important;
        color: #1f2937 !important;
    }
    .stTextInput input:focus {
        border-color: #0a1628 !important;
        box-shadow: 0 0 0 3px rgba(10,22,40,0.08) !important;
    }

    /* ── File uploader ───────────────────────────────────────────────────── */
    [data-testid="stFileUploader"] {
        border: 2px dashed #c7cdd4 !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        background: #ffffff !important;
        transition: border-color 0.3s ease;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #0a1628 !important;
    }

    /* ── Log container ───────────────────────────────────────────────────── */
    .log-entry {
        font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        font-size: 0.78rem;
        padding: 0.3rem 0;
        color: #6b7280;
        border-bottom: 1px solid #f0f0f0;
    }
    .log-success { color: #16a34a; }
    .log-warning { color: #d97706; }
    .log-error { color: #dc2626; }

    /* ── Toast container ─────────────────────────────────────────────────── */
    .pipeline-toast {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin: 1rem 0;
    }

    /* ── Slider ──────────────────────────────────────────────────────────── */
    .stSlider [data-testid="stThumbValue"],
    .stSlider [data-testid="stTickBarMin"],
    .stSlider [data-testid="stTickBarMax"] {
        color: #374151 !important;
    }

    /* ── Radio group label visibility ───────────────────────────────────── */
    div[role='radiogroup'] label {
        color: #0a1628 !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
    }

    /* ── Hide default Streamlit elements ──────────────────────────────────── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: #f5f7fa !important; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: render_metric_cards
# Displays key pipeline stats as clean white metric cards.
# ──────────────────────────────────────────────────────────────────────────────
def render_metric_cards(total: int, processed: int, avg_score: float, status: str):
    """Renders a row of metric cards with live pipeline stats."""
    status_map = {
        "idle":     ("Idle",       "status-idle"),
        "running":  ("Running",    "status-running"),
        "complete": ("Complete",   "status-complete"),
        "error":    ("Error",      "status-error"),
    }
    status_text, status_class = status_map.get(status, status_map["idle"])

    st.markdown(f"""<div class="metric-row">
<div class="metric-card">
<div class="metric-value">{total}</div>
<div class="metric-label">Total Leads</div>
</div>
<div class="metric-card">
<div class="metric-value">{processed}</div>
<div class="metric-label">Processed</div>
</div>
<div class="metric-card">
<div class="metric-value">{avg_score:.1f}</div>
<div class="metric-label">Avg Score</div>
</div>
<div class="metric-card">
<span class="status-badge {status_class}">{status_text}</span>
<div class="metric-label" style="margin-top: 0.5rem;">Pipeline Status</div>
</div>
</div>""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: convert_df_to_csv
# Converts a pandas DataFrame to a downloadable CSV bytes buffer.
# ──────────────────────────────────────────────────────────────────────────────
def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Exports DataFrame to CSV bytes for the download button."""
    return df.to_csv(index=False).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR — Navigation & Brand
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Logo / Brand ──────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align: center; padding: 1.25rem 0 0.5rem 0;">
        <h2 style="margin: 0.3rem 0 0 0; font-weight: 800; color: #0a1628;">Lead Sniper AI</h2>
        <p style="color: #6b7280; font-size: 0.82rem; margin-top: 0.2rem; font-weight: 400;">
            Autonomous Lead Research Engine
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Navigation ────────────────────────────────────────────────────────────
    nav_selection = st.radio(
        "Navigation",
        options=["📊 Dashboard", "📋 Leads Table", "⚙️ Settings"],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()

    # ── System info ───────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0; color: #9ca3af; font-size: 0.7rem;">
        <p style="margin: 0;">Built by Lead Architect</p>
        <p style="margin: 0.2rem 0 0 0;">v3.0.0 | Zero-Cost | Self-Healing</p>
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# SESSION STATE — Persistent across Streamlit reruns.
# This is the backbone of the two-step workflow. Phase 2 only renders
# after Phase 1 sets `phase1_done = True`.
# ──────────────────────────────────────────────────────────────────────────────
if "qualified_leads" not in st.session_state:
    st.session_state.qualified_leads = []
if "phase1_done" not in st.session_state:
    st.session_state.phase1_done = False
if "phase2_done" not in st.session_state:
    st.session_state.phase2_done = False


# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS STATE — Persist settings across nav pages so they survive reruns.
# ──────────────────────────────────────────────────────────────────────────────
if "api_keys_raw" not in st.session_state:
    st.session_state.api_keys_raw = ""
if "selected_provider" not in st.session_state:
    st.session_state.selected_provider = "Grok (x.ai)"
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = "https://api.x.ai/v1/chat/completions"
if "model_name" not in st.session_state:
    st.session_state.model_name = "llama-3.3-70b-versatile"
if "target_industry" not in st.session_state:
    st.session_state.target_industry = "HVAC Contractors"
if "delay_seconds" not in st.session_state:
    st.session_state.delay_seconds = 2


# ──────────────────────────────────────────────────────────────────────────────
# Provider presets for quick selection.
# ──────────────────────────────────────────────────────────────────────────────
provider_presets = {
    "Grok (x.ai)":       "https://api.x.ai/v1/chat/completions",
    "Groq":              "https://api.groq.com/openai/v1/chat/completions",
    "OpenRouter":        "https://openrouter.ai/api/v1/chat/completions",
    "Together AI":       "https://api.together.xyz/v1/chat/completions",
    "Ollama (Local)":    "http://localhost:11434/v1/chat/completions",
    "Custom":            "",
}


# ──────────────────────────────────────────────────────────────────────────────
# COLUMN CONFIG — Shared across all dataframe renders to stay DRY.
# All enrichment columns are TextColumn to prevent PyArrow type crashes.
# ──────────────────────────────────────────────────────────────────────────────
COLUMN_CONFIG = {
    "Lead_Score": st.column_config.TextColumn("Score", help="AI-generated lead score (1–10)"),
    "Summary":    st.column_config.TextColumn("Summary", help="AI-generated business summary", width="large"),
    "Pitch":      st.column_config.TextColumn("Pitch", help="Personalized outreach email", width="large"),
    "Status":     st.column_config.TextColumn("Status", width="small"),
    "Website":    st.column_config.LinkColumn("Website", width="medium"),
    "Valid":      st.column_config.TextColumn("Valid", width="small"),
}


# ══════════════════════════════════════════════════════════════════════════════
#   SETTINGS PAGE
# ══════════════════════════════════════════════════════════════════════════════
if nav_selection == "⚙️ Settings":
    st.markdown('<h2 style="color: #0a1628; font-weight: 700; margin-bottom: 0.25rem;">Settings</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color: #6b7280; margin-bottom: 1.5rem;">Configure your AI provider, target industry, and pipeline settings.</p>', unsafe_allow_html=True)

    # ── AI Provider Configuration Card ────────────────────────────────────────
    st.markdown('<div class="ui-card"><div class="ui-card-header">AI Provider Configuration</div>', unsafe_allow_html=True)

    st.session_state.api_keys_raw = st.text_input(
        "API Keys (comma-separated for rotation)",
        value=st.session_state.api_keys_raw,
        type="password",
        placeholder="key1, key2, key3",
        help="Enter one or more API keys separated by commas. The engine will auto-rotate on 429 rate limits.",
    )

    st.session_state.selected_provider = st.selectbox(
        "Provider Preset",
        options=list(provider_presets.keys()),
        index=list(provider_presets.keys()).index(st.session_state.selected_provider),
        help="Select a preset or choose 'Custom' to enter your own URL.",
    )

    # Auto-fill the base URL from the selected preset.
    default_url = provider_presets[st.session_state.selected_provider]

    api_base_url_input = st.text_input(
        "API Base URL",
        value=default_url if st.session_state.selected_provider != "Custom" else st.session_state.api_base_url,
        placeholder="https://api.example.com/v1/chat/completions",
        help="Full URL to the OpenAI-compatible /v1/chat/completions endpoint.",
        disabled=(st.session_state.selected_provider != "Custom"),
    )

    # If not custom, always use the preset value (prevents stale state).
    if st.session_state.selected_provider != "Custom":
        st.session_state.api_base_url = default_url
    else:
        st.session_state.api_base_url = api_base_url_input

    st.session_state.model_name = st.text_input(
        "Model Name",
        value=st.session_state.model_name,
        placeholder="e.g., llama-3.3-70b-versatile, grok-3-mini",
        help="Model identifier supported by your chosen provider.",
    )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Qualification Card ────────────────────────────────────────────────────
    st.markdown('<div class="ui-card"><div class="ui-card-header">Qualification Settings</div>', unsafe_allow_html=True)

    st.session_state.target_industry = st.text_input(
        "Target Industry",
        value=st.session_state.target_industry,
        placeholder="e.g., HVAC Contractors, Plumbing, Roofing",
        help="Leads that don't match this industry will be filtered out in Phase 1.",
    )

    st.session_state.delay_seconds = st.slider(
        "Minimum Qualification Score",
        min_value=1,
        max_value=10,
        value=st.session_state.delay_seconds,
        help="Courtesy delay between API calls to respect rate limits.",
    )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Key rotation status ───────────────────────────────────────────────────
    api_keys_parsed = [k.strip() for k in st.session_state.api_keys_raw.split(",") if k.strip()] if st.session_state.api_keys_raw else []
    if api_keys_parsed:
        st.markdown(
            f'<div class="ui-card" style="padding: 14px 20px;">'
            f'<span style="color: #0a1628; font-size: 0.85rem; font-weight: 500;">'
            f'{len(api_keys_parsed)} API key{"s" if len(api_keys_parsed) > 1 else ""} loaded for rotation</span></div>',
            unsafe_allow_html=True,
        )

    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
# RESOLVE SETTINGS — Read from session state for Dashboard & Leads Table pages
# ──────────────────────────────────────────────────────────────────────────────
api_keys_raw = st.session_state.api_keys_raw
api_keys = [k.strip() for k in api_keys_raw.split(",") if k.strip()] if api_keys_raw else []
selected_provider = st.session_state.selected_provider
api_base_url = st.session_state.api_base_url
model_name = st.session_state.model_name
target_industry = st.session_state.target_industry
delay_seconds = st.session_state.delay_seconds


# ══════════════════════════════════════════════════════════════════════════════
#   LEADS TABLE PAGE
# ══════════════════════════════════════════════════════════════════════════════
if nav_selection == "📋 Leads Table":
    st.markdown('<h2 style="color: #0a1628; font-weight: 700; margin-bottom: 0.25rem;">Leads Table</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color: #6b7280; margin-bottom: 1.5rem;">View Phase 1 results and generate personalized pitches.</p>', unsafe_allow_html=True)

    if not st.session_state.phase1_done:
        st.markdown("""<div class="ui-card" style="text-align: center; padding: 3rem 2rem;">
<span style="font-size: 1.5rem; opacity: 0.4; color: #9ca3af;">No data</span>
<h3 style="color: #6b7280; font-weight: 600; margin: 1rem 0 0.5rem 0;">No leads processed yet</h3>
<p style="color: #9ca3af; font-size: 0.9rem; max-width: 450px; margin: 0 auto;">
Head to the <strong>Dashboard</strong> to upload a CSV and run Phase 1 qualification first.
</p>
</div>""", unsafe_allow_html=True)
        st.stop()

    # ── Phase 1 Results DataFrame ─────────────────────────────────────────────
    df = st.session_state.phase1_df.copy()

    phase1_columns = [
        col for col in ["Name", "Email", "Company", "Website", "Valid", "Lead_Score", "Summary", "Status"]
        if col in df.columns
    ]
    phase2_columns = [
        col for col in ["Name", "Email", "Company", "Website", "Lead_Score", "Summary", "Pitch", "Status"]
        if col in df.columns
    ]

    st.markdown('<div class="ui-card"><div class="ui-card-header">Phase 1 — Qualification Results</div>', unsafe_allow_html=True)

    # Live data table placeholder
    table_placeholder = st.empty()

    with table_placeholder.container():
        total_leads = len(df)
        st.dataframe(
            df[phase1_columns],
            use_container_width=True,
            height=min(400 + (total_leads * 10), 800),
            column_config=COLUMN_CONFIG,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Download: Qualified CSV ───────────────────────────────────────────────
    qualified_df = df[df["Valid"] == "Yes"][phase1_columns].copy()
    if not qualified_df.empty:
        csv_bytes_p1 = convert_df_to_csv(qualified_df)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label=f"Download Qualified Leads CSV ({len(qualified_df)} leads)",
            data=csv_bytes_p1,
            file_name=f"qualified_leads_{timestamp}.csv",
            mime="text/csv",
            use_container_width=False,
        )

    # ══════════════════════════════════════════════════════════════════════════
    #   STEP 2: GENERATE PITCHES (only visible after Phase 1)
    # ══════════════════════════════════════════════════════════════════════════

    st.markdown('<div class="section-header">Step 2: Generate Pitches</div>', unsafe_allow_html=True)

    qualified_count_p2 = len(st.session_state.qualified_leads)

    st.markdown(f"""<div class="ui-card" style="padding: 16px 20px;">
<p style="color: #374151; margin: 0; font-size: 0.9rem;">
<b>{qualified_count_p2}</b> qualified leads are ready for pitch generation.
This will make <b>{qualified_count_p2}</b> additional AI calls.
</p>
</div>""", unsafe_allow_html=True)

    col_p1, col_p2, _ = st.columns([1, 1, 3])

    with col_p1:
        pitch_clicked = st.button(
            "Generate Pitches",
            use_container_width=True,
            disabled=(qualified_count_p2 == 0 or not api_keys),
            help="Generate personalized cold email pitches for all qualified leads.",
        )

    # ── PHASE 2 EXECUTION ENGINE ──────────────────────────────────────────────
    if pitch_clicked and api_keys:
        brain = LeadBrain()

        # Restore the Phase 1 dataframe so we can add Pitch to it.
        df = st.session_state.phase1_df.copy()
        total_leads = len(df)

        progress_bar_p2 = st.progress(0, text="Initializing Phase 2...")

        st.markdown('<div class="section-header">Phase 2 — Live Log</div>', unsafe_allow_html=True)
        log_container_p2 = st.container()

        p2_success = 0
        p2_failed  = 0
        run_start_p2 = datetime.now()

        for q_idx, q_lead in enumerate(st.session_state.qualified_leads):
            lead_name = q_lead.get("Name", f"Lead #{q_idx + 1}")
            company   = q_lead.get("Company", "Unknown")
            summary   = q_lead.get("summary", "")
            df_row    = q_lead.get("_df_idx", q_idx)  # Original row index in the full df

            df.at[df_row, "Status"] = "Pitching..."

            with table_placeholder.container():
                st.dataframe(df[phase2_columns], use_container_width=True,
                             height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

            progress_bar_p2.progress(
                q_idx / qualified_count_p2,
                text=f"[{q_idx + 1}/{qualified_count_p2}] Pitching: {company}...",
            )

            try:
                with log_container_p2:
                    st.markdown(
                        f'<div class="log-entry">[{q_idx + 1}/{qualified_count_p2}] '
                        f'Generating pitch for <b>{lead_name}</b> at {company}...</div>',
                        unsafe_allow_html=True,
                    )

                p2_result = brain.generate_pitch(
                    lead_data=q_lead,
                    summary=summary,
                    api_keys=api_keys,
                    api_base_url=api_base_url,
                    model_name=model_name,
                )

                pitch = p2_result.get("pitch", "Error generating pitch.")

                df.at[df_row, "Pitch"]  = pitch
                df.at[df_row, "Status"] = "Pitched"
                p2_success += 1

                with log_container_p2:
                    st.markdown(
                        f'<div class="log-entry log-success">'
                        f'{company} — Pitch: {pitch[:100]}...</div>',
                        unsafe_allow_html=True,
                    )

            except Exception as e:
                df.at[df_row, "Pitch"]  = "Error — see log"
                df.at[df_row, "Status"] = "Pitch Failed"
                p2_failed += 1

                with log_container_p2:
                    st.markdown(
                        f'<div class="log-entry log-error">Pitch failed: {company} — {str(e)[:100]}</div>',
                        unsafe_allow_html=True,
                    )

            # ── Live table update ─────────────────────────────────────────────
            with table_placeholder.container():
                st.dataframe(df[phase2_columns], use_container_width=True,
                             height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

            if q_idx < qualified_count_p2 - 1:
                time.sleep(delay_seconds)

        # ── PHASE 2 COMPLETE ──────────────────────────────────────────────────
        progress_bar_p2.progress(1.0, text="Phase 2 complete")

        elapsed_p2 = datetime.now() - run_start_p2
        elapsed_str_p2 = str(elapsed_p2).split(".")[0]

        st.markdown(f"""<div class="pipeline-toast">
<h3 style="color: #16a34a; margin: 0 0 0.5rem 0; font-size: 1.1rem;">Phase 2 Complete — Pitches Generated</h3>
<p style="color: #6b7280; margin: 0; font-size: 0.9rem;">
<b>{p2_success}</b> pitches generated • <b>{p2_failed}</b> failed •
Duration: <b>{elapsed_str_p2}</b>
</p>
</div>""", unsafe_allow_html=True)

        st.session_state.phase2_done = True

        # ── Download: Final Pitched CSV ───────────────────────────────────────
        final_df = df[df["Valid"] == "Yes"][phase2_columns].copy()
        csv_bytes_p2 = convert_df_to_csv(final_df)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label=f"Download Final Pitched CSV ({p2_success} leads)",
            data=csv_bytes_p2,
            file_name=f"lead_sniper_final_{timestamp}.csv",
            mime="text/csv",
            use_container_width=False,
        )

        logger.info(
            "Phase 2 complete. Pitched: %d | Failed: %d | Time: %s",
            p2_success, p2_failed, elapsed_str_p2,
        )

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
#   DASHBOARD PAGE (default)
# ══════════════════════════════════════════════════════════════════════════════

# ── Hero Header ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="background: #ffffff; border: 1px solid #e8ecf0; border-radius: 16px;
            padding: 2rem 2.5rem; margin-bottom: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    <h1 style="font-size: 2.25rem; font-weight: 800; color: #0a1628;
               margin: 0; letter-spacing: -0.03em;">Lead Sniper AI</h1>
    <p style="color: #6b7280; font-size: 1.05rem; margin-top: 0.3rem; font-weight: 400;">
        Upload leads → Scrape websites → AI scores & pitches → Export enriched CSV.
        All in real-time, row by row.
    </p>
</div>
""", unsafe_allow_html=True)


# ── Metric Cards (pre-enrichment) ────────────────────────────────────────────
metrics_placeholder = st.empty()
with metrics_placeholder.container():
    render_metric_cards(total=0, processed=0, avg_score=0.0, status="idle")


# ── CSV Upload area inside a clean white card ─────────────────────────────────
st.markdown('<div class="ui-card"><div class="ui-card-header">Upload Lead Data</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Upload your leads CSV",
    type=["csv"],
    help="Expected columns: Name, Email, Role, Company, Industry, Location, LinkedIn, Website",
)

st.markdown('</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# STATE: No CSV Uploaded — Show Welcome Screen
# ──────────────────────────────────────────────────────────────────────────────
if not uploaded_file:
    with metrics_placeholder.container():
        render_metric_cards(total=0, processed=0, avg_score=0.0, status="idle")

    st.markdown("""<div class="ui-card" style="text-align: center; padding: 3rem 2rem;">
<h3 style="color: #6b7280; font-weight: 600; margin: 1rem 0 0.5rem 0;">Upload your leads CSV to get started</h3>
<p style="color: #9ca3af; font-size: 0.9rem; max-width: 500px; margin: 0 auto;">
Expected columns: <code style="color: #0a1628; background: #eef2f7; padding: 2px 6px; border-radius: 4px;">Name</code>,
<code style="color: #0a1628; background: #eef2f7; padding: 2px 6px; border-radius: 4px;">Email</code>,
<code style="color: #0a1628; background: #eef2f7; padding: 2px 6px; border-radius: 4px;">Company</code>,
<code style="color: #0a1628; background: #eef2f7; padding: 2px 6px; border-radius: 4px;">Website</code>,
and more. Go to <strong>Settings</strong> to configure your AI provider.
</p>
</div>""", unsafe_allow_html=True)

    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
# STATE: CSV Uploaded — Process and Display
# ──────────────────────────────────────────────────────────────────────────────

# ── AGENT 1: Ingest the uploaded CSV via a temp file ──────────────────────────
import tempfile
import os

temp_dir = tempfile.mkdtemp()
temp_csv_path = os.path.join(temp_dir, "uploaded_leads.csv")

with open(temp_csv_path, "wb") as f:
    f.write(uploaded_file.getvalue())

ingestor = LeadIngestor()
validated_leads = ingestor.ingest_csv(temp_csv_path)

if not validated_leads:
    with metrics_placeholder.container():
        render_metric_cards(total=0, processed=0, avg_score=0.0, status="error")
    st.error(
        "Agent 1 returned zero valid leads. "
        "Ensure your CSV has a 'Website' column with valid URLs (http/https)."
    )
    st.stop()

total_leads = len(validated_leads)

# ── Build the working DataFrame ──────────────────────────────────────────────
df = pd.DataFrame(validated_leads)
df["Lead_Score"] = ""
df["Valid"]      = ""
df["Summary"]    = ""
df["Pitch"]      = ""
df["Status"]     = "Pending"

# ── Display columns for each phase ───────────────────────────────────────────
phase1_columns = [
    col for col in ["Name", "Email", "Company", "Website", "Valid", "Lead_Score", "Summary", "Status"]
    if col in df.columns
]
phase2_columns = [
    col for col in ["Name", "Email", "Company", "Website", "Lead_Score", "Summary", "Pitch", "Status"]
    if col in df.columns
]

# ── Update Metric Cards ──────────────────────────────────────────────────────
with metrics_placeholder.container():
    render_metric_cards(total=total_leads, processed=0, avg_score=0.0, status="idle")

# ── Spreadsheet Header ───────────────────────────────────────────────────────
st.markdown('<div class="section-header">Lead Spreadsheet</div>', unsafe_allow_html=True)

# ── Live Data Table Placeholder ───────────────────────────────────────────────
table_placeholder = st.empty()

with table_placeholder.container():
    st.dataframe(
        df[phase1_columns],
        use_container_width=True,
        height=min(400 + (total_leads * 10), 800),
        column_config=COLUMN_CONFIG,
    )


# ══════════════════════════════════════════════════════════════════════════════
#   STEP 1: QUALIFY & SUMMARIZE
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-header">Step 1: Qualify & Summarize</div>', unsafe_allow_html=True)

col_q1, col_q2, _ = st.columns([1, 1, 3])

with col_q1:
    qualify_clicked = st.button(
        "Start Qualification",
        use_container_width=True,
        disabled=(not api_keys or not target_industry),
        help="Scrapes websites and qualifies each lead against your target industry." if api_keys else "Add API keys in Settings first.",
    )

if not api_keys:
    st.info("Enter your API key(s) in the **Settings** page to enable qualification.")


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 EXECUTION ENGINE
# Runs Agent 2 (scrape) → Agent 3 Phase 1 (qualify_and_summarize) per lead.
# Valid leads accumulate in session_state.qualified_leads for Phase 2.
# ──────────────────────────────────────────────────────────────────────────────
if qualify_clicked and api_keys:
    scout = WebScout()
    brain = LeadBrain()

    progress_bar = st.progress(0, text="Initializing Phase 1...")

    st.markdown('<div class="section-header">Phase 1 — Live Log</div>', unsafe_allow_html=True)
    log_container = st.container()

    processed_count  = 0
    qualified_count  = 0
    disqualified_count = 0
    failed_count     = 0
    total_score      = 0
    run_start        = datetime.now()
    qualified_leads_list = []

    with metrics_placeholder.container():
        render_metric_cards(total=total_leads, processed=0, avg_score=0.0, status="running")

    for idx in range(total_leads):
        lead = validated_leads[idx]
        lead_name = lead.get("Name", f"Lead #{idx + 1}")
        company   = lead.get("Company", "Unknown")
        url       = lead.get("Website", "")

        df.at[idx, "Status"] = "Scraping..."
        with table_placeholder.container():
            st.dataframe(df[phase1_columns], use_container_width=True,
                         height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

        progress_bar.progress(
            idx / total_leads,
            text=f"[{idx + 1}/{total_leads}] Qualifying: {company}...",
        )

        try:
            # ── AGENT 2: Scrape Website ───────────────────────────────────────
            with log_container:
                st.markdown(
                    f'<div class="log-entry">[{idx + 1}/{total_leads}] '
                    f'Scraping <b>{company}</b> — {url}</div>',
                    unsafe_allow_html=True,
                )

            scraped_data = scout.scrape_website(url, email=lead.get("Email", ""), person_name=lead.get("Name", ""))

            if "error" in scraped_data:
                lead["scrape_error"]    = scraped_data["error"]
                lead["scraped_title"]   = None
                lead["scraped_content"] = None
                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-warning">Scrape failed: {scraped_data["error"][:80]}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                lead["scrape_error"]    = None
                lead["scraped_title"]   = scraped_data.get("title")
                lead["scraped_content"] = scraped_data.get("content")
                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-success">Scraped: {scraped_data.get("title", "N/A")}</div>',
                        unsafe_allow_html=True,
                    )

            # ── Merge verification signals into lead dict ─────────────────────
            lead["domain_alive"]         = scraped_data.get("domain_alive", False)
            lead["email_found_on_page"]  = scraped_data.get("email_found_on_page", False)
            lead["email_domain_matches"] = scraped_data.get("email_domain_matches", False)
            lead["person_found_on_page"] = scraped_data.get("person_found_on_page", False)
            lead["person_context"]       = scraped_data.get("person_context", "")

            # ── AGENT 3 — Phase 1: Qualify & Summarize ────────────────────────
            df.at[idx, "Status"] = "Qualifying..."
            with table_placeholder.container():
                st.dataframe(df[phase1_columns], use_container_width=True,
                             height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

            with log_container:
                st.markdown(
                    f'<div class="log-entry">Qualifying <b>{lead_name}</b> against "{target_industry}"...</div>',
                    unsafe_allow_html=True,
                )

            p1_result = brain.qualify_and_summarize(
                lead_data=lead,
                scraped_data=lead,
                target_industry=target_industry,
                api_keys=api_keys,
                api_base_url=api_base_url,
                model_name=model_name,
            )

            is_valid = p1_result.get("is_valid", False)
            score    = p1_result.get("score", 0)
            summary  = p1_result.get("summary", "Error.")

            # Cast all values to str() to prevent PyArrow type crashes.
            df.at[idx, "Valid"]      = "Yes" if is_valid else "No"
            df.at[idx, "Lead_Score"] = str(score)
            df.at[idx, "Summary"]    = summary

            if is_valid:
                df.at[idx, "Status"] = "Qualified"
                qualified_count += 1
                total_score += score

                # Store the enriched lead dict for Phase 2.
                enriched_lead = lead.copy()
                enriched_lead["is_valid"] = True
                enriched_lead["score"]    = score
                enriched_lead["summary"]  = summary
                enriched_lead["_df_idx"]  = idx  # Track original row index
                qualified_leads_list.append(enriched_lead)

                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-success">'
                        f'{company} — QUALIFIED | Score: {score}/10 | {summary[:80]}...</div>',
                        unsafe_allow_html=True,
                    )
            else:
                df.at[idx, "Status"] = "Disqualified"
                disqualified_count += 1

                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-warning">'
                        f'{company} — DISQUALIFIED (not {target_industry}) | {summary[:80]}</div>',
                        unsafe_allow_html=True,
                    )

        except Exception as e:
            df.at[idx, "Lead_Score"] = str(0)
            df.at[idx, "Valid"]      = "Error"
            df.at[idx, "Summary"]    = "Error — see log"
            df.at[idx, "Status"]     = "Failed"
            failed_count += 1

            with log_container:
                st.markdown(
                    f'<div class="log-entry log-error">Failed: {company} — {str(e)[:100]}</div>',
                    unsafe_allow_html=True,
                )

        # ── Update counters & live UI ─────────────────────────────────────────
        processed_count += 1
        current_avg = total_score / qualified_count if qualified_count > 0 else 0.0

        with table_placeholder.container():
            st.dataframe(df[phase1_columns], use_container_width=True,
                         height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

        with metrics_placeholder.container():
            render_metric_cards(
                total=total_leads, processed=processed_count,
                avg_score=current_avg, status="running",
            )

        if idx < total_leads - 1:
            time.sleep(delay_seconds)

    # ── PHASE 1 COMPLETE ──────────────────────────────────────────────────────
    progress_bar.progress(1.0, text="Phase 1 complete")
    scout.close()

    elapsed = datetime.now() - run_start
    elapsed_str = str(elapsed).split(".")[0]
    final_avg = total_score / qualified_count if qualified_count > 0 else 0.0

    with metrics_placeholder.container():
        render_metric_cards(
            total=total_leads, processed=processed_count,
            avg_score=final_avg, status="complete",
        )

    st.markdown(f"""<div class="pipeline-toast">
<h3 style="color: #16a34a; margin: 0 0 0.5rem 0; font-size: 1.1rem;">Phase 1 Complete — Qualification Results</h3>
<p style="color: #6b7280; margin: 0; font-size: 0.9rem;">
<b>{qualified_count}</b> qualified • <b>{disqualified_count}</b> disqualified •
<b>{failed_count}</b> failed •
Avg Score: <b>{final_avg:.1f}/10</b> •
Duration: <b>{elapsed_str}</b>
</p>
</div>""", unsafe_allow_html=True)

    # ── Persist qualified leads to session state ──────────────────────────────
    st.session_state.qualified_leads = qualified_leads_list
    st.session_state.phase1_done     = True
    st.session_state.phase1_df       = df.copy()  # Preserve the P1 dataframe state
    st.session_state.phase2_done     = False       # Reset P2 on new P1 run

    # ── Download checkpoint: Qualified Leads CSV ──────────────────────────────
    qualified_df = df[df["Valid"] == "Yes"][phase1_columns].copy()
    csv_bytes_p1 = convert_df_to_csv(qualified_df)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label=f"Download Qualified Leads CSV ({qualified_count} leads)",
        data=csv_bytes_p1,
        file_name=f"qualified_leads_{timestamp}.csv",
        mime="text/csv",
        use_container_width=False,
    )

    logger.info(
        "Phase 1 complete. Qualified: %d | Disqualified: %d | Failed: %d | Avg: %.1f | Time: %s",
        qualified_count, disqualified_count, failed_count, final_avg, elapsed_str,
    )

    st.info("Phase 1 done! Head to **Leads Table** to view results and generate pitches.")


# ── Cleanup temp file ─────────────────────────────────────────────────────────
try:
    os.remove(temp_csv_path)
    os.rmdir(temp_dir)
except OSError:
    pass
