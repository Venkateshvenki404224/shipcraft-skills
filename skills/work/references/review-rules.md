# Review rules (verify and UI review agents)

These are the rules every project gets. The project adds its own in the file the profile names as `review_rules` (for example `.claude/work-review-rules.md`); a project rule wins over a rule here.

Every finding cites one heading from these files, or names a concrete failing behaviour (input → wrong output). A finding that does neither is an opinion; leave it out. Before you report anything, confirm it in the code or the browser: a wrong finding costs the author more time than a missed one.

## Access (BLOCKING)
- A role reaches only what it is allowed to. Check each change as every affected role and signed out.
- Path checks match whole path segments: a bare prefix check for `/app` also lets `/apps` through. Normalise `..` and encoded characters before matching, on the server and in client-side guards.
- A role-gated element is absent from the page, not just hidden, for roles that must not see it.

## Escaping and injection (BLOCKING)
- Every dynamic value in a template is escaped by the template engine or an explicit escape helper.
- Client code writes text with `textContent` (or the framework's text binding), never `innerHTML`, `eval` or `new Function` with data.
- SQL, shell and file paths are built with parameters or allow-lists, never by string concatenation with user input.

## State and storage
- Per-user state is stored per user (server side, or keyed by a per-user id), never per browser when it must follow the user.
- Every `localStorage`/`sessionStorage` access is wrapped in try/catch, and the feature still works with storage blocked.

## APIs
- State-changing requests use the project's existing CSRF or auth transport.
- Reuse an existing endpoint before adding one. A new endpoint checks the session and the role.

## Phones and layout
- No sideways scroll at 360, 375 and 390 px.
- Fixed or floating UI stays inside the viewport after a resize across a breakpoint.
- Dark mode is readable when the app has one.
- Focus returns to a sensible element when a dialog or overlay closes.

## Secrets and data
- No secret appears in code, logs, screenshots or videos (the profile's `secrets` list, tokens, passwords).
- Never open a public database port.

## Tests
- Tests use only the hooks and calls in the plan's test contract.
- A fix never weakens an assertion, widens a timeout or deletes a test to go green.
- A test that fails once and then passes is a flake: name it.

## Do not flag
- Style that a linter or formatter owns.
- Defects that exist on the base branch without this change. Label them "existing bug", and only if you reproduced them with the feature turned off.
- Problems that need an input or situation you cannot name.
- Preferences about wording, unless the text is wrong for the role.
