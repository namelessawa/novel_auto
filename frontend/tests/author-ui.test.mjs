import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const vite = await createServer({
  appType: 'custom',
  logLevel: 'error',
  server: { middlewareMode: true },
})

after(async () => {
  await vite.close()
})

async function render(path, props) {
  const module = await vite.ssrLoadModule(path)
  return renderToStaticMarkup(React.createElement(module.default, props))
}

test('sidebar presents author workflow before experimental diagnostics', async () => {
  const html = await render('/src/dashboard/Sidebar.jsx', {
    novels: [],
    activeNovelId: null,
    view: 'author',
    tasks: [],
  })
  assert.ok(html.indexOf('章节创作') < html.indexOf('Tick 调度 · 实验'))
  assert.match(html, /创作圣经/)
  assert.match(html, /当前故事状态/)
  assert.match(html, /知识图谱 · 派生/)
})

test('new novel dialog defaults to author mode and labels simulation experimental', async () => {
  const html = await render('/src/dashboard/modals/NewNovelModal.jsx', {})
  assert.match(html, /aria-checked="true"/)
  assert.match(html, /作者模式/)
  assert.match(html, /EXPERIMENTAL/)
  assert.match(html, /世界模拟/)
})

test('author authorities have safe empty states without a selected novel', async () => {
  const bible = await render('/src/dashboard/views/StoryBibleView.jsx', {})
  const state = await render('/src/dashboard/views/CanonicalStateView.jsx', {})
  const threads = await render('/src/dashboard/views/StoryThreadsView.jsx', {})
  const studio = await render('/src/dashboard/views/AuthorStudioView.jsx', {})
  for (const html of [bible, state, threads, studio]) {
    assert.match(html, /请先选择作品/)
  }
})
