const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9345;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile14','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const events=[];
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  ws.on('message', d=>{ const m=JSON.parse(d);
    if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);}
    if(m.method==='Runtime.consoleAPICalled' && m.params.type==='log'){ events.push(m.params.args.map(a=>a.value!==undefined?a.value:(a.description||'')).join(' ')); }
    if(m.method==='Runtime.exceptionThrown'){ const ed=m.params.exceptionDetails; events.push('EXC: '+((ed.exception&&ed.exception.description)||ed.text).slice(0,300)); }
  });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,8000));
  // inject canvas hooks (fillRect + stroke) BEFORE interacting
  await send('Runtime.evaluate',{expression:`(() => {
    window.__paintLog = [];
    const C = CanvasRenderingContext2D.prototype;
    const origFill = C.fillRect;
    C.fillRect = function(x,y,w,h){ if (w>500) window.__paintLog.push('fillRect '+w+'x'+h); return origFill.call(this,x,y,w,h); };
    const origStroke = C.stroke;
    C.stroke = function(){ if (this.strokeStyle && String(this.strokeStyle).includes('176,92') && this.lineWidth < 2) window.__paintLog.push('stroke bridge rgba(255,176,92)'); return origStroke.call(this); };
    return 'hooked';
  })()`,returnByValue:true});
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,12000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,9000));
  const res = await send('Runtime.evaluate',{expression:`(() => {
    const gc = document.getElementById('graph-canvas');
    const cv = gc && gc.querySelector('canvas');
    let pix='no-canvas';
    if (cv) { const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; const d=ctx.getImageData(0,0,w,h).data; let nz=0,dark=0; const st=Math.max(8,Math.floor(d.length/4/50000)*4); for(let j=0;j<d.length;j+=st*4){ if(d[j+3]>0)nz++; if(d[j]<25&&d[j+1]<20&&d[j+2]<20&&d[j+3]>200)dark++; } pix={w,h,nz,dark}; }
    return { paintLog: window.__paintLog.slice(0,20), pix, active: [...document.querySelectorAll('[data-graph-preset-choice].active')].map(x=>x.dataset.graphPresetChoice), emptyHidden: document.getElementById('graph-empty').hidden };
  })()`,returnByValue:true});
  console.log('RESULT:', JSON.stringify(res.result && res.result.value, null, 1));
  console.log('CONSOLE/EXC:', JSON.stringify(events.slice(0,10)));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
