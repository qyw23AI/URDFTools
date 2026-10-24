"use strict";
const fs=require('node:fs');
const path=require('node:path');

module.exports=async function runReturnSmoke(window, artifactDir) {
  const js=code=>window.webContents.executeJavaScript(code);
  const waitFor=async expression=>{
    const deadline=Date.now()+90000;
    while(Date.now()<deadline) {
      if(await js(expression))return;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    throw new Error('M02 UI timeout: '+expression+' | '+await js('document.querySelector("main")?.textContent.slice(-900)'));
  };
  const click=label=>js(`(() => {const button=[...document.querySelectorAll('button')].find(item=>item.textContent.trim()===${JSON.stringify(label)});if(!button)throw Error('Missing button');button.click();})()`);
  await click('比较 FreeCAD 回流');
  await waitFor(`document.querySelector('[data-return-status="review_required"]') !== null`);
  const relinked=await js(`document.querySelector('[aria-label="FreeCAD 回流差异"]')?.textContent`);
  if(!relinked.includes('Base → Base') || !relinked.includes('Arm → Arm'))throw new Error('Same-part relink missing');
  await click('接受回流并重新确认关节');
  await waitFor(`document.querySelector('[aria-label="STEP 转换向导"]')?.textContent.includes('0/1 个关节已确认')`);
  process.env.URDFTOOLS_MODEL_RETURN_SMOKE=process.env.URDFTOOLS_MODEL_TOPOLOGY_SMOKE;
  await click('比较 FreeCAD 回流');
  await waitFor(`document.querySelector('[data-return-status="conflict"]') !== null`);
  const conflict=await js(`document.querySelector('[aria-label="FreeCAD 回流差异"]')?.textContent`);
  if(!conflict.includes('topology_changed') || conflict.includes('接受回流并重新确认关节'))throw new Error('Topology conflict not blocked');
  await js(`document.querySelector('[aria-label="FreeCAD 回流差异"]')?.scrollIntoView({block:'center'})`);
  await new Promise(resolve=>setTimeout(resolve,150));
  fs.writeFileSync(path.join(artifactDir,'freecad-return.png'),(await window.webContents.capturePage()).toPNG());
  console.log(JSON.stringify({event:'desktop_model_return_smoke',samePartRelink:true,
    acceptedWithJointReconfirmation:true,topologyConflictBlocked:true}));
};
