# Theme Park Ride Notifier (WDW + Universal Orlando)

Pings your phone about the rides you care about at Walt Disney World **and**
Universal Orlando (including Epic Universe): paid Lightning Lane drops, standby
waits dropping under a threshold, and rides breaking down / coming back up.
Runs entirely in the cloud on GitHub Actions — your computer can be off.

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

### Scope — *where* to watch

| Key | Values | Meaning |
|---|---|---|
| `destinations` | resort name fragments | e.g. `["Walt Disney World", "Universal Orlando"]`. Case-insensitive substring match |
| `parks` | park name fragments | Limit within those resorts, e.g. `["Magic Kingdom", "Epic Universe"]`. Empty = all parks |
| `watchlist` | ride name fragments | If non-empty, **every** alert is limited to matching rides, e.g. `"TRON"`. Empty = all rides |

### Alerts — *what* to be told about (`alerts` object)

| Key | Values | Meaning |
|---|---|---|
| `lightning_lane_drops` | `true`/`false` | A paid Single Pass / Individual Lightning Lane flips sold out → available (with price + return time) |
| `multi_pass_drops` | `true`/`false` | A free Multi Pass / Lightning Lane return time opens |
| `standby_under_minutes` | number or `0`/omit | Standby wait drops below this many minutes — fires once on the downward crossing |
| `ride_down` | `true`/`false` | A ride goes DOWN (breakdown) |
| `ride_back_up` | `true`/`false` | A ride comes back from DOWN to OPERATING |

The shipped config watches both resorts, alerts on Lightning Lane drops +
standby-under-60-min + ride down/up, and limits all of it to a curated list of
headliner rides (the ones where these alerts actually matter). Edit the
`watchlist` to add/remove rides, or empty it (`[]`) to track everything.

> **Note on standby alerts:** an empty `watchlist` plus `standby_under_minutes`
> would alert on nearly every ride (most are always under an hour). Keep a
> watchlist of headliners for standby alerts to stay useful.

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
