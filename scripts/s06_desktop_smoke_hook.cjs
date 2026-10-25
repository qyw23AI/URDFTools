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

  const expectedLinks = modelLabel === 'go2' ? 42 : modelLabel === 'a1' ? 24 : modelLabel === 'a1_user' ? 23 : modelLabel === 'h1' ? 25 : modelLabel === 'mybot_v3' ? 18 : 40;
  const expectedJoints = modelLabel === 'go2' ? 41 : modelLabel === 'a1' ? 23 : modelLabel === 'a1_user' ? 22 : modelLabel === 'h1' ? 24 : modelLabel === 'mybot_v3' ? 17 : 39;
  await waitFor("document.querySelector('[data-assets-loaded]')?.dataset.assetsLoaded === 'true'");
  await waitFor("Number(document.querySelector('[data-tree-link-count]')?.dataset.treeLinkCount) === " + expectedLinks);
  await waitFor("Number(document.querySelector('[data-tree-joint-count]')?.dataset.treeJointCount) === " + expectedJoints);
  await waitFor("Number(document.querySelector('[data-mesh-count]')?.dataset.meshCount) >= 5");

  const baseline = await evaluate("(() => { const v=document.querySelector('[aria-label=\"三维机器人查看器\"]'); return {litMeshCount:Number(v.dataset.litMeshCount), texturedMeshCount:Number(v.dataset.texturedMeshCount), meshFilesLoaded:Number(v.dataset.meshFilesLoaded), assetsLoaded:v.dataset.assetsLoaded === 'true', linkCount:Number(v.dataset.treeLinkCount), jointCount:Number(v.dataset.treeJointCount), meshCount:Number(v.dataset.meshCount), visualCount:Number(v.dataset.visualCount), collisionCount:Number(v.dataset.collisionCount), collisionStyledMeshCount:Number(v.dataset.collisionStyledMeshCount), massKnownCount:Number(v.dataset.massKnownCount), massUnknownCount:Number(v.dataset.massUnknownCount), bounds:v.dataset.overallBounds.split(',').map(Number), physicsFingerprint:v.dataset.physicsFingerprint, selectedModel:document.querySelector('article button[aria-pressed=true]')?.textContent || '', alerts:[...document.querySelectorAll('.robot-viewer [role=\"alert\"]')].map(e=>e.textContent)}; })()");
  fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, modelLabel + '-materials.png'),
    (await window.webContents.capturePage()).toPNG());
  console.log(JSON.stringify({event:'viewer_material_diagnostics',model:modelLabel,texturedMeshCount:baseline.texturedMeshCount,litMeshCount:baseline.litMeshCount,meshFilesLoaded:baseline.meshFilesLoaded,alerts:baseline.alerts}));
  fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, modelLabel + '-initial-canvas.png'),
    Buffer.from((await evaluate("document.querySelector('.robot-canvas canvas').toDataURL('image/png')")).split(',')[1], 'base64'));
  if (modelLabel.startsWith('a1') && baseline.texturedMeshCount < 1) throw new Error('A1 material texture did not load');
  if (!baseline.assetsLoaded || baseline.litMeshCount < 5 || baseline.linkCount !== expectedLinks || baseline.jointCount !== expectedJoints ||
      baseline.meshCount < 5 || baseline.visualCount < 5 || baseline.collisionCount < 1 ||
      baseline.collisionStyledMeshCount < 1 || baseline.massKnownCount < 1 ||
      baseline.bounds.length !== 3 || baseline.bounds.some(n => !(n > 0)) || baseline.alerts.length) {
    throw new Error('S06 ' + modelLabel + ' model did not fully load: ' + JSON.stringify(baseline));
  }
  const expectedName = modelLabel === 'go2' ? 'go2' : modelLabel.startsWith('a1') ? 'a1' : modelLabel === 'h1' ? 'h1_description' : modelLabel === 'mybot_v3' ? 'mybot_v3' : 'g1_29dof';
  if (!baseline.selectedModel.toLowerCase().includes(expectedName)) {
    throw new Error('Wrong selected reference model: ' + baseline.selectedModel);
  }

  await waitFor("document.querySelectorAll('.urdf-panel-dock .floating-panel.is-docked').length === 10");
  const dockLayout = await evaluate(`(() => {
    const read = side => [...document.querySelectorAll('.urdf-panel-dock.panel-dock-' + side + ' .floating-panel')]
      .sort((a, b) => Number(a.style.order) - Number(b.style.order))
      .map(panel => ({ title: panel.dataset.panelTitle, placement: panel.dataset.panelPlacement,
        top: panel.getBoundingClientRect().top, bottom: panel.getBoundingClientRect().bottom }));
    return { left: read('left'), right: read('right') };
  })()`);
  const leftTitles = ['文件 · 导入模型', '显示与姿态', '编辑 · URDF', '对比查看', 'CAD 模块库', 'Agent · CAD 模块'];
  const rightTitles = ['结构树', '关节控制', '质量与惯量', '几何测量'];
  for (const [side, expected] of [['left', leftTitles], ['right', rightTitles]]) {
    const actual = dockLayout[side];
    if (JSON.stringify(actual.map(panel => panel.title)) !== JSON.stringify(expected) ||
        actual.some(panel => panel.placement !== 'dock') ||
        actual.some((panel, index) => index > 0 && panel.top < actual[index - 1].bottom - 1)) {
      throw new Error('S06 panels do not start in a non-overlapping ' + side + ' dock: ' + JSON.stringify(actual));
    }
  }
  fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, modelLabel + '-docked-layout.png'),
    (await window.webContents.capturePage()).toPNG());
  for (const [label, placement] of [['左侧 ¼ 屏', 'left'], ['右侧 ¼ 屏', 'right'], ['底部 ¼ 屏', 'bottom']]) {
    await evaluate(`document.querySelector('button[aria-label="选择放大位置显示与姿态"]').click()`);
    await evaluate(` [...document.querySelectorAll('[aria-label="显示与姿态放大位置"] button')]
      .find(button => button.textContent.trim() === ${JSON.stringify(label)})?.click()`);
    await waitFor(`document.querySelector('[data-panel-title="显示与姿态"]')?.dataset.panelPlacement === ${JSON.stringify(placement)}`);
    const quarter = await evaluate(`(() => {
      const panel = document.querySelector('[data-panel-title="显示与姿态"]');
      const workspace = document.querySelector('.viewer-workspace');
      const p = panel.getBoundingClientRect(), w = workspace.getBoundingClientRect();
      return {x:p.x,y:p.y,width:p.width,height:p.height,workspaceWidth:w.width,workspaceHeight:w.height};
    })()`);
    if (placement === 'bottom' ?
        quarter.width < quarter.workspaceWidth * 0.9 || quarter.height < quarter.workspaceHeight * 0.18 :
        quarter.width < quarter.workspaceWidth * 0.21 || quarter.height < quarter.workspaceHeight * 0.6) {
      throw new Error('S06 ' + placement + ' quarter-panel size is wrong: ' + JSON.stringify(quarter));
    }
    await evaluate(`document.querySelector('button[aria-label="还原显示与姿态"]').click()`);
    await waitFor(`document.querySelector('[data-panel-title="显示与姿态"]')?.dataset.panelPlacement === 'dock'`);
  }

  const selectedJoint = await evaluate("(() => { const button=document.querySelector('[data-structure-node^=\"joint:\"]'); if (!button) return null; button.dispatchEvent(new MouseEvent('click', {bubbles:true})); return button.dataset.structureNode; })()");
  if (!selectedJoint) throw new Error('S06 ' + modelLabel + ' structure tree contains no joint');
  await waitFor("document.querySelector('[data-selected-node]')?.dataset.selectedNode === " + JSON.stringify(selectedJoint));
  await waitFor("document.querySelector('[data-joint-comparison]')?.dataset.jointComparison === " + JSON.stringify(selectedJoint.slice(6)));
  if (await evaluate("document.querySelectorAll('[data-joint-compare-model]').length") !== 1)
    throw new Error('Selected joint physical card is missing');
  const selectedPosition = await evaluate("document.querySelector('[data-selected-position]')?.dataset.selectedPosition");
  if (!selectedPosition || selectedPosition.split(',').length !== 3) throw new Error('Joint coordinate missing: ' + selectedPosition);

  await evaluate("[...document.querySelectorAll('.viewer-panel-launcher button')].find(button => button.textContent.trim() === '关节' && button.getAttribute('aria-pressed') === 'false')?.click()");
  await waitFor("document.querySelector('.joint-panel input[type=\"range\"]') !== null");
  const resizeDirections = await evaluate("[...document.querySelectorAll('.joints-window .floating-panel-resize')].map(item => item.className.split(' ').find(name => name.startsWith('resize-')))");
  if (resizeDirections.length !== 8) throw new Error('Joint panel is missing all-direction resize handles');
  const limitedCount = await evaluate("document.querySelectorAll('.joint-limit-control input').length");
  if (limitedCount) {
    await evaluate("document.querySelector('button[aria-label=\"一键切换全部关节限位\"]')?.click()");
    await waitFor("[...document.querySelectorAll('.joint-limit-control input')].every(input => !input.checked)");
    await evaluate("document.querySelector('button[aria-label=\"一键切换全部关节限位\"]')?.click()");
    await waitFor("[...document.querySelectorAll('.joint-limit-control input')].every(input => input.checked)");
  }
  const slider = await evaluate("(() => { const s=document.querySelector('.joint-panel input[type=\"range\"]'); return s ? {name:s.getAttribute('aria-label'),value:Number(s.value),min:Number(s.min),max:Number(s.max)} : null; })()");
  if (!slider || !slider.name || !Number.isFinite(slider.min) || !Number.isFinite(slider.max) || !(slider.max > slider.min)) {
    throw new Error('S06 ' + modelLabel + ' has no valid movable-joint slider');
  }
  await evaluate("document.querySelector(" + JSON.stringify(`[data-structure-node="joint:${slider.name}"]`) + ")?.dispatchEvent(new MouseEvent('click',{bubbles:true}))");
  await waitFor("document.querySelector('.robot-canvas')?.dataset.jointAxisName === " + JSON.stringify(slider.name));
  const axisMarker = await evaluate("(() => { const scene=document.querySelector('.robot-canvas'); return {origin:scene.dataset.jointAxisOrigin?.split(',').map(Number),direction:scene.dataset.jointAxisDirection?.split(',').map(Number)}; })()");
  if (axisMarker.origin?.length !== 3 || axisMarker.direction?.length !== 3 ||
      ![...axisMarker.origin, ...axisMarker.direction].every(Number.isFinite) ||
      Math.abs(Math.hypot(...axisMarker.direction) - 1) > 0.001)
    throw new Error('Selected revolute joint axis is invalid: ' + JSON.stringify(axisMarker));
  fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, modelLabel + '-selected-axis.png'),
    Buffer.from((await evaluate("document.querySelector('.robot-canvas canvas').toDataURL('image/png')")).split(',')[1], 'base64'));
  console.log(JSON.stringify({event:'viewer_joint_axis_marker', model:modelLabel, joint:slider.name, ...axisMarker}));
  const beforeQuaternion = await evaluate("document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion");
  await evaluate("document.querySelector('.joint-panel input[type=\"range\"]').focus()");
  window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
  window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
  await waitFor("Math.abs(Number(document.querySelector('.joint-panel input[type=\"range\"]')?.value) - " + slider.max + ") < 0.011");
  const afterQuaternion = await evaluate("document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion");
  if (!afterQuaternion || afterQuaternion === beforeQuaternion) throw new Error('S06 ' + modelLabel + ' joint control did not change pose');
  await waitFor("document.querySelector('.robot-canvas')?.dataset.jointAxisName === " + JSON.stringify(slider.name));
  const axisAfter = await evaluate("document.querySelector('.robot-canvas')?.dataset.jointAxisDirection?.split(',').map(Number)");
  if (axisAfter?.length !== 3 || !axisAfter.every(Number.isFinite) || Math.abs(Math.hypot(...axisAfter) - 1) > 0.001)
    throw new Error('Joint axis marker was lost after changing pose: ' + JSON.stringify(axisAfter));
  await evaluate("document.querySelector('[data-structure-node^=\"link:\"]')?.dispatchEvent(new MouseEvent('click',{bubbles:true}))");
  await waitFor("!document.querySelector('.robot-canvas')?.dataset.jointAxisName");
  const afterJoint = await evaluate("document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint");
  if (afterJoint !== baseline.physicsFingerprint) throw new Error('Joint movement changed raw URDF physics fields');
  await evaluate("document.querySelector('[data-structure-node=\"joint:" + slider.name + "\"]')?.dispatchEvent(new MouseEvent('click',{bubbles:true}))");
  await evaluate("document.querySelector('.angle-unit-switch button:last-child')?.click()");
  const degrees = await evaluate("(() => ({unit:document.querySelector('[data-angle-unit]')?.dataset.angleUnit,selected:document.querySelector('[data-structure-joint-value]')?.textContent,graph:document.querySelector('[data-structure-node=\"joint:" + slider.name + "\"] .joint-value')?.textContent,slider:Number(document.querySelector('.joint-panel input[type=\"range\"]')?.value),output:document.querySelector('.joint-panel output')?.textContent}))()");
  if (degrees.unit !== 'deg' || !degrees.selected?.includes('°') || !degrees.graph?.includes('°') ||
      Math.abs(degrees.slider - slider.max) > 0.011)
    throw new Error('Structure angle unit switch changed the pose or failed to display degrees: ' + JSON.stringify(degrees));
  await evaluate("document.querySelector('.angle-unit-switch button:first-child')?.click()");
  if (await evaluate("document.querySelector('[data-angle-unit]')?.dataset.angleUnit") !== 'rad')
    throw new Error('Structure angle unit did not return to radians');

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

  if (modelLabel.startsWith('a1')) {
    await evaluate("document.querySelector('input[aria-label=\"显示碰撞体\"]')?.click()");
    const beforeGravityRoot = await evaluate("Number(document.querySelector('[data-robot-root-z]')?.dataset.robotRootZ)");
    await evaluate("document.querySelector('input[aria-label=\"受重力影响\"]')?.click()");
    await waitFor("document.querySelector('.gravity-status')?.textContent.includes('正在播放重力下落')");
    const playing = await evaluate("document.querySelector('.gravity-status')?.textContent");
    if (!playing.includes('⅔ 倍速')) throw new Error('Gravity trajectory was not visibly slowed');
    const initialGravity = await evaluate("(() => ({root:Number(document.querySelector('[data-robot-root-z]')?.dataset.robotRootZ), visualMin:Number(document.querySelector('[data-gravity-visual-min]')?.dataset.gravityVisualMin)}))()");
    if ((initialGravity.root - beforeGravityRoot > 0.01 || beforeGravityRoot - initialGravity.root > 0.02) || initialGravity.visualMin < -0.0001 ||
        initialGravity.visualMin > 0.002) throw new Error('Gravity preview started with a lift or hover: ' + JSON.stringify({beforeGravityRoot, initialGravity}));
    await waitFor("document.querySelector('.gravity-status')?.textContent.includes('物理地面 z=0')");
    const grounded = await evaluate("(() => ({message:document.querySelector('.gravity-status')?.textContent, thigh:Number(document.querySelector('input[aria-label=\"FR_thigh_joint\"]')?.value), disabled:document.querySelector('input[aria-label=\"FR_thigh_joint\"]')?.disabled, visualGroundMin:Number(document.querySelector('[data-gravity-visual-min]')?.dataset.gravityVisualMin)}))()");
    if (!grounded.message.includes('物理地面 z=0') || !grounded.message.includes('12 个关节已同步') ||
        Math.abs(grounded.thigh) < 0.1 || !grounded.disabled || grounded.visualGroundMin < -0.0001 || grounded.visualGroundMin > 0.002)
      throw new Error('A1 gravity pose or ground clearance was not applied: ' + JSON.stringify(grounded));
    const canvasPng = await evaluate("document.querySelector('.robot-canvas canvas').toDataURL('image/png')");
    fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'a1-grounded-canvas.png'),
      Buffer.from(canvasPng.split(',')[1], 'base64'));
    console.log(JSON.stringify({event:'viewer_ground_diagnostics', ...grounded}));
    await evaluate("document.querySelector('input[aria-label=\"受重力影响\"]')?.click()");
    await waitFor("document.querySelector('.gravity-status')?.textContent.includes('已恢复重力前')");
  }
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
  if (process.env.URDFTOOLS_COMPARE_SECOND && process.env.URDFTOOLS_COMPARE_THIRD) {
    const bounds = await evaluate("(() => {const r=document.querySelector('[aria-label=\"本地导入\"]').getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+45)}})()");
    window.webContents.debugger.attach('1.3');
    const data = {items:[], files:[process.env.URDFTOOLS_COMPARE_SECOND,process.env.URDFTOOLS_COMPARE_THIRD],dragOperationsMask:1};
    for (const type of ['dragEnter','dragOver','drop'])
      await window.webContents.debugger.sendCommand('Input.dispatchDragEvent',{type,x:bounds.x,y:bounds.y,data});
    window.webContents.debugger.detach();
    await waitFor("Number(document.querySelector('[data-compare-loaded-count]')?.dataset.compareLoadedCount) === 2");
    await evaluate("[...document.querySelectorAll('.workbench-toolbar button')].find(b=>b.textContent.startsWith('对比查看'))?.click()");
    await waitFor("document.querySelectorAll('[data-compare-model]').length === 3");
    await evaluate("document.querySelector('[data-compare-model] button[aria-pressed]')?.click()");
    await waitFor("document.querySelector('[data-compare-model]')?.dataset.active === 'true'");
    await waitFor("Number(document.querySelector('[data-compare-loaded-count]')?.dataset.compareLoadedCount) === 2");
    await evaluate("document.querySelector('input[aria-label=\"显示惯量\"]')?.click()");
    await waitFor("Number(document.querySelector('[data-visible-inertia-marker-count]')?.dataset.visibleInertiaMarkerCount) > 0");
    const inertia = await evaluate("Number(document.querySelector('[data-inertia-marker-count]')?.dataset.inertiaMarkerCount)");
    if (inertia < 1) throw new Error('Inertia preview was not generated from mybot_v3');
    await evaluate("document.querySelector('input[aria-label=\"显示已知质心\"]')?.click()");
    await waitFor("Number(document.querySelector('[data-visible-com-marker-count]')?.dataset.visibleComMarkerCount) === 0");
    await evaluate("document.querySelector('input[aria-label=\"显示已知质心\"]')?.click()");
    await waitFor("Number(document.querySelector('[data-visible-com-marker-count]')?.dataset.visibleComMarkerCount) > 0");
    await evaluate("document.querySelector('input[aria-label=\"显示视觉模型\"]')?.click()");
    await waitFor("Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) === 0 && Number(document.querySelector('[data-compare-visible-visual-count]')?.dataset.compareVisibleVisualCount) === 0");
    await evaluate("document.querySelector('input[aria-label=\"显示视觉模型\"]')?.click()");
    await waitFor("Number(document.querySelector('[data-compare-visible-visual-count]')?.dataset.compareVisibleVisualCount) > 0");
    await evaluate("document.querySelector('input[aria-label=\"显示阴影\"]')?.click()");
    const visibility = await evaluate("(() => {const v=document.querySelector('[aria-label=\"三维机器人查看器\"]');return {loaded:Number(v.dataset.compareLoadedCount),passiveVisuals:Number(v.dataset.compareVisibleVisualCount),inertia:Number(v.dataset.inertiaMarkerCount),inertiaVisible:v.dataset.inertiaVisible,shadow:v.dataset.shadowVisible,entries:document.querySelectorAll('[data-compare-model]').length}})()");
    if (visibility.loaded !== 2 || visibility.entries !== 3 || visibility.passiveVisuals < 1 ||
        visibility.inertiaVisible !== 'true' || visibility.shadow !== 'false')
      throw new Error('Comparison display toggles failed: '+JSON.stringify(visibility));
    await evaluate("document.querySelector('input[aria-label=\"显示阴影\"]')?.click()");
    await evaluate("document.querySelector('input[aria-label=\"显示碰撞体\"]')?.click()");
    await waitFor("document.querySelector('[data-shadow-visible]')?.dataset.shadowVisible === 'true'");
    await new Promise(resolve => setTimeout(resolve, 350));
    fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR,'three-urdf-comparison.png'),
      Buffer.from((await evaluate("document.querySelector('.robot-canvas canvas').toDataURL('image/png')")).split(',')[1],'base64'));
    await evaluate("document.querySelector('.file-window button[aria-label^=\"关闭\"]')?.click()");
    await evaluate("[...document.querySelectorAll('.workbench-toolbar button')].find(b=>b.textContent.trim()==='URDF 代码' && b.getAttribute('aria-pressed')==='true')?.click()");
    await evaluate("[...document.querySelectorAll('.viewer-panel-launcher button')].filter(b=>['结构','关节'].includes(b.textContent.trim()) && b.getAttribute('aria-pressed')==='true').forEach(b=>b.click())");
    await new Promise(resolve => setTimeout(resolve, 180));
    fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR,'three-urdf-comparison-ui.png'),
      (await window.webContents.capturePage()).toPNG());
    await evaluate("document.querySelectorAll('[data-compare-model]')[1]?.querySelector('button[aria-pressed]')?.click()");
    await waitFor("document.querySelectorAll('[data-compare-model]')[1]?.dataset.active === 'true' && Number(document.querySelector('[data-compare-loaded-count]')?.dataset.compareLoadedCount) === 2");
    const expectedSwitchedLinks = process.env.URDFTOOLS_COMPARE_SECOND.includes('a1_description') ? 23 : process.env.URDFTOOLS_COMPARE_SECOND.includes('mybot_v3_with_arm') ? 24 : process.env.URDFTOOLS_COMPARE_SECOND.includes('mybot_v3') ? 18 : 2;
    await waitFor("Number(document.querySelector('[data-tree-link-count]')?.dataset.treeLinkCount) === " + expectedSwitchedLinks);
    const switchedLinks = await evaluate("Number(document.querySelector('[data-tree-link-count]')?.dataset.treeLinkCount)");
    const assertGrounded = async () => {
      await waitFor("(() => { const values = document.querySelector('[data-compare-ground-mins]')?.dataset.compareGroundMins?.split(',').map(Number); return values?.length === 3 && values.every(value => Number.isFinite(value) && Math.abs(value) <= 0.005); })()");
      const mins = await evaluate("document.querySelector('[data-compare-ground-mins]')?.dataset.compareGroundMins");
      const values = (mins || '').split(',').map(Number);
      if (values.length !== 3 || values.some(value => !Number.isFinite(value) || Math.abs(value) > 0.005))
        throw new Error('A comparison model sank below the shared grid: ' + mins);
      return values;
    };
    await assertGrounded();
    await evaluate("document.querySelectorAll('[data-compare-model]')[2]?.querySelector('button[aria-pressed]')?.click()");
    await waitFor("document.querySelectorAll('[data-compare-model]')[2]?.dataset.active === 'true' && Number(document.querySelector('[data-compare-loaded-count]')?.dataset.compareLoadedCount) === 2");
    await assertGrounded();
    await evaluate("document.querySelectorAll('[data-compare-model]')[0]?.querySelector('button[aria-pressed]')?.click()");
    await waitFor("document.querySelectorAll('[data-compare-model]')[0]?.dataset.active === 'true' && Number(document.querySelector('[data-compare-loaded-count]')?.dataset.compareLoadedCount) === 2");
    const groundMins = await assertGrounded();
    await evaluate("[...document.querySelectorAll('.viewer-panel-launcher button')].find(button => button.textContent.trim() === '结构' && button.getAttribute('aria-pressed') === 'false')?.click()");
    await evaluate("document.querySelector('[data-structure-node=\"joint:FR_hip_joint\"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))");
    await waitFor("document.querySelectorAll('[data-joint-compare-model]').length === 3");
    console.log(JSON.stringify({event:'urdf_comparison_ground_and_joint_smoke',groundMins,cards:3}));
    if (process.env.URDFTOOLS_COMPARE_TEST_GRAVITY) {
      await evaluate("document.querySelector('input[aria-label=\"受重力影响\"]')?.click()");
      await waitFor("document.querySelector('.gravity-status')?.textContent.includes('正在播放重力下落')");
      await waitFor("document.querySelector('.gravity-status')?.textContent.includes('3 个模型同步预览')");
      const message = await evaluate("document.querySelector('.gravity-status')?.textContent");
      if (!message.includes('3 个模型同步预览')) throw new Error('Multi-model gravity did not complete: ' + message);
      await evaluate("document.querySelector('input[aria-label=\"受重力影响\"]')?.click()");
      await waitFor("document.querySelector('.gravity-status')?.textContent.includes('已恢复重力前')");
      console.log(JSON.stringify({event:'urdf_comparison_gravity_smoke', models:3, restored:true}));
    }
    console.log(JSON.stringify({event:'urdf_comparison_smoke',...visibility,operationSwitched:true,switchedLinks}));
  }
};
