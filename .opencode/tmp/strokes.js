const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const URL = 'https://panteon.alieninc.tech/panteon/cmb/#token=4RhbmR44gGY_5cDropKgXVUPKJpAfYV_fkb_h2yXrHg';
async function getJson(url){ return new Promise((res,rej)=>{ http.get(url,r=>{let d='';r.on('data',c=>d+=c);r.on('end',()=>res(JSON.parse(d)));}).on('error',rej); }); }
(async () => {
  const port = 9346;
  const chrome = spawn('chromium', ['--headless=new','--no-sandbox','--disable-gpu','--ignore-certificate-errors','--host-resolver-rules=MAP panteon.alieninc.tech 127.0.0.1','--user-data-dir=/tmp/chromeprofile15','--remote-debugging-port='+port,'--window-size=1600,1000','about:blank'], { stdio:'ignore' });
  let list; for(let i=0;i<40;i++){ try{ list=await getJson(`http://127.0.0.1:${port}/json/list`); if(list.length) break; }catch(e){} await new Promise(r=>setTimeout(r,250)); }
  const page = list.find(t=>t.type==='page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id=0; const pend=new Map();
  const send=(method,params={})=>new Promise((res,rej)=>{const m=++id;pend.set(m,{res,rej});ws.send(JSON.stringify({id:m,method,params}));});
  ws.on('message', d=>{ const m=JSON.parse(d); if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(m.error):p.res(m.result);} });
  await new Promise(r=>ws.on('open',r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.navigate',{url:URL});
  await new Promise(r=>setTimeout(r,8000));
  await send('Runtime.evaluate',{expression:`(() => {
    window.__cnt = {};
    const add = (k, n=1) => window.__cnt[k] = (window.__cnt[k]||0)+n;
    const C = CanvasRenderingContext2D.prototype;
    const origMove = C.moveTo, origLine = C.lineTo, origQuad = C.quadraticCurveTo;
    let px=0, py=0, minX=0, maxX=0, minY=0, maxY=0, hasPath=false;
    const resetPath = () => { minX=1e9; maxX=-1e9; minY=1e9; maxY=-1e9; hasPath=false; };
    C.moveTo = function(x,y){ px=x; py=y; if(!hasPath){ minX=maxX=x; minY=maxY=y; hasPath=true; } return origMove.call(this,x,y); };
    C.lineTo = function(x,y){ px=x; py=y; minX=Math.min(minX,x); maxX=Math.max(maxX,x); minY=Math.min(minY,y); maxY=Math.max(maxY,y); hasPath=true; return origLine.call(this,x,y); };
    C.quadraticCurveTo = function(cx,cy,x,y){ px=x; py=y; minX=Math.min(minX,x,cx); maxX=Math.max(maxX,x,cx); minY=Math.min(minY,y,cy); maxY=Math.max(maxY,y,cy); hasPath=true; return origQuad.call(this,cx,cy,x,y); };
    const origStroke = C.stroke;
    C.stroke = function(){
      const s = String(this.strokeStyle||'');
      const dx = hasPath ? (maxX-minX) : 0, dy = hasPath ? (maxY-minY) : 0;
      const w = this.lineWidth || 0;
      if (s.includes('0.028')) add('bg_grid');
      else if (s.includes('0.05')) add('rails');
      else if (s.includes('176, 92, 0.18') || s.includes('176,92,.18')) { add(dy < dx*0.5 ? 'bridge_soft_h' : 'bridge_soft_v'); add('bridge_soft_span_x='+Math.round(dx)+'_y='+Math.round(dy)); }
      else if (s.includes('196, 126, 0.5') || s.includes('196,126,.5')) add('bridge_core');
      else if (s.includes('176, 92, 0.2') || s.includes('176,92,.20')) add(dy < dx*0.5 ? 'realedge_h' : 'realedge_v');
      else if (s.includes('176, 92')) add('amber_other');
      else add('other_'+s.slice(0,20));
      resetPath();
      return origStroke.call(this);
    };
    return 'hooked';
  })()`,returnByValue:true});
  await send('Runtime.evaluate',{expression:`(()=>{const b=document.querySelector('[data-view="relations"]');b&&b.click();return 'nav';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,12000));
  await send('Runtime.evaluate',{expression:`(()=>{const b=[...document.querySelectorAll('[data-graph-preset-choice]')].find(x=>x.dataset.graphPresetChoice==='manda');b&&b.click();return 'manda';})()`,returnByValue:true});
  await new Promise(r=>setTimeout(r,9000));
  const res = await send('Runtime.evaluate',{expression:`(() => ({
    counts: window.__cnt,
    active: [...document.querySelectorAll('[data-graph-preset-choice].active')].map(x=>x.dataset.graphPresetChoice)
  }))()`,returnByValue:true});
  console.log('COUNTS:', JSON.stringify(res.result && res.result.value, null, 1));
  ws.close(); chrome.kill();
})().catch(e=>{console.error('ERR',e);process.exit(1);});
