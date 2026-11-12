# Shipcraft

Nine agent skills and three agents for Claude Code. They carry engineering work
from a foggy idea to a merged pull request.

Each skill covers one stage. Use one on its own, or run them in order.

| Stage | Skill | What it does |
|---|---|---|
| 1. Chart | [`wayfinder`](skills/wayfinder/) | Plans work that is too large for one agent session. Writes a map of decision tickets on the issue tracker, then resolves them one at a time. |
| 2. Slice | [`issue-to-phases`](skills/issue-to-phases/) | Breaks a plan into thin end-to-end phases under `specs/`. Can also write a Ralph loop that builds the phases unattended. |
| 3. Build | [`dsa-conscious-coding`](skills/dsa-conscious-coding/) | Picks the data structure and the query before the code. Checks Big O against the data size the feature will really see. |
| 4. Deepen | [`improve-codebase-architecture`](skills/improve-codebase-architecture/) | Finds shallow modules, reports them as an HTML page with before and after diagrams, then works through the one you pick. |
| 3–5. Build to ship | [`work`](skills/work/) | Runs one feature end to end with an agent pipeline: research, plan, an approval agent, your OK, tests first, implementation, the gate, verification, agent QA per role on video, UI before/after screenshots, evidence, your ship decision. A live run board shows every stage. |
| 5. Ship | [`raise-pr`](skills/raise-pr/) | Lints like CI, commits, pushes and opens the PR with a short body and screenshots. Watches the checks. Merges only when you ask. |
| 5. Ship | [`pr-screenshots`](skills/pr-screenshots/) | Captures before and after screenshots of a UI change, crops them to the change, marks it in red, and publishes them in the PR body. |
| 5. Ship | [`visual-reviewer`](skills/visual-reviewer/) | Judges how a UI change looks to a user: light and dark theme, mobile, spacing, contrast. Returns LGTM, REQUEST CHANGES or BLOCKED. |
| Any stage | [`excalidraw-architecture`](skills/excalidraw-architecture/) | Draws the design as Excalidraw diagrams from a Python builder, renders them to PNG on your machine, attaches them to the plan, and reviews the design until every lens approves. |

## Agents

