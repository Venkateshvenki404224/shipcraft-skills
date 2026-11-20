#!/usr/bin/env python3
"""Detect which agent host runs /work and which models it offers, so setup can
write real defaults into the profile instead of shipping hardcoded ones.

  python3 detect_models.py            -> JSON on stdout

Output: {"host": "claude|codex|copilot|unknown", "hosts_found": [...],
         "models": [...], "configured": "<model the host is set to, or null>",
         "source": "<where the list came from>", "note": "..."}

It only reads: environment variables, `--help` output, and the host's own
config or model cache. It never calls a model and never prints credentials.
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path.home()


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def claude_bin():
    return os.environ.get("CLAUDE_CODE_EXECPATH") or shutil.which("claude")


def claude():
    b = claude_bin()
    models, src = [], "none"
    if b:
        # the --model help names the aliases the installed build supports, e.g. 'fable', 'opus', 'sonnet'
        text = run([b, "--help"])
        m = re.search(r"--model <model>(.*?)(?:\n\s*-\w|\n\s*--)", text, re.S)
        block = m.group(1) if m else ""
        models = [a for a in re.findall(r"'([a-z][a-z0-9.\-]*)'", re.sub(r"\s+", " ", block))]
        src = "claude --help (--model aliases)"
    configured = None
    for p in (Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude")) / "settings.json",):
        try:
            configured = json.loads(p.read_text()).get("model")
        except Exception:
            pass
    return models, configured, src


def codex():
    home = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
    models, configured, src = [], None, "none"
    try:
        d = json.loads((home / "models_cache.json").read_text())
        models = [m.get("slug") for m in d.get("models", []) if m.get("slug")]
        src = "codex models_cache.json"
    except Exception:
        pass
    try:
        m = re.search(r'^model\s*=\s*"([^"]+)"', (home / "config.toml").read_text(), re.M)
        configured = m.group(1) if m else None
    except Exception:
        pass
    return models, configured, src


def copilot():
    # Copilot CLI has no model-list command. 'auto' is documented, and the configured model may be in its config.
    configured = None
    try:
        text = (HOME / ".copilot" / "config.json").read_text()
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))
        configured = json.loads(text).get("model")
    except Exception:
        pass
    models = ["auto"] + ([configured] if configured and configured != "auto" else [])
    return models, configured, "copilot --help ('auto') and ~/.copilot/config.json"


def main():
    env = os.environ
    found = [n for n, c in (("claude", bool(claude_bin())), ("codex", bool(shutil.which("codex") or (HOME / ".codex").exists())),
                            ("copilot", bool(shutil.which("copilot")))) if c]
    # the running host: only trust variables that name it unambiguously
    host = "claude" if env.get("CLAUDECODE") else "codex" if env.get("CODEX_HOME") or env.get("CODEX_SANDBOX") else \
        "copilot" if env.get("GITHUB_COPILOT_CLI") or env.get("COPILOT_CLI") else (found[0] if len(found) == 1 else "unknown")
    fn = {"claude": claude, "codex": codex, "copilot": copilot}.get(host)
    models, configured, src = fn() if fn else ([], None, "none")
    note = ""
    if host == "unknown":
        note = "Could not tell which host runs this session: ask the owner (hosts found: %s)." % (", ".join(found) or "none")
    elif not models:
        note = "The host gave no model list: ask the owner which models to use."
    json.dump({"host": host, "hosts_found": found, "models": models, "configured": configured, "source": src, "note": note},
              sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
