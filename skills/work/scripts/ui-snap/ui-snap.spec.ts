/**
 * ui-snap.spec.ts -- one test per shot (page x role x viewport x theme), see spec.ts.
 *   UI_SNAP=before  writes .agent/ui/before/<id>.png + meta/<id>.before.json
 *   UI_SNAP=after   writes .agent/ui/after/<id>.png, and when a before exists, diff/<id>.png + meta/<id>.after.json
 * The diff is computed in the browser (canvas), so there is no image library to install.
 * A shot never fails because the picture changed: changes are for the UI review to judge, not the test.
 */
import { test, type Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import * as path from 'node:path';
import { UI_DIR, loadSpec, storageStatePath, type Shot, type SnapSpec } from './spec';

const PHASE = process.env.UI_SNAP;
if (PHASE !== 'before' && PHASE !== 'after') throw new Error('set UI_SNAP=before or UI_SNAP=after');

const spec: SnapSpec = loadSpec();
const dirOf = (d: string) => { const p = path.join(UI_DIR, d); mkdirSync(p, { recursive: true }); return p; };

const rel = (p: string) => path.relative(UI_DIR, p);  // shots.json paths are relative to .agent/ui

async function capture(page: Page, shot: Shot, file: string): Promise<string> {
  await page.setViewportSize({ width: shot.viewport.width, height: shot.viewport.height });
  await page.emulateMedia({ colorScheme: shot.theme, reducedMotion: 'reduce' });
  if (spec.theme_key)
    await page.addInitScript(([k, t]) => { try { localStorage.setItem(k, t); } catch { /* storage blocked */ } }, [spec.theme_key, shot.theme]);
  await page.goto(shot.path, { waitUntil: 'networkidle' });
  if (spec.hide.length) await page.addStyleTag({ content: `${spec.hide.join(',')} { visibility: hidden !important; }` });
  await page.evaluate(() => document.fonts?.ready);
  await page.waitForTimeout(spec.settle_ms);
  await page.screenshot({
    path: file, fullPage: spec.full_page, animations: 'disabled', caret: 'hide',
    mask: spec.mask.map((s) => page.locator(s)), maskColor: '#ff00ff',
  });
  return new URL(page.url()).pathname;
}

type Box = [number, number, number, number];  // x, y, w, h in after-image pixels
type Diff = { width: number; height: number; size_changed: boolean; changed: number; total: number; png: string; boxes: Box[]; marked: string };

/** Pixel diff in a blank page: changed pixels in red over a faded copy of the after image, plus a copy of the after image
 *  with a red box around each changed area (32 px grid cells, joined when they touch). */
async function diff(page: Page, before: string, after: string): Promise<Diff> {
  await page.goto('about:blank');
  const b64 = (f: string) => 'data:image/png;base64,' + readFileSync(f).toString('base64');
  return page.evaluate(async ({ a, b, tol, minPx }) => {
    const load = (src: string) => new Promise<HTMLImageElement>((ok, bad) => {
      const i = new Image(); i.onload = () => ok(i); i.onerror = () => bad(new Error('image load')); i.src = src;
    });
    const [ib, ia] = await Promise.all([load(b), load(a)]);
    const w = Math.max(ib.width, ia.width), h = Math.max(ib.height, ia.height);
    const px = (img: HTMLImageElement) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h;
      const x = c.getContext('2d')!; x.fillStyle = '#000'; x.fillRect(0, 0, w, h); x.drawImage(img, 0, 0);
      return x.getImageData(0, 0, w, h);
    };
    const B = px(ib).data, A = px(ia), out = new ImageData(w, h), D = A.data, O = out.data;
    const CELL = 32, gw = Math.ceil(w / CELL), gh = Math.ceil(h / CELL), cells = new Uint32Array(gw * gh);
    let changed = 0;
    for (let i = 0; i < D.length; i += 4) {
      const same = Math.abs(D[i] - B[i]) <= tol && Math.abs(D[i + 1] - B[i + 1]) <= tol && Math.abs(D[i + 2] - B[i + 2]) <= tol;
      if (same) {
        const g = (D[i] * 0.3 + D[i + 1] * 0.59 + D[i + 2] * 0.11) * 0.35 + 165;
        O[i] = O[i + 1] = O[i + 2] = g; O[i + 3] = 255;
      } else {
        changed++; O[i] = 230; O[i + 1] = 20; O[i + 2] = 60; O[i + 3] = 255;
        const p = i / 4; cells[Math.floor(Math.floor(p / w) / CELL) * gw + Math.floor((p % w) / CELL)]++;
      }
    }
    // Changed areas: grid cells with a few changed pixels, grouped by 8-neighbour flood fill; tiny specks are ignored.
    const boxes: [number, number, number, number][] = [], seen = new Uint8Array(gw * gh), hot = (k: number) => cells[k] >= 3;
    for (let k = 0; k < cells.length; k++) {
      if (!hot(k) || seen[k]) continue;
      let x0 = k % gw, x1 = x0, y0 = Math.floor(k / gw), y1 = y0, px = 0;
      const stack = [k]; seen[k] = 1;
      while (stack.length) {
        const q = stack.pop()!, cx = q % gw, cy = Math.floor(q / gw);
        px += cells[q]; x0 = Math.min(x0, cx); x1 = Math.max(x1, cx); y0 = Math.min(y0, cy); y1 = Math.max(y1, cy);
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const nx = cx + dx, ny = cy + dy, n = ny * gw + nx;
          if (nx >= 0 && ny >= 0 && nx < gw && ny < gh && !seen[n] && hot(n)) { seen[n] = 1; stack.push(n); }
        }
      }
      if (px >= Math.min(minPx, 20)) boxes.push([x0 * CELL, y0 * CELL, Math.min(w, (x1 + 1) * CELL) - x0 * CELL, Math.min(h, (y1 + 1) * CELL) - y0 * CELL]);
    }
    const shown = boxes.length > 12 ? [boxes.reduce((u, bx) => {
      const x = Math.min(u[0], bx[0]), y = Math.min(u[1], bx[1]);
      return [x, y, Math.max(u[0] + u[2], bx[0] + bx[2]) - x, Math.max(u[1] + u[3], bx[1] + bx[3]) - y] as [number, number, number, number];
    })] : boxes;
    const enc = (draw: (x: CanvasRenderingContext2D) => void) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d')!);
      return c.toDataURL('image/png').split(',')[1];
    };
    const png = enc((x) => x.putImageData(out, 0, 0));
    const marked = enc((x) => {
      x.putImageData(A, 0, 0);
      x.strokeStyle = 'rgb(229, 46, 60)'; x.lineWidth = 4;
      for (const [bx, by, bw, bh] of shown) {
        const pad = 6, rx = Math.max(2, bx - pad), ry = Math.max(2, by - pad);
        x.beginPath(); x.roundRect(rx, ry, Math.min(w - 2, bx + bw + pad) - rx, Math.min(h - 2, by + bh + pad) - ry, 8); x.stroke();
      }
    });
    return { width: w, height: h, size_changed: ib.width !== ia.width || ib.height !== ia.height,
             changed, total: w * h, png, boxes: shown, marked };
  }, { a: b64(after), b: b64(before), tol: spec.tolerance, minPx: spec.min_pixels });
}

