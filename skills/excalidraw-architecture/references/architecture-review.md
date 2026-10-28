# Design review loop: check the design before anyone builds

Use this when the diagram is part of a plan or feature request. The point is to catch a wrong seam,
a missing failure path or a data leak while it is still a picture, when fixing it means rebuilding a
script, not rewriting code.

The review runs in this session. **Do not spawn reviewer agents.** This session writes the
questions and checks the code. [TypeSafe](https://typesafe.ai)'s Jev model answers typed questions
about the design text with calibrated probabilities, in under a second per lens and for a fraction
of a cent. Jev only judges what the text says.

Without `TYPESAFE_API_KEY`, run the same loop and answer each question yourself against the text,
quoting the sentence that settles it. Mark a question you cannot settle from the text as `unsure`.

## What Jev can and cannot do

- **Can:** say, for each question, whether the document states something, with a probability. It
  confirms that a fix is written down and stays written down in every later version. In trials it
  answered "does the doc state X" questions reliably, and fixed gaps flipped from no to yes.
- **Cannot:** read the repo, check that a cited file or line is real, or reason through a race
  between processes. It also cannot find a problem nobody asked about. Those jobs stay with this
  session: steps 1 and 4 below.

## Inputs

- The design doc (`<feature>-design.md` or `plan.md`) with the PNGs attached. Only the text is sent.
- A questions file, `review/<name>-questions.json`, kept with the pack and grown every round:

```json
{
  "seams": {
    "seams_reuse": {"type": "noul", "instructions": "Does the document name the existing module, hook or table each new piece extends?", "expect": true}
  },
  "failure": {},
  "data": {}
}
```

`expect` is the answer that passes (default `true`); it is stripped before the request. Every
question is a yes/no question (`noul`). A `score` question may be added for information, but it
never decides a verdict, because scores did not separate an open major from a fixed one in trials.

## Lenses and their standing questions

Start every new questions file with these, then add the design-specific ones (step 2).

| Lens | Standing questions (all `expect: true`) |
|---|---|
| **Seams & reuse** | Each new box names the existing seam it extends (hook, override, plugin point, module, table field). Each reused function or module is named with its file path. A new table or model is justified against the existing ones. New behaviour joins existing registration points (config, hook lists, routers) rather than adding parallel ones. |
| **Failure & scale** | Every external call has a timeout and a stated failure result. Every write path says what happens on a crash halfway and how a rerun recovers. Every state change says what a concurrent job or request sees, and how it is locked or re-checked. Work on the hot path (page load, per-row loop) is named, with its cost. Every slice lists what it changes for users who have the feature off. Retries say what they repeat and what they never repeat. |
| **Data & privacy** | Every new field states who can read and who can write it. What reaches the browser (page load, realtime, API) is stated per role. What leaves the system, to whom, and under which agreement, is stated. What is logged, for how long, and who reads the log, is stated. Visibility across tenants or accounts is stated. Diagrams and examples use placeholder data only. |

Add the lens your domain needs (for example a regulated-data lens) as a fourth key in the
questions file; the script reviews every key it finds.

## Loop

Write the review table into the doc **before** round 1, with every verdict `pending`, and update it
after each round.

1. **Check the code claims yourself.** For every file path, line number, function or framework
   behaviour the design cites, open the code and confirm it (grep, read, a read-only console). Fix
   the doc where it is wrong. Jev cannot do this step.
2. **Write the design-specific questions.** For each lens, turn the design's own promises into
   yes/no questions ("Does the document say the switch is checked again under the row lock?").
   Turn every finding from earlier rounds into a question that must stay `true`, so a fix cannot
   quietly disappear. Ask about each thing a hostile reader would try. Keep questions atomic: one
   fact each.
3. **Run Jev.**

   ```bash
   . ~/.typesafe_env   # holds TYPESAFE_API_KEY; never print it
   python3 $S/jev_review.py docs/architecture/<feature>/<name>.md \
     docs/architecture/<feature>/review/<name>-questions.json \
     --out docs/architecture/<feature>/review/<name>-round-N-jev.json
   ```

   One request per lens. The state plus one question must fit in 32k tokens (64k per request); split
   a longer doc by chapter. Exit code 0 means every lens approves, 1 means revise, 2 is an error.
4. **Read the answers.**
   - **pass** (≥ 0.7 for `expect: true`): nothing to do.
   - **fail** (≤ 0.3): a finding. Fix the design (builder script and text), rebuild, re-render.
   - **unsure** (between 0.3 and 0.7): open the code or reason it through yourself. Then either fix
     the doc so it states the point plainly, or rewrite the question if it was ambiguous.
5. **Repeat** until every lens approves: every `noul` question passes. Do not stop at a fixed number
   of rounds. Keep each round's doc as `review/<name>-plan-round-N.md` and each Jev answer as
   `review/<name>-round-N-jev.json`.

Re-export every PNG (chapters and full canvas) after the last change and before the final table
update, so the pictures in the plan match what was approved.

## What goes into the plan

```markdown
### Design review
| Lens | R1 | R2 | Questions |
|---|---|---|---|
| Seams & reuse | revise (2 fail, 1 unsure) | approve | 14 |
| Failure & scale | revise (3 fail) | approve | 19 |
| Data & privacy | approve | approve | 12 |

Code claims checked in this session: <list, with file:line>.
```

A plan whose table shows every lens approving, with its code claims checked, is the signal that
implementation may start.

## Rules

- Never send personal or customer data, credentials or a production config to an external
  reviewer. Design text with placeholder names only.
- The key lives in `~/.typesafe_env` (mode 600). Load it per command and never echo it.
- A failed request (401, 429, timeout) is an error, not a "no". Stop and report it.
- Agents are not part of this loop. Spawn one only when the user asks for a deep code review.
