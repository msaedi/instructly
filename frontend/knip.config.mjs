import fs from 'node:fs';
import path from 'node:path';

const configPath = path.resolve('knip.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));

export default config;
