#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

FILE = ".work-chain.json"


def repo_root():
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.stdout.strip() or os.getcwd()


def path():
    return os.path.join(repo_root(), FILE)


def load():
    p = path()
    if not os.path.isfile(p):
        sys.exit("chain: no chain in this repo (start one with: chain.py start <issue> ...)")
    return json.load(open(p, encoding="utf-8"))


def save(c):
    p = path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)
    os.replace(tmp, p)
    exclude = os.path.join(repo_root(), ".git", "info", "exclude")
    if os.path.isfile(exclude) and FILE not in open(exclude).read().split():
        with open(exclude, "a") as f:
            f.write(f"\n{FILE}\n")


def item(c, n):
    for it in c["issues"]:
        if str(it["issue"]) == str(n):
            return it
    sys.exit(f"chain: issue {n} is not in this chain")


def base_for(c, it):
    i = c["issues"].index(it)
    if i == 0:
        return c["base"]
    prev = c["issues"][i - 1]
    if prev["status"] == "merged":
        return c.get("root") or "main"
    if prev["status"] != "shipped" or not prev.get("branch"):
        return None
    return prev["branch"]


def cmd_start(a):
    if os.path.isfile(path()):
        old = json.load(open(path(), encoding="utf-8"))
        if any(it["status"] in ("todo", "running") for it in old["issues"]) and not a.force:
            sys.exit(f"chain: an unfinished chain exists ({', '.join('#' + str(i['issue']) for i in old['issues'])}); finish it or pass --force")
    c = {"base": a.base, "base_pr": a.base_pr, "root": a.root, "stopped": None,
         "issues": [{"issue": str(n), "status": "todo", "branch": None, "pr": None, "note": ""} for n in a.issues]}
    save(c)
    print(f"chain: {' -> '.join('#' + str(n) for n in a.issues)} stacked on {a.base}")


def cmd_next(a):
    c = load()
    if c.get("stopped"):
        print(f"stopped: {c['stopped']}")
        sys.exit(3)
    for it in c["issues"]:
        if it["status"] == "running":
            print(f"running: #{it['issue']} on {it.get('branch')} (base {base_for(c, it)})")
            return
        if it["status"] == "todo":
            b = base_for(c, it)
            if not b:
                sys.exit("chain: the previous issue has not shipped; nothing can start")
            print(f"next: #{it['issue']} base {b}")
            return
    print("done: every issue in the chain shipped")
    sys.exit(4)


def cmd_begin(a):
    c = load()
    it = item(c, a.issue)
    it.update(status="running", branch=a.branch)
    save(c)
    print(f"running: #{a.issue} on {a.branch}")


def cmd_shipped(a):
    c = load()
    it = item(c, a.issue)
    it.update(status="shipped", branch=a.branch or it.get("branch"), pr=a.pr, note=a.note or "")
    save(c)
    print(f"shipped: #{a.issue} as PR #{a.pr} on {it['branch']}")


def cmd_merged(a):
    c = load()
    it = item(c, a.issue)
    it.update(status="merged", pr=a.pr or it.get("pr"), note=a.note or "auto-merged")
    save(c)
    print(f"merged: #{a.issue} (PR #{it['pr']}); the next issue starts from {c.get('root') or 'main'}")


def cmd_stop(a):
    c = load()
    it = item(c, a.issue)
    it.update(status="stopped", note=a.reason)
    c["stopped"] = f"#{a.issue}: {a.reason}"
    for later in c["issues"][c["issues"].index(it) + 1:]:
        if later["status"] == "todo":
            later["status"] = "skipped"
    save(c)
    print(f"stopped: #{a.issue}: {a.reason}")


def cmd_show(a):
    c = load()
    print(f"chain on {c['base']}{' (after PR #' + str(c['base_pr']) + ')' if c.get('base_pr') else ''}")
    for it in c["issues"]:
        pr = f" PR #{it['pr']}" if it.get("pr") else ""
        print(f"  #{it['issue']:<4} {it['status']:<8} {it.get('branch') or '':<40}{pr} {it.get('note') or ''}")
    if c.get("stopped"):
        print(f"stopped: {c['stopped']}")


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout.strip()


def cmd_merge(a):
    c = load()
    prs = ([c["base_pr"]] if c.get("base_pr") else []) + [it["pr"] for it in c["issues"] if it["status"] == "shipped" and it.get("pr")]
    here = os.path.dirname(os.path.abspath(__file__))
    for pr in prs:
        state = json.loads(gh("pr", "view", str(pr), "--json", "state,isDraft,baseRefName,headRefName,mergeable"))
        if state["state"] == "MERGED":
            print(f"merged already: PR #{pr}")
            continue
        steps = []
        if state["isDraft"]:
            steps.append(["gh", "pr", "ready", str(pr)])
        steps.append(["python3", os.path.join(here, "ci_wait.py"), str(pr)])
        steps.append(["gh", "pr", "merge", str(pr), "--merge", "--delete-branch"])
        steps.append(["python3", os.path.join(here, "issue_sync.py"), "closed", str(pr)])
        print(f"PR #{pr} ({state['headRefName']} -> {state['baseRefName']}):")
        for s in steps:
            print("  $ " + " ".join(s))
            if a.dry_run:
                continue
            r = subprocess.run(s, text=True)
            if r.returncode:
                print(f"chain merge: stopped at PR #{pr}: `{' '.join(s)}` exited {r.returncode}. Fix it, then run merge again; merged PRs are skipped.")
                sys.exit(1)
    print("dry run: nothing was changed" if a.dry_run else "chain merge: every PR merged in order")


def main():
    p = argparse.ArgumentParser(description="A /work chain: issues built one after another, each stacked on the previous issue's branch.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("issues", nargs="+")
    s.add_argument("--base", default="main", help="the branch the first issue builds on (an earlier run's branch when its PR is not merged yet)")
    s.add_argument("--base-pr", help="the open PR of --base, merged first by `merge`")
    s.add_argument("--root", default="main", help="the repo's base branch: an issue starts from it when the one before was auto-merged")
    s.add_argument("--force", action="store_true")
    sub.add_parser("next")
    b = sub.add_parser("begin")
    b.add_argument("issue")
    b.add_argument("--branch", required=True)
    sh = sub.add_parser("shipped")
    sh.add_argument("issue")
    sh.add_argument("--pr", required=True)
    sh.add_argument("--branch")
    sh.add_argument("--note")
    mg = sub.add_parser("merged", help="an issue's PR was auto-merged; the next issue starts from the root branch")
    mg.add_argument("issue")
    mg.add_argument("--pr")
    mg.add_argument("--note")
    st = sub.add_parser("stop")
    st.add_argument("issue")
    st.add_argument("--reason", required=True)
    sub.add_parser("show")
    m = sub.add_parser("merge", help="owner only: mark each PR ready, wait for CI, merge bottom-up and delete its branch so the next PR retargets")
    m.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    {"start": cmd_start, "next": cmd_next, "begin": cmd_begin, "shipped": cmd_shipped, "stop": cmd_stop,
     "show": cmd_show, "merge": cmd_merge, "merged": cmd_merged}[a.cmd](a)


if __name__ == "__main__":
    main()