for (const shot of spec.shots) {
  test.describe(shot.role, () => {
    const state = storageStatePath(shot.role);
    if (state) test.use({ storageState: state });

    test(shot.id, async ({ page }) => {
      const file = path.join(dirOf(PHASE), `${shot.id}.png`);
      const finalPath = await capture(page, shot, file);
      const meta: Record<string, unknown> = {
        id: shot.id, page: shot.path, role: shot.role, viewport: shot.viewport, theme: shot.theme,
        [PHASE]: rel(file), [`final_path_${PHASE}`]: finalPath, [`at_${PHASE}`]: new Date().toISOString(),
      };
      const before = path.join(UI_DIR, 'before', `${shot.id}.png`);
      if (PHASE === 'after' && existsSync(before)) {
        const d = await diff(page, before, file);
        const out = path.join(dirOf('diff'), `${shot.id}.png`);
        writeFileSync(out, Buffer.from(d.png, 'base64'));
        const markedFile = path.join(dirOf('marked'), `${shot.id}.png`);
        writeFileSync(markedFile, Buffer.from(d.marked, 'base64'));
        Object.assign(meta, {
          diff: rel(out), marked: rel(markedFile), boxes: d.boxes, changed_pixels: d.changed, changed_pct: Math.round((10000 * d.changed) / d.total) / 100,
          size_changed: d.size_changed, size: [d.width, d.height],
        });
      }
      writeFileSync(path.join(dirOf('meta'), `${shot.id}.${PHASE}.json`), JSON.stringify(meta, null, 1));
    });
  });
}
