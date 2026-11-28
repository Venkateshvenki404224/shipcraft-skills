# The build environment

Agents verify against a running system, never by reading code alone. Have it running before the build starts, and describe it in the run file's `environment` key with exact commands. Builders read that text literally.

## What to put in `environment`

- URLs: the app, the admin UI, the health check.
- How to sign in as each demo user, and the **name** of the env var that holds the demo password (never the password).
- Where the app source lives on the host and how it reaches the running system (bind mount, reload behaviour).
- The one command for framework tasks (migrate, build, run tests), wrapped in a lock.
- The frontend build command, also locked.
- How to drive a browser (for example Playwright from `<root>/qa/e2e/`).
- What needs a restart (background workers, schedulers) and who may do it.

## A Frappe bench pattern that works with parallel agents

| Piece | Why |
|---|---|
| Docker compose: mariadb, two redis (cache, queue), one bench container from `frappe/bench` | Reproducible, multi-arch; the bench on a named volume, the custom app bind-mounted from the host so agents edit with their file tools. |
| An idempotent `setup.sh` | bench init, get-app, new-site, install-app, and the setup wizard run non-interactively (`frappe.desk.page.setup_wizard.setup_wizard.setup_complete` via `bench execute`). |
| A host wrapper that runs `bench` inside the container **under `flock`** | Parallel agents must never run `migrate`, `build` or `install-app` at the same time. Agents use only the locked wrapper. It also passes the demo-password env var in. |
| A Python file poller (on macOS with colima or similar) | Bind mounts often do not deliver inotify events, so the dev server never reloads; a 1-second poller that touches a framework file fixes it. Workers and the scheduler still need a container restart. |
| Frontend builds under their own `flock`; node modules installed only inside the container | Concurrent `yarn build` runs corrupt each other; host-installed native modules break in the container. |
| A reset script that restores a clean backup and moves demo dates to today | A demo reset the evening before shows the wrong "today" after midnight. Only the demo-data role runs it. |
| The gate as files: an e2e spec, a permission-matrix script, security probes | The done gate must be re-runnable by an agent and by you. |

For a backend-only app, the same pattern applies without the frontend build.

## The UI look

If the product has a design system, say where it lives in `context` and add its rules to `rules` (tokens file, component list, the shell). Useful rules from real runs:
- Words, numbers and order come from the live app; a mock gives only the look.
- Keep every test id and accessible name when restyling.
- Status colours always come with a text label; check light and dark, and phone width for mobile users.
