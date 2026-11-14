#!/usr/bin/env python3
"""Control room: a live, self-contained HTML page for a multi-agent project run with the Workflow tool.

Reads, for one Claude Code session (or all of them with --all-sessions):
  <claude config>/projects/<project>/<session>/subagents/workflows/wf_*/journal.jsonl   one per Workflow run
  <claude config>/projects/<project>/<session>/subagents/workflows/wf_*/agent-<id>.jsonl  model + timestamps
  <claude config>/projects/<project>/<session>/workflows/scripts/<name>-<run id>.js       run names
plus the project's Markdown deliverables, an optional health URL and docker compose project, and writes ONE
HTML file (data inlined) that reloads itself. Nothing else is written.

    python3 control_room.py --config control-room.json            # write once
    python3 control_room.py --config control-room.json --watch 10  # rewrite every 10 s until stopped
    python3 control_room.py --once --print                          # zero config: write + print a summary
    python3 control_room.py --config control-room.json --refresh 0  # static snapshot, e.g. to publish as an Artifact

Every key of the config is optional; see references/config.md.
"""
import argparse
import glob
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")

DEFAULTS = {
    "title": "Project control room",
    "subtitle": "",
    "team_note": "You · Claude (orchestrator)",
    "accent": "#0f766e",
    "accent_dark": "#2dd4bf",
    "refresh_seconds": 10,
    "stale_after_seconds": 1200,
    "output": "control-room.html",
    "stages": [],
    "roles": [],
    "default_role": "",
    "environment": {},
    "docs": {"root": ".", "include": ["**/*.md"], "exclude": ["**/node_modules/**", "**/.git/**", "**/.venv/**"]},
    "run_names": {},
    "superseded": {},
    "covered": {},
    "extra_agents": "",
    "include_runs": [],
}


# --------------------------------------------------------------------------------------------- session discovery

def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def project_dirs_for(start_dirs):
    """Claude Code keeps a session's files in <config>/projects/<slug of the folder the session started in>/.
    The session may have started in this folder or one above it (never the home folder or above)."""
    base = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
    home = os.path.realpath(os.path.expanduser("~"))
    seen, out = set(), []
    for start in start_dirs:
        for p in {os.path.abspath(start), os.path.realpath(start)}:
            while p and p != os.path.dirname(p) and os.path.realpath(p) != home:
                d = os.path.join(base, slug(p))
                if d not in seen and os.path.isdir(d):
                    seen.add(d)
                    out.append(d)
                p = os.path.dirname(p)
    return out


def session_dirs(project_dirs, session=None, all_sessions=False):
    """Session folders that hold Workflow runs. Default: the one with the newest journal."""
    if session and os.path.isdir(session):
        return [os.path.abspath(session)]
    found = []
    for pd in project_dirs:
        for sd in glob.glob(os.path.join(pd, "*", "subagents", "workflows")):
            sess = os.path.dirname(os.path.dirname(sd))
            if session and os.path.basename(sess) != session:
                continue
            js = glob.glob(os.path.join(sd, "wf_*", "journal.jsonl"))
            if js:
                found.append((max(os.path.getmtime(j) for j in js), sess))
    found.sort()
    if not found:
        return []
    return [s for _, s in found] if all_sessions else [found[-1][1]]


# --------------------------------------------------------------------------------------------- agents and runs

def agent_info(path):
    """First model seen, first timestamp and last-modified time of an agent transcript."""
    model, first, last = None, None, None
    try:
        with open(path, "rb") as fh:
            for i, raw in enumerate(fh):
                if model and i > 400:
                    break
                try:
                    j = json.loads(raw)
                except Exception:
                    continue
                ts = j.get("timestamp")
                if ts and not first:
                    first = ts
                msg = j.get("message")
                m = msg.get("model") if isinstance(msg, dict) else None
                if m and not model and not m.startswith("<"):
                    model = m
        last = os.path.getmtime(path)
    except (FileNotFoundError, NotADirectoryError):
        pass
    return model, first, last


def short_model(m):
    """claude-opus-5-5 -> Opus 5.5"""
    if not m:
        return ""
    m = m.replace("claude-", "")
    return re.sub(r"-(\d+)-(\d+).*$", r" \1.\2", m).title()


