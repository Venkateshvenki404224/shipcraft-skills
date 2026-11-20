#!/usr/bin/env python3
"""Detect which agent host runs /work and which models it offers, so setup can
write real defaults into the profile instead of shipping hardcoded ones.

  python3 detect_models.py            -> JSON on stdout

Hosts: Claude Code (terminal, VS Code/Cursor extension, desktop app), Codex
(terminal, VS Code extension), Copilot CLI (terminal, `gh copilot`). Each host
is found on PATH first, then inside the app or editor extension that bundles it.

Output: {"host": "claude|codex|copilot|unknown", "hosts_found": [...],
         "by_host": {name: {"binary", "models", "configured", "source"}},
         "models": [...], "configured": "...", "source": "...", "note": "..."}
`host`, `models`, `configured` and `source` describe the running host; `by_host`
has every host found, so setup can offer a choice when the host is unknown.

It reads only: environment variables, `--help` or `debug models` output, and the
host's own config or model cache. It never calls a model and never prints credentials.
"""
import glob, json, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path.home()
EXT_DIRS = [HOME / d / "extensions" for d in (".vscode", ".vscode-insiders", ".cursor", ".windsurf", ".vscode-oss")]
APP_SUPPORT = HOME / "Library" / "Application Support"


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def newest(patterns):
    """Newest executable file matching any glob (by version-ish sort of the path)."""
    hits = []
    for pat in patterns:
        hits += [p for p in glob.glob(pat) if os.path.isfile(p) and os.access(p, os.X_OK)]
    return sorted(hits, key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p)])[-1] if hits else None


def ext_globs(sub):
    return [str(d / sub) for d in EXT_DIRS]


def find_claude():
    env = os.environ.get("CLAUDE_CODE_EXECPATH")
    if env and os.access(env, os.X_OK):
        return env
    return shutil.which("claude") or newest(
        ext_globs("anthropic.claude-code-*/resources/native-binary/claude*")
        + [str(HOME / ".claude/local/claude"), str(HOME / ".local/bin/claude"),
           str(APP_SUPPORT / "Claude/claude-code/*/claude*"), "/Applications/Claude.app/Contents/Resources/claude*",
           "/Applications/Claude.app/Contents/MacOS/claude*"])


def find_codex():
    return shutil.which("codex") or newest(
        ext_globs("openai.chatgpt-*/bin/*/codex") + ["/Applications/Codex.app/Contents/Resources/codex",
                                                     "/Applications/ChatGPT.app/Contents/Resources/codex"])


def find_copilot():
    b = shutil.which("copilot")
    if b:
        return [b]
    gh = shutil.which("gh")
    if gh and (HOME / ".local/share/gh/copilot").exists():
        return [gh, "copilot", "--"]
    return None


def claude():
    b = find_claude()
    models, configured, src = [], None, "none"
    if b:
        # the --model help names the aliases this build supports, e.g. 'fable', 'opus', 'sonnet'
        text = re.sub(r"\s+", " ", run([b, "--help"]))
        m = re.search(r"--model <model>(.*?)(?= -\w, --| --[a-z])", text)
        models = list(dict.fromkeys(re.findall(r"'([a-z][a-z0-9.\-]*)'", m.group(1) if m else "")))
        src = "%s --help (--model aliases)" % b
    for p in (Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude")) / "settings.json",):
        try:
            configured = json.loads(p.read_text()).get("model")
        except Exception:
            pass
    return b, models, configured, src


def codex():
    b = find_codex()
    home = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
    models, configured, src = [], None, "none"
    if b:  # the real catalog for the signed-in account
        try:
            d = json.loads(run([b, "debug", "models"], 30))
            models = [m.get("slug") for m in d.get("models", []) if m.get("slug")]
            src = "%s debug models" % b
        except Exception:
            pass
    if not models:
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
    return b, models, configured, src


def copilot():
    # Copilot CLI has no model-list command (`/model` is interactive, and an admin may pin 'auto').
    # 'auto' is documented in `copilot --help`; the configured model is read from its config.
    cmd = find_copilot()
    configured = None
    for name in ("config.json", "settings.json"):
        try:
            text = (HOME / ".copilot" / name).read_text()
            text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))
            configured = configured or json.loads(text).get("model")
        except Exception:
            pass
    models, src = [], "none"
    if cmd:
        help_text = run(cmd + ["--help"])
        if "--model" in help_text:
            models = ["auto"] if "'auto'" in help_text else []
            if configured and configured not in models:
                models.append(configured)
            src = "%s --help and ~/.copilot config (no list command; /model is interactive)" % " ".join(cmd[:2])
    return (cmd[0] if cmd else None), models, configured, src


def main():
    env = os.environ
    by_host = {}
    for name, fn in (("claude", claude), ("codex", codex), ("copilot", copilot)):
        b, models, configured, src = fn()
        if b:
            by_host[name] = {"binary": b, "models": models, "configured": configured, "source": src}
    found = list(by_host)
    # the running host: only trust variables that name it unambiguously
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        host = "claude"
    elif env.get("CODEX_THREAD_ID") or env.get("CODEX_SANDBOX") or env.get("CODEX_MANAGED_BY_NPM"):
        host = "codex"
    elif env.get("COPILOT_CLI") or env.get("GITHUB_COPILOT_CLI") or env.get("COPILOT_AGENT"):
        host = "copilot"
    else:
        host = found[0] if len(found) == 1 else "unknown"
    cur = by_host.get(host, {})
    note = ""
    if host == "unknown":
        note = "Could not tell which host runs this session: ask the owner (hosts found: %s)." % (", ".join(found) or "none")
    elif host not in by_host:
        note = "%s is the running host but its binary was not found: ask the owner which models it offers." % host
    elif not cur.get("models"):
        note = "The host gave no model list: ask the owner which models to use."
    elif host == "copilot":
        note = "Copilot lists models only in its interactive /model: add the ones the owner uses."
    json.dump({"host": host, "hosts_found": found, "by_host": by_host, "models": cur.get("models", []),
               "configured": cur.get("configured"), "source": cur.get("source", "none"), "note": note}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
