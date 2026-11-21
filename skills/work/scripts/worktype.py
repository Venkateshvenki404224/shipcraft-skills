#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys

OFF_TEAM = {"pm": False, "ceo": False, "design": False, "senior": False}
DEFAULTS = {
    "chore": {
        "about": "a chore: config, deps, docs, refactor, CI; no product behaviour changes",
        "tier": "lean", "team": OFF_TEAM, "qa": False, "video": False, "ui_shots": True,
        "knobs": {"revisions": 0, "areas": 1, "outside": 0, "design_review": "off", "seniors": "none"},
        "models": {"plan": "sonnet", "approve": "sonnet", "verify": "sonnet", "work": "sonnet", "research": "haiku", "cheap": "haiku"},
        "budgets": {"build": 1, "qa": 0}, "minutes": 25,
    },
    "bug": {
        "about": "a bug: something that worked, or should, behaves wrong; a failing test reproduces it first",
        "tier": "lean", "team": OFF_TEAM, "qa": True, "video": False, "ui_shots": True,
        "knobs": {"revisions": 1, "areas": 2, "outside": 1, "design_review": "off", "seniors": "none"},
        "models": {"plan": "sonnet", "approve": "sonnet", "verify": "opus", "work": "sonnet", "research": "haiku", "cheap": "haiku"},
        "budgets": {"build": 2, "qa": 1}, "minutes": 45,
    },
    "feat": {
        "about": "a feature: new behaviour users will see or use",
        "tier": "lean", "team": {"pm": True, "ceo": True, "design": True, "senior": True}, "qa": True, "video": False, "ui_shots": True,
        "knobs": {},
        "models": {"plan": "sonnet", "approve": "sonnet", "verify": "opus", "work": "sonnet", "pm": "opus", "ceo": "opus", "design": "haiku", "senior": "sonnet", "research": "haiku", "cheap": "haiku"},
        "budgets": {"build": 2, "qa": 1}, "minutes": 100,
    },
}
LABELS = {"bug": ("bug", "defect", "regression", "fix"), "chore": ("chore", "documentation", "docs", "dependencies", "deps", "refactor", "ci", "tech-debt"),
          "feat": ("enhancement", "feature", "feat")}
PREFIX = {"bug": ("fix", "bug", "hotfix"), "chore": ("chore", "docs", "refactor", "ci", "build", "deps", "test"), "feat": ("feat", "feature")}


def profile(path):
    for p in (path, os.environ.get("WORK_PROFILE"), ".agent/profile.json", ".work-profile/work.json"):
        if p and os.path.isfile(p):
            return json.load(open(p, encoding="utf-8"))
    return {}


def presets(prof):
    out = json.loads(json.dumps(DEFAULTS))
    for t, v in (prof.get("work_types") or {}).items():
        out.setdefault(t, {}).update(v)
    avail = set(prof.get("available_models") or [])
    if avail:
        for v in out.values():
            v["models"] = {k: m for k, m in (v.get("models") or {}).items() if m in avail}
    return out


def classify(issue_file, labels):
    text = open(issue_file, encoding="utf-8").read() if issue_file and os.path.isfile(issue_file) else ""
    m = re.search(r"- Labels: (.*)", text)
    labels = [l.strip().lower() for l in (labels or (m.group(1).split(",") if m else [])) if l.strip() and l.strip() != "none"]
    for t, names in LABELS.items():
        hit = [l for l in labels if l in names or l.startswith(f"type:{t}") or l.startswith(f"kind/{t}")]
        if hit:
            return t, f"label {hit[0]}"
    tm = re.search(r"## Title\s*\n`{3,}text\n(.*)\n", text)
    title = (tm.group(1) if tm else "").strip().lower()
    for t, names in PREFIX.items():
        if re.match(rf"^({'|'.join(names)})(\(.+\))?!?:", title):
            return t, f"title starts with {title.split(':')[0]}:"
    return None, "no label or conventional title prefix; ask the owner"


def main():
    p = argparse.ArgumentParser(description="/work types: chore, bug or feat, each with a cheaper or fuller preset of models, team, stages and plan knobs.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify")
    c.add_argument("--issue", default=".agent/issue.md")
    c.add_argument("--labels", nargs="*")
    s = sub.add_parser("show")
    s.add_argument("type", nargs="?")
    s.add_argument("--profile")
    ap = sub.add_parser("apply")
    ap.add_argument("type")
    ap.add_argument("--profile")
    ap.add_argument("--file", default=".agent/overrides.json")
    a = p.parse_args()
    if a.cmd == "classify":
        t, why = classify(a.issue, a.labels)
        print(json.dumps({"type": t, "why": why}))
        return
    pre = presets(profile(a.profile))
    if a.cmd == "show":
        print(json.dumps(pre if not a.type else pre.get(a.type), indent=2))
        return
    if a.type not in pre:
        sys.exit(f"worktype: unknown type {a.type} (one of {', '.join(pre)})")
    cur = json.load(open(a.file, encoding="utf-8")) if os.path.isfile(a.file) else {}
    new = dict(cur)
    v = pre[a.type]
    for k in ("tier", "qa", "video", "ui_shots", "knobs", "budgets"):
        if k in v:
            new[k] = v[k]
    new["team"] = dict(v.get("team") or {})
    new["models"] = {**(cur.get("models") or {}), **(v.get("models") or {})}
    new["work_type"] = a.type
    os.makedirs(os.path.dirname(a.file) or ".", exist_ok=True)
    with open(a.file, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2)
    changed = sorted(k for k in set(new) | set(cur) if new.get(k) != cur.get(k))
    print(f"worktype: {a.type} ({v.get('about')}); about {v.get('minutes')} min; changed {', '.join(changed) or 'nothing'} in {a.file}")


if __name__ == "__main__":
    main()
