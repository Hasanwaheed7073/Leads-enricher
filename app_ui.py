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
    - SELLABLE QUALITY: Premium dark UI, live progress, downloadable output.

Usage:
    streamlit run app_ui.py

Dependencies:
    pip install streamlit pandas requests beautifulsoup4 lxml

Author:     Lead Architect via Antigravity Engine
Version:    2.0.0
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
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS — Premium dark theme with glassmorphism accents.
# Overrides Streamlit's default styling for a sellable, polished look.
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
        background: linear-gradient(145deg, #0a0a0f 0%, #0d1117 40%, #111827 100%);
    }

    /* ── Sidebar ─────────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border-right: 1px solid rgba(56, 189, 248, 0.08);
    }
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #e2e8f0 !important;
    }

    /* ── Hero header ─────────────────────────────────────────────────────── */
    .hero-container {
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%);
        border: 1px solid rgba(56, 189, 248, 0.1);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 1.5rem;
        backdrop-filter: blur(20px);
    }
    .hero-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin: 0;
        letter-spacing: -0.03em;
    }
    .hero-subtitle {
        color: #94a3b8;
        font-size: 1.05rem;
        margin-top: 0.3rem;
        font-weight: 400;
    }

    /* ── Metric cards ────────────────────────────────────────────────────── */
    .metric-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        flex: 1;
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(56, 189, 248, 0.1);
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        text-align: center;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        border-color: rgba(56, 189, 248, 0.3);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(56, 189, 248, 0.08);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .metric-label {
        color: #64748b;
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
    .status-idle { background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.2); }
    .status-running { background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); animation: pulse 2s infinite; }
    .status-complete { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.25); }
    .status-error { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.25); }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    /* ── Section headers ─────────────────────────────────────────────────── */
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e2e8f0;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(56, 189, 248, 0.1);
        letter-spacing: -0.01em;
    }

    /* ── Dataframe styling ───────────────────────────────────────────────── */
    .stDataFrame, [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(56, 189, 248, 0.1);
    }

    /* ── Buttons ─────────────────────────────────────────────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 2rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.25) !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(37, 99, 235, 0.35) !important;
    }

    /* ── Download button ─────────────────────────────────────────────────── */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 15px rgba(5, 150, 105, 0.25) !important;
    }

    /* ── Progress bar ────────────────────────────────────────────────────── */
    .stProgress > div > div {
        background: linear-gradient(90deg, #2563eb 0%, #7c3aed 50%, #c084fc 100%) !important;
        border-radius: 999px;
    }

    /* ── Input fields ────────────────────────────────────────────────────── */
    .stTextInput input, .stSelectbox select {
        background: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(56, 189, 248, 0.15) !important;
        border-radius: 8px !important;
        color: #e2e8f0 !important;
    }
    .stTextInput input:focus {
        border-color: rgba(56, 189, 248, 0.4) !important;
        box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.08) !important;
    }

    /* ── File uploader ───────────────────────────────────────────────────── */
    [data-testid="stFileUploader"] {
        border: 2px dashed rgba(56, 189, 248, 0.2) !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        transition: border-color 0.3s ease;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: rgba(56, 189, 248, 0.4) !important;
    }

    /* ── Log container ───────────────────────────────────────────────────── */
    .log-entry {
        font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        font-size: 0.78rem;
        padding: 0.3rem 0;
        color: #94a3b8;
        border-bottom: 1px solid rgba(56, 189, 248, 0.04);
    }
    .log-success { color: #22c55e; }
    .log-warning { color: #f59e0b; }
    .log-error { color: #ef4444; }

    /* ── Toast container ─────────────────────────────────────────────────── */
    .pipeline-toast {
        background: linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%);
        border: 1px solid rgba(34, 197, 94, 0.2);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin: 1rem 0;
    }

    /* ── Hide default Streamlit elements ──────────────────────────────────── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: render_metric_cards
# Displays key pipeline stats as glassmorphic metric cards.
# ──────────────────────────────────────────────────────────────────────────────
def render_metric_cards(total: int, processed: int, avg_score: float, status: str):
    """Renders a row of metric cards with live pipeline stats."""
    status_map = {
        "idle":     ("⏸️ Idle",       "status-idle"),
        "running":  ("⚡ Running",    "status-running"),
        "complete": ("✅ Complete",   "status-complete"),
        "error":    ("❌ Error",      "status-error"),
    }
    status_text, status_class = status_map.get(status, status_map["idle"])

    st.markdown(f"""
    <div class="metric-row">
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
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: convert_df_to_csv
# Converts a pandas DataFrame to a downloadable CSV bytes buffer.
# ──────────────────────────────────────────────────────────────────────────────
def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """Exports DataFrame to CSV bytes for the download button."""
    return df.to_csv(index=False).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR — Configuration Panel
# All API settings and file upload live here to keep the main area for data.
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Logo / Brand ──────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0 0.5rem 0;">
        <span style="font-size: 2.5rem;">🎯</span>
        <h2 style="margin: 0.3rem 0 0 0; font-weight: 800;
                   background: linear-gradient(135deg, #38bdf8, #818cf8);
                   -webkit-background-clip: text;
                   -webkit-text-fill-color: transparent;">Lead Sniper AI</h2>
        <p style="color: #64748b; font-size: 0.8rem; margin-top: 0.2rem;">
            Autonomous Lead Research Engine
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── File Upload ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📄 Lead Data</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Upload your leads CSV",
        type=["csv"],
        help="Expected columns: Name, Email, Role, Company, Industry, Location, LinkedIn, Website",
    )

    st.divider()

    # ── AI Provider Configuration ─────────────────────────────────────────────
    st.markdown('<div class="section-header">🤖 AI Provider</div>', unsafe_allow_html=True)

    api_keys_raw = st.text_input(
        "API Keys (comma-separated for rotation)",
        type="password",
        placeholder="key1, key2, key3",
        help="Enter one or more API keys separated by commas. The engine will auto-rotate on 429 rate limits.",
    )

    # Parse the comma-separated keys into a clean list.
    api_keys = [k.strip() for k in api_keys_raw.split(",") if k.strip()] if api_keys_raw else []

    # Provider presets for quick selection.
    provider_presets = {
        "Grok (x.ai)":       "https://api.x.ai/v1/chat/completions",
        "Groq":              "https://api.groq.com/openai/v1/chat/completions",
        "OpenRouter":        "https://openrouter.ai/api/v1/chat/completions",
        "Together AI":       "https://api.together.xyz/v1/chat/completions",
        "Ollama (Local)":    "http://localhost:11434/v1/chat/completions",
        "Custom":            "",
    }

    selected_provider = st.selectbox(
        "Provider Preset",
        options=list(provider_presets.keys()),
        index=0,
        help="Select a preset or choose 'Custom' to enter your own URL.",
    )

    # Auto-fill the base URL from the selected preset.
    default_url = provider_presets[selected_provider]

    api_base_url = st.text_input(
        "API Base URL",
        value=default_url,
        placeholder="https://api.example.com/v1/chat/completions",
        help="Full URL to the OpenAI-compatible /v1/chat/completions endpoint.",
        disabled=(selected_provider != "Custom"),
    )

    # If not custom, always use the preset value (prevents stale state).
    if selected_provider != "Custom":
        api_base_url = default_url

    model_name = st.text_input(
        "Model Name",
        value="llama-3.3-70b-versatile",
        placeholder="e.g., llama-3.3-70b-versatile, grok-3-mini",
        help="Model identifier supported by your chosen provider.",
    )

    st.divider()

    # ── Target Industry ───────────────────────────────────────────────────────
    st.markdown('<div class="section-header">🏭 Qualification</div>', unsafe_allow_html=True)

    target_industry = st.text_input(
        "Target Industry",
        value="HVAC Contractors",
        placeholder="e.g., HVAC Contractors, Plumbing, Roofing",
        help="Leads that don't match this industry will be filtered out in Phase 1.",
    )

    st.divider()

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">⚙️ Settings</div>', unsafe_allow_html=True)

    delay_seconds = st.slider(
        "Delay between leads (seconds)",
        min_value=1,
        max_value=10,
        value=2,
        help="Courtesy delay between API calls to respect rate limits.",
    )

    # Display key rotation status.
    if api_keys:
        st.markdown(
            f'<div style="color:#38bdf8; font-size:0.75rem; margin-top:0.5rem;">'
            f'🔑 {len(api_keys)} API key{"s" if len(api_keys) > 1 else ""} loaded for rotation</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── System info ───────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0; color: #475569; font-size: 0.7rem;">
        <p style="margin: 0;">Built with ❤️ by Lead Architect</p>
        <p style="margin: 0.2rem 0 0 0;">v2.0.0 • Zero-Cost • Self-Healing</p>
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN CONTENT AREA
# ──────────────────────────────────────────────────────────────────────────────

# ── Hero Header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-container">
    <h1 class="hero-title">Lead Sniper AI</h1>
    <p class="hero-subtitle">
        Upload leads → Scrape websites → AI scores & pitches → Export enriched CSV.
        All in real-time, row by row.
    </p>
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
# COLUMN CONFIG — Shared across all dataframe renders to stay DRY.
# All enrichment columns are TextColumn to prevent PyArrow type crashes.
# ──────────────────────────────────────────────────────────────────────────────
COLUMN_CONFIG = {
    "Lead_Score": st.column_config.TextColumn("🎯 Score", help="AI-generated lead score (1–10)"),
    "Summary":    st.column_config.TextColumn("📝 Summary", help="AI-generated business summary", width="large"),
    "Pitch":      st.column_config.TextColumn("✉️ Pitch", help="Personalized outreach email", width="large"),
    "Status":     st.column_config.TextColumn("Status", width="small"),
    "Website":    st.column_config.LinkColumn("🌐 Website", width="medium"),
    "Valid":      st.column_config.TextColumn("✅ Valid", width="small"),
}


# ──────────────────────────────────────────────────────────────────────────────
# STATE: No CSV Uploaded — Show Welcome Screen
# ──────────────────────────────────────────────────────────────────────────────
if not uploaded_file:
    render_metric_cards(total=0, processed=0, avg_score=0.0, status="idle")

    st.markdown("""
    <div style="text-align: center; padding: 3rem 2rem;
                background: linear-gradient(145deg, rgba(30, 41, 59, 0.3), rgba(15, 23, 42, 0.5));
                border: 1px dashed rgba(56, 189, 248, 0.15);
                border-radius: 16px; margin: 2rem 0;">
        <span style="font-size: 4rem; opacity: 0.5;">📂</span>
        <h3 style="color: #94a3b8; font-weight: 600; margin: 1rem 0 0.5rem 0;">
            Upload your leads CSV to get started
        </h3>
        <p style="color: #64748b; font-size: 0.9rem; max-width: 500px; margin: 0 auto;">
            Expected columns: <code style="color: #38bdf8;">Name</code>,
            <code style="color: #38bdf8;">Email</code>,
            <code style="color: #38bdf8;">Company</code>,
            <code style="color: #38bdf8;">Website</code>,
            and more. Use the sidebar to upload your file and configure your AI provider.
        </p>
    </div>
    """, unsafe_allow_html=True)

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
    render_metric_cards(total=0, processed=0, avg_score=0.0, status="error")
    st.error(
        "⚠️ Agent 1 returned zero valid leads. "
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
df["Status"]     = "⏳ Pending"

# ── Display columns for each phase ───────────────────────────────────────────
phase1_columns = [
    col for col in ["Name", "Email", "Company", "Website", "Valid", "Lead_Score", "Summary", "Status"]
    if col in df.columns
]
phase2_columns = [
    col for col in ["Name", "Email", "Company", "Website", "Lead_Score", "Summary", "Pitch", "Status"]
    if col in df.columns
]

# ── Metric Cards (pre-enrichment) ────────────────────────────────────────────
metrics_placeholder = st.empty()
with metrics_placeholder.container():
    render_metric_cards(total=total_leads, processed=0, avg_score=0.0, status="idle")

# ── Spreadsheet Header ───────────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Lead Spreadsheet</div>', unsafe_allow_html=True)

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

st.markdown('<div class="section-header">🔬 Step 1: Qualify & Summarize</div>', unsafe_allow_html=True)

col_q1, col_q2, _ = st.columns([1, 1, 3])

with col_q1:
    qualify_clicked = st.button(
        "🔬 Start Qualification",
        use_container_width=True,
        disabled=(not api_keys or not target_industry),
        help="Scrapes websites and qualifies each lead against your target industry." if api_keys else "Add API keys in the sidebar first.",
    )

if not api_keys:
    st.info("🔑 Enter your API key(s) in the sidebar to enable qualification.", icon="🔒")


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 EXECUTION ENGINE
# Runs Agent 2 (scrape) → Agent 3 Phase 1 (qualify_and_summarize) per lead.
# Valid leads accumulate in session_state.qualified_leads for Phase 2.
# ──────────────────────────────────────────────────────────────────────────────
if qualify_clicked and api_keys:
    scout = WebScout()
    brain = LeadBrain()

    progress_bar = st.progress(0, text="Initializing Phase 1...")

    st.markdown('<div class="section-header">📋 Phase 1 — Live Log</div>', unsafe_allow_html=True)
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

        df.at[idx, "Status"] = "🔄 Scraping..."
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
                    f'<div class="log-entry">🌐 [{idx + 1}/{total_leads}] '
                    f'Scraping <b>{company}</b> → {url}</div>',
                    unsafe_allow_html=True,
                )

            scraped_data = scout.scrape_website(url)

            if "error" in scraped_data:
                lead["scrape_error"]    = scraped_data["error"]
                lead["scraped_title"]   = None
                lead["scraped_content"] = None
                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-warning">⚠️ Scrape failed: {scraped_data["error"][:80]}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                lead["scrape_error"]    = None
                lead["scraped_title"]   = scraped_data.get("title")
                lead["scraped_content"] = scraped_data.get("content")
                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-success">✅ Scraped: {scraped_data.get("title", "N/A")}</div>',
                        unsafe_allow_html=True,
                    )

            # ── AGENT 3 — Phase 1: Qualify & Summarize ────────────────────────
            df.at[idx, "Status"] = "🧠 Qualifying..."
            with table_placeholder.container():
                st.dataframe(df[phase1_columns], use_container_width=True,
                             height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

            with log_container:
                st.markdown(
                    f'<div class="log-entry">🧠 Qualifying <b>{lead_name}</b> against "{target_industry}"...</div>',
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
            df.at[idx, "Valid"]      = "✅ Yes" if is_valid else "❌ No"
            df.at[idx, "Lead_Score"] = str(score)
            df.at[idx, "Summary"]    = summary

            if is_valid:
                df.at[idx, "Status"] = "✅ Qualified"
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
                        f'🎯 {company} — QUALIFIED | Score: {score}/10 | {summary[:80]}...</div>',
                        unsafe_allow_html=True,
                    )
            else:
                df.at[idx, "Status"] = "⏭️ Disqualified"
                disqualified_count += 1

                with log_container:
                    st.markdown(
                        f'<div class="log-entry log-warning">'
                        f'⏭️ {company} — DISQUALIFIED (not {target_industry}) | {summary[:80]}</div>',
                        unsafe_allow_html=True,
                    )

        except Exception as e:
            df.at[idx, "Lead_Score"] = str(0)
            df.at[idx, "Valid"]      = "❌ Error"
            df.at[idx, "Summary"]    = "Error — see log"
            df.at[idx, "Status"]     = "❌ Failed"
            failed_count += 1

            with log_container:
                st.markdown(
                    f'<div class="log-entry log-error">❌ Failed: {company} — {str(e)[:100]}</div>',
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
    progress_bar.progress(1.0, text="✅ Phase 1 complete!")
    scout.close()

    elapsed = datetime.now() - run_start
    elapsed_str = str(elapsed).split(".")[0]
    final_avg = total_score / qualified_count if qualified_count > 0 else 0.0

    with metrics_placeholder.container():
        render_metric_cards(
            total=total_leads, processed=processed_count,
            avg_score=final_avg, status="complete",
        )

    st.markdown(f"""
    <div class="pipeline-toast">
        <h3 style="color: #22c55e; margin: 0 0 0.5rem 0; font-size: 1.1rem;">
            🔬 Phase 1 Complete — Qualification Results
        </h3>
        <p style="color: #94a3b8; margin: 0; font-size: 0.9rem;">
            <b>{qualified_count}</b> qualified • <b>{disqualified_count}</b> disqualified •
            <b>{failed_count}</b> failed •
            Avg Score: <b>{final_avg:.1f}/10</b> •
            Duration: <b>{elapsed_str}</b>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Persist qualified leads to session state ──────────────────────────────
    st.session_state.qualified_leads = qualified_leads_list
    st.session_state.phase1_done     = True
    st.session_state.phase1_df       = df.copy()  # Preserve the P1 dataframe state
    st.session_state.phase2_done     = False       # Reset P2 on new P1 run

    # ── Download checkpoint: Qualified Leads CSV ──────────────────────────────
    qualified_df = df[df["Valid"] == "✅ Yes"][phase1_columns].copy()
    csv_bytes_p1 = convert_df_to_csv(qualified_df)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label=f"📥 Download Qualified Leads CSV ({qualified_count} leads)",
        data=csv_bytes_p1,
        file_name=f"qualified_leads_{timestamp}.csv",
        mime="text/csv",
        use_container_width=False,
    )

    logger.info(
        "Phase 1 complete. Qualified: %d | Disqualified: %d | Failed: %d | Avg: %.1f | Time: %s",
        qualified_count, disqualified_count, failed_count, final_avg, elapsed_str,
    )


# ══════════════════════════════════════════════════════════════════════════════
#   STEP 2: GENERATE PITCHES (only visible after Phase 1)
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.phase1_done:
    st.markdown('<div class="section-header">✉️ Step 2: Generate Pitches</div>', unsafe_allow_html=True)

    qualified_count_p2 = len(st.session_state.qualified_leads)

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(56, 189, 248, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%);
                border: 1px solid rgba(56, 189, 248, 0.1); border-radius: 12px;
                padding: 1rem 1.5rem; margin-bottom: 1rem;">
        <p style="color: #94a3b8; margin: 0; font-size: 0.9rem;">
            ✅ <b>{qualified_count_p2}</b> qualified leads are ready for pitch generation.
            This will make <b>{qualified_count_p2}</b> additional AI calls.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_p1, col_p2, _ = st.columns([1, 1, 3])

    with col_p1:
        pitch_clicked = st.button(
            "✉️ Generate Pitches",
            use_container_width=True,
            disabled=(qualified_count_p2 == 0 or not api_keys),
            help="Generate personalized cold email pitches for all qualified leads.",
        )

    # ── PHASE 2 EXECUTION ENGINE ──────────────────────────────────────────────
    if pitch_clicked and api_keys:
        brain = LeadBrain()

        # Restore the Phase 1 dataframe so we can add Pitch to it.
        df = st.session_state.phase1_df.copy()

        progress_bar_p2 = st.progress(0, text="Initializing Phase 2...")

        st.markdown('<div class="section-header">📋 Phase 2 — Live Log</div>', unsafe_allow_html=True)
        log_container_p2 = st.container()

        p2_success = 0
        p2_failed  = 0
        run_start_p2 = datetime.now()

        for q_idx, q_lead in enumerate(st.session_state.qualified_leads):
            lead_name = q_lead.get("Name", f"Lead #{q_idx + 1}")
            company   = q_lead.get("Company", "Unknown")
            summary   = q_lead.get("summary", "")
            df_row    = q_lead.get("_df_idx", q_idx)  # Original row index in the full df

            df.at[df_row, "Status"] = "✉️ Pitching..."

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
                        f'<div class="log-entry">✉️ [{q_idx + 1}/{qualified_count_p2}] '
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
                df.at[df_row, "Status"] = "✅ Pitched"
                p2_success += 1

                with log_container_p2:
                    st.markdown(
                        f'<div class="log-entry log-success">'
                        f'✅ {company} — Pitch: {pitch[:100]}...</div>',
                        unsafe_allow_html=True,
                    )

            except Exception as e:
                df.at[df_row, "Pitch"]  = "Error — see log"
                df.at[df_row, "Status"] = "❌ Pitch Failed"
                p2_failed += 1

                with log_container_p2:
                    st.markdown(
                        f'<div class="log-entry log-error">❌ Pitch failed: {company} — {str(e)[:100]}</div>',
                        unsafe_allow_html=True,
                    )

            # ── Live table update ─────────────────────────────────────────────
            with table_placeholder.container():
                st.dataframe(df[phase2_columns], use_container_width=True,
                             height=min(400 + (total_leads * 10), 800), column_config=COLUMN_CONFIG)

            if q_idx < qualified_count_p2 - 1:
                time.sleep(delay_seconds)

        # ── PHASE 2 COMPLETE ──────────────────────────────────────────────────
        progress_bar_p2.progress(1.0, text="✅ Phase 2 complete!")

        elapsed_p2 = datetime.now() - run_start_p2
        elapsed_str_p2 = str(elapsed_p2).split(".")[0]

        st.markdown(f"""
        <div class="pipeline-toast">
            <h3 style="color: #22c55e; margin: 0 0 0.5rem 0; font-size: 1.1rem;">
                ✉️ Phase 2 Complete — Pitches Generated
            </h3>
            <p style="color: #94a3b8; margin: 0; font-size: 0.9rem;">
                <b>{p2_success}</b> pitches generated • <b>{p2_failed}</b> failed •
                Duration: <b>{elapsed_str_p2}</b>
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.session_state.phase2_done = True

        # ── Download: Final Pitched CSV ───────────────────────────────────────
        final_df = df[df["Valid"] == "✅ Yes"][phase2_columns].copy()
        csv_bytes_p2 = convert_df_to_csv(final_df)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label=f"📥 Download Final Pitched CSV ({p2_success} leads)",
            data=csv_bytes_p2,
            file_name=f"lead_sniper_final_{timestamp}.csv",
            mime="text/csv",
            use_container_width=False,
        )

        logger.info(
            "Phase 2 complete. Pitched: %d | Failed: %d | Time: %s",
            p2_success, p2_failed, elapsed_str_p2,
        )


# ── Cleanup temp file ─────────────────────────────────────────────────────────
try:
    os.remove(temp_csv_path)
    os.rmdir(temp_dir)
except OSError:
    pass
