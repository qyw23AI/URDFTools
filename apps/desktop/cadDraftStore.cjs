const fs = require('node:fs');
const path = require('node:path');
const { randomBytes } = require('node:crypto');

const VERSION = 1;
const hashPattern = /^[0-9a-f]{64}$/;

function createCadDraftStore(directory) {
  const manifestPath = path.join(directory, 'draft.json');
  async function read() {
    let record;
    try { record = JSON.parse(await fs.promises.readFile(manifestPath, 'utf8')); }
    catch (error) { if (error.code === 'ENOENT') return null; throw error; }
    if (record.schema_version !== VERSION || !hashPattern.test(record.source_sha256) ||
        record.source_file !== `${record.source_sha256}.step`) throw new Error('CAD 暂存格式不兼容');
    return record;
  }
  async function write(record) {
    await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
    const temporary = `${manifestPath}.${randomBytes(6).toString('hex')}.partial`;
    try {
      await fs.promises.writeFile(temporary, JSON.stringify(record), { mode: 0o600 });
      await fs.promises.rename(temporary, manifestPath);
    } finally { await fs.promises.rm(temporary, { force: true }); }
  }
  return {
    read,
    sourcePath(record) { return path.join(directory, record.source_file); },
    async begin(source, draft, exchangeReport) {
      if (!hashPattern.test(draft.source_sha256)) throw new Error('CAD 文件校验值无效');
      await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
      const sourceFile = `${draft.source_sha256}.step`;
      const target = path.join(directory, sourceFile);
      if (path.resolve(source) !== path.resolve(target)) {
        const temporary = `${target}.${randomBytes(6).toString('hex')}.partial`;
        try {
          await fs.promises.copyFile(source, temporary);
          await fs.promises.chmod(temporary, 0o600);
          await fs.promises.rename(temporary, target);
        } finally { await fs.promises.rm(temporary, { force: true }); }
      }
      const previous = await read().catch(() => null);
      const record = { schema_version: VERSION, source_sha256: draft.source_sha256,
        source_file: sourceFile, source_name: draft.source_name, exchange_report: exchangeReport,
        ui: null, updated_at: new Date().toISOString() };
      await write(record);
      if (previous && previous.source_file !== sourceFile)
        await fs.promises.rm(path.join(directory, previous.source_file), { force: true });
      return record;
    },
    async save(ui) {
      const record = await read();
      if (!record || ui?.source_sha256 !== record.source_sha256 ||
          ui?.config?.source_sha256 !== record.source_sha256) throw new Error('暂存 CAD 来源已改变，请重新导入');
      if (JSON.stringify(ui).length > 2 * 1024 * 1024) throw new Error('CAD 暂存配置过大');
      record.ui = ui;
      record.updated_at = new Date().toISOString();
      await write(record);
      return record.updated_at;
    },
    async clear() { await fs.promises.rm(directory, { recursive: true, force: true }); }
  };
}

module.exports = { createCadDraftStore };
