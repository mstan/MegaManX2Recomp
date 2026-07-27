# Mega Man X2 — OAM survey (measured, read-only)

Hand-maintained measured data. Append to it as more is surveyed.

(Historical note: this repo was originally stood up by a scaffold generator
that owned several files, including `docs/WIDESCREEN.md`. That generator was
retired on 2026-07-26 — every file in this repo is now owned here and edited
directly. Nothing regenerates over your changes.)

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
| **boss health bar** | **16-22** (7 sprites, Y 0-80) | **232** | `0x34` | **RIGHT** |
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

1. ~~The boss bar was EMPTY when sampled.~~ **RESOLVED** from a third save state
   with the bar already filled: the boss bar is exactly slots **16-22** (7
   sprites, Y 0-80). Slots 6, 14-15 and 23 are genuinely never used, and actors
   start at slot 24. So the reserved HUD region is 0-23 (X1 reserves 0-15).
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


---

# 16:9 HUD anchoring — IMPLEMENTED (2026-07-26)

Owner-validated visually: all three bars anchor to the widened edges correctly in
a boss fight at 342x224.

`X2ConfigureWsHud()` in `src/x2_rtl.c`, called once per frame from
`X2Display_PreparePpuFrame()` in `src/main.c`.

## No engine change was needed

`PpuAdjustWidescreenHudOamX` already splits on screen X and pushes each side
outward independently -- sprites left of `wsHudLeftEnd` by `extraLeftCur`, sprites
at/after `wsHudRightStart` by `extraRightCur`. An earlier note here claimed MMX1's
single-shift API could not express opposite directions; that was wrong. It only
needed correct configuration:

    PpuSetWidescreenHudSplit(g_ppu, 96 /*band*/, 64 /*leftEnd*/, 192 /*rightStart*/)
    PpuSetWsHudOamShiftRange(g_ppu, 0, 24)

HP (X=8) and weapon (X=24) fall below `leftEnd`; the boss bar (X=232) is at/above
`rightStart`. The layout is symmetric -- HP's left edge and the boss bar's right
edge are both 8px from their native screen edge -- so both move by the same
margin and stay symmetric at any width.

## The gate

**Cutscenes reuse slots 0-23 for actors** (the intro survey caught the hoverbike
riders there), so shifting the range unconditionally would drag cutscene sprites
into the margins. Rather than invent a WRAM game-state byte, the gate is the
HUD's **own measured signature**:

* slot 0 must be the bar's **icon** -- tile `0x86`, attr `0x34`, X=8, X bit 8
  clear, inside the Y band. Distinctive enough that an actor will not impersonate it.
* corroborated by **at least 4 of slots 0-4** (the bar frame) matching.

Requires the HP bar only -- the weapon bar is absent until a weapon is equipped
and the boss bar only exists in a fight.

**Do NOT require an exact slot count.** The first version demanded all six of
slots 0-5 and was broken nearly everywhere: **slot 5 parks at Y=224** depending on
max health, so the gate evaluated 5/6 and silently disabled itself, leaving the
HUD at 4:3 through most of a stage. Measured across four save states, slots 0-4
are always drawn (Y 80/64/50/44/28) and slot 5 is the variable one. Gating on a
variable-length bar's length was the mistake; gate on the invariant part.

Self-validating and fails safe: no signature means no shift, i.e. authentic
placement. This is the P5 requirement, and it specifically avoids MMX1's bug of
gating partly on an HDMAEN mirror.

## Note on the AOT prerequisite

An earlier entry said widescreen was blocked on AOT coverage. That is true for
spawn and cull, which need `apply_overrides.py` to inject into generated C -- but
**NOT for the HUD**, which is host-side in the renderer and needed no coverage at
all. The blocker was stated too broadly.

## Widescreen checklist status (see snesrecomp/docs/WIDESCREEN_PATTERNS.md)

| | |
|---|---|
| P5 HUD gate | done -- signature-gated |
| HUD anchoring | done -- opposite edges, owner-validated |
| P1-P4 background margins | **NOT DONE** -- margins show adjacent-room tiles |
| P7-P8 cull + OAM emitter | not done |
| P9-P12 spawn | not done |
| P13 stage-trigger bias | not done |
| P16 4:3 regression gate | not established |

`Widescreen` remains **0** in the shipped default. It was enabled only in the
exe-adjacent `build-trace/config.ini` for this test.

---

# Background layer survey (measured 2026-07-26) — P1-P4

Measured from `get_ppu_state` in two owner save states (boss room, scrolling
stage). This is the input to the background-margin work; nothing implemented yet.

## Configuration

    bgmode 1,  screenEnabled main = 0x13  ->  BG1 + BG2 + OBJ   (BG3 NOT enabled)

    layer | tilemap base | size  | scroll behaviour
    BG1   | $5000        | 64x32 | 385 -> 426 over 30 frames (camera rate)
    BG2   | $5800        | 64x32 | 192 -> 213 over 30 frames (HALF rate = parallax)
    BG3   | $0800        | 32x64 | not enabled in either state
    BG4   | $0000        | 32x32 | not enabled

So only **two** layers need margin work, not four. BG2 scrolls at exactly half
BG1's rate, so it is a parallax layer.

## The mechanism, and why the margins are wrong

