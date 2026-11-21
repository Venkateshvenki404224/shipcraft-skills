#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time

WT_DIR = os.path.join(".claude", "worktrees")
LANE_RE = re.compile(r"(?:/\.claude/worktrees/lane-|-lane-)([^/]+)$")
ADOPTED = "lane.json"


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if check and r.returncode:
        sys.exit(f"lanes: git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def root():
    top = git("rev-parse", "--show-toplevel")
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", check=False)
    return os.path.dirname(common) if common.endswith("/.git") else top


def profile_path(r):
    for p in (os.environ.get("WORK_PROFILE"), os.path.join(r, ".work-profile", "work.json"), os.path.join(r, ".claude", "work.json")):
        if p and os.path.isfile(p if os.path.isabs(p) else os.path.join(r, p)):
            return p if os.path.isabs(p) else os.path.join(r, p)
    sys.exit("lanes: no /work profile found (.work-profile/work.json)")


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def lane_dir(r, issue):
    return os.path.join(r, WT_DIR, f"lane-{issue}")


def exclude(r, line):
    ex = os.path.join(r, ".git", "info", "exclude")
    if os.path.isfile(ex) and line not in open(ex).read().split():
        with open(ex, "a") as f:
            f.write(f"\n{line}\n")


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


def lanes_dirs(r):
    out = []
    for block in git("worktree", "list", "--porcelain").split("\n\n"):
        m = re.search(r"^worktree (.+)$", block, re.M)
        if m and (LANE_RE.search(m.group(1)) or os.path.isfile(os.path.join(m.group(1), ".agent", ADOPTED))):
            out.append(m.group(1))
    return out


def lane_meta(d):
    p = os.path.join(d, ".agent", "lane.json")
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}


