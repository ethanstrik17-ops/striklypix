"""Team and player name normalisation / matching across data sources and sportsbooks."""
from __future__ import annotations

import difflib
import re
import unicodedata

NHL_TEAMS = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens",
    "NSH": "Nashville Predators", "NJD": "New Jersey Devils", "NYI": "New York Islanders",
    "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken",
    "STL": "St Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Mammoth", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals", "WPG": "Winnipeg Jets",
}
NHL_ALIASES = {"utah hockey club": "UTA", "utah": "UTA", "montreal": "MTL"}

NBA_TEAMS = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}
NBA_ALIASES = {"la clippers": "LAC", "la lakers": "LAL"}

NFL_TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers", "LAR": "Los Angeles Rams", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SF": "San Francisco 49ers",
    "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WSH": "Washington Commanders",
}
NFL_ALIASES = {"washington": "WSH", "was": "WSH", "jac": "JAX", "lvr": "LV", "la rams": "LAR", "la chargers": "LAC"}

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace(".", " ").replace("'", "").replace("-", " ")
    s = _SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def team_abbr(sport: str, name: str) -> str | None:
    teams = {"nhl": NHL_TEAMS, "nfl": NFL_TEAMS}.get(sport, NBA_TEAMS)
    aliases = {"nhl": NHL_ALIASES, "nfl": NFL_ALIASES}.get(sport, NBA_ALIASES)
    if not name:
        return None
    if name.upper() in teams:
        return name.upper()
    n = norm(name)
    if n in aliases:
        return aliases[n]
    for ab, full in teams.items():
        if norm(full) == n:
            return ab
    for ab, full in teams.items():  # nickname match ("Maple Leafs", "49ers")
        nick = norm(full).split(" ")[-1]
        if n.split(" ")[-1] == nick:
            return ab
    return None


class PlayerMatcher:
    """Map sportsbook player names onto our player ids."""

    def __init__(self, players: "list[tuple[int, str, str]]"):
        # (player_id, name, team)
        self.by_norm: dict[str, list[tuple[int, str]]] = {}
        for pid, name, team in players:
            self.by_norm.setdefault(norm(name), []).append((pid, team))
        self.keys = list(self.by_norm)

    def match(self, name: str, teams: "set[str] | None" = None) -> int | None:
        n = norm(name)
        cands = self.by_norm.get(n)
        if not cands:
            close = difflib.get_close_matches(n, self.keys, n=1, cutoff=0.86)
            if not close:
                # last-name + first initial fallback, e.g. "J. Hughes"
                parts = n.split()
                if len(parts) >= 2:
                    pref = [k for k in self.keys if k.split()[-1] == parts[-1] and k[0] == parts[0][0]]
                    if len(pref) == 1:
                        close = pref
            if not close:
                return None
            cands = self.by_norm[close[0]]
        if teams:
            on_team = [c for c in cands if c[1] in teams]
            if on_team:
                return on_team[0][0]
        return cands[0][0]
