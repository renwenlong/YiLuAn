#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const dryRun = process.argv.includes('--dry-run');

const wechatDir = path.resolve(__dirname, '..');
const targetFile = path.join(wechatDir, 'pages', 'profile', 'about', 'index.js');

// 1. Resolve version
let version = '0.0.0';
const pkgPath = path.join(wechatDir, 'package.json');
const rootPkgPath = path.resolve(wechatDir, '..', 'package.json');

if (fs.existsSync(pkgPath)) {
  version = JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version || version;
} else if (fs.existsSync(rootPkgPath)) {
  version = JSON.parse(fs.readFileSync(rootPkgPath, 'utf8')).version || version;
} else {
  try {
    version = execSync('git describe --tags --always', { encoding: 'utf8' }).trim();
  } catch (_) {
    // keep default
  }
}

// 2. Git short sha
let gitSha = 'unknown';
try {
  gitSha = execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim();
} catch (_) {
  // keep default
}

// 3. Build time (ISO UTC)
const buildTime = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');

// 4. Read, replace, write
let content = fs.readFileSync(targetFile, 'utf8');

const replacements = {
  __APP_VERSION__: version,
  __GIT_SHA__: gitSha,
  __BUILD_TIME__: buildTime,
};

let result = content;
for (const [placeholder, value] of Object.entries(replacements)) {
  result = result.replace(new RegExp(placeholder, 'g'), value);
}

if (dryRun) {
  console.log('[dry-run] Would write to:', targetFile);
  console.log(result);
} else {
  fs.writeFileSync(targetFile, result, 'utf8');
}

console.log(`✅ Injected version ${version} / sha ${gitSha} / ${buildTime}${dryRun ? ' (dry-run)' : ''}`);
