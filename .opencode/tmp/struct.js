const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9335;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile4','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,9000));
  const info = await send('Runtime.evaluate',{expression:`(() => {
    const canvases = [...document.querySelectorAll('canvas')].map(c=>({id:c.id, cls:c.className, w:c.width, h:c.height}));
    const graphEl = document.getElementById('graph-canvas');
    const containers = [...document.querySelectorAll('[id*="graph"],[class*="graph"]')].slice(0,10).map(e=>({id:e.id, cls:(e.className||'').toString().slice(0,40)}));
    const glKeys = Object.keys(window).filter(k=>/graph|state|engine|cmb/i.test(k)).slice(0,20);
    return { canvases, graphEl: !!graphEl, containers, glKeys };
  })()`,returnByValue:true});
  console.log('STRUCT:', JSON.stringify(info.result && info.result.value, null, 0));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
