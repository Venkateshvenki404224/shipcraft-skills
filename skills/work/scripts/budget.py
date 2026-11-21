#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

USAGE = os.path.expanduser(os.environ.get("WORK_USAGE_FILE", "~/.claude/work-usage.json"))
WINDOW = 5 * 3600
DEFAULT_PLAN = {"stop_at_percent": 85, "buffer_minutes": 15, "week_stop_at_percent": 95}


def profile(path):
    for p in (path, os.environ.get("WORK_PROFILE"), ".agent/profile.json", ".work-profile/work.json"):
        if p and os.path.isfile(p):
            return json.load(open(p, encoding="utf-8"))
    return {}


def clock(ts):
    if not ts:
        return "?"
    t = datetime.datetime.fromtimestamp(ts)
    return t.strftime("%H:%M") if ts - time.time() < 20 * 3600 else t.strftime("%a %d %b %H:%M")


def from_tap(max_age):
    if not os.path.isfile(USAGE):
        return None
    d = json.load(open(USAGE, encoding="utf-8"))
    if time.time() - d.get("at", 0) > max_age:
        return None
    return d.get("rate_limits") or None


def from_transcripts():
    root = os.path.expanduser("~/.claude/projects")
    now, stamps = time.time(), []
    for dp, _, fs in os.walk(root):
        for f in fs:
            fp = os.path.join(dp, f)
            if f.endswith(".jsonl") and now - os.path.getmtime(fp) < 2 * WINDOW:
                stamps.append(os.path.getmtime(fp))
                try:
                    with open(fp, "rb") as fh:
                        fh.seek(0, 0)
                        first = fh.readline()
                    t = json.loads(first or b"{}").get("timestamp")
                    if t:
                        stamps.append(datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp())
                except (ValueError, OSError):
                    pass
    stamps = sorted(s for s in stamps if now - s < 2 * WINDOW)
    if not stamps:
        return None
    start = stamps[0]
    for s in stamps:
        if s >= start + WINDOW:
            start = s
    return {"five_hour": {"used_percentage": None, "resets_at": int(start + WINDOW), "estimated": True}}


def main():
    p = argparse.ArgumentParser(description="Check the subscription's usage windows before starting a /work step, so a run pauses cleanly instead of being cut off.")
    p.add_argument("--need", type=int, default=30, help="minutes the next step is expected to take")
    p.add_argument("--profile")
    p.add_argument("--max-age", type=int, default=900, help="seconds the status line's numbers stay trusted")
    p.add_argument("--lanes", type=int, help="the lane cap: also print how many lanes may run now (1 above lanes_one_at_percent, 0 when stopping)")
    a = p.parse_args()
    plan = {**DEFAULT_PLAN, **(profile(a.profile).get("plan") or {})}
    lim = from_tap(a.max_age)
    source = "status line"
    if not lim:
        lim, source = from_transcripts(), "estimated from transcripts (install the status line tap for real numbers)"
    if not lim:
        print("budget: ok (no usage data; nothing in the last 10 hours)")
        return
    now = time.time()
    five, week = lim.get("five_hour") or {}, lim.get("seven_day") or {}
    reset = five.get("resets_at")
    left_min = max(0, int((reset - now) // 60)) if reset else None
    used = five.get("used_percentage")
    stop, why, resume_at = False, [], reset
    if used is not None:
        elapsed = max(1, WINDOW - (reset - now)) if reset else WINDOW
        rate = used / (elapsed / 60)
        projected = used + rate * a.need
        if used >= plan["stop_at_percent"]:
            stop, why = True, why + [f"5-hour window at {used:.0f}% (stop at {plan['stop_at_percent']}%)"]
        elif projected >= 100 - plan["buffer_minutes"] * rate:
            stop, why = True, why + [f"the next {a.need} min would take the 5-hour window to about {projected:.0f}%"]
    elif left_min is not None and plan.get("window_minutes"):
        if WINDOW // 60 - left_min + a.need > plan["window_minutes"] - plan["buffer_minutes"]:
            stop, why = True, why + [f"{WINDOW // 60 - left_min} min used of the {plan['window_minutes']} you set"]
    wu = week.get("used_percentage")
    if wu is not None and wu >= plan["week_stop_at_percent"]:
        stop, why, resume_at = True, why + [f"weekly window at {wu:.0f}% (resets {clock(week.get('resets_at'))})"], max(reset or 0, week.get("resets_at") or 0)
    facts = [f"5h {used:.0f}%" if used is not None else "5h usage unknown", f"resets {clock(reset)} ({left_min} min)" if reset else "", f"week {wu:.0f}%" if wu is not None else "", source]
    line = "; ".join(f for f in facts if f)
    if a.lanes is not None:
        one_at = plan.get("lanes_one_at_percent", 70)
        allowed = 0 if stop else (1 if used is not None and used >= one_at else a.lanes)
        print(f"lanes: {allowed} of {a.lanes} may run" + (f" (usage {used:.0f}% is over {one_at}%)" if allowed == 1 and a.lanes > 1 else ""))
    if stop:
        print(f"budget: stop: {'; '.join(why)}. {line}. Save the run state and stop; /work resume after {clock(resume_at)}.")
        sys.exit(3)
    print(f"budget: ok for {a.need} min. {line}")


if __name__ == "__main__":
    main()
