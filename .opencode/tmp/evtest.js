const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9348;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile17','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  const ev=[];
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} if(m.method==='Runtime.consoleAPICalled'){ ev.push(m.params.type+': '+m.params.args.map(a=>a.value!==undefined?a.value:(a.description||'')).join(' ')); } if(m.method==='Runtime.exceptionThrown'){ ev.push('EXC: '+((m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description)||m.params.exceptionDetails.text)); } });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,8000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,12000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,6000));
  // instrument: wrap addEventListener for graph-link to see if a listener is attached and whether dispatch reaches it
  await send('Runtime.evaluate',{expression:`(() => {
    window.__events = [];
    const el = document.getElementById('graph-link');
    const orig = el.addEventListener;
    el.addEventListener = function(type, fn, opts){ if(type==='input') window.__events.push('attach'); return orig.call(this, type, fn, opts); };
    return 'wrapped';
  })()`,returnByValue:true});
  // NOTE: listener already attached before wrap; instead inspect output before/after dispatch
  const before = await send('Runtime.evaluate',{expression:`(() => ({
    linkValue: document.getElementById('graph-link').value,
    linkOut: document.getElementById('graph-link-output').value,
    settingsRef: typeof window.__ss
  }))()`,returnByValue:true});
  console.log('BEFORE:', JSON.stringify(before.result.value));
  await send('Runtime.evaluate',{expression:`(() => {
    const el = document.getElementById('graph-link');
    el.value = '6';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return 'dispatched';
  })()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,1000));
  const after = await send('Runtime.evaluate',{expression:`(() => ({
    linkValue: document.getElementById('graph-link').value,
    linkOut: document.getElementById('graph-link-output').value,
    linkOutText: document.getElementById('graph-link-output').textContent
  }))()`,returnByValue:true});
  console.log('AFTER:', JSON.stringify(after.result.value));
  console.log('EVENTS:', JSON.stringify(ev.slice(0,10)));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
