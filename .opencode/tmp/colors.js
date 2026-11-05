const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9341;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile10','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,9000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,12000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,8000));
  const probe = await send('Runtime.evaluate',{expression:`(() => {
    const gc = document.getElementById('graph-canvas');
    const cv = gc && gc.querySelector('canvas');
    if (!cv) return {err:'no canvas'};
    const ctx = cv.getContext('2d');
    const w = cv.width, h = cv.height;
    const px = ctx.getImageData(0,0,w,h).data;
    const at = (x,y) => { const i=(Math.floor(y)*w+Math.floor(x))*4; return [px[i],px[i+1],px[i+2],px[i+3]]; };
    const pts = { topLeft: at(10,10), topMid: at(w/2,10), center: at(w/2,h/2), bottomRight: at(w-10,h-10), quarter: at(w/4,h/4), threeQ: at(3*w/4,h/4) };
    // count distinct colors: sample grid 200x140
    const colors = new Map();
    for (let y=0;y<h;y+=6){ for(let x=0;x<w;x+=6){ const c=at(x,y); const key=c.join(','); colors.set(key,(colors.get(key)||0)+1); } }
    const topColors = [...colors.entries()].sort((a,b)=>b[1]-a[1]).slice(0,10);
    return { w, h, pts, topColors };
  })()`,returnByValue:true});
  console.log('PIXELS:', JSON.stringify(probe.result && probe.result.value, null, 1));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
