# src/etl.py — multi-pass, kinda-resilient ETL process for NBA stats
import time
import random
import datetime as dt
import pandas as pd
from sqlalchemy import create_engine

# NBA API imports
from nba_api.stats.static import players as players_static
from nba_api.stats.endpoints import (
    playergamelog,
    commonplayerinfo,
    leaguedashplayerstats,
)

# DB config — just using SQLite locally for now
DB_URL = "sqlite:///nba.sqlite"
engine = create_engine(DB_URL)

# ---------------- Season Selection (find last full season) ----------------
def get_last_completed_season(today: dt.date | None = None) -> str:
    # fallback to today's date if none provided
    today = today or dt.date.today()

    # NBA season rolls over in July
    if today.month >= 7:
        start = today.year - 1
    else:
        start = today.year - 2

    end = str((start + 1) % 100).zfill(2)
    return f"{start}-{end}"

SEASON_STR = get_last_completed_season()

# ---------------- Helper Utilities ----------------

def sleep_a_bit(base=0.25, wiggle=0.25):
    # Slow things down slightly to avoid hammering the API
    time.sleep(base + random.random() * wiggle)

def try_with_retries(fn, tries=4, wait=1.0, wait_max=6.0, jitter=0.4, fallback=None):
    delay = wait
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == tries:
                return fallback
            time.sleep(delay + random.random() * jitter)
            delay = min(wait_max, delay * 1.8)

# ---------------- Player Info ----------------

def get_active_players() -> pd.DataFrame:
    plist = players_static.get_active_players()
    df = pd.DataFrame(plist)[["id", "full_name", "first_name", "last_name", "is_active"]]
    return df.rename(columns={"id": "player_id"})

def get_position_for_player(player_id: int) -> str:
    def _fetch():
        sleep_a_bit(0.2, 0.3)
        data = commonplayerinfo.CommonPlayerInfo(player_id=player_id, timeout=60)
        df = data.get_data_frames()[0]
        return str(df.loc[0, "POSITION"] or "")
    return try_with_retries(_fetch, fallback="") or ""

# ---------------- Relevant Players Filter ----------------

def find_relevant_players(season: str, min_gp=10, min_min=10.0) -> list[int]:
    def _fetch():
        sleep_a_bit(0.2, 0.3)
        resp = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            per_mode_detailed="PerGame",
            season_type_all_star="Regular Season",
            timeout=60,
        )
        return resp.get_data_frames()[0]

    df = try_with_retries(_fetch, fallback=pd.DataFrame())
    if df.empty:
        return []

    df.columns = [c.upper() for c in df.columns]
    df["GP"] = pd.to_numeric(df.get("GP", 0), errors="coerce").fillna(0)
    df["MIN"] = pd.to_numeric(df.get("MIN", 0), errors="coerce").fillna(0)

    mask = (df["GP"] >= min_gp) & (df["MIN"] >= min_min)
    filtered = df.loc[mask]
    return pd.to_numeric(filtered.get("PLAYER_ID", []), errors="coerce").dropna().astype(int).tolist()

# ---------------- Game Log per Player ----------------

def fetch_gamelog_for_player(player_id: int, season: str) -> pd.DataFrame:
    def _fetch():
        sleep_a_bit(0.25, 0.35)
        gl = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season,
            season_type_all_star="Regular Season",
            timeout=60,
        )
        df = gl.get_data_frames()[0].copy()
        if "PLAYER_ID" not in df.columns:
            df["PLAYER_ID"] = player_id  # manually add if missing
        return df

    df = try_with_retries(_fetch, fallback=None)
    if df is None or df.empty:
        return pd.DataFrame()

    renames = {
        "PLAYER_ID": "player_id",
        "Game_ID": "game_id",
        "GAME_DATE": "date",
        "PTS": "pts", "AST": "ast", "REB": "reb",
        "STL": "stl", "BLK": "blk",
        "FG_PCT": "fg_pct", "FG3_PCT": "fg3_pct", "FT_PCT": "ft_pct",
        "MIN": "min",
        "Team_ID": "team_id",
        "Team_Abbreviation": "team",
        "FG3M": "fg3m", "TOV": "tov",
        "FGM": "fgm", "FGA": "fga", "FTM": "ftm", "FTA": "fta",
    }

    cols_to_keep = [c for c in renames if c in df.columns]
    if "PLAYER_ID" not in cols_to_keep:
        cols_to_keep = ["PLAYER_ID"] + cols_to_keep

    df = df[cols_to_keep].rename(columns={k: renames[k] for k in cols_to_keep if k in renames})

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    return df

def gamelog_with_retries(player_id: int, season: str, tries: int = 3) -> pd.DataFrame:
    for _ in range(tries):
        df = fetch_gamelog_for_player(player_id, season)
        if not df.empty:
            return df
        time.sleep(0.6 + random.random() * 0.8)
    return pd.DataFrame()

