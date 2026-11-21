#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys

STAGES = {
    "queued": ("C5DEF5", "/work: queued in a chain or lanes"),
    "planning": ("0E8A16", "/work: planning"),
    "building": ("1D76DB", "/work: building and testing"),
    "in-review": ("FBCA04", "/work: PR open, waiting for review or merge"),
    "needs-human": ("D93F0B", "/work: an agent handed this to a person"),
    "paused": ("BFD4F2", "/work: paused (usage limit or network); resumes later"),
}
NOTE = {
    "queued": "Queued: /work will pick this up after the issues before it.",
    "planning": "Planning started: research, product brief, plan and review.",
    "building": "Plan approved; building: tests first, then the code, the gate and the reviews.",
    "in-review": "In review: {pr}. Merging it closes this issue.",
    "needs-human": "Needs you: {note}",
    "paused": "Paused: {note}",
}


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"issue_sync: gh {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def repo_args(repo):
    return ["--repo", repo] if repo else []


def cmd_stage(a):
    ra = repo_args(a.repo)
    color, desc = STAGES[a.stage]
    gh("label", "create", f"work:{a.stage}", "--color", color, "--description", desc, "--force", *ra, check=False)
    cur = json.loads(gh("issue", "view", a.issue, *ra, "--json", "labels,state").stdout)
    if cur["state"] != "OPEN":
        print(f"issue_sync: #{a.issue} is {cur['state'].lower()}; left as it is")
        return
    old = [l["name"] for l in cur["labels"] if l["name"].startswith("work:") and l["name"][5:] in STAGES and l["name"] != f"work:{a.stage}"]
    args = ["issue", "edit", a.issue, *ra, "--add-label", f"work:{a.stage}"]
    for l in old:
        args += ["--remove-label", l]
    gh(*args)
    if a.comment:
        body = NOTE[a.stage].format(pr=f"#{a.pr}" if a.pr else "the PR", note=a.note or "see the run")
        if a.note and a.stage not in ("needs-human", "paused"):
            body += f" {a.note}"
        gh("issue", "comment", a.issue, *ra, "--body", body)
    print(f"issue_sync: #{a.issue} -> work:{a.stage}" + (f" (removed {', '.join(old)})" if old else ""))


def cmd_link(a):
    ra = repo_args(a.repo)
    pr = json.loads(gh("pr", "view", a.pr, *ra, "--json", "body,baseRefName").stdout)
    body = pr.get("body") or ""
    if not re.search(rf"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#{a.issue}\b", body, re.I):
        gh("pr", "edit", a.pr, *ra, "--body", body.rstrip() + f"\n\nCloses #{a.issue}\n")
        print(f"issue_sync: PR #{a.pr} now says Closes #{a.issue}")
    else:
        print(f"issue_sync: PR #{a.pr} already closes #{a.issue}")
    default = json.loads(gh("repo", "view", *([a.repo] if a.repo else []), "--json", "defaultBranchRef").stdout)["defaultBranchRef"]["name"]
    if pr["baseRefName"] != default:
        print(f"issue_sync: PR #{a.pr} targets {pr['baseRefName']}, not {default}: GitHub closes #{a.issue} only on a merge into {default}; run `issue_sync.py closed {a.pr}` after a merge elsewhere")


def cmd_closed(a):
    ra = repo_args(a.repo)
    pr = json.loads(gh("pr", "view", a.pr, *ra, "--json", "state,body,closingIssuesReferences,mergedAt").stdout)
    if pr["state"] != "MERGED":
        sys.exit(f"issue_sync: PR #{a.pr} is not merged ({pr['state']})")
    nums = {i["number"] for i in pr.get("closingIssuesReferences") or []}
    nums |= {int(n) for n in re.findall(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", pr.get("body") or "", re.I)}
    for n in sorted(nums):
        st = json.loads(gh("issue", "view", str(n), *ra, "--json", "state").stdout)["state"]
        if st == "OPEN":
            gh("issue", "close", str(n), *ra, "--comment", f"Shipped in #{a.pr}{' ' + a.note if a.note else ''}.")
            print(f"issue_sync: closed #{n}")
        else:
            print(f"issue_sync: #{n} already closed")


def main():
    p = argparse.ArgumentParser(description="Keep a GitHub issue in step with its /work run: a work:<stage> label, a short comment per stage, Closes #n on the PR, and closing after a merge GitHub does not see.")
    p.add_argument("--repo")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage")
    s.add_argument("issue")
    s.add_argument("stage", choices=list(STAGES))
    s.add_argument("--pr")
    s.add_argument("--note")
    s.add_argument("--no-comment", dest="comment", action="store_false")
    l = sub.add_parser("link")
    l.add_argument("issue")
    l.add_argument("--pr", required=True)
    c = sub.add_parser("closed")
    c.add_argument("pr")
    c.add_argument("--note")
    a = p.parse_args()
    {"stage": cmd_stage, "link": cmd_link, "closed": cmd_closed}[a.cmd](a)


if __name__ == "__main__":
    main()
