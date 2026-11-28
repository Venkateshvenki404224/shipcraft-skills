#!/usr/bin/env python3
"""Check the PM's tickets.json before the build runs, and build the build workflow's args.

    python3 check_tickets.py <root>/tools/<slug>.run.json [--tickets PATH] [--emit-args OUT.json]

Default tickets path: <root>/<docs>/tickets.json. It checks: unique ids, owners that are builder
roles, depends_on ids that exist, no cycles, no ticket depending on the gate ticket, at most one
gate, acceptance lines present. It prints the schedule the build workflow will follow (one ticket
per role at a time) with an hours estimate, so the owner sees the shape before approving.
With --emit-args it writes {...run file without control_room, "tickets": [...]}, the value to pass
as the build workflow's args. Exit code 1 on any error.
"""
import json
import os
import sys


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("--"):
        print(__doc__)
        sys.exit(1)
    run_path = a[0]
    tickets_path = a[a.index("--tickets") + 1] if "--tickets" in a else None
    emit = a[a.index("--emit-args") + 1] if "--emit-args" in a else None
    run = json.load(open(run_path))
    tickets_path = tickets_path or os.path.join(run["root"], run.get("docs", "docs"), "tickets.json")
    tickets = json.load(open(tickets_path))
    roles = run.get("roles", {})
    builders = {k for k, v in roles.items() if v.get("builder")}

    errors, warnings = [], []
    if not isinstance(tickets, list) or not tickets:
        print(f"ERROR: {tickets_path} must be a non-empty JSON array")
        sys.exit(1)
    ids = [t.get("id") for t in tickets]
    seen = set()
    for i in ids:
        if not i:
            errors.append("a ticket has no id")
        elif i in seen:
            errors.append(f"duplicate id {i}")
        seen.add(i)
    by_id = {t.get("id"): t for t in tickets}
    gates = [t for t in tickets if t.get("gate")]
    if len(gates) > 1:
        errors.append(f"more than one gate ticket: {[g['id'] for g in gates]}")
    gate_ids = {g["id"] for g in gates}
    for t in tickets:
        tid = t.get("id")
        if t.get("owner") not in builders:
            errors.append(f"{tid}: owner '{t.get('owner')}' is not a builder role ({', '.join(sorted(builders))})")
        if not t.get("title"):
            errors.append(f"{tid}: no title")
        if not t.get("acceptance"):
            warnings.append(f"{tid}: no acceptance lines (the agent cannot prove it is done)")
        if t.get("phase", "Build") not in ("Design", "Build"):
            warnings.append(f"{tid}: phase '{t.get('phase')}' is not Design/Build (the control room groups by phase)")
        for d in t.get("depends_on", []):
            if d not in by_id:
                errors.append(f"{tid}: depends on unknown ticket {d}")
            if d in gate_ids:
                errors.append(f"{tid}: depends on the gate ticket {d} (the gate runs after the build)")
        if t.get("stretch") and t.get("gate"):
            errors.append(f"{tid}: a ticket cannot be both stretch and gate")

    # cycles
    state = {}

    def visit(n, path):
        if state.get(n) == 1:
            errors.append("cycle: " + " -> ".join(path + [n]))
            return
        if state.get(n) == 2 or n not in by_id:
            return
        state[n] = 1
        for d in by_id[n].get("depends_on", []):
            visit(d, path + [n])
        state[n] = 2

    for n in by_id:
        visit(n, [])

    for w in warnings:
        print(f"warning  {w}")
    if errors:
        for e in sorted(set(errors)):
            print(f"ERROR    {e}")
        sys.exit(1)

    # simulate the scheduler: one ticket per role at a time, start when deps are finished
    core = [t for t in tickets if not t.get("gate") and not t.get("stretch")]
    stretch = [t for t in tickets if t.get("stretch")]
    finish, busy_until, order = {}, {}, []
    pending = list(core) + list(stretch)
    clock = 0.0
    while pending:
        progressed = False
        for t in list(pending):
            deps = [d for d in t.get("depends_on", []) if d in by_id and not by_id[d].get("gate")]
            if not all(d in finish for d in deps):
                continue
            if t.get("stretch") and not all(c["id"] in finish for c in core):
                continue
            start = max([busy_until.get(t["owner"], 0.0)] + [finish[d] for d in deps])
            finish[t["id"]] = start + float(t.get("hours") or 1)
            busy_until[t["owner"]] = finish[t["id"]]
            order.append((start, t))
            pending.remove(t)
            progressed = True
        if not progressed:
            print("ERROR    scheduler stuck on: " + ", ".join(t["id"] for t in pending))
            sys.exit(1)
    total = max(finish.values()) if finish else 0
    print(f"{len(tickets)} tickets ({len(core)} core, {len(stretch)} stretch, {len(gates)} gate); "
          f"agent-hours {sum(float(t.get('hours') or 1) for t in tickets):.0f}; critical path ~{total:.0f} h of estimate")
    for owner in sorted({t["owner"] for t in tickets}):
        mine = [t for _, t in sorted(order, key=lambda x: x[0]) if t["owner"] == owner]
        hrs = sum(float(t.get("hours") or 1) for t in mine)
        label = roles.get(owner, {}).get("label", owner)
        print(f"  {label:<20} {hrs:>4.0f} h  " + " → ".join(t["id"] for t in mine))
    if gates:
        print(f"  gate: {gates[0]['id']} ({roles.get(gates[0]['owner'], {}).get('label', gates[0]['owner'])}) runs in QA")

    if emit:
        out = {k: v for k, v in run.items() if k not in ("control_room",) and not k.startswith("_")}
        out["tickets"] = tickets
        with open(emit, "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
        print(f"wrote    {emit}")


if __name__ == "__main__":
    main()