**Both BG1 and BG2 are 64x32** — a 512px-wide tilemap holding two adjacent
32-column screens. The visible 256px window sits inside that 512px map, so a
margin column past the native edge reads **the other half of the map**.

That half is not garbage: it is real level data. It is whichever section the game
last streamed in. The game rewrites a whole half at a time as camera-line staging
triggers fire, so:

* moving **into** a freshly staged half, the margin is correct;
* moving **toward** a half that still holds the *previous* section, the margin
  shows that older content.

Owner-reported symptom matches exactly: wrong on both left and right, "as you
walk toward it" — i.e. the LEADING margin is stale.

**This is the same scheme as Mega Man X 1's BG2** (rolling half-map, section
staged a half at a time). The mechanism transfers; the trigger addresses do not.

## Two candidate fixes, and only one is available now

1. **Host-side margin history (P2/P4)** — `WsShadow*`: capture columns as they
   scroll through the native view, key them to an unwrapped world coordinate, and
   serve margins from that instead of from the wrapped map. Periodic rows can fold
   (`WsShadowSetPeriodicFold`) rather than using history. **Needs no AOT
   coverage** — it is entirely renderer-side, like the HUD shift turned out to be.
   Currently stubbed: `X2Display_PrepareBg2Shadow()` calls `WsShadowReset()` +
   `WsShadowFrame()`, i.e. deliberately deactivated, which is why margins fall
   back to plain map wrap.

2. **Stage-trigger bias (P13)** — fire the camera-line staging trigger early by
   the margin so the leading half is loaded before it becomes visible. This is
   what MMX1 does, and it is the real fix for the leading edge. **Requires AOT
   coverage**, since it means injecting into generated C at the trigger compare.

Recommended order: (1) first, because it is available immediately and carries no
simulation risk; (2) once bank `$00`/`$13` coverage exists. Note P13's constraint:
the lead must not exceed the margin, or CHR paging garbles.

## Periodicity proof (measured 2026-07-26) — P3 does NOT transfer

P3 says margins may fold onto a proven per-row period instead of using history.
That is Mega Man X 1's *primary* BG2 margin source. **It is not available here.**

Measured across five owner save states by reading the always-on frame ring
(`dump_frame_vram`) and, per row, searching the 32 natively displayed columns
for the smallest exact period:

    scene    BG1 periodic   BG2 periodic   uniform (BG1/BG2)   other-half agree
    slot 0   2 rows (p=2)   0              0 / 0                15% / 2%
    slot 1   0              0              2 / 0                 5% / 0%
    slot 2   0              0              2 / 0                 5% / 0%
    slot 4   0              0             13 / 12                0% / 31%
    slot 5   6 rows (p=8)   0              0 / 10               45% / 43%

**BG2 has zero periodic rows in every scene surveyed.** BG1 is periodic only in
narrow bands (slot 5 rows 26-31 at p=8, slot 0 rows 20-21 at p=2) — repeating
floor, not a foldable layer. Do not port MMX1's `WsShadowSetPeriodicFold` as the
primary source and expect it to work.

What the same measurement *did* find usable:

* **Uniform rows are common** (slot 4: 13 BG1 / 12 BG2; slot 5: 10 BG2 rows, all
  `$1403`). A uniform row is period-1 and its margin can be filled exactly.
* **Other-half agreement is 0-45%**, confirming directly that the off-screen half
  holds genuinely different content. This is the stale-margin mechanism measured
  rather than inferred.

### Consequence for the fix

Host-side history (P2/P4) serves columns *already seen scrolling through the
native view*, so it fixes the **trailing** margin. It structurally cannot fix the
**leading** margin: those columns have never been displayed, so there is nothing
captured to serve, and it falls back to map wrap. Owner-confirmed symptom
(2026-07-26): *"if you walk long enough in one direction you still get stale
frames"* — sustained travel keeps re-exposing the leading edge, so this is not a
transient that settles.

Margin sources, by what they can actually cover:

    trailing margin        world-keyed history        available now
    uniform rows           fill with the row value    available now
    leading, world-anchored  real level data          NEEDS P13 or prefill

So Fix 1 is necessary but **not sufficient** for the reported symptom. The
leading edge needs either P13 stage-trigger bias (now unblocked — bank `$00` and
`$13` AOT coverage exists as of the 2026-07-26 profile harvest) or a prefill that
reads X2's retained level map, the way MMX1's `MmxDisplay_PrefillBg2Shadow` reads
`$EC00`/`$A600`. X2's equivalent addresses are still unsurveyed.

## Not yet measured

* Which WRAM addresses hold X2's camera and the staging trigger lines.
* Where X2's retained level map lives (the MMX1 `$EC00`/`$A600` equivalent),
  which is what a leading-edge prefill would have to read.

## Measured since (answers to earlier open questions)

* *Whether BG1/BG2 need different treatment* — **yes.** BG2 is never periodic and
  is a half-rate parallax layer; BG1 is camera-rate with occasional periodic
  floor bands. They need different margin sources.
* *Whether BG3 becomes active in other scenes* — **yes.** Slot 4 renders with
  `screenEnabled main = 0x17` (BG1+BG2+BG3+OBJ), not the `0x13` seen elsewhere.
  Margin work must handle BG3 or explicitly stand down when it is enabled.
