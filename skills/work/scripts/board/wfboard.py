#!/usr/bin/env python3
"""Run board for the /work skill: Claude Code workflow runs plus the /work run manifest.

Reads
  - the workflow run folders Claude Code writes under
    <claude config>/projects/<project>/<session>/subagents/workflows/wf_*/ (journal.jsonl + one agent-<id>.jsonl per agent);
  - the /work run manifest <repo>/.agent/state.json (owner gates, inline stages, UI screenshots, QA videos),
exports them every POLL seconds to <out>/data/, and serves <out>/dashboard.html on http://127.0.0.1:<port>/ (localhost only).

    python3 wfboard.py                          # the repo you are in; port 8765 (or the next free one)
    python3 wfboard.py --repo ~/code/acme --port 9000
    python3 wfboard.py --project ~/.claude/projects/-home-me-code-acme   # repeatable; default: worked out from --repo
    python3 wfboard.py --once                   # one export, print the summary, exit
    python3 wfboard.py --snapshot board.html    # one export, then one self-contained HTML file (for an Artifact)

Nothing is written to the repo: the board's files live in <tmp>/work-board-<repo slug>/ unless --out says otherwise.
"""
import argparse
import base64
import datetime as dt
import functools
import glob
import http.server
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVE = None  # set in main(): the folder that holds dashboard.html and data/
OUT = None    # SERVE/data
POLL = 2.0
MAX_RUNS = 8
MAX_EVENTS = 400

# USD per million tokens: input, output, 5 min cache write, 1 h cache write, cache read. The board labels cost as estimated.
# Unknown model ids fall back to their family (see price_of); edit these to your own rates.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 12.5, 20.0, 0.25),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 8.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 4.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.20, 0.01),
}
FAMILY_PRICES = {"fable": PRICES["claude-fable-5-1"], "opus": PRICES["claude-opus-5-5"],
                 "sonnet": PRICES["claude-sonnet-5-5"], "haiku": PRICES["claude-haiku-5-5"]}
SHORT_MODEL = {"fable": "fable", "opus": "opus", "sonnet": "sonnet", "haiku": "haiku"}


def price_of(model):
    if model in PRICES:
        return PRICES[model]
    for fam, p in FAMILY_PRICES.items():
        if model and fam in model:
            return p
    return (0, 0, 0, 0, 0)


def ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def short_model(m):
    for k, v in SHORT_MODEL.items():
        if m and k in m:
            return v
    return m or "?"


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def one_line(s, n=160):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def tool_summary(name, inp):
    inp = inp or {}
    if name == "Bash":
        return inp.get("description") or inp.get("command", "")
    for k in ("file_path", "path", "url", "query", "pattern", "description", "skill"):
        if inp.get(k):
            return str(inp[k])
    return json.dumps(inp)[:160]


# ---------------------------------------------------------------- agent files

_agent_cache = {}  # path -> ((mtime, size), parsed)


def parse_agent(path):
    st = os.stat(path)
    sig = (st.st_mtime, st.st_size)
    hit = _agent_cache.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    info = {"model": None, "first": None, "last": None, "cost": 0.0,
            "tokens_out": 0, "tokens_in": 0, "events": [], "prompt": None}
    seen_req = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = ts(d.get("timestamp", "")) if d.get("timestamp") else None
            if t:
                info["first"] = t if info["first"] is None else min(info["first"], t)
                info["last"] = t if info["last"] is None else max(info["last"], t)
            msg = d.get("message") if isinstance(d.get("message"), dict) else None
            typ = d.get("type")
            if typ == "user" and msg:
                content = msg.get("content")
                if info["prompt"] is None:
                    info["prompt"] = text_of(content)
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                            info["events"].append((t, "error", one_line(text_of(b.get("content")) or b.get("content"), 200)))
            elif typ == "assistant" and msg:
                if msg.get("model"):
                    info["model"] = msg["model"]
                req = d.get("requestId") or msg.get("id")
                u = msg.get("usage") or {}
                if u and req not in seen_req:
                    seen_req.add(req)
                    p = price_of(info["model"] or "")
                    cc = u.get("cache_creation") or {}
                    w5 = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0) or 0)
                    w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
                    inp = u.get("input_tokens", 0) or 0
                    out = u.get("output_tokens", 0) or 0
                    cr = u.get("cache_read_input_tokens", 0) or 0
                    info["cost"] += (inp * p[0] + out * p[1] + w5 * p[2] + w1 * p[3] + cr * p[4]) / 1e6
                    info["tokens_out"] += out
                    info["tokens_in"] += inp + w5 + w1 + cr
                for b in msg.get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        info["events"].append((t, b.get("name"), one_line(tool_summary(b.get("name"), b.get("input")), 200)))
                    elif b.get("type") == "text" and b.get("text", "").strip():
                        info["events"].append((t, "says", one_line(b["text"], 240)))
    _agent_cache[path] = (sig, info)
    return info


# ---------------------------------------------------------------- results