Three subagents for [Frappe](https://frappe.io) and ERPNext apps. Claude Code
starts them by name, or picks one from its description.

| Agent | What it does |
|---|---|
| [`frappe-implementer`](agents/frappe-implementer.md) | Builds a change and raises it as a focused, mergeable PR. Searches for prior art first, and checks its own diff against the reviewer's list before it hands off. |
| [`frappe-reviewer`](agents/frappe-reviewer.md) | Reviews a diff or a PR for reuse, API shape, hot-path queries, permissions and tests. Returns REQUEST CHANGES with cited findings, or APPROVE. |
| [`frappe-tester`](agents/frappe-tester.md) | Writes and runs tests against a real, rolled-back database. Mocks only external boundaries. Never edits the code under test. |

## Install

Add the marketplace, then install the plugin:

```
/plugin marketplace add Venkateshvenki404224/shipcraft-skills
/plugin install shipcraft@shipcraft
```

The same two steps from a terminal:

```bash
claude plugin marketplace add Venkateshvenki404224/shipcraft-skills
claude plugin install shipcraft@shipcraft
```

To install one skill by hand instead, copy its folder into `.claude/skills/` in
your repository:

```bash
git clone https://github.com/Venkateshvenki404224/shipcraft-skills
cp -r shipcraft-skills/skills/wayfinder .claude/skills/
```

## Run `/work` in a cloud session

> **⭐ Recommended starter prompt.** It is tested and works well. Copy it as is into a
> Claude Code cloud session (claude.ai/code), or into a scheduled cloud agent
> (`/schedule`), for the repository you want to work on. Replace the last line
> with your feature or issue number. The agent installs the skill, writes the
> project profile with you, and gives you the run board as an Artifact link.

```
Set up the /work skill from my shipcraft plugin in this repo, then use it.

1. If /work is not in your skill list: add this to .claude/settings.json (merge, don't overwrite), so later sessions load it:
   {"extraKnownMarketplaces": {"shipcraft": {"source": {"source": "github", "repo": "Venkateshvenki404224/shipcraft-skills"}}},
    "enabledPlugins": {"shipcraft@shipcraft": true}}
   For this session, clone https://github.com/Venkateshvenki404224/shipcraft-skills to /tmp/shipcraft, read /tmp/shipcraft/skills/work/SKILL.md, and follow it exactly. S = /tmp/shipcraft/skills/work. Don't commit the settings change unless I say so.
2. Run the first-time setup (references/setup.md): read the repo's CI, scripts and docs, draft .claude/work.json, run the check commands once, and show me the profile as a table to confirm. Don't guess values; mark anything you inferred.
3. This is a cloud session, so I can't open localhost. Make the run board as a snapshot (scripts/board/wfboard.py --snapshot .agent/board.html), publish it with the Artifact tool, give me the link, and republish it at H1, after QA and at H2. Print the stage table (scripts/state.py show) at each gate.
4. Before writing or editing any workflow script, load the workflow-authoring skill.
5. Then run: /work <describe the feature, or the issue number>
If agent-browser, ffmpeg or Playwright are missing here, run without video/screenshots and say so in the evidence. Don't install them without asking.
```

On your own machine you do not need this prompt: install the plugin and type
`/work <feature>`. The board then opens on localhost, and the skill gives you
the link.

The run stops for you twice: at H1 (approve the plan) and at H2 (ship or not).
A scheduled agent cannot answer for you, so it waits at H1. Answer in the
session with `/work approve`, then `/work ship`.

## Companion skills

`wayfinder` and `improve-codebase-architecture` call other skills by name:
`grilling`, `domain-modeling`, `codebase-design`, `research` and `prototype`.
Those skills are not in this repository. Install
[mattpocock/skills](https://github.com/mattpocock/skills) next to this plugin to
get them:

```
/plugin marketplace add mattpocock/skills
/plugin install mattpocock-skills@mattpocock
```

Then run `/setup-matt-pocock-skills` once per repository. This step tells
`wayfinder` which issue tracker to write the map to.

The `pr` skill in that collection writes a PR body with a summary, evidence and
merge danger. `raise-pr` writes a shorter body of its own and does not need it.

The other skills and the agents have no companion skills.

## What each skill assumes

`wayfinder` needs an issue tracker that supports child issues, labels, and a
blocking relationship. GitHub Issues works. A local markdown tracker is the
fallback.

`issue-to-phases` expects a `specs/` folder, one branch per spec, and one pull
request per spec. Its Ralph loop runs a test command that you supply. The worked
examples use Docker and Frappe, so read them as examples and not as a
requirement.

`dsa-conscious-coding` uses Python and Frappe in its code samples. The decision
table and the Big O checks apply to any language.

`excalidraw-architecture` needs Python 3 and Node.js with npm. It drives the
renderer with [agent-browser](https://www.npmjs.com/package/agent-browser)
through `npx`. The first render installs `@excalidraw/excalidraw` from npm and
bundles it, so it needs the network once. After that, rendering is offline.
The design review uses [TypeSafe](https://typesafe.ai) when `TYPESAFE_API_KEY`
is set. Without the key, the agent answers the review questions itself.

`raise-pr` needs the [GitHub CLI](https://cli.github.com) and runs
`pre-commit` when the repository has a `.pre-commit-config.yaml`. It removes the
comments that the branch adds before it commits, so read step 2 of the skill
before you use it. `pr-screenshots` and `visual-reviewer` drive the app with
[agent-browser](https://www.npmjs.com/package/agent-browser). `pr-screenshots`
crops and marks images with Pillow, and commits them under
`docs/implementation/media/` on the PR branch.

The three agents expect a Frappe bench. `frappe-tester` runs
`bench run-tests` against a development site.

`work` needs Python 3, git, and the Workflow tool in Claude Code (without it,
the skill runs the same stages with plain subagents). On first use in a
repository it writes `.claude/work.json`, the project profile: gate commands,
app URL, roles, saved logins. It reads them from your CI config, scripts and
docs, and asks you to confirm. The UI before/after layer needs Playwright; the
QA videos need [agent-browser](https://www.npmjs.com/package/agent-browser)
and ffmpeg. Without them the run still works, and the evidence says what was
skipped. The run board is `skills/work/scripts/board/`: a local page on
localhost, or a snapshot published as an Artifact in a cloud session.

`improve-codebase-architecture` writes an HTML report to the system temporary
directory and opens it. Nothing lands in your repository.

## License

MIT. See [LICENSE](LICENSE).

`wayfinder` and `improve-codebase-architecture` are unchanged copies from
[mattpocock/skills](https://github.com/mattpocock/skills), used under the MIT
license. See [NOTICE.md](NOTICE.md) for the full record.
