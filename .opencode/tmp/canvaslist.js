const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9343;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile12','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
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
    const cvs = [...(gc?gc.querySelectorAll('canvas'):document.querySelectorAll('canvas'))];
    return cvs.map((cv,i) => {
      const ctx = cv.getContext('2d');
      const w = cv.width, h = cv.height;
      if(!w||!h) return {i, w, h, empty:true};
      const px = ctx.getImageData(0,0,Math.min(w,200),Math.min(h,200)).data;
      let nonZero=0, amber=0, dark=0;
      const step=Math.max(1,Math.floor((200*200*4)/20000));
      for(let j=0;j<px.length;j+=step*4){ const r=px[j],g=px[j+1],bl=px[j+2],a=px[j+3]; if(a>0) nonZero++; if(r>80&&r>g+25&&r>bl+25&&a>0) amber++; if(r<25&&g<20&&bl<20&&a>200) dark++; }
      return {i, w, h, nonZero, amber, dark, className:(cv.className||'').slice(0,30), style:(cv.getAttribute('style')||'').slice(0,60)};
    });
  })()`,returnByValue:true});
  console.log('CANVASES:', JSON.stringify(probe.result && probe.result.value, null, 1));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
