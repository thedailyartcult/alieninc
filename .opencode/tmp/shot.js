const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');

const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';

async function getJson(url) {
  return new Promise((res, rej) => {
    http.get(url, r => { let d=''; r.on('data', c => d+=c); r.on('end', () => res(JSON.parse(d))); }).on('error', rej);
  });
}

(async () => {
  const port = 9333;
  const chrome = spawn('chromium', [
    '--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors',
    '--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1',
    '--user-data-dir=/tmp/chromeprofile2','--remote-debugging-port='+port,
    '--window-size=1600,1000','about:blank'
  ], { stdio: 'ignore' });
  let list;
  for (let i=0;i<40;i++){ try { list = await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; } catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const pend = new Map();
  const send = (method, params={}) => new Promise((res, rej) => { const m=++id; pend.set(m,{res,rej}); ws.send(JSON.stringify({id:m,method,params})); });
  ws.on('message', d => { const m=JSON.parse(d); if(m.id && pend.has(m.id)){ const p=pend.get(m.id); pend.delete(m.id); m.error?p.rej(m.error):p.res(m.result); } });
  await new Promise(r => ws.on('open', r));
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  await send('Page.navigate', { url: URL });
  await new Promise(r => setTimeout(r, 9000));
  const click = `(() => { const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda'); if(!b) return 'no-btn'; b.click(); return 'clicked'; })()`;
  const r1 = await send('Runtime.evaluate', { expression: click, returnByValue: true });
  console.log('click:', r1.result && r1.result.value);
  await new Promise(r => setTimeout(r, 6000));
  const r2 = await send('Runtime.evaluate', { expression: `(() => { const m=document.querySelector('[data-graph-preset-choice="manda"]'); const sel=[...document.querySelectorAll('[data-graph-preset-choice].active')].map(x=>x.dataset.graphPresetChoice); return {active: sel, mandaPressed: m?m.getAttribute('aria-pressed'):null}; })()`, returnByValue: true });
  console.log('state:', JSON.stringify(r2.result && r2.result.value));
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  require('fs').writeFileSync('/tmp/cdp/manda.png', Buffer.from(shot.data, 'base64'));
  console.log('screenshot saved /tmp/cdp/manda.png');
  ws.close(); chrome.kill();
})().catch(e => { console.error('ERR', e); process.exit(1); });
