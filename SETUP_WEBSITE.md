# Your private StriklyPix website (free, about 20 minutes, one time)

When you're done:
- The bot runs itself on GitHub every afternoon (and Sunday mornings for NFL). It doesn't need your Mac or Terminal.
- Your page is at `https://ethanstrik17-ops.github.io/striklypix/`, with the **NFL** section first and **NBA** one tap away.
- The page is locked with a password you choose. The content is encrypted, so anyone without the password only sees
  the lock screen. Type it once on your phone and tick "Remember on this device".

## 1. Make a GitHub account
https://github.com/signup. Your username becomes part of your link.

## 2. Create the repository
**+** (top right) → **New repository** → name it `striklypix` → **Public** → **Create repository**.
(Public is required for free GitHub Pages. Your picks stay private because every page and the pick log are
encrypted with your password.)

## 3. Upload the bot
On the new repository page, click **uploading an existing file**. Open the unzipped `striklypix-site` folder,
press **Cmd + A** to select **everything inside it**, and drag it onto the page. Drag the contents, not the
folder itself. Wait for the upload to finish, then click **Commit changes**.

## 4. Add the schedule file
GitHub's uploader skips hidden folders, so create this one by hand:
**Add file** → **Create new file** → name: `.github/workflows/daily.yml` → paste the contents of `daily.yml`
→ **Commit changes**.

## 5. Add your two secrets
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**, twice:
| Name | Value |
|---|---|
| `ODDS_API_KEY` | your key from the-odds-api.com |
| `SITE_PASSWORD` | a password you make up for your page |

## 6. Run it the first time
**Actions** tab → (enable workflows if asked) → **Daily card** → **Run workflow** → **Run workflow**.
The first run takes about 10–15 minutes while it downloads this season. It turns green when it's done.

## 7. Turn on the website
**Settings** → **Pages** → Source **Deploy from a branch** → Branch **main**, folder **/docs** → **Save**.
About a minute later your link appears at the top of that page. Open it on your phone, enter your password,
and bookmark it (Share → **Add to Home Screen** makes it look like an app).

## Day to day
- The page refreshes every day around **4:15 PM ET**, and on **Sundays around 10:30 AM ET** for NFL.
  GitHub can start a run up to about 30 minutes late.
- To refresh sooner (for example after late injury news), go to **Actions** → **Daily card** → **Run workflow**.
  Each extra run uses about 15 odds credits.
- **Tracker** tab: every pick from Top 10 Bets, Top 10 Props and Long shots is logged and graded automatically,
  at 1 unit per pick.

## Going public later
Delete the `SITE_PASSWORD` secret and run the workflow once. The pages are then open to anyone with the link.

## Settings
Edit `site_config.yaml` on GitHub (click it → pencil icon → **Commit changes**):
- `prop_markets`: which player props to price.
- `bankroll: 500`: show stakes in dollars.
- Upgrading the odds plan lets you add more prop types.
