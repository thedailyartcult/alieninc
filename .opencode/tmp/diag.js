const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9334;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile3','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  const errors=[];
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} if(m.method==='Runtime.exceptionThrown'){ errors.push(m.params.exceptionDetails.text + ': ' + (m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description||'')); } if(m.method==='Log.entryAdded'){ errors.push('LOG '+m.params.entry.level+': '+m.params.entry.text); } });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,9000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'clicked';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,7000));
  const diag = await send('Runtime.evaluate',{expression:`(() => {
    const c=document.querySelector('#graph-canvas')||document.querySelector('canvas');
    const cv = c && c.getContext ? c : null;
    return {
      hasCanvas: !!cv,
      canvasW: cv ? cv.canvas.width : -1,
      canvasH: cv ? cv.canvas.height : -1,
      styleName: window.state ? state.styleName : 'n/a',
      settingsMode: window.state ? state.settings.mode : 'n/a',
      bodyText: document.body.innerText.slice(0,200)
    };
  })()`,returnByValue:true});
  console.log('DIAG:', JSON.stringify(diag.result && diag.result.value));
  // inspect the graph engine's node positions if exposed
  const probe = await send('Runtime.evaluate',{expression:`(() => {
    const fg = window.state && state.graphEngine;
    let out = { fg: !!fg };
    if (fg && fg.graphData) { try { const d = fg.graphData(); out.n = (d.nodes||[]).length; out.withCol = (d.nodes||[]).filter(x=>typeof x.mandaColX==='number').length; out.sample = (d.nodes||[]).filter(x=>typeof x.mandaColX==='number').slice(0,3).map(x=>({id:x.id.slice(0,6),cx:x.mandaColX,cy:x.mandaColY})); } catch(e){ out.errd = String(e); } }
    return out;
  })()`,returnByValue:true});
  console.log('PROBE:', JSON.stringify(probe.result && probe.result.value));
  console.log('ERRORS:', JSON.stringify(errors.slice(0,8)));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
