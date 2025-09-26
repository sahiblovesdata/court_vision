# app_fantasy.py — My Personal Fantasy Draft Helper

import os
import sqlite3
import pandas as pd
import streamlit as st
from unidecode import unidecode  # for cleaning names (accents mess up searching)

# Keeping it relative so it'll work on Streamlit Cloud too
DB_PATH = "nba.sqlite"

# --- Streamlit setup ---
st.set_page_config(page_title="Court Vision (Fantasy Draft Hero)", layout="wide")
st.title("Court Vision — My Fantasy Draft Buddy")

st.markdown(
    "<p style='font-size:18px; color:gray;'>Live Fantasy Draft Helper – Ranked Player Recommendations</p>",
    unsafe_allow_html=True
)

# --- Load rankings from the local SQLite DB ---
@st.cache_data
def load_player_rankings(db_file: str):
    if not os.path.exists(db_file):
        st.error(f"Can't find DB at '{db_file}'. Did you forget to add it?")
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(db_file)
        df = pd.read_sql("SELECT * FROM fantasy_rankings", conn)
    except Exception as err:
        st.error(f"Ugh... failed to read from the database: {err}")
        return pd.DataFrame()
    finally:
        try:
            conn.close()
        except:
            pass  # meh, already done

    # Sometimes the columns are missing? Just pad them.
    for col in ["full_name", "position"]:
        if col not in df.columns:
            df[col] = ""

    # Add a cleaned-up version of the name for easier filtering/searching
    df["display_name"] = df["full_name"].fillna("").apply(unidecode)

    # Coerce numeric stats into real numbers (SQLite is weird about types)
    stat_cols = [
        "score", "pts", "reb", "ast", "stl", "blk", "fg3m",
        "fg_pct", "ft_pct", "tov", "games", "mp", "rank"
    ]
    for stat in stat_cols:
        if stat in df.columns:
            df[stat] = pd.to_numeric(df[stat], errors="coerce")

    # Highest score = better, so descending sort
    if "score" in df.columns:
        df = df.sort_values("score", ascending=False)

    return df.reset_index(drop=True)


@st.cache_data
def find_season_info(db_file: str):
    if not os.path.exists(db_file):
        return "Unknown"

    try:
        conn = sqlite3.connect(db_file)
        seasons = pd.read_sql("SELECT DISTINCT season FROM stats", conn)
        conn.close()
        season_vals = seasons["season"].dropna().unique().tolist()
        return " / ".join(sorted(map(str, season_vals))) if season_vals else "Unknown"
    except:
        return "Unknown"


# --- Data load ---
rankings_df = load_player_rankings(DB_PATH)
season_label = find_season_info(DB_PATH)

# Bail early so the page doesn't render half-broken
if rankings_df.empty:
    st.stop()


# --- Intro Card ---
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
    <p style="color:#003366;">I'm trash at fantasy drafts. Always reach for guys who underperform.<br>
    This tool keeps me from panicking during live picks.</p>

    <h3 style="color:#007acc;">⚙️ What it does</h3>
    <p style="color:#003366;">Lets you filter by position, track picked players, and sort by rankings.</p>

    <h3 style="color:#007acc;">📐 How rankings are calculated</h3>
    <ul style="color:#003366;">
      <li>Data from: <b>{season_label}</b> (should be most recent full season)</li>
      <li>Standard fantasy stats (per-game basis)</li>
      <li>Z-scores for better cross-category balance</li>
      <li>Bonus for games played (availability matters!)</li>
      <li>Turnovers = bad (just... don't draft Westbrook 😅)</li>
    </ul>

    <p style="font-size: 14px; color: #555;"><b>Heads-up:</b> Rookies won't appear since there's no past data for them.</p>
    </div>
    """,
    unsafe_allow_html=True
)

# --- Sidebar ---
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
      Filter by position, mark off who’s gone, and limit how many players to show.
    </p>
    </div>
    """,
    unsafe_allow_html=True
)

