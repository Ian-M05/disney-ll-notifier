#!/usr/bin/env python3
"""Theme park ride-availability notifier (WDW + Universal Orlando).

Data source: https://api.themeparks.wiki (free community API).
Notifications: ntfy.sh push and/or email (set via GitHub Secrets).
No third-party Python packages required.

What it can alert on (toggle in config.json -> "alerts"):
  lightning_lane_drops  - a paid Single Pass / Individual Lightning Lane flips
                          from sold out back to AVAILABLE (price + return time).
  multi_pass_drops      - a free Multi Pass / Lightning Lane return time opens.
  standby_under_minutes - a ride's standby wait drops below this many minutes
                          (e.g. 60). Fires once on the downward crossing.
  ride_down             - a ride goes DOWN (breakdown).
  ride_back_up          - a ride comes back from DOWN to OPERATING.

Scope:
  destinations  - which resorts to watch, e.g. ["Walt Disney World",
                  "Universal Orlando"] (case-insensitive name fragments).
  parks         - optional park-name allow-list within those resorts. Empty = all.
  exclude_parks - park-name fragments to skip, e.g. ["Water Park", "Volcano Bay"].
  watchlist     - ride-name fragments that scope the *standby* and *ride
                  down/back-up* alerts. Lightning Lane and Multi Pass drops
                  always fire for every ride in scope. Empty watchlist = those
                  noisier alerts apply to all rides too.
  quiet_hours   - {"start": "HH:MM", "end": "HH:MM"} in US Eastern time; alerts
                  are suppressed during this window (overnight wrap supported).
"""

import json
import os
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

# Both Walt Disney World and Universal Orlando are in US Eastern time.
PARK_TZ = ZoneInfo("America/New_York")

API = "https://api.themeparks.wiki/v1"
STATE_FILE = "state.json"
CONFIG_FILE = "config.json"


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ll-notifier/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def list_parks(cfg):
    """Return parks for every destination whose name matches the config."""
    wanted = [d.lower() for d in cfg.get("destinations", ["walt disney world"])]
    data = http_get_json(f"{API}/destinations")
    parks = []
    for dest in data.get("destinations", []):
        if any(w in dest.get("name", "").lower() for w in wanted):
            parks.extend(dest.get("parks", []))
    if not parks:
        raise SystemExit(f"No destinations matched {wanted}")
    return parks


def fmt_time(iso):
    """'2026-05-28T20:20:00-04:00' -> '20:20' (already park-local time)."""
    return iso[11:16] if iso and len(iso) >= 16 else "?"


def snapshot(park):
    """Return {attraction_id: info} for every ride reporting live status."""
    live = http_get_json(f"{API}/entity/{park['id']}/live")
    out = {}
    for item in live.get("liveData", []):
        if item.get("entityType") != "ATTRACTION":
            continue
        queue = item.get("queue") or {}
        if not item.get("status") and not queue:
            continue  # nothing to track for this entity
        paid = queue.get("PAID_RETURN_TIME") or {}
        multi = queue.get("RETURN_TIME") or {}
        standby = (queue.get("STANDBY") or {}).get("waitTime")
        out[item["id"]] = {
            "name": item.get("name", "Unknown"),
            "park": park["name"],
            "status": item.get("status"),
            "standby": standby,
            "paid_state": paid.get("state"),
            "paid_price": (paid.get("price") or {}).get("formatted") or "",
            "paid_return": fmt_time(paid.get("returnStart")),
            "multi_state": multi.get("state"),
            "multi_return": fmt_time(multi.get("returnStart")),
        }
    return out


