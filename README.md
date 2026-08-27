# Shipcraft

Four agent skills for Claude Code. They carry engineering work from a foggy idea
to shipped code.

Each skill covers one stage. Use one on its own, or run them in order.

| Stage | Skill | What it does |
|---|---|---|
| 1. Chart | [`wayfinder`](skills/wayfinder/) | Plans work that is too large for one agent session. Writes a map of decision tickets on the issue tracker, then resolves them one at a time. |
| 2. Slice | [`issue-to-phases`](skills/issue-to-phases/) | Breaks a plan into thin end-to-end phases under `specs/`. Can also write a Ralph loop that builds the phases unattended. |
| 3. Build | [`dsa-conscious-coding`](skills/dsa-conscious-coding/) | Picks the data structure and the query before the code. Checks Big O against the data size the feature will really see. |
| 4. Deepen | [`improve-codebase-architecture`](skills/improve-codebase-architecture/) | Finds shallow modules, reports them as an HTML page with before and after diagrams, then works through the one you pick. |

## Install

Add the marketplace, then install the plugin:

```
/plugin marketplace add Venkateshvenki404224/shipcraft-skills
/plugin install shipcraft@shipcraft
```

The same two steps from a terminal:

```bash
claude marketplace add shipcraft https://github.com/Venkateshvenki404224/shipcraft-skills
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

`issue-to-phases` and `dsa-conscious-coding` have no companion skills.

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

`improve-codebase-architecture` writes an HTML report to the system temporary
directory and opens it. Nothing lands in your repository.

## License

MIT. See [LICENSE](LICENSE).

`wayfinder` and `improve-codebase-architecture` are unchanged copies from
[mattpocock/skills](https://github.com/mattpocock/skills), used under the MIT
license. See [NOTICE.md](NOTICE.md) for the full record.
