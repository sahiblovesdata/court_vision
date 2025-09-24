# src/fantasy.py
import sqlite3
import numpy as np
import pandas as pd

# Database file — should already exist from the ETL phase
DB_PATH = "nba.sqlite"

# Standard 9-category scoring — typical for roto/points leagues
CATEGORIES = ["pts", "reb", "ast", "stl", "blk", "fg3m", "fg_pct", "ft_pct", "tov"]

# Basic weights — turnovers are penalized
DEFAULT_WEIGHTS = {cat: 1.0 for cat in CATEGORIES}
DEFAULT_WEIGHTS["tov"] = -1.0

# Filter threshold — ignore players with tiny sample sizes
MIN_GAMES = 10
MIN_MINUTES = 10.0


def _parse_minutes(min_str):
    """Convert 'mm:ss' style minutes to float, or pass through if numeric."""
    if isinstance(min_str, (int, float)):
        return float(min_str)
    if isinstance(min_str, str) and ":" in min_str:
        mins, secs = min_str.split(":", 1)
        if mins.isdigit() and secs.isdigit():
            return int(mins) + int(secs) / 60.0
    return np.nan  # fallback if format is weird


def load_tables():
    # Load from local SQLite DB
    con = sqlite3.connect(DB_PATH)
    try:
        stats = pd.read_sql("""
            SELECT player_id, game_id, date, pts, ast, reb, stl, blk,
                   fg3m, fg_pct, ft_pct, tov, min
            FROM stats
        """, con)

        players = pd.read_sql("""
            SELECT player_id, full_name, position
            FROM players
        """, con)
    finally:
        con.close()

    stats["mp"] = stats["min"].apply(_parse_minutes)
    return stats, players


def per_game(stats_df: pd.DataFrame) -> pd.DataFrame:
    # Compute per-game averages (only for players with decent minutes)
    agg = stats_df.groupby("player_id").agg(
        games=("game_id", "nunique"),
        mp=("mp", "mean"),
        pts=("pts", "mean"),
        reb=("reb", "mean"),
        ast=("ast", "mean"),
        stl=("stl", "mean"),
        blk=("blk", "mean"),
        fg3m=("fg3m", "mean"),
        fg_pct=("fg_pct", "mean"),
        ft_pct=("ft_pct", "mean"),
        tov=("tov", "mean"),
    ).reset_index()

    # Filter out the fringe guys
    filtered = agg[(agg["games"] >= MIN_GAMES) & (agg["mp"] >= MIN_MINUTES)].copy()
    return filtered


def zscore_rank(df: pd.DataFrame, cats=CATEGORIES, weights=DEFAULT_WEIGHTS) -> pd.DataFrame:
    # Compute z-scores per category, handle NaNs and zero stddev cases
    df = df.copy()
    for cat in cats:
        vals = pd.to_numeric(df[cat], errors="coerce")
        mean = vals.mean(skipna=True)
        std = vals.std(skipna=True)

        if std is None or std == 0 or np.isnan(std):
            df[f"{cat}_z"] = 0.0
        else:
            df[f"{cat}_z"] = (vals - mean) / std

    # Weighted total score
    df["score"] = 0.0
    for cat in cats:
        df["score"] += weights.get(cat, 1.0) * df[f"{cat}_z"].fillna(0)

    # Adjust by how many games they played (soft bonus for availability)
    max_gp = df["games"].max()
    if max_gp and max_gp > 0:
        df["score"] *= df["games"] / max_gp

    return df


def build_rankings():
    stats_df, players_df = load_tables()
    per_game_df = per_game(stats_df)

    ranked_df = zscore_rank(per_game_df)
    ranked_df = ranked_df.merge(players_df, on="player_id", how="left")

    # Assign ranks (dense so no gaps in case of ties)
    ranked_df["rank"] = ranked_df["score"].rank(method="dense", ascending=False).astype(int)
    ranked_df = ranked_df.sort_values(["rank", "full_name"]).reset_index(drop=True)

    con = sqlite3.connect(DB_PATH)
    try:
        ranked_df.to_sql("fantasy_rankings", con, if_exists="replace", index=False)
    finally:
        con.close()

    print(f"Wrote fantasy_rankings table with {len(ranked_df)} players.")


if __name__ == "__main__":
    build_rankings()
