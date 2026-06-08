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
| `parks` | park name fragments | Allow-list within those resorts, e.g. `["Magic Kingdom", "Epic Universe"]`. Empty = all parks |
| `exclude_parks` | park name fragments | Parks to skip, e.g. `["Water Park", "Volcano Bay"]` |
| `watchlist` | ride name fragments | Scopes the **standby** and **ride down/back-up** alerts to matching rides, e.g. `"Lightcycle"`. Lightning Lane / Multi Pass drops always fire for *every* ride in scope |
| `quiet_hours` | `{"start":"HH:MM","end":"HH:MM"}` | Suppress all alerts during this window (US Eastern, overnight wrap OK). Ships `01:00`–`07:00`. Omit to disable |

### Alerts — *what* to be told about (`alerts` object)

| Key | Values | Meaning |
|---|---|---|
| `lightning_lane_drops` | `true`/`false` | A paid Single Pass / Individual Lightning Lane flips sold out → available (with price + return time) |
| `multi_pass_drops` | `true`/`false` | A free Multi Pass / Lightning Lane return time opens |
| `standby_under_minutes` | number or `0`/omit | Standby wait drops below this many minutes — fires once on the downward crossing |
| `standby_rearm_margin` | number (default `15`) | After a standby alert, don't re-alert that ride until its wait recovers to `standby_under_minutes + this` (anti-flap) |
| `ride_down` | `true`/`false` | A ride goes DOWN (breakdown) |
| `ride_back_up` | `true`/`false` | A ride comes back from DOWN to OPERATING |

The shipped config watches both resorts (water parks excluded), pushes **every
Lightning Lane drop** resort-wide, and adds standby-under-60-min + ride
down/back-up alerts for a broad watchlist of ~85 real rides. Edit the
`watchlist` to add/remove rides.

> **Note on standby alerts:** an empty `watchlist` makes the standby and
> down/back-up alerts apply to *every* ride — noisy, since most rides are
> always under an hour and minor rides break down often. Keep a watchlist for
> those two alert types to stay useful. (Lightning Lane drops are low-volume,
> so they fire resort-wide regardless.)

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
