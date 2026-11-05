#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

# --- A: equal-span columns (all 4 columns span the same total height) ---
oldA1 = "      const nodeDY = 26;\n      cols.forEach((group, ci) => {"
newA1 = ("      const nodeDY = 26;\n"
         "      const maxN = Math.max(...cols.map(g => g.length), 1);\n"
         "      const spanY = (maxN - 1) * nodeDY;\n"
         "      cols.forEach((group, ci) => {")
assert src.count(oldA1) == 1, f"A1 count {src.count(oldA1)}"
src = src.replace(oldA1, newA1)

oldA2 = "        const n = sorted.length;\n        sorted.forEach((node, i) => {"
newA2 = ("        const n = sorted.length;\n"
         "        const stepY = n > 1 ? spanY / (n - 1) : nodeDY;\n"
         "        sorted.forEach((node, i) => {")
assert src.count(oldA2) == 1, f"A2 count {src.count(oldA2)}"
src = src.replace(oldA2, newA2)

oldA3 = "          node.mandaColY = (i - (n - 1) / 2) * nodeDY;"
newA3 = "          node.mandaColY = (i - (n - 1) / 2) * stepY;"
assert src.count(oldA3) == 1, f"A3 count {src.count(oldA3)}"
src = src.replace(oldA3, newA3)

# --- B: ladder rungs paired by vertical fraction (horizontal rungs) ---
oldB = """        const pairsPerGap = [];
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
        ctx.restore();"""
newB = """        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.lineWidth = 1 / scale;
        for (let r = 0; r < colRails.length - 1; r++) {
          const a = colRails[r], b = colRails[r + 1];
          const na = a.members.length, nb = b.members.length;
          const rungs = Math.max(na, nb);
          ctx.strokeStyle = 'rgba(255,176,92,.18)';
          for (let i = 0; i < rungs; i++) {
            const f = rungs > 1 ? i / (rungs - 1) : 0;
            const iA = Math.min(na - 1, Math.round(f * (na - 1)));
            const iB = Math.min(nb - 1, Math.round(f * (nb - 1)));
            ctx.beginPath();
            ctx.moveTo(a.x, a.members[iA].mandaColY);
            ctx.lineTo(b.x, b.members[iB].mandaColY);
            ctx.stroke();
          }
        }
        ctx.globalCompositeOperation = 'source-over';
        ctx.strokeStyle = 'rgba(255,196,126,.5)';
        ctx.lineWidth = 1.3 / scale;
        for (let r = 0; r < colRails.length - 1; r++) {
          const a = colRails[r], b = colRails[r + 1];
          const na = a.members.length, nb = b.members.length;
          const rungs = Math.max(na, nb);
          for (let i = 0; i < rungs; i++) {
            const f = rungs > 1 ? i / (rungs - 1) : 0;
            const iA = Math.min(na - 1, Math.round(f * (na - 1)));
            const iB = Math.min(nb - 1, Math.round(f * (nb - 1)));
            ctx.beginPath();
            ctx.moveTo(a.x, a.members[iA].mandaColY);
            ctx.lineTo(b.x, b.members[iB].mandaColY);
            ctx.stroke();
          }
        }
        ctx.restore();"""
assert src.count(oldB) == 1, f"B count {src.count(oldB)}"
src = src.replace(oldB, newB)

open(path, "w").write(src)
print("v5 applied OK")
