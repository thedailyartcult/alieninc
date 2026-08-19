const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9347;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile16','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  const errors=[];
  ws.on('message', d=>{ const m=JSON.parse(d);
    if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);}
    if(m.method==='Runtime.exceptionThrown'){ errors.push((m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description||m.params.exceptionDetails.text).slice(0,200)); }
  });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,8000));
  await send('Runtime.evaluate',{expression:`(() => {
    window.__snaps = [];
    window.__cur = { minX:1e9, maxX:-1e9, minY:1e9, maxY:-1e9, count:0, widths:{} };
    const C = CanvasRenderingContext2D.prototype;
    const oQ = C.quadraticCurveTo;
    C.quadraticCurveTo = function(cx,cy,x,y){
      const c = window.__cur;
      c.minX=Math.min(c.minX,cx,x); c.maxX=Math.max(c.maxX,cx,x);
      c.minY=Math.min(c.minY,cy,y); c.maxY=Math.max(c.maxY,cy,y);
      return oQ.call(this,cx,cy,x,y);
    };
    const oS = C.stroke;
    C.stroke = function(){
      const w = this.lineWidth||0;
      window.__cur.widths[w.toFixed(2)] = (window.__cur.widths[w.toFixed(2)]||0)+1;
      window.__cur.count++;
      return oS.call(this);
    };
    window.__snap = function(label){
      const c = window.__cur;
      window.__snaps.push({ label, minX:Math.round(c.minX), maxX:Math.round(c.maxX), minY:Math.round(c.minY), maxY:Math.round(c.maxY), count:c.count, widths:c.widths });
      c.minX=1e9; c.maxX=-1e9; c.minY=1e9; c.maxY=-1e9; c.count=0; c.widths={};
      return label;
    };
    return 'hooked';
  })()`,returnByValue:true});
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,12000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,8000));
  await send('Runtime.evaluate',{expression:`window.__snap('default')`,returnByValue:true});
  // compress vertical: set link knob low
  await send('Runtime.evaluate',{expression:`(()=>{const el=document.getElementById('graph-link'); el.value='6'; el.dispatchEvent(new Event('input',{bubbles:true})); return 'link->6';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,4000));
  await send('Runtime.evaluate',{expression:`window.__snap('after_link6')`,returnByValue:true});
  // compress horizontal: set repel knob low
  await send('Runtime.evaluate',{expression:`(()=>{const el=document.getElementById('graph-repel'); el.value='10'; el.dispatchEvent(new Event('input',{bubbles:true})); return 'repel->10';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,4000));
  await send('Runtime.evaluate',{expression:`window.__snap('after_repel10')`,returnByValue:true});
  // restore-ish: expand
  await send('Runtime.evaluate',{expression:`(()=>{const el=document.getElementById('graph-link'); el.value='40'; el.dispatchEvent(new Event('input',{bubbles:true})); return 'link->40';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,4000));
  await send('Runtime.evaluate',{expression:`window.__snap('after_link40')`,returnByValue:true});
  const res = await send('Runtime.evaluate',{expression:`(() => ({
    snaps: window.__snaps,
    active: [...document.querySelectorAll('[data-graph-preset-choice].active')].map(x=>x.dataset.graphPresetChoice),
    linkVal: document.getElementById('graph-link').value,
    repelVal: document.getElementById('graph-repel').value
  }))()`,returnByValue:true});
  console.log('SNAPS:', JSON.stringify(res.result && res.result.value, null, 1));
  console.log('ERRORS:', JSON.stringify(errors.slice(0,5)));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
