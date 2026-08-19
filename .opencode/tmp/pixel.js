const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9336;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile5','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  const errors=[];
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} if(m.method==='Runtime.exceptionThrown'){ errors.push((m.params.exceptionDetails.exception&&m.params.exceptionDetails.exception.description)||m.params.exceptionDetails.text); } if(m.method==='Log.entryAdded'&&m.params.entry.level==='error'){ errors.push('LOG '+m.params.entry.text); } });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,9000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'clicked';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,7000));
  const probe = await send('Runtime.evaluate',{expression:`(() => {
    const cv = document.getElementById('graph-canvas').querySelector('canvas');
    if (!cv) return {err:'no canvas'};
    const ctx = cv.getContext('2d');
    const w = cv.width, h = cv.height;
    const px = ctx.getImageData(0, 0, w, h).data;
    // sample in a horizontal strip across the middle height, count amber-ish pixels per x-bucket
    const BUCKETS = 16; const per = Math.floor(w / BUCKETS);
    const counts = new Array(BUCKETS).fill(0);
    const mid = Math.floor(h/2);
    for (let b=0;b<BUCKETS;b++){
      for (let x=b*per; x<(b+1)*per; x+=2){
        for (let y=Math.max(0,mid-80); y<Math.min(h,mid+80); y+=2){
          const i = (y*w+x)*4;
          const r=px[i],g=px[i+1],bl=px[i+2];
          if (r>90 && r>g+30 && r>bl+30) counts[b]++;
        }
      }
    }
    return { w, h, buckets: counts };
  })()`,returnByValue:true});
  console.log('PIXELS:', JSON.stringify(probe.result && probe.result.value));
  console.log('ERRORS:', JSON.stringify(errors.slice(0,5)));
  const shot = await send('Page.captureScreenshot',{format:'png'});
  require('fs').writeFileSync('/tmp/cdp/manda2.png', Buffer.from(shot.data,'base64'));
  console.log('shot saved');
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
