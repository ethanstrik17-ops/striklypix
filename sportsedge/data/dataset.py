"""Common in-memory schema every data provider (live NHL, live NBA, demo) produces.

player_games : one row per player per game
    sport, season, game_id, date, player_id, player, team, opp, home, pos, minutes, <stats>
team_games   : one row per team per game
    game_id, date, team, opp, home, pf, pa, + sport specific
        nba: poss (game possessions), pace (per 48), ot
        nhl: sf, sa, cf, ca, xgf, xga, ot, so
goalie_games : (nhl) game_id, date, player_id, player, team, opp, home, minutes, sa, saves, ga, started
player_prior : last season per-player totals: player_id, player, pos, games, minutes, <stats>
team_prior   : last season per-team per-game rates (nba: ortg, drtg, pace / nhl: gf, ga, sf, sa)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Dataset:
    sport: str
    player_games: pd.DataFrame
    team_games: pd.DataFrame
    goalie_games: pd.DataFrame = field(default_factory=pd.DataFrame)
    player_prior: pd.DataFrame = field(default_factory=pd.DataFrame)
    team_prior: pd.DataFrame = field(default_factory=pd.DataFrame)

    def before(self, date) -> "Dataset":
        d = pd.Timestamp(date)
        f = lambda df: df[df["date"] < d] if len(df) and "date" in df else df
        return Dataset(self.sport, f(self.player_games), f(self.team_games), f(self.goalie_games),
                       self.player_prior, self.team_prior)

    def players(self):
        """(player_id, name, latest team) tuples for name matching."""
        pg = self.player_games.sort_values("date")
        last = pg.groupby("player_id").tail(1)
        out = list(zip(last.player_id, last.player, last.team))
        if len(self.goalie_games):
            gg = self.goalie_games.sort_values("date").groupby("player_id").tail(1)
            out += list(zip(gg.player_id, gg.player, gg.team))
        return out


def add_combos(df: pd.DataFrame, sport: str) -> pd.DataFrame:
    if sport == "nba":
        df["pra"] = df["pts"] + df["reb"] + df["ast"]
        df["pr"] = df["pts"] + df["reb"]
        df["pa"] = df["pts"] + df["ast"]
        df["ra"] = df["reb"] + df["ast"]
    return df


def season_start_year(date) -> int:
    d = pd.Timestamp(date)
    return d.year if d.month >= 8 else d.year - 1
