# app_fantasy.py — Fantasy Draft Buddy (with themed sidebar and a striped table look)

import sqlite3
import pandas as pd
import streamlit as st
from unidecode import unidecode

DB_PATH = "nba.sqlite"  # might make this configurable later

# ---------------- App Setup ----------------
st.set_page_config(page_title="Court Vision (Fantasy Draft Hero)", layout="wide")
st.title("Court Vision — My Fantasy Draft Buddy")
st.markdown(
    "<p style='font-size:18px; color:gray;'>Live Fantasy Draft Helper – Ranked Player Recommendations</p>",
    unsafe_allow_html=True
)

# ---------------- Data Fetching ----------------

@st.cache_data
def get_fantasy_rankings():
    # Could move this logic to a separate module if it gets bigger
    connection = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM fantasy_rankings", connection)
    finally:
        connection.close()

    # normalize names (for easier matching/searching)
    df["display_name"] = df["full_name"].apply(lambda name: unidecode(name or ""))

    # ensure numeric data is actually numeric
    force_numeric = ["score", "pts", "reb", "ast", "stl", "blk", "fg3m", "fg_pct", "ft_pct", "tov", "games", "mp", "rank"]
    for stat in force_numeric:
        if stat in df.columns:
            df[stat] = pd.to_numeric(df[stat], errors="coerce")  # might still get NaNs here

    if "score" in df.columns:
        df = df.sort_values("score", ascending=False)  # best players first
    return df.reset_index(drop=True)


@st.cache_data
def guess_season_label():
    # Just trying to figure out which seasons we’re pulling from
    try:
        conn = sqlite3.connect(DB_PATH)
        all_seasons = pd.read_sql("SELECT DISTINCT season FROM stats", conn)["season"]
        conn.close()
        valid_seasons = all_seasons.dropna().unique().tolist()
        if valid_seasons:
            return " / ".join(sorted(valid_seasons))
    except Exception:
        pass  # shrug
    return "Unknown"

df = get_fantasy_rankings()
season_info = guess_season_label()

# ---------------- Intro Card ----------------
st.markdown(
    f"""
    <div style="
        background-color:#f9fcff;
        border:1px solid #b3daff;
        border-left:6px solid #66b3ff;
        border-radius:12px;
        padding:20px;
        margin-top:10px;
        margin-bottom:20px;
        box-shadow: 0px 2px 6px rgba(0,0,0,0.05);
    ">
    <h3 style="margin-top:0; color:#007acc;">📊 Why I built this</h3>
    <p style="color:#003366;">I <em>suck</em> at fantasy drafts, picking bum players way too high.<br>
    This tool was created so nobody has to feel my pain.</p>

    <h3 style="color:#007acc;">⚙️ What it does</h3>
    <p style="color:#003366;">Filter by position, mark off picked guys, and see who's best left.<br>
    No more scrambling when someone takes your pick.</p>

    <h3 style="color:#007acc;">📐 How it ranks players</h3>
    <ul style="color:#003366;">
      <li>Stats from <b>{season_info}</b> (pull last completed season)</li>
      <li>Standard fantasy categories (per-game)</li>
      <li>Z-scores normalize stats for better comparisons</li>
      <li>Games played gets a boost (we want players that actually play games!)</li>
      <li>Turnovers are punished because… they're evil! 🫠</li>
    </ul>

    <p style="font-size: 14px; color: #555;"><b>Note:</b> rookies won’t show up (they don't have data from last season!).</p>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- Sidebar Stuff ----------------
st.sidebar.markdown(
    """
    <div style="
        background-color:#f9fcff;
        border:1px solid #b3daff;
        border-left:6px solid #66b3ff;
        border-radius:10px;
        padding:14px;
        margin-bottom:16px;
    ">
    <h4 style="margin:0; color:#007acc;">Draft Settings</h4>
    <p style="margin:6px 0 0 0; color:#003366; font-size:14px;">
      Narrow by position, mark picks, and adjust how many names you want to see.
    </p>
    </div>
    """,
    unsafe_allow_html=True
)

# Filter controls
pos_filter = st.sidebar.selectbox("Filter by position", ["All", "Guard", "Forward", "Center"])

# Build accent-insensitive mapping
all_names = df["display_name"].unique().tolist()
picked_display = st.sidebar.multiselect("Already Picked (searchable)", all_names)

# Reverse map to real names
name_map = {unidecode(n): n for n in df["full_name"].dropna().unique()}
picked_real_names = {name_map.get(n, n) for n in picked_display}

# How many to show in the table
num_to_show = st.sidebar.slider("Show top N players", 10, 200, 50, step=10)

# ---------------- Apply Filters ----------------
table_data = df.copy()

if pos_filter != "All":
    # loosely match position strings
    table_data = table_data[table_data["position"].fillna("").str.contains(pos_filter, case=False)]

if picked_real_names:
    table_data = table_data[~table_data["full_name"].isin(picked_real_names)]

# ---------------- Setup Columns ----------------

cols_order = [
    "rank", "full_name", "position", "score",
    "games", "mp",
    "pts", "reb", "ast", "stl", "blk", "fg3m",
    "fg_pct", "ft_pct", "tov"
]

# just in case the columns aren't there
for col in cols_order:
    if col not in table_data.columns:
        table_data[col] = None  # probably won't happen but playing it safe

# Rename for display
final_table = table_data[cols_order].rename(columns={
    "rank": "Rank", "full_name": "Name", "position": "Position", "score": "Score",
    "games": "GP", "mp": "MP", "pts": "PTS", "reb": "REB", "ast": "AST",
    "stl": "STL", "blk": "BLK", "fg3m": "3PM", "fg_pct": "FG %",
    "ft_pct": "FT %", "tov": "TOV"
})

# convert MP to float for formatting
if "MP" in final_table.columns:
    final_table["MP"] = pd.to_numeric(final_table["MP"], errors="coerce")

# small helper to clean GP
if "GP" in final_table.columns:
    final_table["GP"] = pd.to_numeric(final_table["GP"], errors="coerce").fillna(0).astype(int)

# Number formatting per stat
num_fmt = {
    "Score": "{:.1f}",
    "PTS": "{:.0f}", "REB": "{:.0f}", "AST": "{:.0f}",
    "STL": "{:.1f}", "BLK": "{:.1f}",
    "3PM": "{:.1f}",
    "FG %": "{:.0%}", "FT %": "{:.0%}",
    "TOV": "{:.1f}",
    "MP": "{:.0f}",
}

# ---------------- Styling Helpers ----------------

def zebra_stripe(row: pd.Series):
    bg_color = "#f7fbff" if (row.name % 2 == 0) else "#ffffff"
    return [f"background-color: {bg_color}"] * len(row)

preview = final_table.head(num_to_show).reset_index(drop=True)

styled_table = (
    preview.style
    .format(num_fmt)
    .set_table_styles([
        {"selector": "thead th",
         "props": [("background-color", "#f0f8ff"), ("color", "#003366"),
                   ("font-weight", "bold"), ("text-align", "center")]},
        {"selector": "tbody td",
         "props": [("text-align", "center")]},
        {"selector": "table",
         "props": [("margin-left", "auto"), ("margin-right", "auto")]}
    ])
    .apply(zebra_stripe, axis=1)
)

# ---------------- Render Output ----------------
st.subheader("Best Remaining Players")
st.dataframe(styled_table, use_container_width=True, hide_index=True)

# NOTE: Might add ability to export results later
# st.download_button("Export to CSV", ...)
