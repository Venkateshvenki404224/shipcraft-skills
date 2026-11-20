#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import socket
import subprocess
import sys


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if check and r.returncode:
        sys.exit(f"lanes: git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def root():
    return git("rev-parse", "--show-toplevel")


def profile_path(r):
    for p in (os.environ.get("WORK_PROFILE"), os.path.join(r, ".work-profile", "work.json"), os.path.join(r, ".claude", "work.json")):
        if p and os.path.isfile(p if os.path.isabs(p) else os.path.join(r, p)):
            return p if os.path.isabs(p) else os.path.join(r, p)
    sys.exit("lanes: no /work profile found (.work-profile/work.json)")


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def lane_dir(r, issue):
    return os.path.join(os.path.dirname(r), f"{os.path.basename(r)}-lane-{issue}")


def fill(text, ports):
    for k, v in ports.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def lane_profile(prof, ports):
    cfg = prof.get("lanes") or {}
    env = {k: fill(str(v), ports) for k, v in (cfg.get("env") or {}).items()}
    prefix = ("env " + " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " ") if env else ""
    out = json.loads(json.dumps(prof))
    wrap = lambda c: f"{prefix}sh -c {shlex.quote(c)}" if prefix and c else c
    out["gate"] = [wrap(c) for c in prof.get("gate") or []]
    if out.get("e2e"):
        for k in ("cmd", "full"):
            if out["e2e"].get(k):
                out["e2e"][k] = wrap(out["e2e"][k])
    app = out.get("app") or {}
    if app:
        if cfg.get("url"):
            app["url"] = fill(cfg["url"], ports)
            app["check"] = f"curl -s -o /dev/null -w '%{{http_code}}' {app['url'].rstrip('/')}{cfg.get('health', '/')}"
        if app.get("start"):
            app["start"] = wrap(app["start"])
    out["lane"] = {"ports": ports, "env": env}
    return out


def cmd_add(a):
    r = root()
    prof = json.load(open(profile_path(r), encoding="utf-8"))
    cfg = prof.get("lanes") or {}
    if not cfg:
        sys.exit("lanes: the profile has no \"lanes\" section (url, env with {port}/{e2e_port}); add it first (references/setup.md, Lanes)")
    base = prof.get("base", "main")
    git("fetch", "--quiet", "origin", base, check=False)
    taken = {json.load(open(os.path.join(d, ".agent", "profile.json"))).get("lane", {}).get("ports", {}).get("port")
             for d in lanes_dirs(r) if os.path.isfile(os.path.join(d, ".agent", "profile.json"))}
    step = int(cfg.get("step", 10))
    k = 1
    while True:
        ports = {key: int(v) + k * step for key, v in (cfg.get("ports") or {"port": 8090, "e2e_port": 8099}).items()}
        if ports.get("port") not in taken and all(free(p) for p in ports.values()):
            break
        k += 1
    d = lane_dir(r, a.issue)
    if os.path.exists(d):
        sys.exit(f"lanes: {d} already exists")
    branch = f"{prof.get('branch_prefix', 'agent/')}{a.issue}-{a.slug}"
    git("worktree", "add", "-q", "-b", branch, d, a.from_ref or f"origin/{base}")
    os.makedirs(os.path.join(d, ".agent"), exist_ok=True)
    with open(os.path.join(d, ".agent", "profile.json"), "w", encoding="utf-8") as f:
        json.dump(lane_profile(prof, ports), f, indent=2)
    for name in cfg.get("copy", [".claude/settings.local.json"]):
        src, dst = os.path.join(r, name), os.path.join(d, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, "rb") as s, open(dst, "wb") as t:
                t.write(s.read())
    print(json.dumps({"issue": a.issue, "dir": d, "branch": branch, "ports": ports}))


def lanes_dirs(r):
    out = []
    for block in git("worktree", "list", "--porcelain").split("\n\n"):
        m = re.search(r"^worktree (.+)$", block, re.M)
        if m and re.search(r"-lane-[^/]+$", m.group(1)):
            out.append(m.group(1))
    return out


def cmd_list(a):
    r = root()
    for d in lanes_dirs(r):
        p = os.path.join(d, ".agent", "profile.json")
        lane = json.load(open(p)).get("lane", {}) if os.path.isfile(p) else {}
        branch = git("branch", "--show-current", cwd=d, check=False)
        dirty = len([l for l in git("status", "--short", cwd=d, check=False).splitlines() if l and not l.endswith(".agent/")])
        print(f"{d}  {branch}  ports {lane.get('ports')}  {dirty} changed file(s)")


def cmd_remove(a):
    r = root()
    d = lane_dir(r, a.issue)
    if not os.path.isdir(d):
        sys.exit(f"lanes: no lane for #{a.issue}")
    changed = [l for l in git("status", "--short", cwd=d, check=False).splitlines() if l.strip() and ".agent/" not in l]
    if changed and not a.force:
        sys.exit(f"lanes: {d} has {len(changed)} uncommitted change(s); commit or pass --force")
    git("worktree", "remove", "--force", d)
    print(f"removed {d}")


def main():
    p = argparse.ArgumentParser(description="Parallel /work lanes: one git worktree, branch and port set per independent issue.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("issue")
    ad.add_argument("--slug", required=True)
    ad.add_argument("--from", dest="from_ref", help="start the lane from this ref instead of origin/<base> (for example a chain branch)")
    sub.add_parser("list")
    rm = sub.add_parser("remove")
    rm.add_argument("issue")
    rm.add_argument("--force", action="store_true")
    a = p.parse_args()
    {"add": cmd_add, "list": cmd_list, "remove": cmd_remove}[a.cmd](a)


if __name__ == "__main__":
    main()
