#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = "work:needs-human"


def sh(cmd, check=True, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=isinstance(cmd, str), **kw)
    if check and r.returncode:
        raise RuntimeError(f"{cmd if isinstance(cmd, str) else ' '.join(cmd)} exited {r.returncode}: {(r.stderr or r.stdout).strip()[-800:]}")
    return r


def load_profile(path):
    for p in (path, os.environ.get("WORK_PROFILE"), ".agent/profile.json", ".work-profile/work.json", ".claude/work.json"):
        if p and os.path.isfile(p):
            return json.load(open(p, encoding="utf-8")), p
    sys.exit("merge: no /work profile found")


def merge_mode(prof):
    over = ".agent/overrides.json"
    run = json.load(open(over, encoding="utf-8")).get("merge") if os.path.isfile(over) else None
    return run or (prof.get("ship") or {}).get("merge") or "owner"


def escalate(pr, repo, reason, decision):
    print(f"escalate: PR #{pr}: {reason}")
    sh(["gh", "pr", "ready", str(pr), *repo], check=False)
    sh(["gh", "label", "create", LABEL, "--color", "D93F0B", "--description", "/work: an agent handed this PR to a person", *repo], check=False)
    sh(["gh", "pr", "edit", str(pr), "--add-label", LABEL, *repo], check=False)
    body = f"**/work handed this PR to you.** {reason}"
    if decision and os.path.isfile(decision):
        body += "\n\n" + open(decision, encoding="utf-8").read().strip()
    sh(["gh", "pr", "comment", str(pr), "--body", body, *repo], check=False)
    sys.exit(4)


def main():
    p = argparse.ArgumentParser(description="Auto-merge one /work PR: sync it with the base, run the gate again, wait for CI, then gh pr merge. Anything that fails hands the PR to a person.")
    p.add_argument("pr")
    p.add_argument("--base", help="the PR's base branch (default: the PR's own base)")
    p.add_argument("--profile")
    p.add_argument("--repo", help="owner/name")
    p.add_argument("--decision", default=".agent/decision.md", help="the approver's file; its first line is APPROVE or ESCALATE")
    p.add_argument("--escalate", metavar="REASON", help="skip the merge and hand the PR to a person with this reason")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    repo = ["--repo", a.repo] if a.repo else []
    prof, prof_path = load_profile(a.profile)
    if a.escalate:
        escalate(a.pr, repo, a.escalate, a.decision)
    if merge_mode(prof) != "auto":
        sys.exit("merge: auto-merge is off (ship.merge in the profile, or merge in .agent/overrides.json); the owner merges")
    first = open(a.decision, encoding="utf-8").readline().strip() if os.path.isfile(a.decision) else ""
    if not first.startswith("APPROVE"):
        escalate(a.pr, repo, f"the approver did not approve ({first or 'no ' + a.decision})", a.decision)
    info = json.loads(sh(["gh", "pr", "view", str(a.pr), *repo, "--json", "state,isDraft,baseRefName,headRefName,mergeable"]).stdout)
    if info["state"] != "OPEN":
        sys.exit(f"merge: PR #{a.pr} is {info['state']}")
    base = a.base or info["baseRefName"]
    steps = [
        ("sync", f"git fetch -q origin {base} && git merge --no-edit origin/{base}"),
        *[(f"gate {i + 1}", c) for i, c in enumerate(prof.get("gate") or [])],
        *([("protected", f"python3 {HERE}/protected.py --base origin/{base} --profile {prof_path}")] if os.path.isfile(os.path.join(HERE, "protected.py")) else []),
        ("push", "git push -q"),
    ]
    for name, cmd in steps:
        print(f"  $ {cmd}")
        if a.dry_run:
            continue
        r = sh(cmd, check=False)
        if r.returncode:
            if name == "sync":
                sh("git merge --abort", check=False)
            escalate(a.pr, repo, f"`{name}` failed before the merge: {(r.stderr or r.stdout).strip()[-400:]}", a.decision)
    if a.dry_run:
        print("dry run: nothing was merged")
        return
    ci = sh(["python3", os.path.join(HERE, "ci_wait.py"), str(a.pr), *repo], check=False)
    print(ci.stdout.strip().splitlines()[-1] if ci.stdout.strip() else "ci: no output")
    if ci.returncode:
        escalate(a.pr, repo, f"CI is not green after the sync ({ci.stdout.strip().splitlines()[-1] if ci.stdout.strip() else 'exit ' + str(ci.returncode)})", a.decision)
    if info["isDraft"]:
        sh(["gh", "pr", "ready", str(a.pr), *repo])
    m = sh(["gh", "pr", "merge", str(a.pr), *repo, f"--{(prof.get('ship') or {}).get('merge_method', 'merge')}", "--delete-branch"], check=False)
    if m.returncode:
        escalate(a.pr, repo, f"gh pr merge failed: {(m.stderr or m.stdout).strip()[-400:]}", a.decision)
    print(f"merged: PR #{a.pr} into {base}")


if __name__ == "__main__":
    main()
