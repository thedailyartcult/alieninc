const fs = require("fs");
const html = fs.readFileSync("/tmp/served.html", "utf8");
function grabSrc(name, endPat) {
  const m = html.match(new RegExp("function " + name + "\\([\\s\\S]*?" + (endPat || "\\n  \\}"), "m"));
  if (!m) throw new Error("fn not found: " + name);
  return m[0].replace(/\/\*[\s\S]*?\*\//g, "");
}
const CLUSTER_EXCLUDED_LABELS = { influences: true };
const src = [
  grabSrc("linkEndpoint"), grabSrc("clustersAcross"), grabSrc("idOf"),
  grabSrc("communities", "\\n  \\}\\n\\n  function maxOf").replace("\n\n  function maxOf", ""),
  grabSrc("assignMandaColumns", "\\n    \\}"),
].join("\n");
eval("(function(){\n" + src + "\nglobalThis.__t = { communities, assignMandaColumns };\n})();");
const { communities, assignMandaColumns } = globalThis.__t;
globalThis.state = { settings: { repel: 48, link: 16, linkw: 0.6 } };
const payload = JSON.parse(fs.readFileSync("/tmp/realgraph_ov.json", "utf8"));
const data = { nodes: payload.nodes.map(i => ({ id: i.id, name: i.label || i.id, label: i.label || i.id, degree: i.degree || 0 })), links: [] };
communities(data.nodes, data.links);
assignMandaColumns(data);
const colXs = [...new Set(data.nodes.map(n => n.mandaColX))].sort((a,b)=>a-b);
const rails = colXs.map(x => data.nodes.filter(n => n.mandaColX === x).sort((a,b)=>a.mandaColY-b.mandaColY));
const WIRES = 5;
const fanPairs = (a, b, r) => { const na=a.length, nb=b.length; const p=[]; for(let k=0;k<na;k++){ for(let m=0;m<WIRES;m++){ p.push([k,(k*WIRES+m+r*3)%nb]); } } return p; };
const out = {};  // per-node outgoing count
const inc = {};  // per-node incoming count
for (let r = 0; r < rails.length - 1; r++) {
  const a = rails[r], b = rails[r+1];
  const pairs = fanPairs(a, b, r);
  for (const [k, j] of pairs) {
    out[a[k].id] = (out[a[k].id]||0)+1;
    inc[b[j].id] = (inc[b[j].id]||0)+1;
  }
}
const cols = rails.map((rail,i) => ({
  col: i+1,
  nodes: rail.length,
  totalWirings: rail.reduce((s,n)=>s+((out[n.id]||0)+(inc[n.id]||0)),0),
  minPerNode: Math.min(...rail.map(n=>(out[n.id]||0)+(inc[n.id]||0))),
  maxPerNode: Math.max(...rail.map(n=>(out[n.id]||0)+(inc[n.id]||0))),
}));
cols.forEach(c => console.log(`section ${c.col}: ${c.nodes} nodes, total wirings ${c.totalWirings}, per-node ${c.minPerNode}..${c.maxPerNode}`));