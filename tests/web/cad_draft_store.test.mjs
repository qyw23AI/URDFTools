import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createCadDraftStore } = require('../../apps/desktop/cadDraftStore.cjs');
const root = await fs.mkdtemp(path.join(os.tmpdir(), 'urdf-cad-draft-'));
try {
  const source = path.join(root, 'original.step');
  await fs.writeFile(source, 'original CAD bytes');
  const sha = 'a'.repeat(64);
  const store = createCadDraftStore(path.join(root, 'checkpoint'));
  assert.equal(await store.read(), null);
  await store.begin(source, {source_sha256: sha, source_name: 'original.step'}, null);
  const ui = {source_sha256: sha, config: {source_sha256: sha, links: [], joints: []}, step: 'links'};
  await store.save(ui);
  assert.deepEqual((await store.read()).ui, ui);
  await fs.rm(source);
  assert.equal(await fs.readFile(store.sourcePath(await store.read()), 'utf8'), 'original CAD bytes');
  await assert.rejects(store.save({...ui, source_sha256: 'b'.repeat(64)}), /来源已改变/);
  await store.clear();
  assert.equal(await store.read(), null);
  console.log('CAD draft source, configuration, mismatch protection and clearing passed');
} finally { await fs.rm(root, {recursive: true, force: true}); }