def run_names(session):
    """Run id -> workflow name, from the persisted scripts (<name>-<run id>.js, or meta.name inside)."""
    names = {}
    for p in glob.glob(os.path.join(session, "workflows", "scripts", "*.js")):
        b = os.path.basename(p)[:-3]
        m = re.match(r"(.*)-(wf_[a-z0-9-]+)$", b)
        if m:
            names[m.group(2)] = m.group(1)
    return names


def role_matcher(cfg):
    rules = []
    for r in cfg["roles"]:
        for pat in r.get("match", []):
            rules.append((re.compile(pat, re.I), r["key"]))

    def role_of(label):
        low = label or ""
        for rx, key in rules:
            if rx.search(low):
                return key
        if cfg["default_role"]:
            return cfg["default_role"]
        # zero config: the text before the first ':' is the role ("QA: run e2e" -> "qa")
        head = low.split(":", 1)[0].strip() if ":" in low else "agents"
        return slug(head.lower()).strip("-") or "agents"
    return role_of


def load_runs(sessions, cfg, now):
    role_of = role_matcher(cfg)
    names = {}
    for s in sessions:
        names.update(run_names(s))
    names.update(cfg["run_names"])
    runs = []
    dirs = [d for s in sessions for d in glob.glob(os.path.join(s, "subagents", "workflows", "wf_*"))]
    keep = [re.compile(p, re.I) for p in cfg.get("include_runs") or []]
    for d in sorted(dirs, key=os.path.getmtime):
        rid = os.path.basename(d)
        if keep and not any(k.search(names.get(rid, rid)) or k.search(rid) for k in keep):
            continue
        jp = os.path.join(d, "journal.jsonl")
        if not os.path.exists(jp):
            continue
        agents, order = {}, []
        for raw in open(jp, encoding="utf-8", errors="replace"):
            try:
                j = json.loads(raw)
            except Exception:
                continue
            t, aid = j.get("type"), j.get("agentId")
            if not aid:
                continue
            a = agents.setdefault(aid, {"id": aid, "label": "?", "phase": ""})
            if t == "started":
                a.update(label=j.get("label") or a["label"], phase=j.get("phase") or "", status="running")
                order.append(aid)
            elif t == "result":
                r = j.get("result")
                a["status"] = "failed" if r is None else "done"
                a["result"] = r
            elif t == "failed":
                a["status"] = "failed"
                a["result"] = j.get("error") or "The agent ended with an error before returning a result."
        superseded = cfg["superseded"].get(rid)
        for aid, a in agents.items():
            a.setdefault("status", "running")
            model, first, last = agent_info(os.path.join(d, f"agent-{aid}.jsonl"))
            a["model"], a["first"], a["last"] = short_model(model), first, last
            a["role"] = role_of(a.get("label"))
            if a["status"] == "running" and superseded:
                a["status"], a["result"] = "failed", "Run stopped: " + superseded
            # silent for too long: not running any more (usage limit, network drop, or the run was stopped)
            if a["status"] == "running" and (last is None or now - last > cfg["stale_after_seconds"]):
                a["status"] = "failed"
                a["result"] = ("Ended without a result (usage limit, network drop, or the run was stopped). "
                               "If a later attempt re-did this task, only that attempt is listed.")
        # retries: keep the latest attempt per label, count the attempts
        latest, attempts = {}, {}
        for aid in dict.fromkeys(order):
            base = re.sub(r" \(retry \d+\)$", "", agents[aid].get("label") or "")
            attempts[base] = attempts.get(base, 0) + 1
            latest[base] = aid
        kept = []
        for base, aid in latest.items():
            a = agents[aid]
            a["label"] = base
            if attempts[base] > 1:
                a["attempts"] = attempts[base]
            kept.append(a)
        name = names.get(rid, rid) + (" (stopped)" if superseded else "")
        runs.append({"id": rid, "name": name, "agents": kept, "mtime": os.path.getmtime(jp)})
    # across runs (a resumed or follow-up run re-does a task): keep the newest attempt of each label
    newest = {}
    for wi, wf in enumerate(runs):
        for a in wf["agents"]:
            newest[a["label"]] = (wi, a["id"])
    for wi, wf in enumerate(runs):
        wf["agents"] = [a for a in wf["agents"] if newest.get(a["label"]) == (wi, a["id"])]
        for a in wf["agents"]:
            if a["label"] in cfg["covered"] and a["status"] != "done":
                a["status"], a["result"] = "covered", cfg["covered"][a["label"]]
    return runs


