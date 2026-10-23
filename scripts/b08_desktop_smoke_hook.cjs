const fs = require('node:fs');
const path = require('node:path');

module.exports = async function runResultsSmoke(window, runId, artifactDir) {
  const waitFor = async expression => {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      if (await window.webContents.executeJavaScript(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`B08 UI timeout: ${expression}; ` +
      await window.webContents.executeJavaScript('document.querySelector("main")?.textContent.slice(-600)'));
  };
  await waitFor(`!!document.querySelector('[aria-label="外部训练结果库"] button')`);
  await window.webContents.executeJavaScript(`document.querySelector('[aria-label="外部训练结果库"] button').click()`);
  await waitFor(`document.querySelector('[aria-label="外部训练结果库"]')?.textContent.includes(${JSON.stringify(runId)})`);
  const imported = await window.webContents.executeJavaScript(`window.urdftools.resultRuns()`);
  if (!imported.runs.some(item => item.run_id === runId && item.has_evidence))
    throw new Error('B08 import did not publish indexed evidence');
  await window.reload();
  await waitFor(`document.querySelectorAll('nav button').length === 4`);
  await window.webContents.executeJavaScript(`document.querySelectorAll('nav button')[3].click()`);
  await waitFor(`document.querySelector('[aria-label="外部训练结果库"]')?.textContent.includes(${JSON.stringify(runId)})`);
  const reference = process.env.URDFTOOLS_B08_SMOKE_REFERENCE;
  const candidate = process.env.URDFTOOLS_B08_SMOKE_CANDIDATE;
  let compared = null;
  if (reference && candidate) {
    compared = await window.webContents.executeJavaScript(`window.urdftools.resultCompare(${JSON.stringify(reference)}, ${JSON.stringify(candidate)})`);
    if (compared.comparison.comparability.status !== 'matched' || !compared.fixture_only ||
        compared.reference_media.length !== 1 || compared.candidate_media.length !== 1)
      throw new Error('B08 comparison or video metadata invalid');
    await window.webContents.executeJavaScript(`(() => {
      const controls = document.querySelectorAll('.result-compare-controls select');
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
      setter.call(controls[0], ${JSON.stringify(reference)}); controls[0].dispatchEvent(new Event('change', {bubbles:true}));
      setter.call(controls[1], ${JSON.stringify(candidate)}); controls[1].dispatchEvent(new Event('change', {bubbles:true}));
    })()`);
    await waitFor(`document.querySelector('.result-compare-controls button')?.disabled === false`);
    await window.webContents.executeJavaScript(`document.querySelector('.result-compare-controls button').click()`);
    await waitFor(`document.querySelectorAll('.result-videos video').length === 2`);
    const sha = compared.reference_media[0].source_sha256;
    const video = await window.webContents.executeJavaScript(`(async () => {
      const response = await fetch('urdftools://result/${sha}');
      return {status:response.status, type:response.headers.get('content-type'), bytes:(await response.arrayBuffer()).byteLength};
    })()`);
    if (video.status !== 200 || video.type !== 'video/mp4' || video.bytes < 1000)
      throw new Error('B08 verified local video protocol failed: ' + JSON.stringify(video));
    console.log(JSON.stringify({event:'b08_video_protocol', ...video}));
  }
  if (artifactDir) {
    fs.mkdirSync(artifactDir, {recursive:true});
    fs.writeFileSync(path.join(artifactDir, `b08-${runId}.png`), (await window.webContents.capturePage()).toPNG());
  }
  console.log(JSON.stringify({event:'b08_desktop_smoke', run_id:runId, persisted:true,
    indexed_runs:imported.runs.length, matched:compared?.comparison.comparability.status || null}));
};
