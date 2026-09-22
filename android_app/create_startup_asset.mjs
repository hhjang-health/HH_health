import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const sharp = require('/Users/hohyunjang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');

// Exact user-supplied source.  The preprocessing below removes only the
// contiguous black canvas, then preserves every enclosed artwork pixel.
const icon = '/tmp/codex-remote-attachments/01a0aed8-40e8-74d1-bf34-dfb0c012e358/09123a63-b2b3-4fa6-b75e-d6592fa9c625/1-Photo-1.jpg';
const output = 'assets/startup.png';
const iconOutput = 'assets/icon.png';
const width = 1080;
const height = 2340;
const version = '1.3.6';

// Remove only the contiguous near-black source canvas. This is deterministic
// background extraction, so line art, lettering, and the bear are not
// regenerated or redrawn.
const source = await sharp(icon).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
const { data, info } = source;
const visited = new Uint8Array(info.width * info.height);
const queue = [];
const isCanvasBlack = (index) => data[index] < 42 && data[index + 1] < 42 && data[index + 2] < 42;
const add = (x, y) => {
  if (x < 0 || x >= info.width || y < 0 || y >= info.height) return;
  const point = y * info.width + x;
  if (visited[point] || !isCanvasBlack(point * 4)) return;
  visited[point] = 1;
  queue.push(point);
};
for (let x = 0; x < info.width; x++) { add(x, 0); add(x, info.height - 1); }
for (let y = 0; y < info.height; y++) { add(0, y); add(info.width - 1, y); }
for (let head = 0; head < queue.length; head++) {
  const point = queue[head], x = point % info.width, y = Math.floor(point / info.width);
  add(x - 1, y); add(x + 1, y); add(x, y - 1); add(x, y + 1);
}
for (let point = 0; point < visited.length; point++) if (visited[point]) data[point * 4 + 3] = 0;
const foreground = await sharp(data, { raw: { width: info.width, height: info.height, channels: 4 } }).png().toBuffer();
const suppliedArtwork = await sharp(foreground)
  .resize({ width: 590, height: 738, fit: 'contain', withoutEnlargement: true })
  .png().toBuffer();

const svg = `
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0c2440"/>
      <stop offset="0.30" stop-color="#0e192b"/>
      <stop offset="1" stop-color="#070d1b"/>
    </linearGradient>
    <radialGradient id="headerGlow" cx="52%" cy="0%" r="78%">
      <stop offset="0" stop-color="#16436d" stop-opacity=".22"/>
      <stop offset="1" stop-color="#0a1729" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="tealGlow" cx="82%" cy="58%" r="46%"><stop offset="0" stop-color="#176d68" stop-opacity=".22"/><stop offset="1" stop-color="#176d68" stop-opacity="0"/></radialGradient>
    <radialGradient id="warmGlow" cx="12%" cy="77%" r="42%"><stop offset="0" stop-color="#824b32" stop-opacity=".16"/><stop offset="1" stop-color="#824b32" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#headerGlow)"/>
  <rect width="100%" height="100%" fill="url(#tealGlow)"/>
  <rect width="100%" height="100%" fill="url(#warmGlow)"/>
  <text x="540" y="1430" text-anchor="middle" fill="#c7d6e7" opacity=".92"
        font-family="Apple SD Gothic Neo, Noto Sans CJK KR, sans-serif" font-size="35" font-weight="400">오늘도 건강하게, 한 걸음 더</text>
  <text x="540" y="2140" text-anchor="middle" fill="#8fa5bd" opacity=".74"
        font-family="Apple SD Gothic Neo, Noto Sans CJK KR, sans-serif" font-size="25">살빼자  ·  v${version}</text>
  <text x="540" y="2200" text-anchor="middle" fill="#7d95b0" opacity=".72"
        font-family="Arial, sans-serif" font-size="23" letter-spacing="3">HHJANG</text>
</svg>`;

await sharp({ create: { width, height, channels: 4, background: '#00000000' } })
  .composite([
    { input: Buffer.from(svg), top: 0, left: 0 },
    // Exact foreground, proportionally reduced to 80% only.
    { input: suppliedArtwork, top: 385, left: 245 },
  ])
  .png({ compressionLevel: 9 })
  .toFile(output);

// Android requires a square icon.  The exact supplied portrait is only
// proportionally reduced and centred on a black square; nothing is cropped.
await sharp({ create: { width: 1024, height: 1024, channels: 3, background: '#000000' } })
  .composite([{ input: await sharp(icon).resize({ width: 819, height: 1024, fit: 'contain' }).png().toBuffer(), left: 102, top: 0 }])
  .png({ compressionLevel: 9 })
  .toFile(iconOutput);

console.log(`${output}\n${iconOutput}`);
