#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

# --- A: write node.x/y directly so positions and bbox are correct immediately ---
oldA = "          node.fx = node.mandaColX; node.fy = node.mandaColY; node.vx = 0; node.vy = 0;"
newA = "          node.fx = node.mandaColX; node.fy = node.mandaColY; node.vx = 0; node.vy = 0;\n          node.x = node.mandaColX; node.y = node.mandaColY;"
assert src.count(oldA) == 1, f"A count {src.count(oldA)}"
src = src.replace(oldA, newA)

# --- B: setSettings -> fit for manda layout keys (reheat moves nothing when pinned) ---
oldB = """    api.setSettings = patch => {
      if (LAYOUT_KEYS.some(k => patch && patch[k] !== undefined)) fullLayoutDirty = true;
      Object.assign(state.settings, patch);
      render(false, LAYOUT_KEYS.some(k => patch && patch[k] !== undefined));
    };"""
newB = """    api.setSettings = patch => {
      const layoutKey = LAYOUT_KEYS.some(k => patch && patch[k] !== undefined);
      if (layoutKey) fullLayoutDirty = true;
      Object.assign(state.settings, patch);
      /* Manda is a fully pinned layout: reheating the simulation moves nothing (every node is
         held by fx/fy), so force-graph sees no motion and parks the redraw. Fit instead, so a
         tune-knob change (repel/link/spacing) visibly re-shapes the ladder live. */
      render(layoutKey && state.settings.mode === 'manda', layoutKey && state.settings.mode !== 'manda');
    };"""
assert src.count(oldB) == 1, f"B count {src.count(oldB)}"
src = src.replace(oldB, newB)

open(path, "w").write(src)
print("setSettings + direct positions applied")