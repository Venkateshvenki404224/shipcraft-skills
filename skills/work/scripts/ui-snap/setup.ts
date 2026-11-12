/**
 * setup.ts -- checks every role has a saved login, then clears what this phase replaces:
 *   before: everything except pages.json (a new baseline makes every after, diff and review stale)
 *   after:  after/, diff/, marked/, meta/*.after.json and review.json (a new after makes the old review stale)
 * Logging in is the project's job (its e2e login setup); this tool only loads the saved storageState.
 */
import { existsSync, readdirSync, rmSync } from 'node:fs';
import * as path from 'node:path';
import { UI_DIR, loadSpec, storageStatePath } from './spec';

export default async function setup(): Promise<void> {
  const phase = process.env.UI_SNAP;
  if (phase !== 'before' && phase !== 'after') throw new Error('set UI_SNAP=before or UI_SNAP=after');
  const missing = [...new Set(loadSpec().shots.map((s) => s.role))]
    .map((r) => [r, storageStatePath(r)] as const)
    .filter(([, p]) => p && !existsSync(p));
  if (missing.length)
    throw new Error(`no saved login for ${missing.map(([r, p]) => `${r} (${p})`).join(', ')}: run the project's login setup first`);
  const rm = (p: string) => rmSync(path.join(UI_DIR, p), { recursive: true, force: true });
  if (phase === 'before') ['before', 'after', 'diff', 'marked', 'meta', 'shots.json', 'run.json', 'review.json'].forEach(rm);
  else {
    ['after', 'diff', 'marked', 'review.json'].forEach(rm);
    const meta = path.join(UI_DIR, 'meta');
    if (existsSync(meta)) readdirSync(meta).filter((f) => f.endsWith('.after.json')).forEach((f) => rm(path.join('meta', f)));
  }
}