pos_choice = st.sidebar.selectbox("Filter by position", ["All", "Guard", "Forward", "Center"])
table_type = st.sidebar.radio("View mode", ["Interactive grid", "Styled (static)"])

# Player picker – use cleaned names to search easily
searchable_names = rankings_df["display_name"].dropna().unique().tolist()
already_picked = st.sidebar.multiselect("Already Picked (search)", searchable_names)

# Map back to actual names (for filtering)
name_map = {unidecode(n): n for n in rankings_df["full_name"].dropna().unique()}
picked_names = {name_map.get(name, name) for name in already_picked}

top_n = st.sidebar.slider("Top N players to show", 10, 200, 50, step=10)


# --- Apply filters ---
filtered_df = rankings_df.copy()

if pos_choice != "All":
    filtered_df["position"] = filtered_df["position"].fillna("").astype(str)
    filtered_df = filtered_df[filtered_df["position"].str.contains(pos_choice, case=False)]

if picked_names:
    filtered_df = filtered_df[~filtered_df["full_name"].isin(picked_names)]

# --- Reorganize columns ---
columns_in_order = [
    "rank", "full_name", "position", "score", "games", "mp",
    "pts", "reb", "ast", "stl", "blk", "fg3m",
    "fg_pct", "ft_pct", "tov"
]

for col in columns_in_order:
    if col not in filtered_df.columns:
        filtered_df[col] = pd.NA  # if it's missing, fill it with blanks

renamed_cols = {
    "rank": "Rank", "full_name": "Name", "position": "Position", "score": "Score",
    "games": "GP", "mp": "MP", "pts": "PTS", "reb": "REB", "ast": "AST",
    "stl": "STL", "blk": "BLK", "fg3m": "3PM", "fg_pct": "FG %",
    "ft_pct": "FT %", "tov": "TOV"
}

display_table = filtered_df[columns_in_order].rename(columns=renamed_cols)

# Coerce again just in case
for col in display_table.columns:
    display_table[col] = pd.to_numeric(display_table[col], errors="ignore")

# Format numbers – some unnecessary overkill here, but it's fine
num_formatting = {
    "Score": "{:.1f}", "PTS": "{:.0f}", "REB": "{:.0f}", "AST": "{:.0f}",
    "STL": "{:.1f}", "BLK": "{:.1f}", "3PM": "{:.1f}",
    "FG %": "{:.0%}", "FT %": "{:.0%}", "TOV": "{:.1f}", "MP": "{:.0f}"
}

top_players = display_table.head(top_n).reset_index(drop=True)


# --- Output table ---
st.subheader("Best Remaining Players")

if top_players.empty:
    st.warning("Hmm, no data to display. Check filters or if the DB has the right stuff.")
else:
    if table_type == "Interactive grid":
        st.dataframe(top_players, use_container_width=True, hide_index=True)
    else:
        # Static styled table (kinda hacky but looks nice)
        def alt_row_color(row):
            bg = "#f7fbff" if row.name % 2 == 0 else "#ffffff"
            return [f"background-color: {bg}"] * len(row)

        styled_df = (
            top_players.style
            .format(num_formatting)
            .set_table_styles([
                {"selector": "thead th", "props": [("background-color", "#f0f8ff"), ("color", "#003366"),
                                                   ("font-weight", "bold"), ("text-align", "center")]},
                {"selector": "tbody td", "props": [("text-align", "center")]},
                {"selector": "table", "props": [("margin-left", "auto"), ("margin-right", "auto")]}
            ])
            .apply(alt_row_color, axis=1)
        )

        st.markdown(styled_df.to_html(), unsafe_allow_html=True)

# --- Debug dump (expandable) ---
with st.expander("Debug info"):
    st.write({"rows": len(top_players), "columns": list(top_players.columns)})
    st.dataframe(top_players.head(5), use_container_width=True, hide_index=True)
