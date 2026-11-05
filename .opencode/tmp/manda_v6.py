#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

# --- A: assignMandaColumns wired to tune knobs (repel -> column spacing, link -> row spacing) ---
oldA = """      const spacing = 360;
      const nodeDY = 26;
      const maxN = Math.max(...cols.map(g => g.length), 1);
      const spanY = (maxN - 1) * nodeDY;"""
newA = """      /* Tune knobs drive the Manda shape live: "Repel force" spreads/pulls the columns
         apart horizontally, "Link distance" compresses/stretches the rows vertically, so the
         ladder can be squeezed down or drawn out. Defaults reproduce the approved look. */
      const repel = Number(state.settings.repel) || 48;
      const link = Number(state.settings.link) || 16;
      const spacing = 120 + repel * 5;
      const nodeDY = 4 + link * 1.375;
      const maxN = Math.max(...cols.map(g => g.length), 1);
      const spanY = (maxN - 1) * nodeDY;"""
assert src.count(oldA) == 1, f"A count {src.count(oldA)}"
src = src.replace(oldA, newA)

# --- B: neural-network cross wiring between columns ---
oldB = """      if (colXs.length > 1) {
        const colRails = colXs.map(x => ({
          x,
          members: nodes.filter(n => n.mandaColX === x).slice().sort((a, b) => a.mandaColY - b.mandaColY),
        }));
        ctx.save();
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
        ctx.restore();
      }"""
newB = """      if (colXs.length > 1) {
        const colRails = colXs.map(x => ({
          x,
          members: nodes.filter(n => n.mandaColX === x).slice().sort((a, b) => a.mandaColY - b.mandaColY),
        }));
        /* Neural-network wiring: instead of straight row-to-row rungs, each node fires to one
           or two nodes in the neighbouring column at a shifted offset (e.g. column 1 node 1 to
           column 2 node 10), with a seeded per-node bend so the fibre paths cross and weave
           like a neural net. Deterministic per node id, so it never flickers between frames. */
        function mandaHash(s, r) {
          let h = (2166136261 ^ r) >>> 0;
          for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
          return h >>> 0;
        }
        const linkw = Number(state.settings.linkw);
        const lineBase = Number.isFinite(linkw) && linkw > 0 ? linkw : 0.72;
        const band = Math.max(3, Math.round((nodes.length / Math.max(1, colXs.length)) * 0.12));
        const neuralPairs = (a, b, r) => {
          const na = a.members.length, nb = b.members.length;
          const pairs = [];
          for (let k = 0; k < na; k++) {
            const h = mandaHash(a.members[k].id, r);
            const rel = (h % (2 * band + 1)) - band;
            const j = Math.max(0, Math.min(nb - 1, k + rel));
            pairs.push([k, j, ((h >> 9) % 41) - 20]);
            if ((h >> 3) % 3 === 0) {
              const rel2 = (((h >> 16) % (2 * band + 1)) - band);
              const j2 = Math.max(0, Math.min(nb - 1, k + rel2));
              if (j2 !== j) pairs.push([k, j2, ((h >> 5) % 41) - 20]);
            }
          }
          return pairs;
        };
        ctx.save();
        for (let r = 0; r < colRails.length - 1; r++) {
          const a = colRails[r], b = colRails[r + 1];
          const segs = neuralPairs(a, b, r).map(([k, j, bend]) => {
            const x0 = a.x, y0 = a.members[k].mandaColY;
            const x1 = b.x, y1 = b.members[j].mandaColY;
            return [x0, y0, (x0 + x1) / 2, (y0 + y1) / 2 + bend, x1, y1];
          });
          ctx.globalCompositeOperation = 'lighter';
          ctx.strokeStyle = 'rgba(255,176,92,.16)';
          ctx.lineWidth = (lineBase * 3.2) / scale;
          for (const [x0, y0, mx, my, x1, y1] of segs) {
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.quadraticCurveTo(mx, my, x1, y1); ctx.stroke();
          }
          ctx.globalCompositeOperation = 'source-over';
          ctx.strokeStyle = 'rgba(255,196,126,.5)';
          ctx.lineWidth = lineBase / scale;
          for (const [x0, y0, mx, my, x1, y1] of segs) {
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.quadraticCurveTo(mx, my, x1, y1); ctx.stroke();
          }
        }
        ctx.restore();
      }"""
assert src.count(oldB) == 1, f"B count {src.count(oldB)}"
src = src.replace(oldB, newB)

open(path, "w").write(src)
print("v6 applied OK")
