#!/usr/bin/env python3
"""Maintain <repo>/.agent/state.json, the /work run manifest: the stage table, and what scripts/board/wfboard.py shows.

    state.py init   --run agent/12-tour --name "Getting started tour" [--session <uuid>] [--issue 12] [--no-app]
    state.py step   <key> --phase Plan --title "Plan + approval" --status RUN [--who architect] [--summary "..."]
                    [--detail-file .agent/plan.md] [--artifact .agent/plan.md ...] [--deps plan,h1]
    state.py set    <key> --status DONE [--summary "..."]       # update an existing step
    state.py finish [--stopped]
    state.py show [--plain]                                    # stage table (markdown) for chat and /work status

Statuses: RUN DONE PASS FAIL CHANGES WAIT TODO SKIP STOPPED (WAIT = the owner's turn).
Writes atomically; never touches anything outside .agent/.
"""
import argparse
import json
import os
import subprocess
import sys

PHASES = ["Intake", "Plan", "Tests first", "Implement", "Gate + E2E", "Verify", "Agent QA", "UI + video", "Ship"]
STATUSES = {"RUN", "DONE", "PASS", "FAIL", "CHANGES", "WAIT", "TODO", "SKIP", "STOPPED"}
# The 18 stages of references/stages.md: (key, phase, title, who, deps). init writes them all as TODO.
STAGES = [
    ("intake", "Intake", "Request, branch, manifest", "orchestrator", []),
    ("stack", "Intake", "App up, logins saved", "orchestrator", ["intake"]),
    ("research", "Plan", "Research", "agents", ["intake"]),
    ("plan", "Plan", "Plan, tickets, test plan", "planner", ["research"]),
    ("approve", "Plan", "Approval agent", "approver", ["plan"]),
    ("h1", "Plan", "H1: owner approves the plan", "owner", ["approve"]),
    ("tests", "Tests first", "Tests written", "agents", ["h1"]),
    ("red", "Tests first", "Red run", "agent", ["tests"]),
    ("ui-before", "UI + video", "UI before screenshots", "agent", ["red"]),
    ("implement", "Implement", "Tickets in dependency waves", "agents", ["red"]),
    ("gate", "Gate + E2E", "Gate and end-to-end tests", "agent", ["implement"]),
    ("verify", "Verify", "Verify by risk tier", "agents", ["gate"]),
    ("qa", "Agent QA", "Agent QA per role, on video", "agents", ["verify"]),
    ("ui-after", "UI + video", "UI after screenshots and review", "agents", ["qa"]),
    ("qa-fix", "Agent QA", "QA fix round", "agent", ["qa"]),
    ("evidence", "Ship", "Evidence report", "agent", ["qa-fix"]),
    ("h2", "Ship", "H2: owner decides to ship", "owner", ["evidence"]),
    ("ship", "Ship", "Rebase, gate, ship checks, merge", "orchestrator", ["h2"]),
]
NO_APP = {"stack", "ui-before", "ui-after"}


def repo_root():
    try:
        return subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    except Exception:
        return os.getcwd()


PATH = os.path.join(repo_root(), ".agent", "state.json")


def load():
    if not os.path.isfile(PATH):
        sys.exit(f"{PATH} missing: run `state.py init` first")
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(m):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
        f.write("\n")
    os.replace(tmp, PATH)


def add_artifact(lst, rel):
    if rel and rel not in lst:
        lst.append(rel)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--run", required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--session")
    i.add_argument("--issue")
    i.add_argument("--no-app", action="store_true", help="the project has no running app: stack and UI stages start as SKIP")
    for name in ("step", "set"):
        s = sub.add_parser(name)
        s.add_argument("key")
        s.add_argument("--phase")
        s.add_argument("--title")
        s.add_argument("--status")
        s.add_argument("--who")
        s.add_argument("--summary")
        s.add_argument("--detail-file")
        s.add_argument("--artifact", action="append", default=[])
        s.add_argument("--deps")
    f = sub.add_parser("finish")
    f.add_argument("--stopped", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("--plain", action="store_true")
    a = ap.parse_args()

    if a.cmd == "init":
        if os.path.isfile(PATH):
            old = json.load(open(PATH, encoding="utf-8"))
            if old.get("run") != a.run and not old.get("finished"):
                sys.exit(f".agent/ belongs to unfinished run {old.get('run')!r}; refusing to overwrite")
        steps = [{"key": k, "num": k, "phase": ph, "title": t, "who": who, "deps": deps, "artifacts": [],
                  "status": "SKIP" if a.no_app and k in NO_APP else "TODO"} for k, ph, t, who, deps in STAGES]
        m = {"run": a.run, "name": a.name, "phases": PHASES, "steps": steps, "finished": False,
             "artifacts": [".agent/issue.md"]}
        if a.session:
            m["session"] = a.session
        if a.issue:
            m["issue"] = a.issue
        save(m)
        print(f"init {a.run}")
        return

    m = load()
    if a.cmd in ("step", "set"):
        st = next((s for s in m["steps"] if s.get("key") == a.key), None)
        if st is None:
            if a.cmd == "set":
                sys.exit(f"no step {a.key!r}")
            st = {"key": a.key, "num": a.key, "status": "TODO"}
            m["steps"].append(st)
        for k in ("phase", "title", "who", "summary"):
            if getattr(a, k):
                st[k] = getattr(a, k)
        if a.status:
            s = a.status.upper()
            if s not in STATUSES:
                sys.exit(f"bad status {s}; one of {sorted(STATUSES)}")
            st["status"] = s
        if a.detail_file:
            st["detail"] = open(os.path.join(repo_root(), a.detail_file), encoding="utf-8").read()[:20000]
        st.setdefault("artifacts", [])
        for rel in a.artifact:
            add_artifact(st["artifacts"], rel)
        if a.deps:
            st["deps"] = [d.strip() for d in a.deps.split(",") if d.strip()]
        save(m)
        print(f"{a.key}: {st.get('status')}")
    elif a.cmd == "finish":
        m["finished"] = True
        for s in m["steps"]:
            if s.get("status") == "RUN":
                s["status"] = "STOPPED"
        save(m)
        print("finished")
    elif a.cmd == "show":
        print(f"**{m.get('run')}** · {m.get('name')}{' · finished' if m.get('finished') else ''}\n")
        if a.plain:
            for s in m["steps"]:
                print(f"  {s.get('status', 'TODO'):8} {s.get('phase', ''):12} {s.get('key'):18} {s.get('summary', '')[:90]}")
        else:
            print("| # | status | phase | step | summary |\n|---|---|---|---|---|")
            for n, s in enumerate(m["steps"], 1):
                summ = str(s.get("summary", "")).replace("|", "¦").replace("\n", " ")[:120]
                print(f"| {n} | {s.get('status', 'TODO')} | {s.get('phase', '')} | {s.get('title') or s.get('key')} | {summ} |")
        waiting = [s["key"] for s in m["steps"] if s.get("status") == "WAIT"]
        if waiting:
            print("\nowner's turn: " + ", ".join(waiting))


if __name__ == "__main__":
    main()
