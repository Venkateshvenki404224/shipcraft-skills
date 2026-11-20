#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time


def checks(pr, repo):
    cmd = ["gh", "pr", "checks", str(pr), "--json", "name,state,bucket,link"]
    if repo:
        cmd += ["--repo", repo]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode and not r.stdout.strip():
        err = r.stderr.strip()
        if "no checks reported" in err:
            return []
        sys.exit(f"ci_wait: gh pr checks failed: {err}")
    return json.loads(r.stdout or "[]")


def main():
    p = argparse.ArgumentParser(description="Wait for a pull request's CI checks and report one verdict.")
    p.add_argument("pr")
    p.add_argument("--repo")
    p.add_argument("--timeout", type=int, default=1800, help="seconds to wait for every check to finish")
    p.add_argument("--appear", type=int, default=180, help="seconds to wait for the first check to show up")
    p.add_argument("--interval", type=int, default=15)
    a = p.parse_args()
    start = time.time()
    while True:
        rows = checks(a.pr, a.repo)
        waited = time.time() - start
        pending = [c for c in rows if c.get("bucket") in ("pending", None, "")]
        if not rows and waited < a.appear:
            time.sleep(a.interval)
            continue
        if not rows:
            print(f"none: no CI checks reported on PR {a.pr} after {int(waited)}s")
            sys.exit(2)
        if pending and waited < a.timeout:
            time.sleep(a.interval)
            continue
        failed = [c for c in rows if c.get("bucket") in ("fail", "cancel")]
        for c in rows:
            print(f"  {c.get('bucket', '?'):8} {c.get('name')}  {c.get('link') or ''}")
        if pending:
            print(f"pending: {len(pending)} check(s) still running after {int(waited)}s")
            sys.exit(3)
        if failed:
            print(f"red: {len(failed)} of {len(rows)} check(s) failed: " + ", ".join(c["name"] for c in failed))
            sys.exit(1)
        print(f"green: all {len(rows)} check(s) passed in {int(waited)}s")
        return


if __name__ == "__main__":
    main()
