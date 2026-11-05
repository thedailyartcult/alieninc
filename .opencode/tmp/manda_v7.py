#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

old = """        /* Neural-network wiring: instead of straight row-to-row rungs, each node fires to one
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
        ctx.restore();"""

new = """        /* Feed-forward neural wiring: every node in a section wires to at least five nodes in
           the NEXT section only (section 1 -> section 2 -> section 3 -> section 4), never back
           into its own column. Targets spread evenly and deterministically — no stray random
           lines — and each fibre runs straight into the receiving node's centre so every wire
           visibly belongs to two real nodes. */
        const WIRES = 5;
        const linkw = Number(state.settings.linkw);
        const lineBase = Number.isFinite(linkw) && linkw > 0 ? linkw : 0.6;
        const fanPairs = (a, b, r) => {
          const na = a.members.length, nb = b.members.length;
          const pairs = [];
          for (let k = 0; k < na; k++) {
            for (let m = 0; m < WIRES; m++) {
              const j = (k * WIRES + m + r * 3) % nb;
              pairs.push([k, j]);
            }
          }
          return pairs;
        };
        ctx.save();
        for (let r = 0; r < colRails.length - 1; r++) {
          const a = colRails[r], b = colRails[r + 1];
          const segs = fanPairs(a, b, r).map(([k, j]) => {
            const x0 = a.x, y0 = a.members[k].mandaColY;
            const x1 = b.x, y1 = b.members[j].mandaColY;
            return [x0, y0, x1, y1];
          });
          ctx.globalCompositeOperation = 'lighter';
          ctx.strokeStyle = 'rgba(255,176,92,.14)';
          ctx.lineWidth = (lineBase * 3) / scale;
          for (const [x0, y0, x1, y1] of segs) {
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          }
          ctx.globalCompositeOperation = 'source-over';
          ctx.strokeStyle = 'rgba(255,196,126,.42)';
          ctx.lineWidth = lineBase / scale;
          for (const [x0, y0, x1, y1] of segs) {
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          }
        }
        ctx.restore();"""

assert src.count(old) == 1, f"count {src.count(old)}"
src = src.replace(old, new)
open(path, "w").write(src)
print("v7 fan-out wiring applied")