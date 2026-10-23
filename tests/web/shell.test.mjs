import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'vite';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';

await build({ root: 'apps/web', build: { ssr: 'src/App.tsx', outDir: '../../dist/ssr' } });
const { App } = await import('../../dist/ssr/App.js');

test('React shell renders four workspace buttons and initial workspace', () => {
  const html = renderToStaticMarkup(createElement(App));
  assert.equal((html.match(/<nav[\s\S]*?<\/nav>/)[0].match(/<button /g) || []).length, 4);
  assert.match(html, /<h1>查看<\/h1>/);
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 1);
  for (const name of ['查看','转换','建模','评估']) assert.ok(html.includes(name));
});

test('initial import workspace exposes local input choices', () => {
  const html = renderToStaticMarkup(createElement(App));
  assert.match(html, /选择文件夹/);
  assert.match(html, /选择 URDF \/ ZIP/);
  assert.match(html, /单独导入 URDF 仅包含该文件/);
  assert.match(html, /本地导入/);
  assert.match(html, /尚未连接/);
  assert.match(html, /当前是浏览器界面预览/);
  assert.match(html, /<button disabled=""[^>]*>选择文件夹<\/button>/);
});