def diff_alerts(prev, curr, cfg):
    a = cfg.get("alerts", {})
    want_ll = a.get("lightning_lane_drops", True)
    want_multi = a.get("multi_pass_drops", False)
    threshold = a.get("standby_under_minutes")
    want_down = a.get("ride_down", False)
    want_up = a.get("ride_back_up", False)
    margin = a.get("standby_rearm_margin", 15)
    watch = [w.lower() for w in cfg.get("watchlist", [])]

    alerts = []
    for aid, now in curr.items():
        before = prev.get(aid)
        if before is None:
            continue  # first time we've seen this ride; baseline only
        where = f"{now['name']} ({now['park']})"
        in_watch = not watch or any(w in now["name"].lower() for w in watch)

        # Lightning Lane / Multi Pass drops fire for every ride in scope.
        if want_ll and now["paid_state"] == "AVAILABLE" \
                and before.get("paid_state") != "AVAILABLE":
            price = now["paid_price"] or "paid"
            alerts.append(
                f"🎢 {where}: Lightning Lane open — {price}, next {now['paid_return']}"
            )

        if want_multi and now["multi_state"] == "AVAILABLE" \
                and before.get("multi_state") != "AVAILABLE":
            alerts.append(
                f"🎟️ {where}: Multi Pass return times open, next {now['multi_return']}"
            )

        # Standby / breakdown alerts are limited to the watchlist (noisier).
        if not in_watch:
            continue

        # Standby drop with anti-flap: once we alert, don't alert again until the
        # wait climbs back to threshold + margin (so a ride hovering near the
        # cutoff doesn't ping repeatedly).
        armed = before.get("standby_armed", True)
        now_wait, was_wait = now["standby"], before.get("standby")
        if threshold and now["status"] == "OPERATING" and isinstance(now_wait, int):
            if armed and isinstance(was_wait, int) \
                    and was_wait >= threshold and now_wait < threshold:
                alerts.append(
                    f"⏱️ {where}: standby down to {now_wait} min (under {threshold})"
                )
                armed = False
            if now_wait >= threshold + margin:
                armed = True
        now["standby_armed"] = armed

        if want_down and now["status"] == "DOWN" and before.get("status") != "DOWN":
            alerts.append(f"🛠️ {where}: went DOWN")

        if want_up and now["status"] == "OPERATING" and before.get("status") == "DOWN":
            wait = f" — {now['standby']} min standby" if isinstance(now["standby"], int) else ""
            alerts.append(f"✅ {where}: back up{wait}")

    return alerts


def in_quiet_hours(cfg):
    """True if the current Eastern time falls in the configured quiet window."""
    qh = cfg.get("quiet_hours") or {}
    start, end = qh.get("start"), qh.get("end")
    if not start or not end:
        return False
    now = datetime.now(PARK_TZ).strftime("%H:%M")
    if start <= end:                 # same-day window, e.g. 13:00–14:00
        return start <= now < end
    return now >= start or now < end  # overnight window, e.g. 01:00–07:00


def notify(alerts):
    body = "\n".join(alerts)
    sent = False

    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if topic:
        req = urllib.request.Request(
            f"https://ntfy.sh/{urllib.parse.quote(topic)}",
            data=body.encode(),
            headers={
                "Title": "Theme park alert",
                "Priority": "high",
                "Tags": "ferris_wheel",
            },
        )
        urllib.request.urlopen(req, timeout=30).read()
        print("Sent ntfy push")
        sent = True

    host = (os.environ.get("SMTP_HOST") or "").strip()
    to = (os.environ.get("EMAIL_TO") or "").strip()
    if host and to:
        msg = MIMEText(body)
        msg["Subject"] = f"Theme park alert ({len(alerts)})"
        msg["From"] = os.environ.get("SMTP_USER", "ll-notifier")
        msg["To"] = to
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        print(f"Sent email to {to}")
        sent = True

    if not sent:
        print("WARNING: no notification channel configured "
              "(set NTFY_TOPIC and/or SMTP_* + EMAIL_TO secrets)")


def main():
    if os.environ.get("LL_TEST_NOTIFY") == "true":
        notify(["✅ Test alert from disney-ll-notifier — your phone link works!"])
        return

    cfg = load_json(CONFIG_FILE, {})
    park_filter = [p.lower() for p in cfg.get("parks", [])]
    exclude = [p.lower() for p in cfg.get("exclude_parks", [])]
    prev = load_json(STATE_FILE, {})

    curr = {}
    for park in list_parks(cfg):
        name = park["name"].lower()
        if park_filter and not any(p in name for p in park_filter):
            continue
        if exclude and any(x in name for x in exclude):
            continue
        try:
            curr.update(snapshot(park))
        except Exception as e:  # one park glitching shouldn't kill the run
            print(f"WARNING: live fetch failed for {park.get('name')}: {e}")

    if not curr:
        print("No live data returned; keeping previous state")
        return

    if prev:
        alerts = diff_alerts(prev, curr, cfg)
        if alerts and in_quiet_hours(cfg):
            print(f"{len(alerts)} alert(s) suppressed (quiet hours)")
        elif alerts:
            print(f"{len(alerts)} alert(s):")
            for a in alerts:
                print(" ", a)
            notify(alerts)
        else:
            print(f"No changes ({len(curr)} attractions tracked)")
    else:
        print(f"First run: baseline saved for {len(curr)} attractions, no alerts")

    with open(STATE_FILE, "w") as f:
        json.dump(curr, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
