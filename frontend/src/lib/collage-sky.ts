// Procedural "posterized sky" backgrounds for the landing page. Everything is
// generated from seeded noise at paint time, so no photos or third-party art
// ship with the site. Rendered at 1/3 resolution and scaled up with
// `image-rendering: pixelated` for the jagged, cut-out cloud edges.

export type SkyPreset = {
  seed: number;
  top: string; // sky colour at the top edge
  bot: string; // sky colour at the bottom edge
  cover: number; // 0..1 noise threshold for white clouds; lower = cloudier
  grass: "left" | "right" | null; // grassy wedge in a bottom corner
};

export const SKY_PRESETS = {
  hero: { seed: 3, top: "#4877b6", bot: "#b9cde6", cover: 0.56, grass: "left" },
  pale: { seed: 8, top: "#8fb2dc", bot: "#e3eaf4", cover: 0.5, grass: null },
  haze: { seed: 21, top: "#a7c1e2", bot: "#f2f5fa", cover: 0.46, grass: null },
  grass: { seed: 13, top: "#5383bf", bot: "#c6d6ea", cover: 0.58, grass: "right" },
} satisfies Record<string, SkyPreset>;

type RGB = [number, number, number];

function makeNoise(seed: number) {
  const h = (i: number, j: number) => {
    const s = Math.sin(i * 127.1 + j * 311.7 + seed * 74.7) * 43758.5453;
    return s - Math.floor(s);
  };
  const sm = (t: number) => t * t * (3 - 2 * t);
  const v = (x: number, y: number) => {
    const i = Math.floor(x), j = Math.floor(y);
    const fx = sm(x - i), fy = sm(y - j);
    const a = h(i, j), b = h(i + 1, j), c = h(i, j + 1), d = h(i + 1, j + 1);
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  };
  return (x: number, y: number, oct = 5) => {
    let s = 0, amp = 0.5, f = 1, n = 0;
    for (let k = 0; k < oct; k++) {
      s += amp * v(x * f, y * f);
      n += amp;
      amp *= 0.5;
      f *= 2.03;
    }
    return s / n;
  };
}

const rng = (seed: number) => () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const hex = (c: string): RGB => [
  parseInt(c.slice(1, 3), 16),
  parseInt(c.slice(3, 5), 16),
  parseInt(c.slice(5, 7), 16),
];
const mix = (a: RGB, b: RGB, t: number): RGB => [
  a[0] + (b[0] - a[0]) * t,
  a[1] + (b[1] - a[1]) * t,
  a[2] + (b[2] - a[2]) * t,
];
const ss = (e0: number, e1: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};

const WHITE: RGB = [252, 253, 255];
const HAZE = hex("#dfe5f0");
const EDGE = hex("#4a5268");
const GRASS_DARK = hex("#4e6b27");
const GRASS_LITE = hex("#a3b86a");
const FRINGE_PINK: RGB = [235, 120, 170];
const FRINGE_CYAN: RGB = [110, 200, 235];

/** Paint `p` into `canvas` at 1/3 of the given CSS size. */
export function paintSky(canvas: HTMLCanvasElement, cssW: number, cssH: number, p: SkyPreset) {
  const k = 3;
  const w = Math.max(2, Math.round(cssW / k));
  const hgt = Math.max(2, Math.round(cssH / k));
  canvas.width = w;
  canvas.height = hgt;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const img = ctx.createImageData(w, hgt);
  const d = img.data;
  const n = makeNoise(p.seed), g = makeNoise(p.seed + 99), r = rng(p.seed * 31 + 7);
  const top = hex(p.top), bot = hex(p.bot);
  const sc = 1 / 70;
  // 0 = sky, 1 = haze, 2 = white cloud, 3 = grass
  const band = new Uint8Array(w * hgt);
  const base = new Float32Array(w * hgt * 3);

  for (let y = 0; y < hgt; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x, yy = y / hgt, xx = x / w;
      const wx = x * sc + n(x * sc * 0.5, y * sc * 0.5, 3) * 2.2;
      const v = n(wx * 0.7, y * sc * 1.6);
      let c = mix(top, bot, Math.pow(yy, 0.85));
      c = mix(c, WHITE, ss(p.cover - 0.14, p.cover + 0.2, v) * 0.75);
      let b = v > p.cover + 0.06 ? 2 : v > p.cover ? 1 : 0;
      if (p.grass) {
        const gx = p.grass === "left" ? xx : 1 - xx;
        if (yy > 0.7 + gx * 0.55 + (g(x * 0.05, y * 0.05, 2) - 0.5) * 0.12) {
          const gv = g(x * 0.35, y * 0.12, 4);
          c = mix(GRASS_DARK, GRASS_LITE, gv);
          b = gv > 0.66 ? 2 : 3;
          if (r() > 0.985) b = 2;
        }
      }
      band[i] = b;
      base.set(b === 2 ? WHITE : b === 1 ? mix(c, HAZE, 0.75) : c, i * 3);
    }
  }

  for (let y = 0; y < hgt; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x, o = i * 4;
      let c: RGB = [base[i * 3], base[i * 3 + 1], base[i * 3 + 2]];
      const b = band[i];
      const bR = x + 1 < w ? band[i + 1] : b;
      const bD = y + 1 < hgt ? band[i + w] : b;
      // Dark outline round white areas, with a slight pink/cyan colour fringe.
      if ((b === 2) !== (bR === 2) || (b === 2) !== (bD === 2)) c = EDGE;
      else if (x + 1 < w && (band[i + 1] === 2) !== (b === 2)) c = mix(c, FRINGE_PINK, 0.4);
      else if (x > 0 && (band[i - 1] === 2) !== (b === 2)) c = mix(c, FRINGE_CYAN, 0.4);
      const grain = (r() - 0.5) * 10;
      d[o] = c[0] + grain;
      d[o + 1] = c[1] + grain;
      d[o + 2] = c[2] + grain;
      d[o + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
}
