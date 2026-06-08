# Disney World Lightning Lane Notifier

Pings your phone when a sold-out Lightning Lane at Walt Disney World becomes
available again. Runs entirely in the cloud on GitHub Actions — your computer
can be off.

Data comes from the free community [ThemeParks.wiki API](https://api.themeparks.wiki),
so no Disney credentials or scraping involved.

## Setup (~10 minutes)

### 1. Get push notifications on your phone

1. Install the **ntfy** app ([iOS](https://apps.apple.com/us/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
2. In the app, subscribe to a topic with a random, hard-to-guess name, e.g.
   `ian-disney-ll-x7k2m9`. (Topics are public — the random name is your password.)

### 2. Create the GitHub repo

1. Create a **public** repo (public = unlimited free Actions minutes; a private
   repo's 2,000 free min/month is not enough for a 5-minute cron — if you want
   private, change the cron to `*/15` or wider).
2. Add these files. The easiest way for the workflow file: in GitHub click
   **Add file → Create new file** and type the path
   `.github/workflows/check.yml` (slashes create the folders), then paste the
   contents. Add `check_lightning_lanes.py` and `config.json` the same way.

### 3. Add your secret

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `NTFY_TOPIC` | your topic name, e.g. `ian-disney-ll-x7k2m9` |

### 4. Test it

Repo → **Actions → Lightning Lane watch → Run workflow**. The first run saves a
baseline (no alert). Run it again later — you'll get pushes whenever a
Lightning Lane flips back to available. Send yourself a test push any time:
`curl -d "test" ntfy.sh/your-topic-name`

## Optional: email instead of (or in addition to) push

Add these secrets and email kicks in automatically:

| Secret | Value (Gmail example) |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | a [Gmail app password](https://myaccount.google.com/apppasswords) (not your real password) |
| `EMAIL_TO` | where to send, e.g. `mullinsij@vcu.edu` |

**Text messages:** set `EMAIL_TO` to your carrier's email-to-SMS gateway
(e.g. `5551234567@vtext.com` for Verizon). Carriers are deprecating these,
so the ntfy push is more reliable.

## Settings (`config.json`)

| Key | Values | Meaning |
|---|---|---|
| `alert_mode` | `"drops"` (default) | Alert when any paid Single Pass flips from sold out → available |
| | `"watchlist"` | Only rides in `watchlist` (matches Single Pass *and* Multi Pass openings) |
| | `"all"` | Every Lightning Lane state change, all rides — noisy |
| `watchlist` | ride name fragments | Case-insensitive substring match, e.g. `"TRON"` |
| `parks` | park name fragments | Limit to certain parks, e.g. `["Magic Kingdom", "EPCOT"]`. Empty = all four |

## Good to know

- **Timing:** GitHub cron isn't exact — runs can lag 5–20 minutes during busy
  periods. Fine for catching drops, but paid services that poll constantly
  will sometimes beat it.
- **Auto-pause:** GitHub disables scheduled workflows after 60 days with no
  repo activity. The bot's own state commits usually prevent this; if it
  pauses, one click in the Actions tab re-enables it.
- **State:** the bot commits `state.json` after each change so it remembers
  what was available between runs and only alerts on *changes*.
- **Accuracy:** data is as good as ThemeParks.wiki's feed — community-run,
  widely used, but not guaranteed by Disney.
