# StriklyPix: NFL and NBA projections, picks and tracking (engine: sportsedge)

A Python tool you run on your own computer. It does four things:

1. **Projects player stats.** NHL: shots on goal, shot attempts, goals, assists, points, hits, blocks, power-play points and goalie saves. NBA: points, rebounds, assists, threes, FGA, 3PA, FTA, steals, blocks, turnovers and the PRA/PR/PA/RA combos.
2. **Projects games.** It gives expected scores, win probability, spread or puck-line odds and total over/under probabilities. NHL games include overtime and shootouts.
3. **Finds value.** It pulls sportsbook lines, removes the vig, blends its own probability with the market's, shops for the best price across books, and reports EV and a fractional-Kelly stake.
4. **Checks trends properly.** Every "hit in 7 of 10" comes with a confidence interval and a verdict saying whether it's real or just noise. It also scans for hot/cold streaks and changes in a player's role (minutes).

It also includes a walk-forward **backtest** for tuning the model and a **pick log** that records results and closing line value (CLV).

---

## 1. Install (one time)

You need Python 3.10 or newer.

```bash
cd sportsedge
pip install -e .          # installs the `sportsedge` command
```
(Or skip installing: `pip install -r requirements.txt`, then use `python -m sportsedge ...` from this folder.)

## 2. Try it with no internet (demo mode)

`--demo` runs everything on a simulated league with fake players and fake sportsbooks, so you can see what the output looks like:

```bash
sportsedge slate nhl --demo
sportsedge props nba --demo
sportsedge trends nhl --demo
sportsedge backtest nba --demo --start 2026-10-25 --end 2026-11-02
```

## 3. Use it for real

The game data is free and needs no key:
- NHL: `api-web.nhle.com` and `api.nhle.com/stats` (boxscores, play-by-play, shot locations)
- NBA: ESPN's public game feed (box scores and schedule). The first run also downloads the last 400 games of last season as a starting point, which takes a few minutes once and is cached after that.

**Sportsbook odds (optional, but needed for value):** get a free key from https://the-odds-api.com, then set it:

```bash
# Mac/Linux
export ODDS_API_KEY=your_key_here
# Windows PowerShell
$env:ODDS_API_KEY="your_key_here"
```

The free tier is about 500 credits a month. Game lines cost about 3 credits per run. Props cost about (games × markets) credits per run, so an NBA slate is roughly 50. Cut `odds.prop_markets` in config.yaml to save credits.

**Only books you can bet at:** set `odds.my_books` in config.yaml (for example `[draftkings, fanduel, betrivers, espnbet, bet99, proline]`). Every book still feeds the fair-price estimate, but the "best price" and EV only come from your books.

**Books the API doesn't cover** (for example Bet99, Sports Interaction, theScore): type the lines into a CSV and pass `--lines my_lines.csv`. See `lines.example.csv` for the format. Manual lines are compared side by side with the API books for the same game.

```bash
sportsedge daily nba --bankroll 500      # START HERE: one page with everything (opens in your browser)
sportsedge slate nhl                     # today's NHL games + game-line value
sportsedge props nhl --stat sog          # SOG props only
sportsedge props nba --overrides overrides.yaml --log
sportsedge player nhl "Auston Matthews" --line sog=3.5 points=0.5
sportsedge trends nba
sportsedge backtest nhl --start 2026-10-15 --end 2026-11-02
sportsedge grade nhl                     # grade --log'd picks + CLV
```

The first NHL run of a season downloads every game played so far, which takes a few minutes. Those games are cached in `~/.sportsedge/cache`, so later runs only fetch new games. Each run saves an HTML report and CSVs to `reports/`.

Other NBA sources if you ever need them: `nba: {source: cdn}` (NBA.com feed) or `nba: {source: stats}` (stats.nba.com) in config.yaml. Both block many home connections.

### A good daily routine

1. Update `overrides.yaml` with injuries, minutes limits and confirmed NHL goalies.
2. Run `props` and `slate`.
3. Treat **BET** rows as leads, not orders. **CHECK NEWS** means the model and the market disagree by more than 12 points. Usually the market knows something, like an injury or a scratch.
4. Re-run close to puck drop or tip-off if news breaks. Use `--log` on what you actually bet.
5. Run `grade` the next day.

## Website (private, auto-updating)

`.github/workflows/daily.yml` runs the bot on GitHub every afternoon (and Sunday mornings for NFL) and publishes a
password-protected page at `https://<your-github-username>.github.io/sportsedge/`. It has an NFL section and an
NBA section, each with Top 10 Bets, Top 10 Props, Long shots, Streaks & injuries, a pick Tracker, Parlays, All
picks, Games and Players tabs. Setup is in `SETUP_WEBSITE.md`, and website settings are in `site_config.yaml`.

