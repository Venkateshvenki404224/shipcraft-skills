/**
 * spec.ts -- reads <repo>/.agent/ui/pages.json and expands it into shots (page x role x viewport x theme).
 *
 * pages.json (only "pages" is needed; the rest has defaults):
 * {
 *   "pages":     ["/dashboard", {"path": "/login", "roles": ["signed-out"]}],
 *   "roles":     ["user", "admin"],                 // any names; each needs a saved login (UI_SNAP_AUTH), except "signed-out"
 *   "viewports": [{"name": "desktop", "width": 1280, "height": 800}, {"name": "phone", "width": 390, "height": 844}],
 *   "themes":    ["light"],                         // light | dark (sets prefers-color-scheme)
 *   "theme_key": "app-theme",                       // optional localStorage key the app reads its theme from
 *   "hide":      [".cookie-banner"],                // CSS selectors made invisible before the shot (layout kept)
 *   "mask":      ["[data-relative-time]"],          // CSS selectors painted over (dynamic text: times, ids)
 *   "settle_ms": 400,                               // wait after network idle
 *   "full_page": true,
 *   "tolerance": 24,                                // per-channel difference (0-255) still counted as equal
 *   "min_pixels": 40                                // fewer changed pixels than this = unchanged
 * }
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import * as path from 'node:path';

export type Viewport = { name: string; width: number; height: number };
export type Shot = { id: string; path: string; role: string; viewport: Viewport; theme: 'light' | 'dark' };
export type SnapSpec = {
  shots: Shot[]; hide: string[]; mask: string[]; settle_ms: number; full_page: boolean; tolerance: number; min_pixels: number;
  theme_key: string | null;
};

function gitTop(): string {
  try { return execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim(); } catch { return process.cwd(); }
}

export const REPO_ROOT = process.env.UI_SNAP_REPO || gitTop();
export const UI_DIR = process.env.UI_SNAP_DIR || path.join(REPO_ROOT, '.agent', 'ui');

/** Saved login (Playwright storageState) for a role, from UI_SNAP_AUTH; null for signed-out. */
export function storageStatePath(role: string): string | null {
  if (role === 'signed-out') return null;
  const pattern = process.env.UI_SNAP_AUTH;
  if (!pattern) throw new Error(`role "${role}" needs a saved login: set UI_SNAP_AUTH, e.g. "tests/e2e/.auth/{role}.json"`);
  const p = pattern.replace('{role}', role);
  return path.isAbsolute(p) ? p : path.join(REPO_ROOT, p);
}

const DEFAULT_VIEWPORTS: Viewport[] = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'phone', width: 390, height: 844 },
];

export function shotId(p: string, role: string, vp: string, theme: string): string {
  const slug = p.replace(/^\/+|\/+$/g, '').replace(/[^A-Za-z0-9]+/g, '-') || 'root';
  return `${slug}--${role}--${vp}--${theme}`;
}

export function loadSpec(): SnapSpec {
  let raw: any;
  try {
    raw = JSON.parse(readFileSync(path.join(UI_DIR, 'pages.json'), 'utf8'));
  } catch (e: any) {
    throw new Error(`${path.join(UI_DIR, 'pages.json')}: ${e.code === 'ENOENT' ? 'missing (the planner writes it when ui is true)' : e.message}`);
  }
  if (!Array.isArray(raw.pages) || !raw.pages.length) throw new Error('pages.json: "pages" must list at least one page');
  const roles: string[] = raw.roles || ['signed-out'];
  const viewports: Viewport[] = raw.viewports || DEFAULT_VIEWPORTS;
  const themes: ('light' | 'dark')[] = raw.themes || ['light'];
  const shots: Shot[] = [];
  for (const entry of raw.pages) {
    const p: string = typeof entry === 'string' ? entry : entry.path;
    if (!/^\/[A-Za-z0-9/_.~%?=&#-]*$/.test(p)) throw new Error(`pages.json: bad path ${JSON.stringify(p)}`);
    const pageRoles: string[] = (typeof entry === 'object' && entry.roles) || roles;
    for (const role of pageRoles) {
      if (!/^[A-Za-z0-9_-]+$/.test(role)) throw new Error(`pages.json: bad role ${JSON.stringify(role)}`);
      for (const vp of viewports)
        for (const theme of themes) shots.push({ id: shotId(p, role, vp.name, theme), path: p, role, viewport: vp, theme });
    }
  }
  return {
    shots,
    hide: raw.hide || [],
    mask: raw.mask || [],
    settle_ms: raw.settle_ms ?? 400,
    full_page: raw.full_page ?? true,
    tolerance: raw.tolerance ?? 24,
    min_pixels: raw.min_pixels ?? 40,
    theme_key: raw.theme_key || null,
  };
}
