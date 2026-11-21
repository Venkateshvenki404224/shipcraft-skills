#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time

OUT = os.path.expanduser(os.environ.get("WORK_USAGE_FILE", "~/.claude/work-usage.json"))


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        data = {}
    limits = data.get("rate_limits")
    if limits:
        tmp = OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"at": int(time.time()), "rate_limits": limits, "model": (data.get("model") or {}).get("id")}, f)
        os.replace(tmp, OUT)
    nxt = os.environ.get("WORK_STATUSLINE_NEXT")
    if nxt:
        r = subprocess.run(nxt, shell=True, input=raw, capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        return
    five = (limits or {}).get("five_hour") or {}
    week = (limits or {}).get("seven_day") or {}
    parts = [(data.get("model") or {}).get("display_name") or ""]
    if five.get("used_percentage") is not None:
        left = max(0, int((five.get("resets_at", 0) - time.time()) // 60))
        parts.append(f"5h {five['used_percentage']:.0f}% (resets in {left // 60}h{left % 60:02d}m)")
    if week.get("used_percentage") is not None:
        parts.append(f"week {week['used_percentage']:.0f}%")
    print(" · ".join(p for p in parts if p))


if __name__ == "__main__":
    main()