What it uses:
- **Game data:** ESPN box scores (NBA and NFL), free.
- **Game lines:** spread, total and moneyline from ESPN's DraftKings feed, free, including line movement since open.
- **Injuries:** ESPN's injury report. OUT players are removed automatically and their minutes or targets go to
  teammates. Questionable players are flagged.
- **Player props:** The Odds API. NBA points + PRA daily, NFL receiving yards on Sundays, about 460 credits a month.

On your Mac: `python -m sportsedge daily nba` or `python -m sportsedge daily nfl` builds the same page locally.

## 4. How the model works

**Players.** Projection = projected minutes × per-minute rate × opponent factor × home/away factor.
- *Minutes / TOI*: a recency-weighted average of recent games (half-life 5–6 games), blended with the season average. Back-to-backs are reduced. Players marked OUT have their minutes redistributed to teammates.
- *Rate*: a recency-weighted per-minute rate, shrunk toward last season's rate (and toward the league/position rate) until the player has enough minutes this season. This is why an early hot streak doesn't produce a crazy projection. How much data a stat needs before it's trusted is set in `stabilize`.
- *Opponent factor*: what this opponent allows per minute to this position (NHL: F/D; NBA: G/F/C) relative to league average. It's shrunk by sample size and capped at ±15%.
- *Distribution*: negative binomial, so any line (including whole-number lines with pushes) can be priced. Run `backtest` to calibrate the dispersion.

**NHL games.** Team attack and defence ratings blend expected goals (60%) with actual goals (40%). Expected goals come from a logistic model on shot distance, angle, rebounds, strength state and shot type, fit to this season's play-by-play. The model then applies home ice and a goalie adjustment (projected starter vs. team average), builds a Poisson score grid, and resolves ties as overtime/shootout wins (+1 goal, matching how books grade). It also projects team shots on goal, which drive the goalie saves projections. The result is blended 25% with the sum of the skater goal projections.

**NBA games.** Expected pace × offensive/defensive efficiency, with home court and back-to-back adjustments. The result is blended 50% with the sum of the player point projections, so injuries in `overrides.yaml` move the spread and total too.

**Value.** Each book's two-way price is de-vigged with the power method. The market price is the sharp book (Pinnacle, if your regions include it) or the median across books. The final probability is `w × model + (1 − w) × market`, with w = 0.35 for props and 0.20 for game lines, because game lines are sharper. EV uses the best available price. Stakes are quarter-Kelly, capped at 2% of bankroll.

## 5. Tuning: do this before betting real money

```bash
sportsedge backtest nhl --start 2026-10-15 --end 2026-11-02
```

The backtest only uses data from before each game. It reports:
- **MAE / RMSE vs simple baselines** (season average, last 10). If the model doesn't beat them for a stat, don't bet that stat.
- **Brier score vs raw hit rate.** This tells you whether the model's probabilities beat "how often did he go over".
- **A calibration table.** When the model says 60%, does it happen about 60% of the time?
- **Suggested `alpha` values** (per-stat dispersion) and, for the NBA, `total_sd`/`margin_sd`. Paste them into `config.yaml`.

Re-run it every few weeks. Early-season numbers are noisy.

## 6. Honest limitations

- **The model only knows box scores and play-by-play.** It doesn't know about injuries, line changes, power-play unit changes, rest decisions or confirmed goalies unless you put them in `overrides.yaml`. That information is most of the edge in props.
- **Sportsbook lines are already good.** Expect most "edges" to be small. Trust consistent positive CLV in `grade` more than a hot week of wins.
- **Historical prop lines aren't free,** so the backtest checks calibration against synthetic lines, not real closing lines.
- **The NHL and NBA endpoints are unofficial and can change.** If a fetch breaks, the parsers are in `sportsedge/data/nhl.py` and `nba.py`.
- **Demo-mode numbers are simulated.** Ignore the size of the edges in demo mode.

Bet within your limits. In Ontario, ConnexOntario (1-866-531-2600) offers free, confidential support.

## Files

```
sportsedge/
  data/      nhl.py, nba.py (live data) · odds.py (The Odds API + manual CSV) · demo.py · names.py · http.py (cache)
  models/    players.py (skaters/players + goalies) · games.py (team ratings, score distributions) · xg.py · dist.py
  value.py   de-vig, best price, EV, Kelly, flags
  trends.py  hit rates with confidence intervals, hot/cold & role-change scan, team over/under history
  backtest.py · ledger.py (pick log, grading, CLV) · pipeline.py · cli.py · report.py
tests/       offline tests (run: pytest)
```