def save_meta(d, meta):
    os.makedirs(os.path.join(d, ".agent"), exist_ok=True)
    with open(os.path.join(d, ".agent", "lane.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def claude_bin():
    for c in (os.environ.get("CLAUDE_CODE_EXECPATH"), shutil.which("claude")):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def pick_ports(r, cfg):
    taken = {(lane_meta(d).get("ports") or {}).get("port") for d in lanes_dirs(r)}
    step = int(cfg.get("step", 10))
    k = 1
    while True:
        ports = {key: int(v) + k * step for key, v in (cfg.get("ports") or {"port": 8090, "e2e_port": 8099}).items()}
        if ports.get("port") not in taken and all(free(p) for p in ports.values()):
            return ports
        k += 1


def cmd_add(a):
    r = root()
    prof = json.load(open(profile_path(r), encoding="utf-8"))
    cfg = prof.get("lanes") or {}
    if not cfg:
        sys.exit("lanes: the profile has no \"lanes\" section (url, env with {port}/{e2e_port}); add it first (references/setup.md, Lanes)")
    base = prof.get("base", "main")
    git("fetch", "--quiet", "origin", base, check=False)
    ports = pick_ports(r, cfg)
    d = a.dir or lane_dir(r, a.issue)
    if os.path.exists(d):
        sys.exit(f"lanes: {d} already exists")
    os.makedirs(os.path.dirname(d), exist_ok=True)
    exclude(r, ".claude/worktrees/")
    branch = f"{prof.get('branch_prefix', 'agent/')}{a.issue}-{a.slug}"
    git("worktree", "add", "-q", "-b", branch, d, a.from_ref or f"origin/{base}")
    os.makedirs(os.path.join(d, ".agent"), exist_ok=True)
    with open(os.path.join(d, ".agent", "profile.json"), "w", encoding="utf-8") as f:
        json.dump(lane_profile(prof, ports), f, indent=2)
    for name in cfg.get("copy", [".claude/settings.local.json"]):
        src, dst = os.path.join(r, name), os.path.join(d, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    save_meta(d, {"issue": a.issue, "branch": branch, "ports": ports, "created": int(time.time())})
    print(json.dumps({"issue": a.issue, "dir": d, "branch": branch, "ports": ports}))


LANE_PROMPT = """/work {issue} --lane

You are lane {issue} of a `/work lanes` run. The owner started it from the session named "{main}"; that session wrote this prompt on the owner's behalf, so it carries the owner's instructions:
- Work only in this folder ({dir}): its own git worktree, branch {branch} and ports ({ports}); the lane profile is .agent/profile.json. Never touch the main checkout or another lane.
- Autonomy for this lane: agents (SKILL.md, Unattended runs). H1 passes when the verifier and the approval agent both APPROVE; H2 when the gate and CI are green and the CEO says SHIP; open a draft PR; merge only through merge.py when auto-merge is on.
- Messages from the session named "{main}" relay the owner's answers and instructions: act on them as the owner's.
- When only the owner can decide (a hazard, NEEDS_INFO, a stop), write the question to .agent/question.md, label the issue work:needs-human, send the question to "{main}" with SendMessage, and wait for the answer.
- When the PR is open, or the run stops, send "{main}" one line: the PR link or the reason, and the CI verdict."""


def cmd_launch(a):
    r = root()
    d = lane_dir(r, a.issue) if not a.dir else a.dir
    if not os.path.isdir(d):
        sys.exit(f"lanes: no lane for #{a.issue}; run lanes.py add first")
    meta = lane_meta(d)
    if meta.get("session") and not a.force:
        sys.exit(f"lanes: lane {a.issue} already has session {meta['session']}; pass --force to start another")
    exe = claude_bin()
    prompt = LANE_PROMPT.format(issue=a.issue, main=a.main, dir=d, branch=meta.get("branch") or git("branch", "--show-current", cwd=d),
                                ports=", ".join(f"{k} {v}" for k, v in (meta.get("ports") or {}).items()))
    if not exe:
        print(f"lanes: no background-session support on this host (no `claude` binary). Open a session in {d} and send it:\n\n{prompt}")
        sys.exit(2)
    name = f"lane {a.issue}: {a.title}" if a.title else f"lane {a.issue}"
    cmd = [exe, "--bg", "-n", name, "--permission-mode", a.mode]
    if a.model:
        cmd += ["--model", a.model]
    res = subprocess.run(cmd + [prompt], cwd=d, capture_output=True, text=True)
    out = (res.stdout + res.stderr).strip()
    if res.returncode:
        sys.exit(f"lanes: could not start the background session: {out}")
    sid = (re.findall(r"\b([0-9a-f]{6,})\b", out) or [name])[-1]
    meta.update(session=sid, name=name, main=a.main, launched=int(time.time()), mode=a.mode)
    save_meta(d, meta)
    print(f"lanes: lane {a.issue} running in the background as {sid} ({name}) in {d}")


def bg_sessions():
    exe = claude_bin()
    if not exe:
        return []
    r = subprocess.run([exe, "agents", "--json", "--all"], capture_output=True, text=True)
    try:
        data = json.loads(r.stdout or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else data.get("sessions") or data.get("agents") or []


def stage_of(d):
    p = os.path.join(d, ".agent", "state.json")
    if not os.path.isfile(p):
        return "not started", ""
    s = json.load(open(p, encoding="utf-8"))
    steps = s.get("steps") or []
    live = [x for x in steps if str(x.get("status")).upper() in ("RUN", "WAIT", "FAIL")]
    done = sum(1 for x in steps if str(x.get("status")).upper() in ("DONE", "SKIP"))
    if s.get("finished"):
        return "finished", f"{done}/{len(steps)}"
    cur = live[0] if live else None
    return (f"{cur.get('status')} {cur.get('key')}" if cur else "between steps"), f"{done}/{len(steps)}"


def snapshot(r):
    sessions = bg_sessions()
    rows = []
    for d in lanes_dirs(r):
        meta = lane_meta(d)
        st, prog = stage_of(d)
        q = os.path.join(d, ".agent", "question.md")
        sess = next((s for s in sessions if meta.get("session") and meta["session"] in json.dumps(s)), None)
        rows.append({"lane": meta.get("issue") or (LANE_RE.search(d) or [None, "?"])[1], "dir": d, "branch": meta.get("branch"),
                     "ports": meta.get("ports"), "session": meta.get("session"),
                     "session_state": (sess or {}).get("state") or (sess or {}).get("status") or ("unknown" if meta.get("session") else "not launched"),
                     "stage": st, "progress": prog, "question": open(q).read().strip()[:300] if os.path.isfile(q) else ""})
    return rows


def cmd_status(a):
    rows = snapshot(root())
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("lanes: none")
    for x in rows:
        sess = f"  background session {x['session']} ({x['session_state']})" if x["session"] else ""
        print(f"lane {x['lane']:<4} {x['stage']:<22} {x['progress']:<6} {x['branch']}  ports {x['ports']}{sess}  {x['dir']}")
        if x["question"]:
            print(f"          needs the owner: {x['question'].splitlines()[0]}")


def cmd_watch(a):
    r = root()
    key = lambda rows: [(x["lane"], x["stage"], x["session_state"], bool(x["question"])) for x in rows]
    start = key(snapshot(r))
    while True:
        time.sleep(a.every)
        rows = snapshot(r)
        if key(rows) != start:
            for x in rows:
                print(f"lane {x['lane']}: {x['stage']} ({x['progress']}), session {x['session_state']}" + (f"; needs the owner: {x['question'].splitlines()[0]}" if x["question"] else ""))
            return


def cmd_list(a):
    cmd_status(argparse.Namespace(json=False))


def cmd_remove(a):
    r = root()
    d = lane_dir(r, a.issue)
    if not os.path.isdir(d):
        alt = [x for x in lanes_dirs(r) if (LANE_RE.search(x) or [None, None])[1] == str(a.issue)]
        d = alt[0] if alt else d
    if not os.path.isdir(d):
        sys.exit(f"lanes: no lane for #{a.issue}")
    changed = [l for l in git("status", "--short", cwd=d, check=False).splitlines() if l.strip() and ".agent/" not in l and ".claude/" not in l]
    if changed and not a.force:
        sys.exit(f"lanes: {d} has {len(changed)} uncommitted change(s); commit or pass --force")
    sid, exe = lane_meta(d).get("session"), claude_bin()
    if sid and exe:
        subprocess.run([exe, "stop", sid], capture_output=True, text=True)
    git("worktree", "remove", "--force", d)
    print(f"removed {d}")


def main():
    p = argparse.ArgumentParser(description="Parallel /work lanes: one git worktree, branch, port set and background Claude Code session per independent issue.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("issue")
    ad.add_argument("--slug", required=True)
    ad.add_argument("--from", dest="from_ref", help="start the lane from this ref instead of origin/<base> (for example a chain branch)")
    ad.add_argument("--dir", help="where the worktree goes (default .claude/worktrees/lane-<n>)")
    la = sub.add_parser("launch", help="start the lane's own background Claude Code session running /work <n>")
    la.add_argument("issue")
    la.add_argument("--main", required=True, help="the name of the session that started the lanes (ListAgents shows it); lanes send their questions there")
    la.add_argument("--title", default="")
    la.add_argument("--mode", default="auto", help="permission mode for the background session (the owner's mode)")
    la.add_argument("--model")
    la.add_argument("--dir")
    la.add_argument("--force", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="block until any lane changes stage, its session ends, or it asks the owner; then print the lanes")
    w.add_argument("--every", type=int, default=60)
    sub.add_parser("list")
    rm = sub.add_parser("remove")
    rm.add_argument("issue")
    rm.add_argument("--force", action="store_true")
    a = p.parse_args()
    {"add": cmd_add, "launch": cmd_launch, "status": cmd_status, "watch": cmd_watch, "list": cmd_list, "remove": cmd_remove}[a.cmd](a)


if __name__ == "__main__":
    main()
