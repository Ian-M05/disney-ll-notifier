#!/usr/bin/env python3
"""Walt Disney World Lightning Lane availability notifier.

Data source: https://api.themeparks.wiki (free community API).
Notifications: ntfy.sh push and/or email (set via GitHub Secrets).
No third-party Python packages required.

Alert modes (config.json -> "alert_mode"):
  drops     - Single Pass (paid Lightning Lane) flips from sold out back to
              AVAILABLE on any ride. The classic "drop" alert. (default)
  all       - any Lightning Lane state change on any ride (noisy).
  watchlist - only rides listed in "watchlist" flipping to AVAILABLE
              (Single Pass or Multi Pass).
"""

import json
import os
import smtplib
import urllib.parse
import urllib.request
from email.mime.text import MIMEText

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


def wdw_parks():
    data = http_get_json(f"{API}/destinations")
    for dest in data.get("destinations", []):
        if "walt disney world" in dest.get("name", "").lower():
            return dest.get("parks", [])
    raise SystemExit("Walt Disney World not found in destinations list")


def fmt_time(iso):
    """'2026-05-28T20:20:00-04:00' -> '20:20' (already park-local time)."""
    return iso[11:16] if iso and len(iso) >= 16 else "?"


def snapshot(park):
    """Return {attraction_id: info} for attractions with Lightning Lane queues."""
    live = http_get_json(f"{API}/entity/{park['id']}/live")
    out = {}
    for item in live.get("liveData", []):
        if item.get("entityType") != "ATTRACTION":
            continue
        queue = item.get("queue") or {}
        paid = queue.get("PAID_RETURN_TIME")
        multi = queue.get("RETURN_TIME")
        if not paid and not multi:
            continue
        price = (paid or {}).get("price") or {}
        out[item["id"]] = {
            "name": item.get("name", "Unknown"),
            "park": park["name"],
            "paid_state": (paid or {}).get("state"),
            "paid_price": price.get("formatted") or "",
            "paid_return": fmt_time((paid or {}).get("returnStart")),
            "multi_state": (multi or {}).get("state"),
            "multi_return": fmt_time((multi or {}).get("returnStart")),
        }
    return out


def diff_alerts(prev, curr, cfg):
    mode = cfg.get("alert_mode", "drops")
    watchlist = [w.lower() for w in cfg.get("watchlist", [])]
    alerts = []
    for aid, now in curr.items():
        before = prev.get(aid)
        if before is None:
            continue  # first time we've seen this ride; baseline only
        if mode == "watchlist" and not any(
            w in now["name"].lower() for w in watchlist
        ):
            continue
        paid_was, paid_is = before.get("paid_state"), now["paid_state"]
        multi_was, multi_is = before.get("multi_state"), now["multi_state"]
        where = f"{now['name']} ({now['park']})"

        if mode == "all":
            if paid_was != paid_is:
                extra = ""
                if paid_is == "AVAILABLE":
                    extra = f" {now['paid_price']}, next return {now['paid_return']}"
                alerts.append(
                    f"{where}: Single Pass {paid_was or '—'} → {paid_is or '—'}{extra}"
                )
            if multi_was != multi_is:
                extra = ""
                if multi_is == "AVAILABLE":
                    extra = f", next return {now['multi_return']}"
                alerts.append(
                    f"{where}: Multi Pass {multi_was or '—'} → {multi_is or '—'}{extra}"
                )
        else:  # drops / watchlist: only flips back to AVAILABLE
            if paid_is == "AVAILABLE" and paid_was != "AVAILABLE":
                alerts.append(
                    f"🎢 {where}: Single Pass AVAILABLE "
                    f"{now['paid_price']}, next return {now['paid_return']}"
                )
            if (
                mode == "watchlist"
                and multi_is == "AVAILABLE"
                and multi_was != "AVAILABLE"
            ):
                alerts.append(
                    f"🎢 {where}: Multi Pass return times open, "
                    f"next {now['multi_return']}"
                )
    return alerts


def notify(alerts):
    body = "\n".join(alerts)
    sent = False

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        req = urllib.request.Request(
            f"https://ntfy.sh/{urllib.parse.quote(topic)}",
            data=body.encode(),
            headers={
                "Title": "Lightning Lane alert",
                "Priority": "high",
                "Tags": "ferris_wheel",
            },
        )
        urllib.request.urlopen(req, timeout=30).read()
        print("Sent ntfy push")
        sent = True

    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("EMAIL_TO")
    if host and to:
        msg = MIMEText(body)
        msg["Subject"] = f"Lightning Lane alert ({len(alerts)})"
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
    cfg = load_json(CONFIG_FILE, {})
    park_filter = [p.lower() for p in cfg.get("parks", [])]
    prev = load_json(STATE_FILE, {})

    curr = {}
    for park in wdw_parks():
        if park_filter and not any(p in park["name"].lower() for p in park_filter):
            continue
        curr.update(snapshot(park))

    if not curr:
        print("No live data returned; keeping previous state")
        return

    if prev:
        alerts = diff_alerts(prev, curr, cfg)
        if alerts:
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
