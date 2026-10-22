'use strict';
const fs=require('node:fs');
const path=require('node:path');

module.exports=async function agentSmoke(window,artifactDir) {
  const js=code=>window.webContents.executeJavaScript(code);
  const waitFor=async(expression,timeout=240000)=>{
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){if(await js(expression))return;await new Promise(resolve=>setTimeout(resolve,100));}
    throw new Error('A01 UI timeout: '+expression+' | '+await js('document.querySelector("main")?.textContent.slice(-1000)'));
  };
  const click=label=>js(`(() => {const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(label)});if(!b)throw Error('Missing '+${JSON.stringify(label)});b.click()})()`);
  const fill=instruction=>js(`(() => {const t=document.querySelector('textarea[aria-label="Agent 建模指令"]');const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;setter.call(t,${JSON.stringify(instruction)});t.dispatchEvent(new Event('input',{bubbles:true}));t.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await fill('Increase only Arm profile width_mm from 20 to 30. Keep Base and every other parameter unchanged.');
  await click('生成建模建议');
  await waitFor(`document.querySelector('[data-agent-status="preview_only"]') !== null`);
  const first=await js(`document.querySelector('[data-agent-status]')?.textContent`);
  if(!first.includes('Arm') || !first.includes('0.'))throw new Error('Agent diff or mass not shown');
  await click('拒绝建议');
  await waitFor(`document.querySelector('[data-agent-status]') === null`);
  const before=await js(`document.querySelector('[aria-label="机器人建模工作台"]')?.textContent.includes('当前版本 1；')`);
  if(!before)throw new Error('Reject changed revision');
  await click('生成建模建议');
  await waitFor(`document.querySelector('[data-agent-status="preview_only"]') !== null`);
  await click('接受建议并生成新版本');
  await waitFor(`document.querySelector('[aria-label="机器人建模工作台"]')?.textContent.includes('当前版本 2')`);
  await click('撤销');
  await waitFor(`![...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='重做')?.disabled`);
  await click('生成 CAD 与 URDF 预览来源');
  await waitFor(`document.querySelector('[aria-label="机器人建模工作台"]')?.textContent.includes('当前版本 3')`,120000);
  fs.writeFileSync(path.join(artifactDir,'agent.png'),(await window.webContents.capturePage()).toPNG());
  console.log(JSON.stringify({event:'desktop_agent_smoke',rejected_without_revision:true,accepted_revision:2,undo_revision:3,screenshot:true}));
};
