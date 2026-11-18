"""Default settings. Override any of these in a config.yaml (see config.example.yaml).

The numbers here are sensible starting points, NOT tuned truths. Run
`sportsedge backtest <sport>` on your own data and adjust.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "general": {
        "cache_dir": "~/.sportsedge/cache",
        "output_dir": "reports",
        "picks_file": "picks.csv",
        "auto_injuries": True,       # use ESPN injury report to remove OUT players automatically
        "bankroll": None,            # e.g. 500 -> stakes shown in dollars on the daily card
        "request_delay": 0.35,  # seconds between live API calls (be polite)
    },
    "odds": {
        "api_key_env": "ODDS_API_KEY",  # The Odds API key is read from this env var
        "regions": "us",               # each region costs credits; "us,eu" adds Pinnacle
        "bookmakers": None,            # e.g. "draftkings,fanduel,betmgm,pinnacle"
        "min_credits_left": 0,         # stop fetching props when credits would drop below this
        "enabled_sports": ["nba", "nhl", "nfl"],  # sports that fetch prop odds (others: projections only)
        "game_lines_source": "espn",   # "espn" = free DraftKings lines from ESPN; "oddsapi" = multi-book, costs credits
        "props_source": "espn",        # "espn" = free DraftKings player props for NBA/NFL; "oddsapi" = paid multi-book
        "prop_days": {},               # e.g. {"nfl": ["Sunday"]}: only buy prop odds on these days
        "reuse_props_hours": {},       # e.g. {"nfl": 12}: later runs the same day reuse the morning's prop prices
        "my_books": None,              # books you can bet at; best price is only taken from these
        "sharp_books": ["pinnacle", "circasports", "lowvig", "betonlineag"],
        "prop_markets": {
            "nba": ["player_points", "player_rebounds", "player_assists", "player_threes",
                    "player_points_rebounds_assists"],
            "nfl": ["player_reception_yds", "player_rush_yds", "player_pass_yds"],
            "nhl": ["player_shots_on_goal", "player_points", "player_assists",
                    "player_blocked_shots", "player_total_saves"],
        },
    },
    "value": {
        "min_ev": 0.03,              # flag bets with >= 3% expected value
        "max_disagreement": 0.12,    # model vs market prob gap that triggers "CHECK NEWS"
        "kelly_fraction": 0.25,      # quarter Kelly
        "max_stake_pct": 0.02,       # never suggest more than 2% of bankroll
        "max_parlay_stake_pct": 0.005,
        "model_weight_props": 0.35,  # blend: final = w*model + (1-w)*no-vig market (raise only after CLV proves it)
        "model_weight_games": 0.20,  # game lines are sharper -> trust market more
        "min_games_played": 5,
    },
    "nba": {
        "minutes_halflife": 5,       # games
        "rate_halflife": 15,         # games
        "min_proj_minutes": 12.0,
        "max_minutes": 42.0,
        # minutes of play needed before a player's own rate gets 50% weight vs prior
        "stabilize": {"pts": 300, "reb": 350, "ast": 350, "fg3m": 600, "fga": 200,
                      "fg3a": 300, "fta": 450, "stl": 900, "blk": 700, "tov": 500,
                      "oreb": 400, "dreb": 350, "pra": 300, "pr": 300, "pa": 300, "ra": 350},
        "opp_shrink_games": 15,
        "opp_factor_cap": [0.85, 1.15],
        "b2b_minutes_factor": 0.97,
        "team_halflife": 12,
        "team_shrink_games": 8,
        "prior_regression": 0.5,     # how far last season's team rating regresses to average
        "home_court_pts": 2.3,
        "b2b_pts": 1.2,
        "margin_sd": 12.5,
        "total_sd": 18.0,
        "bottom_up_weight": 0.5,     # weight on sum-of-player-projections for team scores
        "default_alpha": 0.06,       # negative-binomial overdispersion fallback
        "alpha_floor": 0.06,         # min overdispersion (projection error adds variance)
        "alpha": {},                 # per-stat values from `backtest` output override the above
    },
    "nfl": {
        "team_halflife": 5,          # games
        "team_shrink_games": 4,
        "prior_regression": 0.35,    # last season's team numbers count 65% toward this year's start
        "home_field_pts": 1.6,
        "margin_sd": 13.5,
        "total_sd": 13.0,
        "opp_factor_cap": [0.85, 1.15],
        "share_halflife": 3,         # how fast target/carry share reacts to recent games
        "prior_weeks": 8,            # last N weeks of last season used as a starting point
        "slate_days": 7,             # NFL page shows games in the next 7 days
        "alpha_floor": {"pass_yds": 0.05, "pass_att": 0.02, "pass_cmp": 0.03, "pass_td": 0.1, "rush_yds": 0.2,
                        "rush_att": 0.08, "rec": 0.1, "rec_yds": 0.25, "targets": 0.1, "td": 0.05,
                        "rush_rec_yds": 0.2, "pass_rush_yds": 0.05},
        "alpha": {},
    },
    "nhl": {
        "minutes_halflife": 6,
        "rate_halflife": 20,
        "min_proj_minutes": 7.0,
        "max_minutes": 28.0,
        "stabilize": {"sog": 250, "attempts": 200, "goals": 1500, "assists": 1200,
                      "points": 900, "hits": 300, "blocks": 300, "ppp": 1500},
        "opp_shrink_games": 20,
        "opp_factor_cap": [0.85, 1.15],
        "team_halflife": 20,
        "team_shrink_games": 12,
        "prior_regression": 0.5,
        "home_goal_factor": 1.05,    # home/away scoring ratio
        "xg_weight": 0.6,            # weight on xG vs actual goals for team strength
        "goalie_shrink_shots": 1500,
        "default_alpha": 0.08,
        "alpha_floor": 0.02,
        "alpha": {},
        "max_goals": 12,
        "bottom_up_weight": 0.25,
    },
}

PLAYER_STATS = {
    "nba": ["pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta", "stl", "blk", "tov",
            "oreb", "dreb", "pra", "pr", "pa", "ra"],
    "nhl": ["sog", "attempts", "goals", "assists", "points", "hits", "blocks", "ppp"],
    "nfl": ["pass_yds", "pass_att", "pass_cmp", "pass_td", "rush_yds", "rush_att", "rec", "rec_yds", "targets", "td",
            "rush_rec_yds", "pass_rush_yds"],
}

# The Odds API market key -> our stat column
ODDS_MARKET_TO_STAT = {
    "nba": {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast",
            "player_threes": "fg3m", "player_blocks": "blk", "player_steals": "stl",
            "player_turnovers": "tov", "player_points_rebounds_assists": "pra",
            "player_points_rebounds": "pr", "player_points_assists": "pa",
            "player_rebounds_assists": "ra"},
    "nhl": {"player_shots_on_goal": "sog", "player_points": "points", "player_assists": "assists",
            "player_goals": "goals", "player_goal_scorer_anytime": "goals",
            "player_blocked_shots": "blocks", "player_power_play_points": "ppp",
            "player_total_saves": "saves"},
    "nfl": {"player_pass_yds": "pass_yds", "player_pass_attempts": "pass_att", "player_pass_completions": "pass_cmp",
            "player_pass_tds": "pass_td", "player_rush_yds": "rush_yds", "player_rush_attempts": "rush_att",
            "player_receptions": "rec", "player_reception_yds": "rec_yds", "player_anytime_td": "td"},
}

ODDS_SPORT_KEY = {"nba": "basketball_nba", "nhl": "icehockey_nhl", "nfl": "americanfootball_nfl"}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> dict:
    cfg = DEFAULTS
    candidates = [path] if path else ["config.yaml", os.path.expanduser("~/.sportsedge/config.yaml")]
    for p in candidates:
        if p and Path(p).exists():
            with open(p) as fh:
                cfg = _deep_merge(cfg, yaml.safe_load(fh) or {})
            break
    cfg = copy.deepcopy(cfg)
    cfg["general"]["cache_dir"] = os.path.expanduser(cfg["general"]["cache_dir"])
    return cfg
