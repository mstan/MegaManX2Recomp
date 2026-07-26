# Mega Man X2 — OAM survey (measured, read-only)

Not generated. `docs/WIDESCREEN.md` is written by
`_tools/scaffold_mmx_sequel.py` and will be overwritten; this file is
hand-maintained measured data. Append to it as more is surveyed.

Measured 2026-07-26 from the always-on write-log ring
(`SNESRECOMP_WLOG_ADDR=6000:63FF` + `SNESRECOMP_WLOG_STATE=1`, armed at process
start, ~20k events) plus the register-write ring, during the **intro cutscene**.
Nothing here required modifying the game or the engine.

## Where X2 stages OAM — and it is not where X1 does

X1 stages OAM in WRAM (`$0200`). **X2 stages it in Cx4 data RAM.** Confirmed from
the DMA register ring, every frame from frame 2 onward:

```
channel 0:  $4301 = $04   (B-bus $2104 = OAMDATA)
            $4302/03/04 = $00:6000
            $4305/06    = $0220   (544 bytes)
```

So the layout inside the Cx4 window is:

```
$6000-$61FF   128 sprites x 4 bytes   (X lo8, Y, tile, attr)
$6200-$621F   32-byte high table      (X bit 8 + size, 2 bits per sprite)
$6220-$63FF   NOT DMAd -- other game use (see below)
```

Writes arrive as bank `$06` (`$06:6000`), which is inside the Cx4 window
(`$00-$3F:$6000-$7FFF`), so they route through `cpu_write8` -> `cart_write` ->
`cx4_write`. That is why they are visible to the write log at all.

**The 65816 builds this OAM, not the Cx4.** Every writer below is a 65816
interpreter PC. The Cx4's own writes to its data RAM go through `cx4_bus_write`
and would NOT appear in this log; the log is full, so the CPU is the author.
That means widescreen OAM work is ordinary 65816-side hooking, the same shape as
X1 — the unusual storage location does not change the technique.

## Writer census

Interpreter PCs, by which field of the 4-byte entry they touch:

| PC | field(s) | slots | reading |
|---|---|---|---|
| `$00:86DF` | Y | 0-63 contiguous | sprite-hide: writes `$E0` to Y, stride 4 |
| `$00:86E2` | Y | 64-127 contiguous | sprite-hide, upper bank |
| `$00:86ED` | high table | all 32 bytes | clears/sets X bit 8 + size for every slot |
| `$00:B93D` | X lo8 + high | 0-119 | metasprite emitter A |
| `$00:B945` | tile + attr + high | 0-119 | metasprite emitter A (2nd store) |
| `$00:B94D` | X lo8 | 8-127 | metasprite emitter B |
| `$00:B955` | tile + attr | 8-127 | metasprite emitter B (2nd store) |
| `$00:B319` | X, tile, attr, high | 1-115 | a third emitter path |
| `$00:B2DA` | all fields + high | 0-127 | bulk mover / buffer copy |
| `$13:F944` | all fields + high | 0-127 | bulk clear (writes all 1024 bytes) |
| `$00:D5B8` | Y | 0-7 contiguous | per-slot Y, low 8 slots |
| `$00:D6D6` | Y | 8-15 contiguous | per-slot Y, slots 8-15 |
| `$00:D443`-`$00:D496` | — | — | write `$6220-$6269`, i.e. OUTSIDE the OAM DMA |

## What this means for widescreen

Cross-referenced against `snesrecomp/docs/WIDESCREEN_PATTERNS.md`.

**Genuinely easier than it might have been:**