# ---------------- Per-game Table ----------------

def get_league_pergame(season: str) -> pd.DataFrame:
    def _fetch():
        sleep_a_bit(0.2, 0.3)
        return leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            per_mode_detailed="PerGame",
            season_type_all_star="Regular Season",
            timeout=60,
        ).get_data_frames()[0]

    df = try_with_retries(_fetch, fallback=pd.DataFrame())
    if df.empty:
        return df

    df.columns = [c.upper() for c in df.columns]
    for col in ["PLAYER_ID", "GP", "MIN", "PTS"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

def make_games_table(df: pd.DataFrame) -> pd.DataFrame:
    return df[["game_id", "date"]].drop_duplicates(subset=["game_id"]).reset_index(drop=True)

# ---------------- Main Process ----------------

def main():
    print(f"Season selected: {SEASON_STR}")

    try:
        prev_players = pd.read_sql("players", engine)
        prev_pos = prev_players[["player_id", "position"]].dropna()
    except Exception:
        prev_pos = pd.DataFrame(columns=["player_id", "position"])

    print("Pulling list of active players …")
    players = get_active_players()

    print("Fetching positions (with retries)…")
    players["position"] = players["player_id"].apply(get_position_for_player)

    if not prev_pos.empty:
        players = players.merge(prev_pos, on="player_id", how="left", suffixes=("", "_old"))
        players["position"] = players["position"].mask(players["position"] == "", players["position_old"])
        players.drop(columns=["position_old"], inplace=True)

    players["position"] = players["position"].fillna("")
    players.to_sql("players", engine, if_exists="replace", index=False)
    print(f"Saved player table with {len(players)} entries")

    print(f"Filtering relevant players for {SEASON_STR} …")
    relevant_ids = set(find_relevant_players(SEASON_STR))
    if not relevant_ids:
        print("No relevant players found — using all actives instead.")
        relevant_ids = set(players["player_id"].tolist())

    target_ids = [pid for pid in players["player_id"] if pid in relevant_ids]
    print(f"Targeting {len(target_ids)} players for logs …")

    # -------- PASS 1 --------
    gamelogs = []
    missed_first = []

    for pid in target_ids:
        df = gamelog_with_retries(pid, SEASON_STR, tries=2)
        if df.empty:
            missed_first.append(pid)
        else:
            gamelogs.append(df)

    print(f"Pass 1 complete: {len(gamelogs)} success, {len(missed_first)} missed")

    # -------- PASS 2 --------
    if missed_first:
        print("Retrying missed players (second pass)…")
        recovered = 0
        for pid in missed_first:
            df = gamelog_with_retries(pid, SEASON_STR, tries=4)
            if not df.empty:
                gamelogs.append(df)
                recovered += 1
        print(f"Recovered {recovered} additional logs")

    # -------- Safety Sweep --------
    fetched_ids = set()
    for gdf in gamelogs:
        if "player_id" in gdf.columns:
            fetched_ids.update(pd.to_numeric(gdf["player_id"], errors="coerce").dropna().astype(int).tolist())

    still_missing = [pid for pid in players["player_id"] if pid not in fetched_ids]

    if still_missing:
        table = get_league_pergame(SEASON_STR)
        if not table.empty:
            extras = table[table["PLAYER_ID"].isin(still_missing)].copy()
            if not extras.empty:
                extras = extras.sort_values(["MIN", "PTS", "GP"], ascending=[False, False, False])
                for pid in extras["PLAYER_ID"].astype(int).head(150).tolist():
                    df = gamelog_with_retries(pid, SEASON_STR, tries=3)
                    if not df.empty:
                        gamelogs.append(df)

    # -------- Save Everything --------
    if not gamelogs:
        raise RuntimeError("No data collected — something’s off with the API or season logic")

    stats_df = pd.concat(gamelogs, ignore_index=True)
    stats_df["season"] = SEASON_STR
    stats_df.to_sql("stats", engine, if_exists="replace", index=False)

    games_df = make_games_table(stats_df)
    games_df.to_sql("games", engine, if_exists="replace", index=False)

    # Log unresolved
    fetched_ids = set(pd.to_numeric(stats_df["player_id"], errors="coerce").dropna().astype(int).tolist())
    missing_ids = [pid for pid in target_ids if pid not in fetched_ids]

    if missing_ids:
        import csv
        with open("etl_missing_ids.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["player_id"])
            writer.writerows([[pid] for pid in missing_ids])
        print(f"Saved list of {len(missing_ids)} missing player IDs to etl_missing_ids.csv")

    print(f"Saved {len(stats_df)} rows across {len(games_df)} games")
    print("All done — DB: nba.sqlite")

if __name__ == "__main__":
    main()
