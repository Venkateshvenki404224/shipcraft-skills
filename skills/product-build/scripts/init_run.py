#!/usr/bin/env python3
"""Set a project up for a product-build run from its run file.

    python3 init_run.py <root>/tools/<slug>.run.json [--force]

It checks the run file, then writes (next to the run file, in tools/):
  - control-room-<slug>.json   the control room config (stages, roles, environment, docs)
  - extra-agents-<slug>.json   an empty list, for agents run outside workflows
  - <slug>-plan.workflow.js    copy of workflows/plan.js with meta.name = '<slug>-plan'
  - <slug>-build.workflow.js   copy of workflows/build.js with meta.name = '<slug>-build'
and creates the run's docs folder. Existing files are kept unless --force.
Prints the next commands. Writes nothing outside the project.
"""
import json
import os
import re
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED_ROLES = ["pm", "ceo", "ver"]


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    if len(argv) != 1:
        fail(__doc__)
    run_path = os.path.abspath(argv[0])
    try:
        run = json.load(open(run_path))
    except Exception as e:  # noqa: BLE001
        fail(f"cannot read {run_path}: {e}")

    problems, warnings = [], []
    for k in ["slug", "product", "root", "context", "roles"]:
        if not run.get(k):
            problems.append(f"missing '{k}'")
    slug = run.get("slug", "")
    if slug and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        problems.append("slug must be lowercase letters, digits and dashes")
    root = run.get("root", "")
    if root and not os.path.isabs(root):
        problems.append("root must be an absolute path")
    if root and not os.path.isdir(root):
        problems.append(f"root does not exist: {root}")
    if run.get("mode", "new-product") not in ("new-product", "feature"):
        problems.append("mode must be 'new-product' or 'feature'")
    roles = run.get("roles") or {}
    for r in REQUIRED_ROLES:
        if r not in roles:
            problems.append(f"roles.{r} is required")
    builders = [k for k, v in roles.items() if v.get("builder")]
    if not builders:
        problems.append("no role has \"builder\": true (tickets need owners)")
    for k, v in roles.items():
        if not v.get("label"):
            problems.append(f"roles.{k}.label is required")
        if not v.get("desc"):
            warnings.append(f"roles.{k} has no desc: agents get only the label")
        if v.get("model") not in (None, "haiku", "sonnet", "opus", "fable"):
            warnings.append(f"roles.{k}.model '{v.get('model')}' is not haiku/sonnet/opus/fable")
    if run.get("ui", True) and "ux" not in roles:
        warnings.append("ui is on but there is no 'ux' role: the design review runs as a default UI/UX agent on the session's model (add \"ux\" with \"model\": \"sonnet\" to keep it cheap)")
    gate_role = run.get("gate_role")
    if gate_role and gate_role not in builders:
        problems.append(f"gate_role '{gate_role}' must be a builder role ({', '.join(sorted(builders))})")
    if not gate_role and not any(k in builders for k in ("qa", "seed")):
        warnings.append("no gate_role and no 'qa' or 'seed' builder: the gate falls to the gate ticket's owner or the first ticket's owner. Set gate_role.")
    if run.get("today") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(run["today"])):
        problems.append("today must be YYYY-MM-DD")
    for i, r in enumerate(run.get("research") or []):
        for k in ["key", "title", "task", "out"]:
            if not r.get(k):
                problems.append(f"research[{i}] missing '{k}'")
    if re.search(r"(password|passwd|secret|token)\s*[:=]\s*\S{6,}", json.dumps(run), re.I):
        problems.append("the run file looks like it contains a secret: agents and the control room show it. Use an env var name instead.")
    if problems:
        fail("run file problems:\n  - " + "\n  - ".join(problems))

    tools = os.path.dirname(run_path)
    docs_rel = run.get("docs", "docs")
    os.makedirs(os.path.join(root, docs_rel, "research"), exist_ok=True)

    def write(path, content):
        if os.path.exists(path) and not force:
            print(f"kept      {path}")
            return
        with open(path, "w") as f:
            f.write(content)
        print(f"wrote     {path}")

    # Control room config
    cr = run.get("control_room") or {}
    stages = []
    if run.get("research"):
        stages.append({"title": "Research", "detail": "Research sub-agents; a verifier checks the briefs", "phases": ["Research"]})
    stages += [
        {"title": "Requirements", "detail": "PM writes the requirements", "phases": ["Requirements"]},
        {"title": "Decide", "detail": "CEO decides scope and the demo slice", "phases": ["Decide"]},
        {"title": "Feasibility", "detail": "Senior Frappe dev + senior dev", "phases": ["Feasibility"]},
        {"title": "Plan", "detail": "PM plan and tickets; verifier review; owner approval", "phases": ["Plan"]},
        {"title": "Design", "detail": "Design tickets and the CEO design review", "phases": ["Design"]},
        {"title": "Build", "detail": "Backend, frontend, prints, demo data", "phases": ["Build"]},
        {"title": "QA", "detail": "Close-out, verifier, design review, gate, fixes", "phases": ["QA", "Fix"]},
        {"title": "Demo", "detail": "Final gate, PM report, CEO sign-off", "phases": ["Demo"]},
    ]
    cr_roles = []
    for k, v in roles.items():
        cr_roles.append({
            "key": k,
            "name": v.get("name", v["label"]),
            "model": (v.get("model") or "inherit").capitalize(),
            "desc": (v.get("desc") or "").split(":")[0][:80],
            "match": ["^" + re.escape(v["label"]) + r"\s·"],
        })
    brief = (run.get("brief") or "").strip().splitlines()
    config = {
        "_comment": f"Generated by product-build init_run.py from {os.path.basename(run_path)}. Edit the run file and re-run with --force, or edit here for superseded/covered.",
        "title": cr.get("title", f"{run['product']} · {slug}"),
        "subtitle": cr.get("subtitle", (brief[0][:160] if brief else "") + " · built by an agent team"),
        "team_note": cr.get("team_note", "You (owner) · Claude (orchestrator)"),
        "output": cr.get("output", f"../{slug}-dashboard.html"),
        "refresh_seconds": cr.get("refresh_seconds", 10),
        "include_runs": [f"^{re.escape(slug)}-"],
        "stages": stages,
        "roles": cr_roles,
        "default_role": "pm",
        "docs": {"root": os.path.relpath(root, tools), "include": [f"{docs_rel}/**/*.md", "DEMO.md", "README.md"], "exclude": ["**/node_modules/**"]},
        "superseded": {},
        "covered": {},
        "extra_agents": f"extra-agents-{slug}.json",
    }
    for k in ("environment", "accent", "accent_dark", "stale_after_seconds"):
        if k in cr:
            config[k] = cr[k]
    cr_path = os.path.join(tools, f"control-room-{slug}.json")
    write(cr_path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    write(os.path.join(tools, f"extra-agents-{slug}.json"), "[]\n")

    # Workflow copies with the run's name, so the control room can tell runs apart
    for half in ("plan", "build"):
        src = open(os.path.join(SKILL, "workflows", f"{half}.js")).read()
        out, n = re.subn(r"name: 'pb-%s'" % half, f"name: '{slug}-{half}'", src, count=1)
        if n != 1:
            fail(f"workflows/{half}.js: meta.name not found")
        write(os.path.join(tools, f"{slug}-{half}.workflow.js"), out)

    for w in warnings:
        print(f"warning   {w}")
    cr_script = os.path.join(os.path.dirname(SKILL), "control-room", "scripts", "control_room.py")
    if not os.path.exists(cr_script):
        warnings.append("the control-room skill was not found next to this skill; install the whole shipcraft plugin")
        for w in warnings[-1:]:
            print(f"warning   {w}")
    print(f"""
Next:
  1. Control room (background, keep it running):
     python3 "{cr_script}" --config "{cr_path}" --watch 10
  2. Plan: Workflow scriptPath="{tools}/{slug}-plan.workflow.js", args = the contents of {os.path.basename(run_path)}
  3. After the owner approves the plan:
     python3 {SKILL}/scripts/check_tickets.py "{run_path}" --emit-args "{tools}/{slug}-build.args.json"
     Workflow scriptPath="{tools}/{slug}-build.workflow.js", args = the contents of {slug}-build.args.json""")


if __name__ == "__main__":
    main()
