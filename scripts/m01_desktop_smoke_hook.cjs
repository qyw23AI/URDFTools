"use strict";
const fs = require('node:fs');
const path = require('node:path');

module.exports = async function runModelSmoke(window, artifactDir) {
  const js = code => window.webContents.executeJavaScript(code);
  const waitFor = async expression => {
    const deadline = Date.now() + 90000;
    while (Date.now() < deadline) {
      if (await js(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('M01 UI timeout: ' + expression + ' | ' + await js('document.querySelector("main")?.textContent.slice(-900)'));
  };
  const click = label => js(`(() => {const target=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(label)});if(!target)throw Error('Missing button: '+${JSON.stringify(label)});target.click()})()`);
  const input = (label, value) => js(`(() => {const target=document.querySelector('input[aria-label=${JSON.stringify(label)}]');if(!target)throw Error('Missing input: '+${JSON.stringify(label)});const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(target,${JSON.stringify(String(value))});target.dispatchEvent(new Event('input',{bubbles:true}));target.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  console.log(JSON.stringify({event:'m01_step',step:'open'}));
  await click('建模');
  await waitFor('document.querySelector("[aria-label=机器人建模工作台]") !== null');
  console.log(JSON.stringify({event:'m01_step',step:'add'}));
  await click('添加零件');
  await waitFor('document.querySelector("main").textContent.includes("Base · rectangle")');
  await input('零件名称', 'Arm');
  await click('添加零件');
  await waitFor('document.querySelector("main").textContent.includes("Arm · rectangle")');
  await input('Arm x mm', '50');
  console.log(JSON.stringify({event:'m01_step',step:'undo'}));
  await click('撤销');
  await waitFor(`Number(document.querySelector('input[aria-label="Arm x mm"]')?.value) === 0`);
  await click('重做');
  await waitFor(`Number(document.querySelector('input[aria-label="Arm x mm"]')?.value) === 50`);
  await click('生成 CAD 与 URDF 预览来源');
  console.log(JSON.stringify({event:'m01_step',step:'build'}));
  await waitFor(`document.querySelector('[aria-label="STEP 转换向导"]') !== null`);
  const jointName = await js('document.querySelector(".cad-joint legend")?.textContent.split(" · ")[0]');
  if (!jointName) throw new Error('Model joint was not created');
  await js(`(() => {const s=document.querySelector('select[aria-label=${JSON.stringify(jointName+' type')}]');s.value='revolute';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await input(jointName+' effort', '8');
  await input(jointName+' velocity', '3');
  await js(`(() => {const s=document.querySelector('input[aria-label=${JSON.stringify(jointName+' confirmed')}]');s.click()})()`);
  console.log(JSON.stringify({event:'m01_step',step:'preview'}));
  await waitFor('Number(document.querySelector("[data-joint-gizmo-count]")?.dataset.jointGizmoCount) === 1');
  await input('Base density','2700');
  await input('Arm density','7800');
  await click('导出并交叉校验 URDF / ROS ZIP');
  await waitFor('document.querySelector("main")?.textContent.includes("导出完成：")');
  const result = { revision: await js('document.querySelector("[aria-label=机器人建模工作台]")?.textContent.match(/版本 (\\d+)：/)?.[1]'),
    gizmos: await js('Number(document.querySelector("[data-joint-gizmo-count]")?.dataset.jointGizmoCount)'),
    zipBytes: fs.statSync(process.env.URDFTOOLS_CAD_EXPORT_SMOKE).size };
  await js('document.querySelector("[data-joint-gizmo-count]")?.scrollIntoView({block:"center"})');
  await new Promise(resolve => setTimeout(resolve, 150));
  fs.writeFileSync(path.join(artifactDir,'model.png'),(await window.webContents.capturePage()).toPNG());
  console.log(JSON.stringify({event:'desktop_model_smoke',...result}));
};