* **P8 (the OAM emitter's unsigned X reject) has a small, enumerated surface.**
  X bit 8 lives in the high table, and only six PCs write it: `$0086ED`,
  `$00B93D`, `$00B945`, `$00B2DA`, `$00B319`, `$13F944`. The X low byte is
  written by four. That is a short list to widen, and it was found without any
  reverse engineering of code — purely from the write ring.
* **One flat buffer, DMA'd whole, every frame.** No partial/incremental OAM
  upload to reason about, and one obvious chokepoint.
* `$0086DF`/`$0086E2` are unmistakably X2's analogue of X1's `ResetSpritesFunc`
  (`$E0` to Y at stride 4 across both 64-slot halves), which pins the sprite-hide
  convention immediately.

**Not easier, and unmeasured:**

* **This is INTRO-scene data.** `$00D5B8`/`$00D6D6` writing exactly slots 0-7 and
  8-15, ~7.5k times each, look like a HUD fingerprint — but the intro has no HUD,
  so they are far more likely the two hoverbike riders. **Do not treat them as the
  HUD (P5) without re-measuring in gameplay.**
* **Nothing here touches cull, spawn, or the camera** — P7, P9-P13, which is where
  X1's effort actually went. The three emitter paths (`$B93D`, `$B94D`, `$B319`)
  also need distinguishing: which is the general enemy metasprite emitter versus
  a HUD or effect path.
* **The OAM buffer shares Cx4 data RAM with other game state.** `$00D44x` writes
  `$6220-$6269` and the bulk clear covers `$6000-$63FF`. Widening OAM X must not
  disturb whatever else lives in that 3 KB, and the Cx4 program itself has access
  to all of it.

## The blocking prerequisite: AOT coverage

X1's widescreen hooks are injected into **generated C** by
`apply_overrides.py`, which pattern-matches emitted function bodies. A routine
that only ever runs on the interpreter has no generated body to patch.

X2 currently has **5 AOT variants** from a one-directive `bank00.cfg` seed, so
none of the PCs above are AOT-covered. Widescreen is therefore gated on growing
static coverage over bank `$00` (`$86DF`, `$86ED`, `$B2DA`, `$B319`, `$B93D`-`$B955`)
and bank `$13` (`$F944`) first — the same static-coverage burndown that is already
the next job for its own sake.

Alternative, if that proves slow: hook at the interpreter tier keyed on PC. That
is **not** the established mechanism in this project and would be a new pattern,
so it should be a deliberate decision rather than a shortcut.

## Reproducing this survey

```powershell
$env:SNESRECOMP_WLOG_ADDR='6000:63FF:<out>.txt'   # OAM buffer + high table
$env:SNESRECOMP_WLOG_STATE='1'                    # attach the interpreter PC
$env:SNESRECOMP_WLOG_ADDR_CAP='400000'
# then launch normally; the ring is armed from process start, not attached later
```

For gameplay coverage of the same range, a human has to drive the game to a
stage — gameplay verdicts are the owner's, not the agent's.

---

# HUD slot map (measured in gameplay, 2026-07-26)

From owner-supplied save states via `tools/hud_map.py`, cross-checked against
screenshots. This **supersedes the intro-scene speculation above**: the earlier
guess that `$00D5B8`/`$00D6D6` (slots 0-7 / 8-15) were the HUD was wrong in
substance -- those were cutscene actors. Slots 0-5 are the HP bar, and the
weapon bar is a *separate* column starting at slot 7.

    save slot 0 : health + weapon bars, X idle, safe
    save slot 1 : boss fight opening -- health + weapon + boss bar

## The map

| element | OAM slots | screen X | attr | anchor |
|---|---|---|---|---|
| **X health bar** | 0-5 (6 park at low fill) | **8** | `0x34` | **LEFT** |
| **weapon / ammo bar** | 7-13 (14-15 park) | **24** | `0x36` | **LEFT** |
| **boss health bar** | 16-22 (23 parks) | **232** | `0x34` | **RIGHT** |
| player (X) | 16-33 varies | follows camera | `0x62` | — |
| boss / effects | 32-71 varies | — | `0x29`, others | — |

Each bar is a vertical stack of 16x16 sprites (size bit 1) sharing one X, with
its icon as the bottom element. HP and weapon sit side by side 16px apart.

## The fact that matters for 16:9

**HP and weapon anchor LEFT; the boss bar anchors RIGHT.** They must be pushed in
**opposite directions**, not shifted as one block. And the layout is symmetric
about the screen: HP's left edge is 8px from the left; the boss bar is at X=232
and is 16px wide, so its right edge is 248 -- also 8px from the right. So for a
margin `m`:

    HP     X:   8  ->   8 - m
    weapon X:  24  ->  24 - m
    boss   X: 232  -> 232 + m

The engine hook is `PpuSetWsHudOamShift(g_ppu, n)`. Note MMX1 passes a single
shift for slots 0-15 -- that is not sufficient here, because slot 16-23 must move
the *other* way. Expect to need a signed/per-range shift, or two calls. Check
whether the existing API can express that before assuming it can.

## Caveats -- read before using these numbers

1. **The boss bar was EMPTY when sampled.** The screenshot confirms it: the boss
   bar fills progressively during the boss intro, so only slots 16, 21, 22 were
   drawn at that instant. Slot 23 is parked directly after 22 and is almost
   certainly part of the bar at full fill. **Re-measure with a full boss bar
   before hardcoding the range.** Same applies to slot 6 (HP) and 14-15 (weapon).
2. **The player can masquerade as HUD.** In a side-scroller the player is
   screen-static while the world scrolls -- identical signature to a HUD element.
   Two earlier attempts misreported X as HUD. The discriminator that works is
   sampling *while a direction is held*, and even that fails during a boss intro
   because input is locked (which is why slots 24-31 show as static in the boss
   state -- that is X, not HUD). `attr` is the reliable secondary signal: HUD is
   `0x34`/`0x36`, the player is `0x62`.
3. **Two stages measured, not all.** Slot assignment looks global but has not
   been checked in every scene (no sub-tank state, no ride armour, no
   two-boss/co-op HUD variants).

## Tooling

* `tools/hud_map.py` -- loads both states and produces the table above.
* `tools/hud_survey.py` -- single-state survey with the held-input discriminator.
* `tools/navigate.py` -- TCP driving + screenshots with measured pixel stats.

Use `loadstate <slot>` (no underscore) to load a game save state: it routes
through `RtlSaveLoad` on the main thread and runs the `X2StateLoadExtra` /
`X2OnStateLoaded` hooks that restore the LLE resume cursor. `load_state <file>`
is a different, raw L3-snapshot command keyed by literal filename -- it does NOT
touch `saves/`, and passing it a slot number silently creates a file named after
the number.