def result_text(r):
    if r is None:
        return ""
    if isinstance(r, str):
        return r
    if not isinstance(r, dict):
        return json.dumps(r)[:4000]
    parts = []
    for k in ("verdict", "status", "summary", "estimate", "report_file"):
        v = r.get(k)
        if isinstance(v, str) and v:
            parts.append(v if k == "summary" else f"{k.replace('_', ' ').capitalize()}: {v}")
    for k in ("fixed", "not_fixed", "corrections", "findings", "defects"):
        v = r.get(k)
        if isinstance(v, list) and v:
            parts.append(f"{k.replace('_', ' ').capitalize()} ({len(v)}):\n" +
                         "\n".join("• " + (x if isinstance(x, str) else json.dumps(x))[:600] for x in v[:30]))
    return "\n\n".join(parts) or json.dumps(r)[:4000]


# --------------------------------------------------------------------------------------------- stages, docs, env

def stage_status(runs, cfg):
    seen, first_order = {}, []
    for wf in runs:
        for a in wf["agents"]:
            ph = a.get("phase") or "Other"
            if ph not in seen:
                first_order.append(ph)
            seen.setdefault(ph, []).append(a["status"])
    stages = cfg["stages"] or [{"title": p, "detail": "", "phases": [p]} for p in first_order]
    out = []
    for s in stages:
        sts = [x for p in s.get("phases", [s["title"]]) for x in seen.get(p, [])]
        state = "pending" if not sts else "active" if "running" in sts else "done"
        out.append({"title": s["title"], "detail": s.get("detail", ""), "state": state,
                    "agents": len(sts), "done": sum(1 for x in sts if x != "running")})
    return out


def roles_out(runs, cfg):
    if cfg["roles"]:
        return [{k: r.get(k, "") for k in ("key", "name", "model", "desc")} for r in cfg["roles"]]
    keys = list(dict.fromkeys(a["role"] for wf in runs for a in wf["agents"]))
    return [{"key": k, "name": k.replace("-", " ").title(), "model": "", "desc": ""} for k in keys]


def load_docs(cfg, base):
    dc = {**DEFAULTS["docs"], **(cfg.get("docs") or {})}
    if dc.get("enabled") is False:
        return []
    root = os.path.abspath(os.path.join(base, dc.get("root", ".")))
    paths = set()
    for pat in dc["include"]:
        paths.update(glob.glob(os.path.join(root, pat), recursive=True))
    docs = []
    for p in sorted(paths):
        rel = os.path.relpath(p, root)
        if any(fnmatch.fnmatch(rel, x) or fnmatch.fnmatch("/" + rel, x) for x in dc["exclude"]):
            continue
        if not os.path.isfile(p):
            continue
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception:  # noqa: BLE001
            continue
        if len(txt) > dc.get("max_bytes", 400_000):
            txt = txt[: dc.get("max_bytes", 400_000)] + "\n\n…(truncated)"
        title = next((ln.lstrip("# ").strip() for ln in txt.splitlines() if ln.startswith("#")), rel)
        docs.append({"path": rel, "title": title[:90], "size": len(txt), "mtime": os.path.getmtime(p), "md": txt})
    return docs


def env_status(cfg):
    env = cfg.get("environment") or {}
    if not env:
        return None
    out = {"label": env.get("label", "Environment"), "links": env.get("links", []), "notes": env.get("notes", []),
           "up": None, "detail": "", "containers": []}
    h = env.get("health")
    if h and h.get("url"):
        try:
            with urllib.request.urlopen(h["url"], timeout=h.get("timeout", 2)) as resp:
                body = resp.read(4096).decode(errors="replace")
            ok = (h.get("expect") or "") in body
            out["up"], out["detail"] = ok, (h.get("ok_text") or "healthy") if ok else body[:80]
        except Exception as e:  # noqa: BLE001
            out["up"], out["detail"] = False, type(e).__name__
    cp = env.get("compose_project")
    if cp:
        try:
            r = subprocess.run(["docker", "ps", "--filter", f"label=com.docker.compose.project={cp}",
                                "--format", "{{.Names}}|{{.Status}}"], capture_output=True, text=True, timeout=5)
            out["containers"] = [ln.split("|", 1) for ln in r.stdout.strip().splitlines() if "|" in ln]
            if out["up"] is None:
                out["up"] = bool(out["containers"])
                out["detail"] = f"{len(out['containers'])} containers up" if out["containers"] else "no containers"
        except Exception:  # noqa: BLE001
            pass
    return out


