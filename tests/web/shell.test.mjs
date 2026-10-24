import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'vite';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';

await build({ root: 'apps/web', build: { ssr: 'src/App.tsx', outDir: '../../dist/ssr' } });
const { App } = await import('../../dist/ssr/App.js');

test('React shell renders unified URDF workspace and initial workspace', () => {
  const html = renderToStaticMarkup(createElement(App));
  assert.equal((html.match(/<nav[\s\S]*?<\/nav>/)[0].match(/<button /g) || []).length, 3);
  assert.match(html, /<h1>打开机器人模型<\/h1>/);
  assert.match(html, /URDF 查看与构建/);
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 1);
  for (const name of ['URDF 工作区','转换','评估']) assert.ok(html.includes(name));
});

test('initial import workspace exposes local input choices', () => {
  const html = renderToStaticMarkup(createElement(App));
  assert.match(html, /选择文件夹/);
  assert.match(html, /选择 URDF \/ ZIP/);
  assert.match(html, /URDF 代码/);
  assert.match(html, /CAD 模块库/);
  assert.match(html, /Agent 生成 CAD/);
  assert.match(html, /本地导入/);
  assert.match(html, /当前为浏览器界面预览/);
  assert.match(html, /打开内置示例/);
  assert.match(html, /aria-label="打开内置示例" disabled=""/);
  assert.match(html, /<button disabled=""[^>]*>选择文件夹<\/button>/);
});
