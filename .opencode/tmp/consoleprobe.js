const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9344;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile13','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const events=[];
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  ws.on('message', d=>{ const m=JSON.parse(d);
    if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);}
    if(m.method==='Runtime.consoleAPICalled'){ events.push('console.'+m.params.type+': '+m.params.args.map(a=>a.value!==undefined?a.value:(a.description||'')).join(' ').slice(0,250)); }
    if(m.method==='Runtime.exceptionThrown'){ const ed=m.params.exceptionDetails; events.push('EXC: '+((ed.exception&&ed.exception.description)||ed.text).slice(0,400)); }
    if(m.method==='Log.entryAdded'){ events.push('LOG.'+m.params.entry.level+': '+m.params.entry.text.slice(0,250)); }
  });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,9000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,12000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,8000));
  const probe = await send('Runtime.evaluate',{expression:`(() => {
    const gc = document.getElementById('graph-canvas');
    const cv = gc && gc.querySelector('canvas');
    const ge = document.getElementById('graph-empty');
    let pix='n/a';
    if (cv) { const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; const d=ctx.getImageData(0,0,w,h).data; let nz=0,amber=0,dark=0; const st=Math.max(4,Math.floor(d.length/4/60000)*4); for(let j=0;j<d.length;j+=st*4){ const a=d[j+3]; if(a>0)nz++; if(d[j]>80&&d[j]>d[j+1]+25&&d[j]>d[j+2]+25&&a>0)amber++; if(d[j]<25&&d[j+1]<20&&d[j+2]<20&&a>200)dark++; } pix={nz,amber,dark}; }
    return {
      canvas: !!cv,
      pix,
      graphEmptyText: ge?ge.textContent:null,
      graphEmptyHidden: ge?ge.hidden:null,
      activePreset: [...document.querySelectorAll('[data-graph-preset-choice].active')].map(x=>x.dataset.graphPresetChoice)
    };
  })()`,returnByValue:true});
  console.log('PROBE:', JSON.stringify(probe.result && probe.result.value, null, 1));
  console.log('EVENTS ('+events.length+'):');
  events.slice(0,30).forEach(e=>console.log('  '+e));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