def load_extra(cfg, base):
    p = cfg.get("extra_agents")
    if not p:
        return []
    try:
        return json.load(open(os.path.join(base, p), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------------------------- main

def build(cfg, base, sessions):
    now = time.time()
    runs = load_runs(sessions, cfg, now)
    data = {
        "generated": now,
        "title": cfg["title"], "subtitle": cfg["subtitle"], "team_note": cfg["team_note"],
        "refresh": cfg["refresh_seconds"],
        "runs": [{**w, "agents": [{**a, "result": result_text(a.get("result"))} for a in w["agents"]]} for w in runs],
        "stages": stage_status(runs, cfg),
        "roles": roles_out(runs, cfg),
        "env": env_status(cfg),
        "docs": load_docs(cfg, base),
        "extra": load_extra(cfg, base),
    }
    page = open(TEMPLATE, encoding="utf-8").read()
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")  # noqa: E731
    color = lambda c, d: c if re.fullmatch(r"#[0-9a-fA-F]{3,8}", c or "") else d  # noqa: E731
    page = (page.replace("__TITLE__", esc(cfg["title"]))
                .replace("__ACCENT__", color(cfg["accent"], DEFAULTS["accent"]))
                .replace("__ACCENT_DARK__", color(cfg["accent_dark"], DEFAULTS["accent_dark"]))
                .replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
    return data, page


def summary(data):
    agents = [a for w in data["runs"] for a in w["agents"]] + data["extra"]
    c = {}
    for a in agents:
        c[a.get("status")] = c.get(a.get("status"), 0) + 1
    st = " · ".join(f"{s['title']}:{s['state']}" for s in data["stages"])
    return f"{len(data['runs'])} runs, {len(agents)} agents {c}; stages {st}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="control-room.json (every key optional)")
    ap.add_argument("--out", help="output HTML (default: config 'output', relative to the config's folder)")
    ap.add_argument("--project", action="append", help="<claude config>/projects/<slug>; repeatable. "
                    "Default: worked out from the config's folder and the current folder")
    ap.add_argument("--session", help="session id or session folder (default: the one with the newest run)")
    ap.add_argument("--all-sessions", action="store_true", help="merge the runs of every session of the project")
    ap.add_argument("--watch", type=float, metavar="SECONDS", help="rewrite the page every SECONDS until stopped")
    ap.add_argument("--once", action="store_true", help="write once and exit (the default without --watch)")
    ap.add_argument("--print", action="store_true", help="print a one-line summary after each write")
    ap.add_argument("--refresh", type=int, metavar="SECONDS", help="page reload interval; 0 = a static snapshot "
                    "(for publishing). Default: config 'refresh_seconds'")
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    base = os.getcwd()
    if args.config:
        base = os.path.dirname(os.path.abspath(args.config))
        user = json.load(open(args.config, encoding="utf-8"))
        cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
    if args.refresh is not None:
        cfg["refresh_seconds"] = args.refresh
    out = os.path.abspath(args.out) if args.out else os.path.normpath(os.path.join(base, cfg["output"]))
    projects = args.project or project_dirs_for([base, os.getcwd()])
    if not projects:
        sys.exit("no Claude Code project folder found; pass --project <claude config>/projects/<slug>")

    first = True
    while True:
        sessions = session_dirs(projects, args.session, args.all_sessions)
        if first and not sessions:
            print("no Workflow runs yet in " + ", ".join(projects) + " (the page will fill in when one starts)",
                  file=sys.stderr)
        data, page = build(cfg, base, sessions)
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(page)
        os.replace(tmp, out)
        if first:
            print(out, flush=True)
        if args.print:
            print(summary(data), flush=True)
        first = False
        if not args.watch:
            break
        time.sleep(max(2.0, args.watch))


if __name__ == "__main__":
    main()
