#!/usr/bin/env python3
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
    if b:
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


def acp_models(cmd, timeout=30):
    import select, time
    try:
        p = subprocess.Popen(cmd + ["--acp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd="/tmp")
    except Exception:
        return []

    def call(i, method, params):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
        p.stdin.flush()
        end = time.time() + timeout
        while time.time() < end:
            if select.select([p.stdout], [], [], 1)[0]:
                line = p.stdout.readline()
                if not line:
                    return None
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                if m.get("id") == i:
                    return m.get("result")
        return None

    try:
        call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        res = call(2, "session/new", {"cwd": "/tmp", "mcpServers": []}) or {}
        out = []
        for m in (res.get("models") or {}).get("availableModels", []):
            if (m.get("_meta") or {}).get("copilotEnablement", "enabled") == "enabled" and m.get("modelId") not in out:
                out.append(m["modelId"])
        return out
    except Exception:
        return []
    finally:
        p.kill()


def copilot():
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
        models = acp_models(cmd)
        src = "%s --acp (session/new availableModels)" % " ".join(cmd[:2])
        if not models and "--model" in run(cmd + ["--help"]):
            models, src = ["auto"], "%s --help ('auto' only; /model is interactive)" % " ".join(cmd[:2])
    return (cmd[0] if cmd else None), models, configured, src


def main():
    env = os.environ
    by_host = {}
    for name, fn in (("claude", claude), ("codex", codex), ("copilot", copilot)):
        b, models, configured, src = fn()
        if b:
            by_host[name] = {"binary": b, "models": models, "configured": configured, "source": src}
    found = list(by_host)
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
    json.dump({"host": host, "hosts_found": found, "by_host": by_host, "models": cur.get("models", []),
               "configured": cur.get("configured"), "source": cur.get("source", "none"), "note": note}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
