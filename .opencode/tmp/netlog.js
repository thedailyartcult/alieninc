const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9338;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile7','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const events=[];
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  ws.on('message', d=>{ const m=JSON.parse(d);
    if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);}
    if(m.method==='Runtime.consoleAPICalled'){ events.push('console['+m.params.type+']: '+m.params.args.map(a=>a.value||a.description||'').join(' ').slice(0,200)); }
    if(m.method==='Runtime.exceptionThrown'){ events.push('EXC: '+((m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description)||m.params.exceptionDetails.text).slice(0,300)); }
    if(m.method==='Log.entryAdded'){ events.push('LOG['+m.params.entry.level+']: '+m.params.entry.text.slice(0,200)); }
    if(m.method==='Network.responseReceived'){ const r=m.params.response; if(r.status>=400) events.push('HTTP '+r.status+' '+r.url.slice(0,120)); }
    if(m.method==='Network.loadingFailed'){ events.push('LOADFAIL '+m.params.errorText+' '+m.params.url.slice(0,120)); }
  });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,10000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'clicked';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,8000));
  const final = await send('Runtime.evaluate',{expression:`(() => ({
    childCount: document.getElementById('graph-canvas').childElementCount,
    canvases: document.querySelectorAll('canvas').length,
    graphEmptyText: (document.getElementById('graph-empty')||{}).textContent || null,
    graphEmptyHidden: (document.getElementById('graph-empty')||{}).hidden ?? null
  }))()`,returnByValue:true});
  console.log('FINAL:', JSON.stringify(final.result && final.result.value));
  console.log('EVENTS:');
  events.forEach(e=>console.log('  '+e));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