def to_md(v, depth=0):
    if v is None:
        return "_No result: the agent failed or was skipped._"
    if isinstance(v, str):
        s = v.strip()
        if s[:1] in "{[":
            try:
                return to_md(json.loads(s), depth)
            except Exception:
                pass
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, list):
        if not v:
            return "_none_"
        if all(not isinstance(x, (dict, list)) for x in v):
            return "\n".join(f"- {x}" for x in v)
        parts = []
        for i, x in enumerate(v, 1):
            if isinstance(x, dict):
                title = x.get("id") or x.get("title") or x.get("issue") or f"{i}"
                sub = x.get("title") if x.get("id") and x.get("title") else ""
                parts.append(f"{'#' * min(4, depth + 3)} {title}{' · ' + sub if sub else ''}")
                for k, val in x.items():
                    if k in ("id",) or (k == "title" and sub):
                        continue
                    body = to_md(val, depth + 1)
                    if "\n" in body:
                        parts.append(f"**{k}**\n\n{body}")
                    else:
                        parts.append(f"- **{k}**: {body}")
            else:
                parts.append(to_md(x, depth + 1))
        return "\n\n".join(parts)
    if isinstance(v, dict):
        lines = []
        if depth == 0:
            for k in ("approved", "pass"):
                if isinstance(v.get(k), bool):
                    lines.append("VERDICT: PASS" if v[k] else "VERDICT: CHANGES")
                    lines.append("")
                    break
        for k, val in v.items():
            if depth == 0 and k in ("approved", "pass"):
                continue
            lines.append(f"{'#' * min(4, depth + 2)} {k.replace('_', ' ')}")
            lines.append(to_md(val, depth + 1))
            lines.append("")
        return "\n".join(lines)
    return str(v)


def verdict(result):
    if isinstance(result, str) and result.strip()[:1] == "{":
        try:
            result = json.loads(result)
        except Exception:
            pass
    if isinstance(result, dict):
        for k in ("approved", "pass"):
            if isinstance(result.get(k), bool):
                return "PASS" if result[k] else "CHANGES"
    return "DONE"


# ---------------------------------------------------------------- runs


def script_info(session_dir, run_id):
    """Phase titles and .md artifact paths from the workflow script file."""
    phases, artifacts, worktrees, name = [], [], [], None
    for path in glob.glob(os.path.join(session_dir, "workflows", "scripts", f"*-{run_id}.js")):
        src = open(path, encoding="utf-8", errors="replace").read()
        m = re.search(r"name:\s*'([^']+)'", src)
        name = m.group(1) if m else None
        meta = re.search(r"phases:\s*\[(.*?)\]\s*,?\s*\}", src, re.S)
        if meta:
            phases = re.findall(r"title:\s*'([^']+)'", meta.group(1))
        consts = {}
        for k, val in re.findall(r"const (\w+) = '(/[^']+)'", src):
            consts[k] = val
        for k, base, rest in re.findall(r"const (\w+) = (\w+) \+ '([^']+)'", src):
            if base in consts:
                consts[k] = consts[base] + rest
        for k, val in consts.items():
            if val.endswith(".md"):
                artifacts.append(val)
            elif os.path.exists(os.path.join(val, ".git")):
                worktrees.append(val)
    return name, phases, artifacts, worktrees


def group_of(label, phase):
    pre, _, rest = label.partition(":")
    if phase == "Implement" and rest:
        return rest, pre
    if phase == "Approve":
        m = re.search(r"(\d+)$", label)
        step = ("review " if pre == "approve" else "revise ") + (m.group(1) if m else "")
        return "approval", step.strip()
    return label, pre


_written = {}


def write(path, text):
    if _written.get(path) == text:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    _written[path] = text


