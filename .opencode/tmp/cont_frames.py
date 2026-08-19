#!/usr/bin/env python3
path = "/home/alieninc/panteon/cmb/cmb.html"
src = open(path).read()

old = """    function needsContinuousFrames() {
      return !reduced() && state.styleName === 'galaxy' && !large;
    }"""
new = """    function needsContinuousFrames() {
      /* Galaxy needs its starfield on every frame. Manda is fully pinned (fx/fy), so the
         simulation never moves and force-graph would otherwise park the redraw — but the
         Manda shape is driven live by the tune knobs (repel/link/spacing), so keep painting
         so those changes show up the instant a knob moves. */
      return !reduced() && (state.styleName === 'galaxy' ? !large : state.settings.mode === 'manda');
    }"""
assert src.count(old) == 1, f"count {src.count(old)}"
src = src.replace(old, new)
open(path, "w").write(src)
print("needsContinuousFrames patched")
