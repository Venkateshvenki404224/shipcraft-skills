"""Offline tests for the run board's liveness decisions (skills/work/scripts/board/wfboard.py).

Everything is built in a temp dir: a workflow run folder, a fake session registry and a fake /proc.
Run: python3 -m unittest tests.work.test_board_liveness -v
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "skills", "work", "scripts", "board"))
import wfboard  # noqa: E402

NOW = 1_800_000_000.0
BTIME = int(NOW) - 1_000_000
CLK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
SID = "sess-0001"
OWNER_PID = 4242


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def ticks(t):
    return int((t - BTIME) * CLK)


def rec_user(t, text="go"):
    return {"type": "user", "timestamp": iso(t), "message": {"role": "user", "content": text}}


def rec_tool_use(t, tid, name="Bash", timeout=None):
    inp = {"command": "run", "description": "run the suite"}
    if timeout:
        inp["timeout"] = timeout
    return {"type": "assistant", "timestamp": iso(t), "message": {"role": "assistant", "model": "claude-sonnet-5-5", "id": "m" + tid,
            "stop_reason": "tool_use", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def rec_tool_result(t, tid):
    return {"type": "user", "timestamp": iso(t), "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}}


def rec_text(t, text="working", stop="end_turn"):
    return {"type": "assistant", "timestamp": iso(t), "message": {"role": "assistant", "model": "claude-sonnet-5-5", "id": "x" + str(t),
            "stop_reason": stop, "content": [{"type": "text", "text": text}]}}


def rec_api_error(t):
    return {"type": "assistant", "timestamp": iso(t), "isApiErrorMessage": True, "error": "rate_limit",
            "message": {"role": "assistant", "model": "<synthetic>", "id": "e" + str(t), "stop_reason": "stop_sequence",
                        "content": [{"type": "text", "text": "You've hit your limit for today"}]}}


class Fixture:
    def __init__(self, root):
        self.root = root
        self.proj = os.path.join(root, "proj")
        self.session_dir = os.path.join(self.proj, SID)
        self.run_dir = os.path.join(self.session_dir, "subagents", "workflows", "wf_test")
        self.out = os.path.join(root, "out")
        self.sessions = os.path.join(root, "sessions")
        self.proc = os.path.join(root, "proc")
        os.makedirs(self.run_dir)
        os.makedirs(self.proc)
        with open(os.path.join(self.proc, "stat"), "w") as f:
            f.write(f"cpu 0 0 0\nbtime {BTIME}\n")
        self.journal_lines = []

    def reg_dir(self):
        os.makedirs(self.sessions, exist_ok=True)

    def owner(self, kind, started=None):
        """kind: alive | dead | empty (registry folder, no entry) | none (no registry folder)."""
        if kind == "none":
            return
        self.reg_dir()
        if kind == "empty":
            return
        started = NOW - 50_000 if started is None else started
        with open(os.path.join(self.sessions, f"{OWNER_PID}.json"), "w") as f:
            json.dump({"pid": OWNER_PID, "sessionId": SID, "procStart": ticks(started), "startedAt": int(started * 1000)}, f)
        if kind == "alive":
            self.proc_stat(OWNER_PID, 1, started)

    def proc_stat(self, pid, ppid, started):
        os.makedirs(os.path.join(self.proc, str(pid)), exist_ok=True)
        with open(os.path.join(self.proc, str(pid), "stat"), "w") as f:
            f.write(f"{pid} (claude) S {ppid} " + " ".join(["0"] * 17) + f" {ticks(started)} 0 0\n")

    def start(self, aid, label, phase="Gate + E2E", key=None):
        d = {"type": "started", "agentId": aid, "label": label, "phase": phase}
        if key:
            d["key"] = key
        self.journal_lines.append(d)

    def result(self, aid, result=None):
        self.journal_lines.append({"type": "result", "agentId": aid, "result": result if result is not None else {"ok": True}})

    def transcript(self, aid, records, mtime=None):
        path = os.path.join(self.run_dir, f"agent-{aid}.jsonl")
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        stamp = mtime if mtime is not None else max(ts for ts in (wfboard.ts(r["timestamp"]) for r in records))
        os.utime(path, (stamp, stamp))
        return path

    def append(self, aid, record, mtime):
        path = os.path.join(self.run_dir, f"agent-{aid}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
        os.utime(path, (mtime, mtime))

    def write_journal(self, mtime):
        path = os.path.join(self.run_dir, "journal.jsonl")
        with open(path, "w") as f:
            for d in self.journal_lines:
                f.write(json.dumps(d) + "\n")
        os.utime(path, (mtime, mtime))

    def status_file(self, status, mtime):
        d = os.path.join(self.session_dir, "workflows")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "wf_test.json")
        with open(path, "w") as f:
            json.dump({"status": status}, f)
        os.utime(path, (mtime, mtime))

    def export(self, now=NOW):
        setattr(wfboard, "OUT", self.out)
        setattr(wfboard, "SESSIONS_DIR", self.sessions)
        setattr(wfboard, "PROC", self.proc)
        return wfboard.export_run(self.run_dir, now)


def rows(run):
    return {a["id"]: a for g in run["groups"] for a in g["agents"]}


class BoardLiveness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="board-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        wfboard._agent_cache.clear()
        if hasattr(wfboard, "_owner_pid"):
            wfboard._owner_pid.clear()
        self.fx = Fixture(self.tmp)

    def one_agent(self, records, journal_age, owner="alive", label="Gate: red run 2", **kw):
        self.fx.start("a1", label, **kw)
        self.fx.transcript("a1", records)
        self.fx.write_journal(NOW - journal_age)
        self.fx.owner(owner)
        return self.fx.export()

    def problem(self, run):
        return wfboard.run_problem([run])

    def test_01_long_agent_with_old_journal_is_running(self):
        run = self.one_agent([rec_user(NOW - 1500), rec_text(NOW - 5, stop="tool_use")], 1200)
        self.assertEqual(run["state"], "running")
        self.assertIsNone(self.problem(run))

    def test_02_long_bash_call_is_running_and_says_so(self):
        run = self.one_agent([rec_user(NOW - 1500), rec_tool_use(NOW - 505, "t1", timeout=600000)], 1200)
        self.assertEqual(run["state"], "running")
        self.assertIsNone(self.problem(run))
        self.assertIn("running a command for 8 min", rows(run)["a1"]["last"])

    def test_03_waiting_on_the_model_is_noted(self):
        recs = [rec_user(NOW - 400), rec_tool_use(NOW - 180, "t1"), rec_tool_result(NOW - 174, "t1")]
        run = self.one_agent(recs, 100)
        self.assertEqual(run["state"], "running")
        self.assertIn("waiting on the model for 2 min", rows(run)["a1"]["last"])

    def test_04_model_silence_past_limit_is_stalled_and_names_the_agent(self):
        recs = [rec_user(NOW - 900), rec_tool_use(NOW - 700, "t1"), rec_tool_result(NOW - 601, "t1")]
        run = self.one_agent(recs, 700)
        self.assertEqual(run["state"], "stalled")
        p = self.problem(run)
        self.assertEqual(p["state"], "stalled")
        self.assertIn("Gate: red run 2", p["why"])

    def test_05_stalled_run_clears_on_the_next_write(self):
        recs = [rec_user(NOW - 900), rec_tool_use(NOW - 700, "t1"), rec_tool_result(NOW - 601, "t1")]
        self.assertEqual(self.one_agent(recs, 700)["state"], "stalled")
        self.fx.append("a1", rec_text(NOW - 1, stop="tool_use"), NOW - 1)
        run = self.fx.export()
        self.assertEqual(run["state"], "running")
        self.assertIsNone(self.problem(run))

    def test_06_tool_past_its_limit_with_a_live_child_is_running(self):
        self.fx.owner("alive")
        self.fx.proc_stat(5001, OWNER_PID, NOW - 699.7)
        recs = [rec_user(NOW - 900), rec_tool_use(NOW - 700, "t1", timeout=600000)]
        run = self.one_agent(recs, 700)
        self.assertEqual(run["state"], "running")

    def test_07_tool_past_its_limit_without_a_child_is_stalled(self):
        recs = [rec_user(NOW - 900), rec_tool_use(NOW - 700, "t1", timeout=600000)]
        run = self.one_agent(recs, 700)
        self.assertEqual(run["state"], "stalled")

    def test_08_dead_session_is_stopped_at_once(self):
        recs = [rec_user(NOW - 600), rec_tool_use(NOW - 300, "t1", timeout=600000)]
        run = self.one_agent(recs, 300, owner="dead")
        self.assertEqual(run["state"], "stopped")
        self.assertEqual(rows(run)["a1"]["status"], "STOPPED")
        self.assertEqual(run["running"], 0)
        self.assertEqual(run["elapsed"], 300)
        p = self.problem(run)
        self.assertEqual(p["state"], "stopped")

    def test_09_session_started_after_the_last_write_is_stopped(self):
        recs = [rec_user(NOW - 600), rec_tool_use(NOW - 300, "t1", timeout=600000)]
        self.fx.start("a1", "Gate: red run 2", key="k1")
        self.fx.transcript("a1", recs)
        self.fx.write_journal(NOW - 300)
        self.fx.owner("alive", started=NOW - 100)
        run = self.fx.export()
        self.assertEqual(run["state"], "stopped")

    def test_10_resume_clears_the_stop_and_stops_the_old_attempt(self):
        self.fx.start("a1", "Gate: red run 2", key="k1")
        self.fx.transcript("a1", [rec_user(NOW - 600), rec_tool_use(NOW - 300, "t1", timeout=600000)])
        self.fx.start("a2", "Gate: red run 2", key="k1")
        self.fx.transcript("a2", [rec_user(NOW - 3), rec_tool_use(NOW - 2, "t2", timeout=600000)])
        self.fx.write_journal(NOW - 2)
        self.fx.owner("alive", started=NOW - 100)
        run = self.fx.export()
        r = rows(run)
        self.assertEqual(run["state"], "running")
        self.assertEqual(r["a1"]["status"], "STOPPED")
        self.assertEqual(r["a2"]["status"], "RUN")
        self.assertEqual(run["running"], 1)

    def test_11_killed_agent_does_not_inflate_the_step_time(self):
        old = NOW - 17 * 3600
        self.fx.start("k", "Dev: T1", phase="Implement")
        self.fx.transcript("k", [rec_user(old - 1140), rec_tool_use(old, "t1")])
        for i, dur in enumerate((100, 200, 300)):
            aid = f"s{i}"
            self.fx.start(aid, f"Dev{i}: T1", phase="Implement")
            self.fx.transcript(aid, [rec_user(NOW - 4000 - dur), rec_text(NOW - 4000)])
            self.fx.result(aid)
        self.fx.write_journal(NOW - 4000)
        self.fx.owner("dead")
        run = self.fx.export()
        g = next(g for g in run["groups"] if g["key"] == "T1")
        self.assertEqual(g["elapsed"], 1140 + 100 + 200 + 300)
        self.assertNotEqual(g["status"], "RUN")
        self.assertEqual(rows(run)["k"]["status"], "STOPPED")

    def refused(self, labels, results=()):
        for i, label in enumerate(labels):
            aid = f"r{i}"
            self.fx.start(aid, label)
            self.fx.transcript(aid, [rec_user(NOW - 305 + i), rec_api_error(NOW - 300 + i)])
            if aid in results:
                self.fx.result(aid)
        self.fx.write_journal(NOW - 290)
        self.fx.owner("alive")
        return self.fx.export()

    def test_12_refused_attempts_are_failed_not_recovered(self):
        run = self.refused(["Tester: X", "Tester: X (retry 1)", "Tester: X (retry 2)"])
        self.assertEqual({a["status"] for a in rows(run).values()}, {"FAIL"})
        self.assertEqual(run["running"], 0)
        p = self.problem(run)
        self.assertEqual(p["state"], "failed")
        self.assertIn("hit your limit", p["why"])

    def test_13_a_retry_that_returned_is_recovered(self):
        run = self.refused(["Tester: X", "Tester: X (retry 1)"], results=("r1",))
        p = self.problem(run)
        self.assertEqual(p["state"], "retried")

    def test_14_status_file_older_than_the_journal_is_ignored(self):
        self.fx.status_file("completed", NOW - 5000)
        run = self.one_agent([rec_user(NOW - 200), rec_tool_use(NOW - 30, "t1")], 100)
        self.assertEqual(run["state"], "running")

    def test_15_status_file_newer_than_the_journal_ends_the_run(self):
        self.fx.status_file("completed", NOW - 50)
        run = self.one_agent([rec_user(NOW - 200), rec_tool_use(NOW - 30, "t1")], 100)
        self.assertEqual(run["state"], "finished")

    def test_16_stopped_marker_counts_only_when_newer_than_the_journal(self):
        marker = os.path.join(self.fx.run_dir, ".stopped")
        run = self.one_agent([rec_user(NOW - 200), rec_tool_use(NOW - 30, "t1")], 100)
        open(marker, "w").close()
        os.utime(marker, (NOW - 5000, NOW - 5000))
        self.assertEqual(self.fx.export()["state"], "running")
        os.utime(marker, (NOW - 50, NOW - 50))
        self.assertEqual(self.fx.export()["state"], "finished")

    def test_17_no_registry_folder_falls_back_to_the_timers(self):
        run = self.one_agent([rec_user(NOW - 900), rec_tool_use(NOW - 100, "t1")], 800, owner="none")
        self.assertEqual(run["state"], "running")
        recs = [rec_user(NOW - 900), rec_tool_use(NOW - 700, "t1"), rec_tool_result(NOW - 601, "t1")]
        self.fx.transcript("a1", recs)
        self.assertEqual(self.fx.export()["state"], "stalled")

    def test_18_registry_folder_without_an_entry_and_a_fresh_write_is_running(self):
        run = self.one_agent([rec_user(NOW - 100), rec_tool_use(NOW - 4, "t1")], 4, owner="empty")
        self.assertEqual(run["state"], "running")

    def test_19_pipeline_agent_with_an_open_tool_gets_a_note_not_a_stale_flag(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".agent"))
        manifest = os.path.join(repo, ".agent", "state.json")
        with open(manifest, "w") as f:
            json.dump({"run": "agent/1-x", "name": "x", "phases": ["Build"], "session": SID,
                       "steps": [{"phase": "Build", "key": "build", "title": "Build", "status": "RUN",
                                  "agents": [{"id": "pa1", "label": "Builder"}]}]}, f)
        path = os.path.join(self.fx.session_dir, "subagents", "agent-pa1.jsonl")
        with open(path, "w") as f:
            for r in (rec_user(NOW - 1100), rec_tool_use(NOW - 1000, "t1", timeout=3600000)):
                f.write(json.dumps(r) + "\n")
        os.utime(path, (NOW - 1000, NOW - 1000))
        self.fx.owner("alive")
        setattr(wfboard, "OUT", self.fx.out)
        setattr(wfboard, "SESSIONS_DIR", self.fx.sessions)
        setattr(wfboard, "PROC", self.fx.proc)
        run = wfboard.export_pipeline(manifest, [self.fx.proj], NOW)
        agent = rows(run)["pa1"]
        self.assertEqual(agent["status"], "RUN")
        self.assertNotIn("no activity", agent["last"])
        self.assertIn("running a command for 16 min", agent["last"])

    def test_20_nothing_running_with_queued_tickets_is_stalled_after_silence(self):
        self.fx.start("t", "tickets", phase="Plan")
        self.fx.result("t", {"tickets": [{"id": "T1", "title": "one"}]})
        self.fx.transcript("t", [rec_user(NOW - 800), rec_text(NOW - 700)])
        self.fx.write_journal(NOW - 700)
        self.fx.owner("alive")
        self.assertEqual(self.fx.export()["state"], "stalled")
        self.fx.write_journal(NOW - 100)
        self.fx.transcript("t", [rec_user(NOW - 800), rec_text(NOW - 100)])
        self.assertEqual(self.fx.export()["state"], "between steps")

    def refused_then_resumed(self, ended_at):
        for i, label in enumerate(("Verifier: UI", "Verifier: UI (retry 1)", "Verifier: UI (retry 2)")):
            aid = f"v{i}"
            self.fx.start(aid, label, phase="Verify")
            self.fx.transcript(aid, [rec_user(NOW - 3010 + i), rec_api_error(NOW - 3005 + i)])
            self.fx.journal_lines.append({"type": "failed", "agentId": aid})
        self.fx.status_file("completed", ended_at)
        self.fx.start("f2", "Fixer: gate round 2")
        self.fx.transcript("f2", [rec_user(NOW - 200), rec_tool_use(NOW - 20, "t1", timeout=600000)])
        self.fx.write_journal(NOW - 200)
        self.fx.owner("alive")
        return self.fx.export()

    def test_21_failures_before_a_resume_do_not_stop_the_resumed_run(self):
        run = self.refused_then_resumed(ended_at=NOW - 2990)
        self.assertEqual(run["state"], "running")
        self.assertEqual(run["unrecovered"], [])
        self.assertEqual(run["failed_agents"], [])
        self.assertIsNone(self.problem(run))
        self.assertEqual({rows(run)[f"v{i}"]["status"] for i in range(3)}, {"STOPPED"})

    def test_22_failures_after_the_last_end_still_stop_the_run(self):
        run = self.refused_then_resumed(ended_at=NOW - 5000)
        self.assertEqual(run["unrecovered"], ["Verifier: UI"])
        self.assertEqual(self.problem(run)["state"], "failed")


class AppProbe(unittest.TestCase):
    URL = "https://app.test"

    def setUp(self):
        wfboard._app_state.clear()

    def test_one_slow_answer_does_not_raise_the_banner(self):
        wfboard.app_record(self.URL, True, NOW)
        self.assertTrue(wfboard.app_record(self.URL, False, NOW + 3)["up"])

    def test_two_failures_in_a_row_raise_it(self):
        wfboard.app_record(self.URL, True, NOW)
        wfboard.app_record(self.URL, False, NOW + 3)
        self.assertFalse(wfboard.app_record(self.URL, False, NOW + 6)["up"])

    def test_the_first_answer_after_an_outage_clears_it(self):
        for t in (0, 3, 6):
            wfboard.app_record(self.URL, False, NOW + t)
        self.assertTrue(wfboard.app_record(self.URL, True, NOW + 9)["up"])

    def test_no_answer_yet_is_not_shown_as_down(self):
        self.assertIsNone(wfboard.app_record(self.URL, False, NOW)["up"])


if __name__ == "__main__":
    unittest.main()