def export_run(run_dir, now):
    run_id = os.path.basename(run_dir)
    session_dir = os.path.dirname(os.path.dirname(os.path.dirname(run_dir)))
    name, phases, artifacts, worktrees = script_info(session_dir, run_id)
    agents, order, other = {}, [], []
    jpath = os.path.join(run_dir, "journal.jsonl")
    if os.path.exists(jpath):
        for line in open(jpath, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "started":
                aid = d.get("agentId")
                agents[aid] = {"id": aid, "label": d.get("label") or aid, "phase": d.get("phase") or "Other",
                               "done": False, "result": None}
                order.append(aid)
            elif d.get("type") == "result":
                a = agents.get(d.get("agentId"))
                if a:
                    a["done"] = True
                    a["result"] = d.get("result")
            elif d.get("type") not in ("launched",):
                other.append(d.get("type"))
    j_age = now - os.path.getmtime(jpath) if os.path.exists(jpath) else 1e9
    finished = any(t in ("completed", "complete", "finished", "done", "returned", "failed", "error", "aborted", "killed", "stopped") for t in other)
    # TaskStop leaves no marker in the journal; the orchestrator drops a ".stopped" file in the run dir instead
    finished = finished or os.path.exists(os.path.join(os.path.dirname(jpath), ".stopped"))
    # The Workflow tool writes the run's final status to <session>/workflows/<run_id>.json, not to the journal.
    # Without this, an agent superseded by a resume (started, never got a result) shows as running forever.
    try:
        wf_status = json.load(open(os.path.join(session_dir, "workflows", run_id + ".json"))).get("status")
    except Exception:
        wf_status = None
    finished = finished or (wf_status not in (None, "", "running", "pending", "queued"))

    base = os.path.join(OUT, run_id)
    tickets = {}
    groups, gindex = [], {}
    total_cost, first, last = 0.0, None, None
    for aid in order:
        a = agents[aid]
        apath = os.path.join(run_dir, f"agent-{aid}.jsonl")
        info = parse_agent(apath) if os.path.exists(apath) else {"model": None, "first": None, "last": None, "cost": 0.0, "tokens_out": 0, "tokens_in": 0, "events": [], "prompt": None}
        meta_path = os.path.join(run_dir, f"agent-{aid}.meta.json")
        if not info["model"] and os.path.exists(meta_path):
            try:
                info = dict(info, model=json.load(open(meta_path)).get("model"))
            except Exception:
                pass
        total_cost += info["cost"]
        if info["first"]:
            first = info["first"] if first is None else min(first, info["first"])
        if info["last"]:
            last = info["last"] if last is None else max(last, info["last"])
        status = ("FAIL" if a["result"] is None else verdict(a["result"])) if a["done"] else ("STOPPED" if finished else "RUN")
        if a["label"] == "tickets" and a["result"]:
            r = a["result"]
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except Exception:
                    r = {}
            for t in (r or {}).get("tickets", []) if isinstance(r, dict) else []:
                if isinstance(t, dict) and t.get("id"):
                    tickets[t["id"]] = t

        adir = os.path.join(base, "agents", aid)
        write(os.path.join(adir, "result.md"), to_md(a["result"]) if a["done"] else "_Still running._")
        ev = info["events"][-MAX_EVENTS:]
        act = [f"# Activity · {a['label']}", "",
               f"Model `{short_model(info['model'])}` · {info['tokens_out']:,} output tokens · ${info['cost']:.2f}", ""]
        if len(info["events"]) > MAX_EVENTS:
            act.append(f"_Showing the last {MAX_EVENTS} of {len(info['events'])} events._\n")
        act.append("| time | tool | detail |")
        act.append("|---|---|---|")
        for t, tool, detail in ev:
            when = dt.datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else ""
            act.append(f"| {when} | {tool} | {str(detail).replace('|', '¦')} |")
        write(os.path.join(adir, "activity.md"), "\n".join(act))
        write(os.path.join(adir, "prompt.md"), info["prompt"] or "_Prompt not recorded yet._")

        key, step = group_of(a["label"], a["phase"])
        gid = f"{a['phase']}/{key}"
        if gid not in gindex:
            gindex[gid] = len(groups)
            groups.append({"id": gid, "phase": a["phase"], "key": key, "agents": []})
        end = info["last"] if (a["done"] or finished) else now
        groups[gindex[gid]]["agents"].append({
            "id": aid, "label": a["label"], "step": step or a["label"], "status": status,
            "model": short_model(info["model"]), "cost": round(info["cost"], 4),
            "tokens_out": info["tokens_out"], "started": info["first"],
            "elapsed": (end - info["first"]) if (info["first"] and end) else 0,
            "ended": info["last"] if a["done"] else None,
            "last": (f"{info['events'][-1][1]}: {info['events'][-1][2]}" if info["events"] else ""),
        })

    # Tickets the run planned but has not started yet: shown as queued so the graph shows what comes next.
    impl_keys = {g["key"] for g in groups if g["phase"] == "Implement"}
    if not finished:
        for tid, t in tickets.items():
            if tid in impl_keys:
                continue
            pid = f"ticket-{re.sub(r'[^A-Za-z0-9_-]+', '-', tid)}"
            pdir = os.path.join(base, "agents", pid)
            write(os.path.join(pdir, "result.md"), f"# {tid} · {t.get('title') or ''}\n\n_Queued: not started yet._\n\n" + to_md(
                {k: v for k, v in t.items() if k not in ("id", "title")}))
            write(os.path.join(pdir, "activity.md"), "_Not started yet._")
            write(os.path.join(pdir, "prompt.md"), "_Not started yet._")
            groups.append({"id": f"Implement/{tid}", "phase": "Implement", "key": tid, "agents": [{
                "id": pid, "label": f"impl:{tid}", "step": "queued", "status": "TODO", "model": "queued", "cost": 0.0,
                "tokens_out": 0, "started": None, "elapsed": 0, "ended": None, "last": ""}]})

    for g in groups:
        ag = g["agents"]
        g["cost"] = round(sum(x["cost"] for x in ag), 4)
        g["running"] = any(x["status"] == "RUN" for x in ag)
        g["status"] = "RUN" if g["running"] else ag[-1]["status"]
        g["started"] = min((x["started"] for x in ag if x["started"]), default=None)
        g["ended"] = None if g["running"] else max((x["ended"] for x in ag if x.get("ended")), default=None)
        g["elapsed"] = sum(x["elapsed"] for x in ag)
        g["last"] = next((x["last"] for x in reversed(ag) if x["last"]), "")
        g["deps"] = []
        if g["phase"] == "Implement":
            t = tickets.get(g["key"]) or {}
            g["title"] = t.get("title") or g["key"]
            g["num"] = g["key"]
            g["deps"] = [f"Implement/{d}" for d in (t.get("depends_on") or t.get("deps") or []) if isinstance(d, str)]
        elif g["key"] == "approval":
            g["title"], g["num"] = "Opus plan approval", "approve"
        else:
            pre, _, rest = g["key"].partition(":")
            g["title"], g["num"] = (rest or g["key"]).replace("-", " "), pre

    arts = []
    for p in artifacts:
        if os.path.exists(p):
            dest = os.path.join(base, "artifacts", os.path.basename(p))
            write(dest, open(p, encoding="utf-8", errors="replace").read())
            arts.append({"name": os.path.basename(p), "path": f"{run_id}/artifacts/{os.path.basename(p)}", "source": p})
    for wt in worktrees:
        try:
            status = subprocess.run(["git", "-C", wt, "status", "--short"], capture_output=True, text=True, timeout=10).stdout
            stat = subprocess.run(["git", "-C", wt, "diff", "--stat"], capture_output=True, text=True, timeout=10).stdout
            branch = subprocess.run(["git", "-C", wt, "branch", "--show-current"], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            continue
        n = len([l for l in status.splitlines() if l.strip()])
        body = f"# Changes in the worktree\n\n`{wt}` on branch `{branch}`: {n} changed file(s), uncommitted.\n\n```\n{status or '(no changes yet)'}\n```\n\n## diff --stat\n\n```\n{stat or '(none)'}\n```\n"
        write(os.path.join(base, "artifacts", "changes.md"), body)
        arts.append({"name": f"changes ({n})", "path": f"{run_id}/artifacts/changes.md", "source": wt})

    running = sum(1 for a in agents.values() if not a["done"]) if not finished else 0
    queued = any(g["status"] == "TODO" for g in groups)
    # Nothing running and no journal write for 10 min: the script has returned (or died). With planned
    # tickets still unstarted that is a stall; otherwise the run is complete.
    state = "finished" if finished else ("running" if running else (
        ("stalled" if queued else "completed") if j_age > 600 else "between steps"))
    seen_phases = [g["phase"] for g in groups]
    cols = phases + [p for p in dict.fromkeys(seen_phases) if p not in phases]
    return {
        "id": run_id, "name": name or run_id, "state": state, "events": other,
        "phases": cols, "groups": groups, "artifacts": arts,
        "agents": len(agents), "running": running, "cost": round(total_cost, 2),
        "started": first, "updated": last, "elapsed": ((now if not finished else (last or now)) - first) if first else 0,
    }


def find_runs(project_dirs):
    runs = [r for d in project_dirs for r in glob.glob(os.path.join(d, "*", "subagents", "workflows", "wf_*"))]
    runs = [r for r in runs if os.path.isdir(r)]
    runs.sort(key=lambda r: os.path.getmtime(os.path.join(r, "journal.jsonl")) if os.path.exists(os.path.join(r, "journal.jsonl")) else os.path.getmtime(r), reverse=True)
    return runs[:MAX_RUNS]


# ---------------------------------------------------------------- pipeline runs
#
# A /work run has stages no workflow journal can show (the owner's gates, checks the orchestrator runs inline,
# screenshots, videos), and without the Workflow tool it launches agents with the Agent tool, so there is no
# journal at all. The orchestrator keeps a manifest at <repo>/.agent/state.json (scripts/state.py):
#   {"run": "agent/<n>-<slug>", "name": "...", "phases": ["Plan", ...],
#    "steps": [{"phase": "Plan", "key": "plan", "title": "...", "status": "RUN|DONE|PASS|FAIL|CHANGES|WAIT|TODO|SKIP",
#               "who": "owner", "detail": "markdown", "agents": [{"id": "<agentId>", "label": "...", "status": "..."}],
#               "artifacts": [".agent/plan.md"]}],
#    "artifacts": [".agent/issue.md"], "finished": false}
# Agent transcripts are found as <project>/<session>/subagents/agent-<id>.jsonl.

STALE = 900  # a running agent with no transcript write for this long is flagged
STATUSES = {"RUN", "DONE", "PASS", "FAIL", "CHANGES", "WAIT", "TODO", "SKIP", "STOPPED"}


def agent_file(project_dirs, aid):
    hits = [h for d in project_dirs for h in glob.glob(os.path.join(d, "*", "subagents", f"agent-{aid}.jsonl"))]
    return max(hits, key=os.path.getmtime) if hits else None


def final_text(path):
    """The agent's last assistant text block, in full (its report)."""
    last = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"assistant"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}
            if d.get("type") == "assistant":
                t = text_of(msg.get("content"))
                if t.strip():
                    last = t
    return last


def artifact_text(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    if path.endswith(".json"):
        return f"# {os.path.basename(path)}\n\n```json\n{src}\n```\n"
    return src


# UI verification layer (references/media.md, "UI before / after"): the skill's ui-snap tool writes
# <repo>/.agent/ui/{before,after,diff}/<id>.png + shots.json; the UI review agent writes .agent/ui/review.json:
#   {"verdict": "PASS|CHANGES", "summary": "...", "shots": {"<id>": {"verdict": "expected|unexpected|broken", "note": "..."}}}
# The images are served straight from the repo through a symlink data/<run>/ui -> <repo>/.agent/ui (no copying).
UI_VERDICTS = {"expected", "unexpected", "broken"}


def _ui_rel_ok(p):
    return isinstance(p, str) and p and not os.path.isabs(p) and ".." not in p.replace("\\", "/").split("/")


def export_ui(root, base, run_id):
    ui_dir = os.path.join(root, ".agent", "ui")
    shots_f = os.path.join(ui_dir, "shots.json")
    if not os.path.isfile(shots_f):
        return None
    d = json.load(open(shots_f, encoding="utf-8"))
    review = {}
    rf = os.path.join(ui_dir, "review.json")
    if os.path.isfile(rf):
        try:
            review = json.load(open(rf, encoding="utf-8"))
        except Exception as e:  # a half-written review must not hide the screenshots
            review = {"verdict": None, "summary": f"review.json unreadable: {e}"}
    link = os.path.join(base, "ui")
    if os.path.realpath(link) != os.path.realpath(ui_dir):
        os.makedirs(base, exist_ok=True)
        if os.path.islink(link) or os.path.isfile(link):
            os.remove(link)
        os.symlink(ui_dir, link)
    rv = review.get("shots") if isinstance(review.get("shots"), dict) else {}
    shots = []
    for s in d.get("shots") or []:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        r = rv.get(s["id"]) if isinstance(rv.get(s["id"]), dict) else {}
        out = {k: s.get(k) for k in ("id", "page", "role", "theme", "status", "changed_pct", "changed_pixels",
                                     "size_changed", "final_path_before", "final_path_after", "boxes")}
        out["viewport"] = (s.get("viewport") or {}).get("name") if isinstance(s.get("viewport"), dict) else s.get("viewport")
        for k in ("before", "after", "diff", "marked"):
            f = os.path.join(ui_dir, s[k]) if _ui_rel_ok(s.get(k)) else None
            out[k] = f"data/{run_id}/ui/{s[k]}?v={int(os.path.getmtime(f))}" if f and os.path.isfile(f) else None
        v = str(r.get("verdict") or "").lower()
        out["verdict"] = v if v in UI_VERDICTS else None
        out["note"] = r.get("note")
        shots.append(out)
    verdict = str(review.get("verdict") or "").upper() or None
    return {"run": d.get("run") or {}, "generated": d.get("generated"), "shots": shots,
            "verdict": verdict, "summary": review.get("summary")}


# Video layer: QA agents record with `agent-browser record` into <repo>/.agent/video/{demo,qa}-<role>.webm (+ .contact-sheet.png).
VIDEO_RE = re.compile(r"^(demo|qa)-(.+)$")


def export_video(root, base, run_id):
    vdir = os.path.join(root, ".agent", "video")
    if not os.path.isdir(vdir):
        return None
    files = sorted(f for f in os.listdir(vdir) if f.lower().endswith((".webm", ".mp4")))
    if not files:
        return None
    link = os.path.join(base, "video")
    if os.path.realpath(link) != os.path.realpath(vdir):
        os.makedirs(base, exist_ok=True)
        if os.path.islink(link) or os.path.isfile(link):
            os.remove(link)
        os.symlink(vdir, link)
    out = []
    for f in files:
        stem = f.rsplit(".", 1)[0]
        m = VIDEO_RE.match(stem)
        p = os.path.join(vdir, f)
        sheet = stem + ".contact-sheet.png"
        sp = os.path.join(vdir, sheet)
        out.append({"name": f, "kind": m.group(1) if m else "other", "role": m.group(2) if m else stem,
                    "src": f"data/{run_id}/video/{f}?v={int(os.path.getmtime(p))}", "bytes": os.path.getsize(p),
                    "sheet": f"data/{run_id}/video/{sheet}?v={int(os.path.getmtime(sp))}" if os.path.isfile(sp) else None})
    return out


def export_pipeline(manifest, project_dirs, now):
    m = json.load(open(manifest, encoding="utf-8"))
    root = os.path.dirname(os.path.dirname(manifest))
    run_id = "pl_" + re.sub(r"[^A-Za-z0-9_-]+", "-", m.get("run") or os.path.basename(root)).strip("-")[:48]
    base = os.path.join(OUT, run_id)
    finished = bool(m.get("finished"))
    groups, arts = [], []
    total_cost, first, last, n_agents, n_running = 0.0, None, None, 0, 0

    def add_art(rel, label=None):
        p = os.path.join(root, rel)
        if os.path.isfile(p) and not any(a["source"] == p for a in arts):
            name = label or os.path.basename(p)
            write(os.path.join(base, "artifacts", os.path.basename(p) + ".md"), artifact_text(p))
            arts.append({"name": name, "path": f"{run_id}/artifacts/{os.path.basename(p)}.md", "source": p})

    for rel in m.get("artifacts", []):
        add_art(rel)

    for i, s in enumerate(m.get("steps", [])):
        status = str(s.get("status", "TODO")).upper()
        status = status if status in STATUSES else "TODO"
        key = s.get("key") or f"step{i}"
        entries = []
        for a in s.get("agents") or []:
            aid = a.get("id")
            path = agent_file(project_dirs, aid) if aid else None
            info = parse_agent(path) if path else {"model": None, "first": None, "last": None, "cost": 0.0,
                                                   "tokens_out": 0, "tokens_in": 0, "events": [], "prompt": None}
            ast = str(a.get("status") or status).upper()
            ast = ast if ast in STATUSES else status
            if finished and ast == "RUN":
                ast = "STOPPED"
            n_agents += 1
            n_running += ast == "RUN"
            total_cost += info["cost"]
            if info["first"]:
                first = info["first"] if first is None else min(first, info["first"])
            if info["last"]:
                last = info["last"] if last is None else max(last, info["last"])
            lastline = f"{info['events'][-1][1]}: {info['events'][-1][2]}" if info["events"] else ""
            if ast == "RUN" and path and now - os.path.getmtime(path) > STALE:
                lastline = f"(no activity for {int((now - os.path.getmtime(path)) // 60)} min) " + lastline
            adir = os.path.join(base, "agents", aid)
            report = final_text(path) if path and ast != "RUN" else None
            write(os.path.join(adir, "result.md"), report or ("_Still running._" if ast == "RUN" else "_No report text._"))
            act = [f"# Activity · {a.get('label') or aid}", "",
                   f"Model `{short_model(info['model'])}` (`{info['model'] or '?'}`) · {info['tokens_out']:,} output tokens · ${info['cost']:.2f}", "",
                   "| time | tool | detail |", "|---|---|---|"]
            for t, tool, detail in info["events"][-MAX_EVENTS:]:
                when = dt.datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else ""
                act.append(f"| {when} | {tool} | {str(detail).replace('|', '¦')} |")
            write(os.path.join(adir, "activity.md"), "\n".join(act))
            write(os.path.join(adir, "prompt.md"), info["prompt"] or "_Prompt not recorded yet._")
            end = now if ast == "RUN" else info["last"]
            entries.append({"id": aid, "label": a.get("label") or key, "step": a.get("label") or key, "status": ast,
                            "model": short_model(info["model"] or a.get("model")), "cost": round(info["cost"], 4),
                            "tokens_out": info["tokens_out"], "started": info["first"],
                            "elapsed": (end - info["first"]) if (info["first"] and end) else 0,
                            "ended": None if ast == "RUN" else info["last"], "last": lastline})
        if not entries:
            # A step with no agent: an owner gate, or a check the orchestrator runs itself.
            sid = f"step-{re.sub(r'[^A-Za-z0-9_-]+', '-', key)}"
            detail = s.get("detail") or ""
            detail = "\n".join(detail) if isinstance(detail, list) else str(detail)
            write(os.path.join(base, "agents", sid, "result.md"), f"# {s.get('title') or key}\n\n{detail or '_Nothing recorded yet._'}")
            write(os.path.join(base, "agents", sid, "activity.md"), f"_No agent: this step is done by the {s.get('who') or 'orchestrator'}._")
            write(os.path.join(base, "agents", sid, "prompt.md"), "_No prompt._")
            n_running += status == "RUN"
            entries.append({"id": sid, "label": key, "step": key, "status": status, "model": s.get("who") or "orchestrator",
                            "cost": 0.0, "tokens_out": 0, "started": None, "elapsed": 0,
                            "last": one_line(s.get("summary") or detail, 200)})
        for rel in s.get("artifacts") or []:
            add_art(rel)
        run_any = any(e["status"] == "RUN" for e in entries)
        groups.append({"id": f"{s.get('phase', 'Other')}/{key}", "phase": s.get("phase", "Other"), "key": key,
                       "agents": entries, "cost": round(sum(e["cost"] for e in entries), 4), "running": run_any,
                       "status": "RUN" if run_any else status,
                       "started": min((e["started"] for e in entries if e["started"]), default=None),
                       "elapsed": sum(e["elapsed"] for e in entries),
                       "ended": None if run_any else max((e["ended"] for e in entries if e.get("ended")), default=None),
                       "last": s.get("summary") or next((e["last"] for e in reversed(entries) if e["last"]), ""),
                       # optional "deps": ["<step key>" | "<phase>/<key>"] in the manifest; without it the board
                       # links each phase to the one before it
                       "deps": [d for d in (s.get("deps") or []) if isinstance(d, str)],
                       "title": s.get("title") or key, "num": s.get("num") or key})

    # The orchestrating session itself (the main transcript): its cost is part of the run's cost.
    sess = m.get("session")
    spath = next((p for d in project_dirs for p in [os.path.join(d, f"{sess}.jsonl")] if os.path.isfile(p)), None) if sess else None
    if spath:
        info = parse_agent(spath)
        total_cost += info["cost"]
        groups.insert(0, {"id": "Orchestrator/main", "phase": m.get("phases", ["Orchestrator"])[0], "key": "main",
                          "agents": [{"id": f"session-{sess[:8]}", "label": "orchestrator", "step": "main",
                                      "status": "STOPPED" if finished else "RUN", "model": short_model(info["model"]),
                                      "cost": round(info["cost"], 4), "tokens_out": info["tokens_out"],
                                      "started": info["first"], "elapsed": ((info["last"] or now) - info["first"]) if info["first"] else 0,
                                      "last": ""}],
                          "cost": round(info["cost"], 4), "running": not finished, "status": "STOPPED" if finished else "RUN",
                          "started": info["first"], "elapsed": ((info["last"] or now) - info["first"]) if info["first"] else 0,
                          "last": f"main session · {info['tokens_out']:,} output tokens (includes work outside this run)",
                          "title": "orchestrator session", "num": "main"})
        sdir = os.path.join(base, "agents", f"session-{sess[:8]}")
        write(os.path.join(sdir, "result.md"), "_The orchestrating session. Its cost covers the whole conversation, including work outside this run._")
        write(os.path.join(sdir, "activity.md"), "\n".join(
            ["# Activity · orchestrator", "", "| time | tool | detail |", "|---|---|---|"] +
            [f"| {dt.datetime.fromtimestamp(t).strftime('%H:%M:%S') if t else ''} | {tool} | {str(d).replace('|', '¦')} |"
             for t, tool, d in info["events"][-MAX_EVENTS:]]))
        write(os.path.join(sdir, "prompt.md"), "_Main session._")
        first = info["first"] if first is None or (info["first"] and info["first"] < first) else first
        last = info["last"] if last is None or (info["last"] and info["last"] > last) else last

    waiting = any(g["status"] == "WAIT" for g in groups)
    state = "finished" if finished else ("running" if n_running else ("waiting on owner" if waiting else "between steps"))
    cols = list(m.get("phases") or []) + [p for p in dict.fromkeys(g["phase"] for g in groups) if p not in (m.get("phases") or [])]
    return {"id": run_id, "name": m.get("name") or m.get("run") or run_id, "state": state, "events": [],
            "phases": cols, "groups": groups, "artifacts": arts, "agents": n_agents, "running": n_running,
            "ui": export_ui(root, base, run_id),
            "videos": export_video(root, base, run_id),
            "cost": round(total_cost, 2), "started": first, "updated": last,
            "elapsed": ((now if not finished else (last or now)) - first) if first else 0,
            "_mtime": os.path.getmtime(manifest)}


def export_once(project_dirs, pipeline_globs):
    now = time.time()
    try:
        runs = []
        pl = sorted({p for g in pipeline_globs for p in glob.glob(os.path.expanduser(g))}, key=os.path.getmtime, reverse=True)
        for p in pl[:MAX_RUNS]:
            try:
                runs.append(export_pipeline(p, project_dirs, now))
            except Exception as e:  # a half-written manifest must not take the board down
                runs.append({"id": "pl_" + os.path.basename(os.path.dirname(os.path.dirname(p))), "name": p, "state": "error",
                             "error": f"{p}: {e}", "phases": [], "groups": [], "artifacts": [], "agents": 0, "running": 0,
                             "cost": 0, "elapsed": 0})
        for r in find_runs(project_dirs):
            try:
                runs.append(export_run(r, now))
            except Exception as e:  # keep the board alive on a bad file
                runs.append({"id": os.path.basename(r), "name": os.path.basename(r), "state": "error", "error": str(e),
                             "phases": [], "groups": [], "artifacts": [], "agents": 0, "running": 0, "cost": 0, "elapsed": 0})
        state = {"generated": now, "project": project_dirs, "runs": runs}
    except Exception as e:
        state = {"generated": now, "error": str(e), "runs": []}
    write(os.path.join(OUT, "state.json"), json.dumps(state))
    return state


def loop(project_dirs, pipeline_globs):
    while True:
        export_once(project_dirs, pipeline_globs)
        time.sleep(POLL)


# ---------------------------------------------------------------- snapshot (one self-contained HTML file)
#
# For sessions where nobody can open localhost (a cloud session): every file the page would fetch is inlined as
# window.BOARD_SNAPSHOT, and screenshots / contact sheets / videos become data: URIs while they fit the budget.
# dashboard.html reads the snapshot instead of polling when it is present.

SNAPSHOT_BUDGET = 12 * 1024 * 1024  # bytes of embedded media; the page must stay well under 16 MB


def _media_uri(src, budget):
    """data/<run>/ui/x.png?v=1 -> data: URI, or None when the file is missing or over the budget."""
    if not src or not isinstance(src, str) or src.startswith("data:image") or src.startswith("data:video"):
        return src, 0
    p = os.path.join(SERVE, src.split("?", 1)[0])
    if not os.path.isfile(p):
        return None, 0
    size = os.path.getsize(p)
    if size * 4 // 3 > budget:
        return None, 0
    mime = mimetypes.guess_type(p)[0] or ("video/webm" if p.endswith(".webm") else "application/octet-stream")
    with open(p, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii"), size * 4 // 3


def snapshot(state, dest, repo):
    budget, skipped = SNAPSHOT_BUDGET, 0
    # A snapshot is meant to be published: keep local folder names (and so the user name) out of it.
    state["project"] = []
    home = os.path.expanduser("~")
    for run in state.get("runs", []):
        for a in run.get("artifacts") or []:
            src = str(a.get("source") or "")
            a["source"] = os.path.relpath(src, repo) if src.startswith(repo + os.sep) else os.path.basename(src)
        if run.get("error"):
            run["error"] = run["error"].replace(repo, ".").replace(home, "~")
        ui = run.get("ui") or {}
        # changed shots first: they are what the owner needs to see
        for s in sorted(ui.get("shots") or [], key=lambda s: s.get("status") == "unchanged"):
            for k in ("marked", "before", "after", "diff"):
                uri, used = _media_uri(s.get(k), budget)
                skipped += uri is None and bool(s.get(k))
                s[k], budget = uri, budget - used
        for v in run.get("videos") or []:
            uri, used = _media_uri(v.get("sheet"), budget)
            v["sheet"], budget = uri, budget - used
            uri, used = _media_uri(v.get("src"), budget)
            if uri is None:
                v["note"] = f"Not embedded (size budget). In the repo: .agent/video/{v.get('name')}"
                skipped += 1
            v["src"], budget = uri, budget - used
    files = {"data/state.json": json.dumps(state)}
    for dirpath, _dirs, names in os.walk(OUT):  # does not follow the ui/ and video/ symlinks
        for n in names:
            if n.endswith(".md"):
                p = os.path.join(dirpath, n)
                files[os.path.relpath(p, SERVE).replace(os.sep, "/")] = open(p, encoding="utf-8", errors="replace").read()
    blob = json.dumps({"generated": state.get("generated"), "files": files}).replace("</", "<\\/")
    page = open(os.path.join(HERE, "dashboard.html"), encoding="utf-8").read()
    page = page.replace("<script>", f"<script>window.BOARD_SNAPSHOT = {blob};</script>\n<script>", 1)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(page)
    return os.path.getsize(dest), skipped


# ---------------------------------------------------------------- where things are


def git_root(path):
    try:
        return subprocess.check_output(["git", "-C", path, "rev-parse", "--show-toplevel"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return os.path.abspath(path)


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def project_dirs_for(repo, cwd):
    """Claude Code keeps a session's transcripts in <config>/projects/<slug of the folder the session started in>/.
    The session may have started in the repo or in a folder above it, so check the repo, its parents (not the home
    folder or above) and the current folder."""
    base = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
    home = os.path.realpath(os.path.expanduser("~"))
    seen, out = set(), []
    for start in (repo, cwd):
        for p in {os.path.abspath(start), os.path.realpath(start)}:
            while p and p != os.path.dirname(p) and os.path.realpath(p) != home:
                d = os.path.join(base, slug(p))
                if d not in seen and os.path.isdir(d):
                    seen.add(d)
                    out.append(d)
                p = os.path.dirname(p)
    return out


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    global SERVE, OUT
    ap = argparse.ArgumentParser(description="Run board for the /work skill")
    ap.add_argument("--repo", default=".", help="the repository whose .agent/state.json to show (default: the one you are in)")
    ap.add_argument("--port", type=int, default=8765, help="first port to try; the next 20 are tried when it is taken")
    ap.add_argument("--project", action="append", default=None,
                    help="Claude Code project folder(s) with the session transcripts; repeatable; default: worked out from --repo")
    ap.add_argument("--pipeline", action="append", default=None,
                    help="glob of run manifests; repeatable; default <repo>/.agent/state.json")
    ap.add_argument("--out", help="folder for the board's files (default: <tmp>/work-board-<repo slug>)")
    ap.add_argument("--once", action="store_true", help="export once, print a summary, exit")
    ap.add_argument("--snapshot", metavar="FILE", help="export once and write one self-contained HTML file")
    args = ap.parse_args()

    repo = git_root(args.repo)
    SERVE = os.path.abspath(args.out) if args.out else os.path.join(tempfile.gettempdir(), "work-board" + slug(repo)[:80])
    OUT = os.path.join(SERVE, "data")
    os.makedirs(OUT, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "dashboard.html"), os.path.join(SERVE, "dashboard.html"))
    project_dirs = [os.path.expanduser(p) for p in args.project] if args.project else project_dirs_for(repo, os.getcwd())
    pipelines = args.pipeline or [os.path.join(repo, ".agent", "state.json")]
    if not project_dirs:
        print("note: no Claude Code project folder found for this repo; showing the run manifest only "
              "(pass --project <config>/projects/<slug> to add workflow runs)", flush=True)

    if args.once or args.snapshot:
        state = export_once(project_dirs, pipelines)
        if state.get("error"):
            raise SystemExit(f"board export failed: {state['error']}")
        for r in state["runs"]:
            print(f"{r['id']:40} {r.get('state', ''):16} {r.get('agents', 0):3} agents  ${r.get('cost', 0):.2f}  {r.get('error', '')}")
        if args.snapshot:
            size, skipped = snapshot(state, args.snapshot, repo)
            print(f"snapshot: {args.snapshot} ({size / 1048576:.1f} MB){f', {skipped} media file(s) not embedded' if skipped else ''}")
        return

    threading.Thread(target=loop, args=(project_dirs, pipelines), daemon=True).start()
    handler = functools.partial(Quiet, directory=SERVE)
    srv = None
    for port in range(args.port, args.port + 21):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit(f"ports {args.port}-{args.port + 20} are all taken")
    print(f"Run board: http://127.0.0.1:{srv.server_address[1]}/dashboard.html  (repo {repo}; files in {SERVE})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
