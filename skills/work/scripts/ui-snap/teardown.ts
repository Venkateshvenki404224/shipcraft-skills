/**
 * teardown.ts -- merges meta/<id>.{before,after}.json into .agent/ui/shots.json after each phase.
 * status per shot: unchanged | changed | new (no before) | removed (no after) | pending (after not taken yet).
 * Records the commit and whether the tree was dirty for each phase, so the review knows what it compared.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import * as path from 'node:path';
import { REPO_ROOT, UI_DIR, loadSpec } from './spec';

function git(...args: string[]): string {
  try { return execFileSync('git', ['-C', REPO_ROOT, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { return ''; }
}

export default async function teardown(): Promise<void> {
  const phase = process.env.UI_SNAP as 'before' | 'after';
  const metaDir = path.join(UI_DIR, 'meta');
  if (!existsSync(metaDir)) return;
  const runFile = path.join(UI_DIR, 'run.json');
  const run = existsSync(runFile) ? JSON.parse(readFileSync(runFile, 'utf8')) : {};
  run[phase] = { commit: git('rev-parse', '--short', 'HEAD'), dirty_files: git('status', '--porcelain').split('\n').filter(Boolean).length,
                 at: new Date().toISOString() };
  writeFileSync(runFile, JSON.stringify(run, null, 1));

  const { min_pixels } = loadSpec();
  const byId: Record<string, any> = {};
  for (const f of readdirSync(metaDir).filter((n) => n.endsWith('.json')).sort()) {
    const m = JSON.parse(readFileSync(path.join(metaDir, f), 'utf8'));
    byId[m.id] = { ...(byId[m.id] || {}), ...m };
  }
  const shots = Object.values(byId).map((s: any) => {
    let status: string;
    if (!s.after) status = run.after ? 'removed' : 'pending';
    else if (!s.before) status = 'new';
    else status = s.size_changed || s.changed_pixels >= min_pixels ? 'changed' : 'unchanged';
    return { ...s, status };
  });
  const order = { changed: 0, new: 1, removed: 2, pending: 3, unchanged: 4 } as Record<string, number>;
  shots.sort((a: any, b: any) => order[a.status] - order[b.status] || a.id.localeCompare(b.id));
  const counts = shots.reduce((c: Record<string, number>, s: any) => ({ ...c, [s.status]: (c[s.status] || 0) + 1 }), {});
  writeFileSync(path.join(UI_DIR, 'shots.json'), JSON.stringify({ generated: new Date().toISOString(), run, counts, shots }, null, 1));
  console.log(`ui-snap ${phase}: ${shots.length} shots`, counts);
}
