#!/usr/bin/env python3
import argparse
import fnmatch
import json
import os
import subprocess
import sys

DEFAULT = [".work-profile/**", ".claude/work.json", ".github/workflows/**"]


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"protected: git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def changed(base):
    names = set(git("diff", "--name-only", f"{base}...HEAD").split())
    names |= set(git("diff", "--name-only", "HEAD").split())
    names |= set(git("ls-files", "--others", "--exclude-standard").split())
    deleted = set(git("diff", "--name-only", "--diff-filter=D", base).split())
    return sorted(names), deleted


def matches(path, pattern):
    if pattern.endswith("/**"):
        return path == pattern[:-3] or path.startswith(pattern[:-2])
    return fnmatch.fnmatchcase(path, pattern)


def profile_patterns(profile):
    if not profile or not os.path.isfile(profile):
        return []
    return json.load(open(profile, encoding="utf-8")).get("protected_paths") or []


def main():
    p = argparse.ArgumentParser(description="Fail when a run branch edits a protected path: the checks and config a branch is judged by.")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--profile", help="the /work profile; its protected_paths are added to the defaults")
    p.add_argument("--allow", action="append", default=[], help="a protected path the owner allowed for this run")
    a = p.parse_args()
    patterns = DEFAULT + profile_patterns(a.profile)
    files, deleted = changed(a.base)
    hits = [f for f in files if any(matches(f, pat) for pat in patterns) and not any(matches(f, al) for al in a.allow)]
    if not hits:
        print(f"protected: ok ({len(files)} changed file(s), {len(patterns)} protected pattern(s))")
        return
    for f in hits:
        print(f"  {'deleted' if f in deleted else 'changed'}  {f}")
    print(f"protected: FAIL: {len(hits)} protected file(s) changed. Revert them, or ask the owner to allow them for this run.")
    sys.exit(1)


if __name__ == "__main__":
    main()
