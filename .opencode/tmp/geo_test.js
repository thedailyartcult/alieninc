const fs = require("fs");
const html = fs.readFileSync(process.argv[2] || "/tmp/served.html", "utf8");
function grabSrc(name, endPat) {
  const m = html.match(new RegExp("function " + name + "\\([\\s\\S]*?" + (endPat || "\\n  \\}"), "m"));
  if (!m) throw new Error("fn not found: " + name);
  return m[0].replace(/\/\*[\s\S]*?\*\//g, "");
}
const CLUSTER_EXCLUDED_LABELS = { influences: true };
const src = [
  grabSrc("linkEndpoint"),
  grabSrc("clustersAcross"),
  grabSrc("idOf"),
  grabSrc("communities", "\\n  \\}\\n\\n  function maxOf").replace("\n\n  function maxOf", ""),
  grabSrc("assignMandaColumns", "\\n    \\}"),
].join("\n");
eval("(function(){\n" + src + "\nglobalThis.__t = { communities, assignMandaColumns };\n})();");
const { communities, assignMandaColumns } = globalThis.__t;
const payload = JSON.parse(fs.readFileSync("/tmp/realgraph.json", "utf8"));
const data = { nodes: payload.nodes.map(i => ({ id: i.id, name: i.label || i.id, label: i.label || i.id, degree: i.degree || 0 })), links: (payload.edges || []).map((e, idx) => ({ id: e.id || "e" + idx, source: e.from, target: e.to, label: e.label || "related" })) };
communities(data.nodes, data.links);
assignMandaColumns(data);
const perCol = {};
data.nodes.forEach(n => perCol[n.mandaColumn] = (perCol[n.mandaColumn] || 0) + 1);
console.log("per column (count):", Object.values(perCol).join(","));
const colXs = [...new Set(data.nodes.map(n => n.mandaColX))].sort((a,b)=>a-b);
console.log("distinct node x:", colXs.length);
const blocks = {};
data.nodes.forEach(n => { const col=n.mandaColumn; if(!blocks[col]) blocks[col]={xs:[],ys:[]}; blocks[col].xs.push(n.mandaColX); blocks[col].ys.push(n.mandaColY); });
Object.keys(blocks).sort((a,b)=>a-b).forEach(col => {
  const b = blocks[col];
  const minX = Math.min(...b.xs), maxX = Math.max(...b.xs);
  const minY = Math.min(...b.ys), maxY = Math.max(...b.ys);
  console.log(`  col ${col}: width=${(maxX-minX).toFixed(0)}px height=${(maxY-minY).toFixed(0)}px (${b.xs.length} nodes)`);
});
const allXs = data.nodes.map(n=>n.mandaColX);
const allYs = data.nodes.map(n=>n.mandaColY);
console.log("overall x span:", (Math.min(...allXs)).toFixed(0), "to", Math.max(...allXs).toFixed(0));
console.log("overall y span:", (Math.min(...allYs)).toFixed(0), "to", Math.max(...allYs).toFixed(0));
const pinned = data.nodes.filter(n=>typeof n.fx==="number").length;
console.log("pinned:", pinned, "/", data.nodes.length);
