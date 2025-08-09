#!/usr/bin/env node
/*
 Upload assets in ./assets to Cloudflare R2 using wrangler with --remote.
 Folder layout enforced:
 backgrounds/auth/, backgrounds/activities/<activity>/, icons/, animations/

 Usage:
   node scripts/upload-assets.js

 Requires:
   - scripts/.env with R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
   - wrangler installed and authenticated
*/

const fs = require('fs');
const path = require('path');
const { execSync, spawnSync } = require('child_process');
// Optional dotenv; script works without it if env vars are provided via shell
try {
  require('dotenv').config({ path: path.join(__dirname, '.env') });
} catch (_) {}

const ROOT = path.join(__dirname, '..');
const ASSETS_DIR = path.join(ROOT, 'assets');
const BUCKET = process.env.R2_BUCKET_NAME || 'instainstru-assets';

function walk(dir) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...walk(full));
    else files.push(full);
  }
  return files;
}

function toKey(filePath) {
  // enforce relative path inside backgrounds/, icons/, animations/
  const rel = path.relative(ASSETS_DIR, filePath).replace(/\\/g, '/');
  if (!/^(backgrounds|icons|animations)\//.test(rel)) {
    throw new Error(`Invalid asset path, must be under backgrounds/ icons/ or animations/: ${rel}`);
  }
  return rel;
}

function uploadFile(localPath, key) {
  const cmd = `wrangler r2 object put ${BUCKET}/${key} --file ${JSON.stringify(localPath)} --remote`;
  execSync(cmd, { stdio: 'inherit' });
}

function ensureWebp(localPngPath) {
  const dir = path.dirname(localPngPath);
  const base = path.basename(localPngPath, path.extname(localPngPath));
  const webpPath = path.join(dir, `${base}.webp`);
  if (fs.existsSync(webpPath)) return webpPath;
  // Try cwebp; if missing, skip silently
  const cwebp = spawnSync('cwebp', ['-version']);
  if (cwebp.status !== 0) return null;
  const res = spawnSync('cwebp', ['-q', '80', localPngPath, '-o', webpPath], { stdio: 'inherit' });
  if (res.status === 0 && fs.existsSync(webpPath)) return webpPath;
  return null;
}

function main() {
  if (!fs.existsSync(ASSETS_DIR)) {
    console.error(`No assets directory: ${ASSETS_DIR}`);
    process.exit(1);
  }
  const files = walk(ASSETS_DIR);
  const manifest = [];
  for (const file of files) {
    const key = toKey(file);
    console.log(`Uploading: ${key}`);
    uploadFile(file, key);
    manifest.push({ key, size: fs.statSync(file).size });

    // Auto-generate WebP for PNGs and upload alongside
    if (/\.png$/i.test(file)) {
      const webpPath = ensureWebp(file);
      if (webpPath) {
        const relWebpKey = toKey(webpPath);
        console.log(`Uploading (webp): ${relWebpKey}`);
        uploadFile(webpPath, relWebpKey);
        manifest.push({ key: relWebpKey, size: fs.statSync(webpPath).size });
      }
    }
  }
  const out = path.join(ROOT, 'assets-manifest.json');
  fs.writeFileSync(out, JSON.stringify({ bucket: BUCKET, uploadedAt: new Date().toISOString(), files: manifest }, null, 2));
  console.log(`Wrote manifest: ${out}`);
}

main();
