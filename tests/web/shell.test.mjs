import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'vite';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';

await build({ root: 'apps/web', build: { ssr: 'src/App.tsx', outDir: '../../dist/ssr' } });
const { App } = await import('../../dist/ssr/App.js');

test('React shell renders four workspace buttons and initial workspace', () => {
  const html = renderToStaticMarkup(createElement(App));
  assert.equal((html.match(/<button /g) || []).length, 4);
  assert.match(html, /<h1>查看<\/h1>/);
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 1);
  for (const name of ['查看','转换','建模','评估']) assert.ok(html.includes(name));
});

test('empty shell states capability boundaries', () => {
  const html = renderToStaticMarkup(createElement(App));
  assert.match(html, /尚未打开工程/);
  assert.match(html, /功能将在后续阶段提供/);
  assert.match(html, /尚未连接/);
});
