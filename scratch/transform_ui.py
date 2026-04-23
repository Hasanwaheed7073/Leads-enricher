import os
import re

file_path = "d:\\Leads agents\\app_ui.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace colors for dark mode transition
color_map = {
    "#ffffff": "#0b0f19",
    "#f5f7fa": "#040914",
    "#0a1628": "#ffffff",
    "#6b7280": "#94a3b8",
    "#4b5563": "#cbd5e1",
    "#374151": "#e2e8f0",
    "#e8ecf0": "#1e293b",
    "#eef2f7": "#1e293b",
    "#d1d5db": "#334155",
    "#1f2937": "#f8fafc",
    "#c7cdd4": "#475569"
}

# Apply mappings
for old, new in color_map.items():
    content = content.replace(old, new)
    content = content.replace(old.upper(), new.upper())

# Inject glassmorphism and center uploader text
css_improvements = """
    /* Premium Glassmorphism UI */
    .ui-card {
        background: rgba(11, 15, 25, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2) !important;
    }
    
    [data-testid="stMetric"], [data-testid="metric-container"] {
        background: rgba(11, 15, 25, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15) !important;
    }
    
    section[data-testid="stSidebar"] {
        background: rgba(4, 9, 20, 0.8) !important;
        backdrop-filter: blur(16px) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    
    /* Center the uploader text explicitly */
    [data-testid="stFileUploader"] {
        align-items: center;
        text-align: center;
        border: 2px dashed rgba(255, 255, 255, 0.15) !important;
        background: rgba(0, 0, 0, 0.2) !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
    }
    [data-testid="stFileUploaderDropzone"] > div {
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
"""

content = content.replace("</style>", css_improvements + "\n</style>")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Applied UI transformations for Dark Tech aesthetic and centered Uploader.")
