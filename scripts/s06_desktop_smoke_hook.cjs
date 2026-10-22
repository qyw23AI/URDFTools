module.exports = async function runS06ViewerSmoke(window, path, fs, modelLabel) {
  const evaluate = expression => window.webContents.executeJavaScript(expression);
  window.webContents.on('console-message', ({ level, message }) => {
    console.log(JSON.stringify({ event: 's06_renderer_console', model: modelLabel, level, message }));
  });
  const waitFor = async expression => {
    const until = Date.now() + 90000;
    while (Date.now() < until) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const diagnostics = await evaluate("(() => { const v=document.querySelector('[aria-label=\"三维机器人查看器\"]'); return {status:document.querySelector('[data-import-status]')?.dataset.importStatus, assetsLoaded:v?.dataset.assetsLoaded, links:v?.dataset.treeLinkCount, joints:v?.dataset.treeJointCount, meshes:v?.dataset.meshCount, visuals:v?.dataset.visualCount, collisions:v?.dataset.collisionCount, errors:[...document.querySelectorAll('.robot-viewer [role=\"alert\"]')].map(e=>e.textContent), text:document.querySelector('main')?.textContent.slice(-800)}; })()");
    throw new Error('S06 ' + modelLabel + ' timeout: ' + expression + ' | ' + JSON.stringify(diagnostics));
  };

  const expectedLinks = modelLabel === 'go2' ? 42 : 40;
  const expectedJoints = modelLabel === 'go2' ? 41 : 39;
  await waitFor("document.querySelector('[data-assets-loaded]')?.dataset.assetsLoaded === 'true'");
  await waitFor("Number(document.querySelector('[data-tree-link-count]')?.dataset.treeLinkCount) === " + expectedLinks);
  await waitFor("Number(document.querySelector('[data-tree-joint-count]')?.dataset.treeJointCount) === " + expectedJoints);
  await waitFor("Number(document.querySelector('[data-mesh-count]')?.dataset.meshCount) >= 5");

  const baseline = await evaluate("(() => { const v=document.querySelector('[aria-label=\"三维机器人查看器\"]'); return {assetsLoaded:v.dataset.assetsLoaded === 'true', linkCount:Number(v.dataset.treeLinkCount), jointCount:Number(v.dataset.treeJointCount), meshCount:Number(v.dataset.meshCount), visualCount:Number(v.dataset.visualCount), collisionCount:Number(v.dataset.collisionCount), collisionStyledMeshCount:Number(v.dataset.collisionStyledMeshCount), massKnownCount:Number(v.dataset.massKnownCount), massUnknownCount:Number(v.dataset.massUnknownCount), bounds:v.dataset.overallBounds.split(',').map(Number), physicsFingerprint:v.dataset.physicsFingerprint, selectedModel:document.querySelector('article button[aria-pressed=true]')?.textContent || '', alerts:[...document.querySelectorAll('.robot-viewer [role=\"alert\"]')].map(e=>e.textContent)}; })()");
  if (!baseline.assetsLoaded || baseline.linkCount !== expectedLinks || baseline.jointCount !== expectedJoints ||
      baseline.meshCount < 5 || baseline.visualCount < 5 || baseline.collisionCount < 1 ||
      baseline.collisionStyledMeshCount < 1 || baseline.massKnownCount < 1 ||
      baseline.bounds.length !== 3 || baseline.bounds.some(n => !(n > 0)) || baseline.alerts.length) {
    throw new Error('S06 ' + modelLabel + ' model did not fully load: ' + JSON.stringify(baseline));
  }
  const expectedName = modelLabel === 'go2' ? 'go2' : 'g1_29dof';
  if (!baseline.selectedModel.toLowerCase().includes(expectedName)) {
    throw new Error('Wrong selected reference model: ' + baseline.selectedModel);
  }

  const selectedJoint = await evaluate("(() => { const button=document.querySelector('[data-structure-node^=\"joint:\"]'); if (!button) return null; button.click(); return button.dataset.structureNode; })()");
  if (!selectedJoint) throw new Error('S06 ' + modelLabel + ' structure tree contains no joint');
  await waitFor("document.querySelector('[data-selected-node]')?.dataset.selectedNode === " + JSON.stringify(selectedJoint));
  const selectedPosition = await evaluate("document.querySelector('[data-selected-position]')?.dataset.selectedPosition");
  if (!selectedPosition || selectedPosition.split(',').length !== 3) throw new Error('Joint coordinate missing: ' + selectedPosition);

  const slider = await evaluate("(() => { const s=document.querySelector('.joint-panel input[type=\"range\"]'); return s ? {name:s.getAttribute('aria-label'),value:Number(s.value),min:Number(s.min),max:Number(s.max)} : null; })()");
  if (!slider || !slider.name || !Number.isFinite(slider.min) || !Number.isFinite(slider.max) || !(slider.max > slider.min)) {
    throw new Error('S06 ' + modelLabel + ' has no valid movable-joint slider');
  }
  const beforeQuaternion = await evaluate("document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion");
  await evaluate("document.querySelector('.joint-panel input[type=\"range\"]').focus()");
  window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
  window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
  await waitFor("Math.abs(Number(document.querySelector('.joint-panel input[type=\"range\"]')?.value) - " + slider.max + ") < 0.011");
  const afterQuaternion = await evaluate("document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion");
  if (!afterQuaternion || afterQuaternion === beforeQuaternion) throw new Error('S06 ' + modelLabel + ' joint control did not change pose');
  const afterJoint = await evaluate("document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint");
  if (afterJoint !== baseline.physicsFingerprint) throw new Error('Joint movement changed raw URDF physics fields');

  await evaluate("document.querySelector('input[aria-label=\"显示碰撞体\"]').click()");
  await waitFor("Number(document.querySelector('[data-visible-collision-count]')?.dataset.visibleCollisionCount) > 0");
  const afterCollision = await evaluate("document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint");
  if (afterCollision !== baseline.physicsFingerprint) throw new Error('Collision toggle changed raw URDF physics fields');
  await evaluate("document.querySelector('input[aria-label=\"显示视觉模型\"]').click()");
  await waitFor("Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) === 0");
  const hiddenVisualCount = await evaluate("Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount)");
  await evaluate("document.querySelector('input[aria-label=\"显示视觉模型\"]').click()");
  await waitFor("Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) > 0");
  const restoredVisualCount = await evaluate("Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount)");
  const physicsAfterToggles = await evaluate("document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint");
  if (hiddenVisualCount !== 0 || restoredVisualCount < 1 || physicsAfterToggles !== baseline.physicsFingerprint) {
    throw new Error('S06 ' + modelLabel + ' visibility regression');
  }

  await evaluate("document.querySelector('button[aria-label=\"重置视角\"]').click()");
  await waitFor("Number(document.querySelector('[data-view-reset-count]')?.dataset.viewResetCount) === 1");
  const exportPath = path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, modelLabel + '-viewer-export.png');
  const exportPromise = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('S06 screenshot download timed out: ' + modelLabel)), 12000);
    window.webContents.session.once('will-download', (event, item) => {
      item.setSavePath(exportPath);
      item.once('done', (_downloadEvent, state) => {
        clearTimeout(timeout);
        if (state !== 'completed') return reject(new Error('S06 screenshot download failed: ' + state));
        try { resolve({ state, bytes: fs.statSync(exportPath).size }); }
        catch (error) { reject(error); }
      });
    });
  });
  await evaluate("document.querySelector('button[aria-label=\"导出三维截图\"]').click()");
  const exportResult = await exportPromise;
  if (exportResult.bytes < 1000) throw new Error('S06 exported PNG is too small');
  await waitFor("document.querySelector('[data-screenshot-ready]')?.dataset.screenshotReady === 'true'");

  const finalMetrics = await evaluate("(() => { const v=document.querySelector('[aria-label=\"三维机器人查看器\"]'); return {assetsLoaded:v.dataset.assetsLoaded === 'true', linkCount:Number(v.dataset.treeLinkCount), jointCount:Number(v.dataset.treeJointCount), meshCount:Number(v.dataset.meshCount), visualCount:Number(v.dataset.visualCount), visibleVisualCount:Number(v.dataset.visibleVisualCount), collisionCount:Number(v.dataset.collisionCount), collisionStyledMeshCount:Number(v.dataset.collisionStyledMeshCount), visibleCollisionCount:Number(v.dataset.visibleCollisionCount), massKnownCount:Number(v.dataset.massKnownCount), massUnknownCount:Number(v.dataset.massUnknownCount), bounds:v.dataset.overallBounds.split(',').map(Number), jointValue:Number(document.querySelector('.joint-panel input[type=\"range\"]').value), physicsFingerprint:v.dataset.physicsFingerprint, screenshotReady:v.dataset.screenshotReady === 'true', viewResetCount:Number(v.dataset.viewResetCount), alerts:[...document.querySelectorAll('.robot-viewer [role=\"alert\"]')].map(e=>e.textContent)}; })()");
  finalMetrics.model = modelLabel;
  finalMetrics.selectedModel = baseline.selectedModel;
  finalMetrics.selectedJoint = slider.name;
  finalMetrics.jointMin = slider.min;
  finalMetrics.jointMax = slider.max;
  finalMetrics.jointPosition = selectedPosition;
  finalMetrics.jointPoseChanged = afterQuaternion !== beforeQuaternion;
  finalMetrics.collisionToggleVerified = finalMetrics.visibleCollisionCount > 0;
  finalMetrics.visualToggleVerified = hiddenVisualCount === 0 && restoredVisualCount > 0;
  finalMetrics.physicsUnchanged = finalMetrics.physicsFingerprint === baseline.physicsFingerprint;
  finalMetrics.screenshotExportBytes = exportResult.bytes;
  finalMetrics.screenshotReady = finalMetrics.screenshotReady && exportResult.state === 'completed';
  delete finalMetrics.physicsFingerprint;
  if (finalMetrics.alerts.length || !finalMetrics.physicsUnchanged || !finalMetrics.jointPoseChanged) {
    throw new Error('S06 final checks failed: ' + JSON.stringify(finalMetrics));
  }
  // Record the real 3D overlay instead of the scrolled-to-slider section.
  await evaluate("document.querySelector('[aria-label=\"机器人三维场景\"]').scrollIntoView({block:'center',behavior:'instant'})");
  await new Promise(resolve => setTimeout(resolve, 180));
  const pagePng = (await window.webContents.capturePage()).toPNG();
  fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, modelLabel + '-viewer.png'), pagePng);
  console.log(JSON.stringify({ event: 'desktop_viewer_s06_smoke', ...finalMetrics, screenshotBytes: pagePng.length }));
};
