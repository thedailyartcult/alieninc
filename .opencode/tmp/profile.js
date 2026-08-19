const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9340;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile9','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
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
    // horizontal profile: sum amber pixels per x (step 3), full height
    const N = Math.floor(w/3);
    const prof = new Array(N).fill(0);
    for (let y=0;y<h;y+=3){ for(let xb=0;xb<N;xb++){ const x=xb*3; const i=(y*w+x)*4; const r=px[i],g=px[i+1],bl=px[i+2]; if(r>90&&r>g+30&&r>bl+30) prof[xb]++; } }
    // find local maxima (peaks) separated by >10 buckets
    const peaks=[]; const MIN=200;
    for(let xb=1;xb<N-1;xb++){ if(prof[xb]>=MIN && prof[xb]>=prof[xb-1] && prof[xb]>=prof[xb+1]){ if(!peaks.length || xb-peaks[peaks.length-1].x>10) peaks.push({x:xb, v:prof[xb]}); } }
    const top = peaks.sort((a,b)=>b.v-a.v).slice(0,8).sort((a,b)=>a.x-b.x);
    return { w, h, N, peaks: top.map(p=>({px:p.x*3, v:p.v})) };
  })()`,returnByValue:true});
  console.log('PROFILE:', JSON.stringify(probe.result && probe.result.value));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
