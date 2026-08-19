#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

# --- Edit A: assignMandaColumns -> single vertical file per column ---
oldA1 = "      const spacing = 360;\n      const nodeDX = 34;\n      const nodeDY = 26;"
newA1 = "      const spacing = 360;\n      const nodeDY = 26;"
assert src.count(oldA1) == 1, f"A1 count {src.count(oldA1)}"
src = src.replace(oldA1, newA1)

oldA2 = "        const colW = n > 60 ? 7 : n > 30 ? 5 : n > 12 ? 4 : 3;\n        const rows = Math.ceil(n / colW);\n        sorted.forEach((node, i) => {\n          const r = Math.floor(i / colW), c = i % colW;"
newA2 = "        sorted.forEach((node, i) => {"
assert src.count(oldA2) == 1, f"A2 count {src.count(oldA2)}"
src = src.replace(oldA2, newA2)

oldA3 = "          node.mandaColX = cx + (c - (colW - 1) / 2) * nodeDX;\n          node.mandaColY = (r - (rows - 1) / 2) * nodeDY;"
newA3 = "          node.mandaColX = cx;\n          node.mandaColY = (i - (n - 1) / 2) * nodeDY;"
assert src.count(oldA3) == 1, f"A3 count {src.count(oldA3)}"
src = src.replace(oldA3, newA3)

# --- Edit B: drawMandaFan links pass -> skip same-column (vertical) edges ---
oldB = "        var sa = lk.source, ta = lk.target;\n        if (!sa || !ta) continue;"
newB = ("        var sa = lk.source, ta = lk.target;\n"
        "        if (!sa || !ta) continue;\n"
        "        /* Only left-right connections: skip edges whose endpoints sit in the same\n"
        "           column, otherwise the vertical up/down lines inside a building return. */\n"
        "        if (typeof sa.mandaColumn === 'number' && typeof ta.mandaColumn === 'number' && sa.mandaColumn === ta.mandaColumn) continue;")
assert src.count(oldB) == 1, f"B count {src.count(oldB)}"
src = src.replace(oldB, newB)

# --- Edit C: replace center-chain with ladder bridge ---
oldC = """      /* ---- Chain connections between adjacent columns ----
         Column 1 connects to column 2, column 2 to column 3, column 3 to column 4, so the
         whole arrangement reads as one intact, cohesive structure. A warm glowing connector
         joins each neighbouring column's centre. */
      if (colXs.length > 1) {
        const centers = colXs.map(x => {
          const members = nodes.filter(n => n.mandaColX === x);
          const y = members.reduce((sum, n) => sum + n.mandaColY, 0) / Math.max(1, members.length);
          return { x, y };
        });
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.strokeStyle = 'rgba(255,150,60,.16)';
        ctx.lineWidth = 6 / scale;
        ctx.beginPath();
        centers.forEach((pt, i) => { if (i === 0) ctx.moveTo(pt.x, pt.y); else ctx.lineTo(pt.x, pt.y); });
        ctx.stroke();
        ctx.globalCompositeOperation = 'source-over';
        ctx.strokeStyle = 'rgba(255,196,126,.9)';
        ctx.lineWidth = 1.6 / scale;
        ctx.beginPath();
        centers.forEach((pt, i) => { if (i === 0) ctx.moveTo(pt.x, pt.y); else ctx.lineTo(pt.x, pt.y); });
        ctx.stroke();
        centers.forEach(pt => { ctx.fillStyle = 'rgba(255,182,104,.95)'; ctx.beginPath(); ctx.arc(pt.x, pt.y, 3.4 / scale, 0, 6.2832); ctx.fill(); });
        ctx.restore();
      }"""
newC = """      /* ---- Ladder bridge between adjacent columns ----
         Column 1 connects to column 2, column 2 to column 3, column 3 to column 4 — a
         horizontal left-to-right chain. Each column is one vertical file of nodes; the bridge
         links neighbouring columns row by row (node i of the left column to node i of the
         right column) so the connection between any two columns is plainly visible. */
      if (colXs.length > 1) {
        const colRails = colXs.map(x => ({
          x,
          members: nodes.filter(n => n.mandaColX === x).slice().sort((a, b) => a.mandaColY - b.mandaColY),
        }));
        const pairsPerGap = [];
        for (let r = 0; r < colRails.length - 1; r++) pairsPerGap.push(Math.min(colRails[r].members.length, colRails[r + 1].members.length));
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.lineWidth = 1 / scale;
        for (let r = 0; r < colRails.length - 1; r++) {
          const a = colRails[r], b = colRails[r + 1];
          ctx.strokeStyle = 'rgba(255,176,92,.18)';
          for (let i = 0; i < pairsPerGap[r]; i++) {
            ctx.beginPath();
            ctx.moveTo(a.x, a.members[i].mandaColY);
            ctx.lineTo(b.x, b.members[i].mandaColY);
            ctx.stroke();
          }
        }
        ctx.globalCompositeOperation = 'source-over';
        ctx.strokeStyle = 'rgba(255,196,126,.5)';
        ctx.lineWidth = 1.3 / scale;
        for (let r = 0; r < colRails.length - 1; r++) {
          const a = colRails[r], b = colRails[r + 1];
          for (let i = 0; i < pairsPerGap[r]; i++) {
            ctx.beginPath();
            ctx.moveTo(a.x, a.members[i].mandaColY);
            ctx.lineTo(b.x, b.members[i].mandaColY);
            ctx.stroke();
          }
        }
        ctx.restore();
      }"""
assert src.count(oldC) == 1, f"C count {src.count(oldC)}"
src = src.replace(oldC, newC)

open(path, "w").write(src)
print("v4 applied OK")
