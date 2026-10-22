// Offline recovery helper. Metadata comes only from integrity-verified public
// npm tarballs in npm-cache-catalog.json, never from another project's source.
const fs = require('node:fs');
const semver = require('../.tools/npm/node_modules/semver');
const entries = JSON.parse(fs.readFileSync('artifacts/S01/npm-cache-catalog.json'));
const root = JSON.parse(fs.readFileSync('package.json'));
const packages = { '': { name: root.name, version: root.version,
  dependencies: root.dependencies, devDependencies: root.devDependencies, engines: root.engines } };
function add(name, range, optional = false) {
  const key = `node_modules/${name}`;
  if (packages[key]) {
    if (!semver.satisfies(packages[key].version, range)) throw new Error(`Conflicting versions: ${name} ${range}`);
    return;
  }
  const candidates = entries.filter(e => e.manifest.name === name && semver.satisfies(e.manifest.version, range))
    .sort((a,b) => semver.rcompare(a.manifest.version, b.manifest.version));
  const e = candidates[0];
  if (!e) { if (optional) return; throw new Error(`Missing cached tarball ${name}@${range}`); }
  const m = e.manifest;
  if (optional && ((m.os && !m.os.includes('linux')) || (m.cpu && !m.cpu.includes('x64')))) return;
  packages[key] = { version: m.version, resolved: e.resolved, integrity: e.integrity,
    license: m.license, dependencies: m.dependencies, optionalDependencies: m.optionalDependencies,
    engines: m.engines, bin: m.bin, os: m.os, cpu: m.cpu, optional: optional || undefined };
  for (const [n,r] of Object.entries(m.dependencies || {})) add(n,r);
  for (const [n,r] of Object.entries(m.optionalDependencies || {})) add(n,r,true);
}
for (const [n,r] of Object.entries({...root.dependencies,...root.devDependencies})) add(n,r);
fs.writeFileSync('package-lock.json', JSON.stringify({name:root.name,version:root.version,lockfileVersion:3,requires:true,packages},null,2)+'\n');
console.log(`Locked ${Object.keys(packages).length-1} integrity-verified public packages`);
