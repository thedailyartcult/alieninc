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
console.log("distinct node x (must be 4):", colXs.length, JSON.stringify(colXs));
const colSets = {};
data.nodes.forEach(n => { (colSets[n.mandaColX] = colSets[n.mandaColX] || []).push(n.mandaColY); });
Object.keys(colSets).sort((a,b)=>a-b).forEach(x => {
  const ys = colSets[x];
  const min = Math.min(...ys), max = Math.max(...ys);
  const step = ys.length > 1 ? (max - min) / (ys.length - 1) : 0;
  console.log(`  col@${x}: ${ys.length} nodes, y span ${min.toFixed(0)}..${max.toFixed(0)}, step ${step.toFixed(1)}`);
});
// verify no two nodes share a y within the same column (single file)
let collisions = 0;
Object.values(colSets).forEach(ys => { if (new Set(ys.map(y=>y.toFixed(4))).size !== ys.length) collisions++; });
console.log("columns with duplicate y:", collisions);
const pinned = data.nodes.filter(n=>typeof n.fx==="number").length;
console.log("pinned:", pinned, "/", data.nodes.length);
