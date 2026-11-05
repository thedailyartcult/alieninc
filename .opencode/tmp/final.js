const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
const sleep = ms => new Promise(r=>setTimeout(r,ms));
(async () => {
  const port = 9354;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile23','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await sleep(250); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  const errs=[];
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} if(m.method==='Runtime.exceptionThrown'){ errs.push((m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description||m.params.exceptionDetails.text).slice(0,250)); } });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable');
  await send('Page.navigate',{url:URL});
  for(let i=0;i<60;i++){ const r=await send('Runtime.evaluate',{expression:`!!document.querySelector('[data-view="relations"]')`,returnByValue:true}); if(r.result.value) break; await sleep(500); }
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  let mounted=false;
  for(let i=0;i<90;i++){ const r=await send('Runtime.evaluate',{expression:`!!document.querySelector('#graph-canvas canvas')`,returnByValue:true}); if(r.result.value){mounted=true;break;} await sleep(500); }
  console.log('mounted:', mounted);
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await sleep(6000);
  const base = await send('Runtime.evaluate',{expression:`(() => {
    window.__S = { minY: 1e9, maxY: -1e9, count: 0, widths: {} };
    const C = CanvasRenderingContext2D.prototype;
    const oQ = C.quadraticCurveTo;
    C.quadraticCurveTo = function(cx,cy,x,y){ const s=window.__S; s.minY=Math.min(s.minY,cy,y); s.maxY=Math.max(s.maxY,cy,y); s.count++; return oQ.apply(this,arguments); };
    const oS = C.stroke;
    C.stroke = function(){ const w=this.lineWidth||0; window.__S.widths[w.toFixed(2)]=(window.__S.widths[w.toFixed(2)]||0)+1; return oS.apply(this,arguments); };
    return {
      linkOut: document.getElementById('graph-link-output').value,
      repelOut: document.getElementById('graph-repel-output').value,
      sizeOut: document.getElementById('graph-node-size-output').value,
      lineOut: document.getElementById('graph-line-width-output').value
    };
  })()`,returnByValue:true});
  console.log('post-manda knob values:', JSON.stringify(base.result.value));
  await sleep(2000);
  const idle = await send('Runtime.evaluate',{expression:`(() => ({ curves: window.__S.count, ySpan: window.__S.maxY - window.__S.minY }))()`,returnByValue:true});
  console.log('idle 2s:', JSON.stringify(idle.result.value));
  await send('Runtime.evaluate',{expression:`(()=>{const el=document.getElementById('graph-link'); el.value='6'; el.dispatchEvent(new Event('input',{bubbles:true})); return 'ev';})()`,returnByValue:true});
  await sleep(2500);
  const after = await send('Runtime.evaluate',{expression:`(() => ({ curves: window.__S.count, ySpan: window.__S.maxY - window.__S.minY, linkOut: document.getElementById('graph-link-output').value, topW: Object.entries(window.__S.widths).sort((a,b)=>b[1]-a[1]).slice(0,4) }))()`,returnByValue:true});
  console.log('post-knob(link6):', JSON.stringify(after.result.value));
  console.log('ERR:', JSON.stringify(errs.slice(0,5)));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});