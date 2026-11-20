#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys


def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"branch_guard: git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def pr_state(branch):
    if not shutil.which("gh"):
        return None
    r = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number,state", "--limit", "1"],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    rows = json.loads(r.stdout or "[]")
    return rows[0] if rows else None


def verdict(base):
    git("fetch", "--quiet", "origin", base, check=False)
    ref = f"origin/{base}" if git("rev-parse", "--verify", "--quiet", f"origin/{base}", check=False).returncode == 0 else base
    cur = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if cur in (base, "HEAD"):
        return "new", f"on {cur}: commits go on a new branch from {ref}", ref
    pr = pr_state(cur)
    if pr and pr["state"] in ("MERGED", "CLOSED"):
        return "new", f"{cur} belongs to PR #{pr['number']}, which is {pr['state'].lower()}: commits go on a new branch from {ref}", ref
    ahead = git("rev-list", "--count", f"{ref}..HEAD").stdout.strip()
    if ahead == "0" and git("rev-parse", "HEAD").stdout.strip() != git("rev-parse", ref).stdout.strip():
        return "new", f"every commit on {cur} is already in {ref} (merged): commits go on a new branch from {ref}", ref
    if pr:
        return "ok", f"commit on {cur} (PR #{pr['number']} is open)", ref
    return "ok", f"commit on {cur} (no pull request yet)", ref


def main():
    p = argparse.ArgumentParser(description="Say whether the current branch may take a commit, and make a fresh one when it may not.")
    p.add_argument("--base", default="main")
    p.add_argument("--new", metavar="BRANCH", help="when the current branch is stale, switch to this new branch from the base, keeping uncommitted changes")
    a = p.parse_args()
    state, msg, ref = verdict(a.base)
    if state == "ok":
        print(f"ok: {msg}")
        return
    if not a.new:
        print(f"stale: {msg}. Run again with --new <branch>.")
        sys.exit(3)
    r = git("switch", "-c", a.new, ref, check=False)
    if r.returncode:
        sys.exit(f"branch_guard: could not create {a.new} from {ref}: {r.stderr.strip()}")
    print(f"new: switched to {a.new} from {ref} ({msg})")


if __name__ == "__main__":
    main()
