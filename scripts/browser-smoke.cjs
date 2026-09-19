/* Optional UI QA only. The app itself has no Node/browser-package dependency. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawn } = require('node:child_process');
const { chromium } = require(process.env.WORKBENCH_PLAYWRIGHT || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, 'test-results');
  await fs.mkdir(output, { recursive: true });
  const runDir = await fs.mkdtemp(path.join(output, 'run-'));
  const referenceRoot = path.join(runDir, 'injectors');
  await fs.cp(path.join(root, 'reference/injectors'), referenceRoot, { recursive: true });
  const sourcePath = path.join(root, 'reference/injectors/QOFT_XI_HEX_STANDALONE_v1.1.txt');
  const sourceBefore = await fs.readFile(sourcePath);
  // Fault injection only touches this run's temporary reference copy, never release sources.
  const python = 'import os; from pathlib import Path; import uvicorn; from workbench.app import create_app; uvicorn.run(create_app(db_path=Path(os.environ["WORKBENCH_DB"]), reference_root=Path(os.environ["WORKBENCH_QA_REFERENCES"])), host="127.0.0.1", port=8765)';
  const server = spawn('uv', ['run', '--locked', 'python', '-c', python], {
    cwd: root, env: { ...process.env, WORKBENCH_ENABLE_OPENAI: '', OPENAI_API_KEY: '', WORKBENCH_DB: path.join(runDir, 'browser.sqlite3'), WORKBENCH_QA_REFERENCES: referenceRoot },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let serverLog = '';
  server.stdout.on('data', chunk => { serverLog += chunk; });
  server.stderr.on('data', chunk => { serverLog += chunk; });
  let browser;
  try {
    let healthy = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await fetch('http://127.0.0.1:8765/health');
        if (response.ok) {
          const health = await response.json();
          if (health.status === 'ok' && health.version === '0.2.0') { healthy = true; break; }
        }
      } catch { /* Server is still starting. */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.equal(healthy, true, `Server failed to become healthy: ${serverLog}`);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [], externalRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (!request.url().startsWith('http://127.0.0.1:8765/')) externalRequests.push(request.url());
    });
    await page.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle' });
    await page.locator('#artifact-status.valid').waitFor();
    await page.screenshot({ path: path.join(output, 'workspace-desktop.png'), fullPage: true });
    await page.locator('#title').fill('Browser smoke · demo comparison');
    const task = '  Ξ · Test exact input\n<script>window.UNSAFE = true</script>\nDo not trim.  ';
    await page.locator('#task').fill(task);
    await page.locator('#run-button').click();
    await page.locator('#experiment-status.completed').waitFor();
    assert.equal(await page.locator('.response-card').count(), 3);
    assert.equal(await page.locator('.response-card .badge.succeeded').count(), 3);
    assert.equal(await page.evaluate(() => window.UNSAFE), undefined);
    const firstMeta = await page.locator('#record-meta').textContent();
    await page.locator('#export-json').click({ trial: true });
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#export-json').click();
    const download = await downloadPromise;
    await download.saveAs(path.join(output, 'browser-demo-export.json'));
    const record = JSON.parse(await fs.readFile(path.join(output, 'browser-demo-export.json'), 'utf8'));
    assert.equal(record.experiment.request.task, task);
    assert.equal(record.experiment.runs.length, 3);
    assert.equal(record.experiment.artifact.identity.status, 'VALID');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: path.join(output, 'comparison-desktop.png'), fullPage: true });
    const jsonlDownloadPromise = page.waitForEvent('download');
    await page.locator('#export-jsonl').click();
    const jsonlDownload = await jsonlDownloadPromise;
    await jsonlDownload.saveAs(path.join(output, 'browser-demo-export.jsonl'));
    const jsonl = await fs.readFile(path.join(output, 'browser-demo-export.jsonl'), 'utf8');
    assert.equal(jsonl.trimEnd().split('\n').length, 1);
    assert.equal(JSON.parse(jsonl).experiment.experiment_id, record.experiment.experiment_id);
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator(`[data-experiment-id="${record.experiment.experiment_id}"]`).click();
    await page.locator('#experiment-status.completed').waitFor();
    assert.equal(await page.locator('#record-meta').textContent(), firstMeta);
    await page.locator('#reuse').click();
    assert.equal(await page.locator('#task').inputValue(), task);
    await page.locator('#artifact').selectOption('QOFT_XI_HEX_STANDALONE_v1.1');
    assert.equal(await page.locator('#artifact-status').textContent(), 'VALID');
    await page.locator('#title').fill('Restored QOFT · offline verification');
    await page.locator('#load-example').click();
    const qoftRequest = page.waitForResponse(response => response.url().endsWith('/api/experiments') && response.request().method() === 'POST');
    await page.locator('#run-button').click();
    const qoftId = (await (await qoftRequest).json()).experiment_id;
    await page.locator('#record-meta').filter({ hasText: qoftId }).waitFor();
    await page.locator('#experiment-status.completed').waitFor();
    assert.equal(await page.locator('.response-card .badge.succeeded').count(), 3);
    const qoftDownloadPromise = page.waitForEvent('download');
    await page.locator('#export-json').click();
    await (await qoftDownloadPromise).saveAs(path.join(output, 'browser-qoft-export.json'));
    const qoftExport = JSON.parse(await fs.readFile(path.join(output, 'browser-qoft-export.json'), 'utf8'));
    const qoftBytes = Buffer.from(qoftExport.experiment.artifact.bytes_base64, 'base64');
    assert.equal(qoftBytes.length, 80140);
    assert.equal(createHash('sha256').update(qoftBytes).digest('hex'), '6ee2dc6f39bbc24aee92656aa74f71020caf7d4ca4c0897a3b14c0b245242db6');
    assert.equal(qoftExport.experiment.artifact.identity.scoped_sha256, '83b31740773a0ec0cc772104bf78fe4209a0161ef58b6ac8ecd20ebd4075a0c2');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: path.join(output, 'qoft-valid-desktop.png'), fullPage: true });
    await page.locator('#delivery').selectOption('USER_PASTE_WITH_HANDSHAKE');
    await page.locator('#replicates').fill('2');
    await page.locator('#seed').fill('42');
    await page.locator('#title').fill('Handshake and replicate verification');
    const handshakeRequest = page.waitForResponse(r => r.url().endsWith('/api/experiments') && r.request().method() === 'POST');
    await page.locator('#run-button').click();
    const handshakeId = (await (await handshakeRequest).json()).experiment_id;
    await page.locator('#record-meta').filter({hasText:handshakeId}).waitFor();
    await page.locator('#experiment-status.completed').waitFor();
    assert.equal(await page.locator('.response-card .badge.succeeded').count(), 6);
    const handshakeRecord = await (await fetch('http://127.0.0.1:8765/api/experiments/' + handshakeId)).json();
    assert.equal(handshakeRecord.runs.every(r => r.calls.length === 2), true);
    assert.deepEqual(handshakeRecord.runs.map(r => r.replicate_index), [0,0,0,1,1,1]);
    assert.equal(handshakeRecord.runs.every(r => r.model_settings.seed === 42), true);
    await fs.writeFile(path.join(output, 'browser-handshake-export.json'), JSON.stringify(handshakeRecord, null, 2));
    await page.screenshot({path:path.join(output,'handshake-desktop.png'), fullPage:true});
    await fs.copyFile(path.join(root, 'reference/rejected/QOFT_XI_HEX_STANDALONE_v1.1.CRLF.txt'), path.join(referenceRoot, 'QOFT_XI_HEX_STANDALONE_v1.1.txt'));
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#artifact').selectOption('QOFT_XI_HEX_STANDALONE_v1.1');
    assert.equal(await page.locator('#artifact-status').textContent(), 'INVALID');
    // Replay succeeds from the snapshot despite the corrupted working reference.
    await page.locator(`[data-experiment-id="${handshakeId}"]`).click();
    await page.locator('#record-meta').filter({hasText:handshakeId}).waitFor();
    const replayRequest = page.waitForResponse(r => r.url().endsWith('/replay') && r.request().method() === 'POST');
    await page.locator('#replay').click();
    const replayId = (await (await replayRequest).json()).experiment_id;
    await page.locator('#record-meta').filter({hasText:replayId}).waitFor();
    await page.locator('#experiment-status.completed').waitFor();
    const replayRecord = await (await fetch('http://127.0.0.1:8765/api/experiments/' + replayId)).json();
    assert.equal(replayRecord.replay_of_experiment_id, handshakeId);
    assert.deepEqual(replayRecord.runs.map(r => r.final_condition.prompt_hash), handshakeRecord.runs.map(r => r.final_condition.prompt_hash));
    assert.equal(replayRecord.runs.every(r => r.calls.length === 1), true);
    await page.locator('#title').fill('Browser smoke · rejected QOFT artifact');
    await page.locator('#run-button').click();
    await page.locator('#experiment-status.partial').waitFor();
    assert.equal(await page.locator('[data-condition="FULL_INJECTOR"] .badge').textContent(), 'BLOCKED');
    assert.equal(await page.locator('[data-condition="BASELINE"] .badge').textContent(), 'SUCCEEDED');
    assert.equal(await page.locator('[data-condition="NEUTRAL_LENGTH_CONTROL"] .badge').textContent(), 'BLOCKED');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.screenshot({ path: path.join(output, 'integrity-block-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, 'workspace-mobile.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.locator('#artifact').selectOption('');
    await page.locator('#title').fill('Browser smoke · baseline only');
    await page.locator('#run-button').click();
    await page.locator('#experiment-status.completed').waitFor();
    assert.equal(await page.locator('.response-card').count(), 1);
    assert.deepEqual(errors, []);
    assert.deepEqual(externalRequests, []);
    assert.deepEqual(await fs.readFile(sourcePath), sourceBefore);
    const report = { status: 'PASS', browser: await browser.version(), release: '0.2.0',
      checks: ['page render', 'three isolated lanes', 'XSS text escaping', 'JSON download',
        'JSONL download', 'history after reload', 'reuse setup', 'restored QOFT VALID',
        'restored QOFT three-condition run', 'QOFT export exact full and scope hashes', 'CRLF treatment blocked',
        'baseline still succeeds', '390px no overflow', 'baseline-only run', 'no JS errors',
        'no external browser requests', 'release sources unchanged', 'handshake two-call transcripts', 'replicate indices',
        'seed settings preserved', 'snapshot replay after disk corruption', 'replay final hashes match',
        'replay uses one task call', 'invalid neutral control blocked'], output };
    await fs.writeFile(path.join(output, 'browser-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
    await context.close();
  } finally {
    if (browser) await browser.close();
    server.kill('SIGINT');
    await new Promise(resolve => {
      const timer = setTimeout(resolve, 3000);
      server.once('exit', () => { clearTimeout(timer); resolve(); });
    });
    await fs.writeFile(path.join(output, 'browser-server.log'), serverLog);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
