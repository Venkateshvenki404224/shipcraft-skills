# Shipcraft

Eight agent skills and three agents for Claude Code. They carry engineering work
from a foggy idea to a merged pull request.

Each skill covers one stage. Use one on its own, or run them in order.

| Stage | Skill | What it does |
|---|---|---|
| 1. Chart | [`wayfinder`](skills/wayfinder/) | Plans work that is too large for one agent session. Writes a map of decision tickets on the issue tracker, then resolves them one at a time. |
| 2. Slice | [`issue-to-phases`](skills/issue-to-phases/) | Breaks a plan into thin end-to-end phases under `specs/`. Can also write a Ralph loop that builds the phases unattended. |
| 3. Build | [`dsa-conscious-coding`](skills/dsa-conscious-coding/) | Picks the data structure and the query before the code. Checks Big O against the data size the feature will really see. |
| 4. Deepen | [`improve-codebase-architecture`](skills/improve-codebase-architecture/) | Finds shallow modules, reports them as an HTML page with before and after diagrams, then works through the one you pick. |
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

`improve-codebase-architecture` writes an HTML report to the system temporary
directory and opens it. Nothing lands in your repository.

## License

MIT. See [LICENSE](LICENSE).

`wayfinder` and `improve-codebase-architecture` are unchanged copies from
[mattpocock/skills](https://github.com/mattpocock/skills), used under the MIT
license. See [NOTICE.md](NOTICE.md) for the full record.
