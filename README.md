# Court Vision — Fantasy Draft Hero

[![Live Demo](https://img.shields.io/badge/Live-Demo-brightgreen)](https://courtvisionfantasy.streamlit.app/)
[![Built with Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-ff4b4b)](https://streamlit.io)


A data-driven **fantasy basketball draft helper** that ranks players across **9 categories** and makes it easy to search, filter, and draft confidently.

> **Why?** Losing a $50 buy-in every year hurts... Court Vision was built to arm newbies (like me) with solid data so you don’t draft bums.

## Live App

**Try it here:** https://courtvisionfantasy.streamlit.app/

## Features

- **Composite 9-cat rankings**: PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TOV (turnovers penalized)
- **Smart scoring**: Standardized **z-scores** from per-game stats, then **weighted by games played**
- **Fast search**: Accent-insensitive player search (e.g., “Nikola Jokić” → “Nikola Jokic”)

## Ranking Methodology

1. Load last season’s player per-game stats  
2. Convert each stat to a **z-score** (how many standard deviations above/below average)  
3. Flip the sign for **TOV** (lower is better)  
4. Average the category z-scores into one **composite score**  
5. **Weight by Games Played** to reward availability - players who miss 40 games suck!
6. Sort by the final score → that’s your **rank** 

## Screenshots

<img width="1922" height="804" alt="image" src="https://github.com/user-attachments/assets/a61d286f-3ca7-46f9-a404-20d21683bdf3" />
<img width="1919" height="800" alt="image" src="https://github.com/user-attachments/assets/4f2faac0-17e8-4e5d-b72f-08264e8db287" />


## Data

- Local SQLite DB: `nba.sqlite`
- Expected table: `fantasy_rankings`

