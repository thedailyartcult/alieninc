const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9342;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile11','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  const errors=[];
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} if(m.method==='Runtime.exceptionThrown'){ errors.push((m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description||m.params.exceptionDetails.text).slice(0,150)); } });
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
    const amber = (x,y) => { const i=(y*w+x)*4; const r=px[i],g=px[i+1],bl=px[i+2]; return r>90 && r>g+25 && r>bl+25; };
    // horizontal profile: amber count per x (sampled every 2 px full height)
    const prof = new Array(w).fill(0);
    for (let x=0;x<w;x+=2){ for(let y=0;y<h;y+=4){ if(amber(x,y)) prof[x]++; } }
    // find 4 dominant peaks
    const peaks=[]; const smooth = (x)=> (prof[Math.max(0,x-2)]+prof[Math.max(0,x-1)]+prof[x]+prof[Math.min(w-1,x+1)]+prof[Math.min(w-1,x+2)]);
    for(let x=3;x<w-3;x++){ const s=smooth(x); const s0=smooth(x-1), s1=smooth(x+1); if(s>=s0&&s>=s1){ const pr=smooth(x-3), nr=smooth(x+3); if(s>=pr&&s>=nr&&s>50){ if(!peaks.length||x-peaks[peaks.length-1].x>15) peaks.push({x,v:s}); } } }
    const top = peaks.sort((a,b)=>b.v-a.v).slice(0,6).sort((a,b)=>a.x-b.x);
    // For the 4 largest peaks, measure vertical pattern at that x: fraction of y that are amber (dots => ~node/step, line => ~1)
    const vinfo = top.map(pk => {
      let count=0, runs=0, inRun=false;
      for(let y=0;y<h;y+=1){ if(amber(pk.x,y)){ count++; if(!inRun){runs++; inRun=true;} } else inRun=false; }
      return {x:pk.x, v:pk.v, amberFrac:(count/h).toFixed(3), runs};
    });
    // For each midpoint gap between adjacent top peaks, measure horizontal pattern: for each y, frac of x in gap that are amber; report max row frac
    const gapinfo = [];
    for(let i=0;i<top.length-1;i++){
      const a=top[i], b=top[i+1];
      let rowCount=0, bestRow=0;
      for(let y=0;y<h;y+=1){ let c=0; for(let x=a.x+4;x<b.x-4;x+=2){ if(amber(x,y)) c++; } const frac=c/((b.x-a.x-8)/2); if(frac>0.5) rowCount++; if(frac>bestRow) bestRow=frac; }
      gapinfo.push({from:a.x, to:b.x, horizontalRows:rowCount, bestRowFrac:bestRow.toFixed(2)});
    }
    return { w, h, peaks: top, vinfo, gapinfo };
  })()`,returnByValue:true});
  console.log('VERIFY:', JSON.stringify(probe.result && probe.result.value, null, 1));
  console.log('ERRORS:', JSON.stringify(errors.slice(0,5)));
  const shot = await send('Page.captureScreenshot',{format:'png'});
  require('fs').writeFileSync('/tmp/cdp/manda4.png', Buffer.from(shot.data,'base64'));
  console.log('shot saved');
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
