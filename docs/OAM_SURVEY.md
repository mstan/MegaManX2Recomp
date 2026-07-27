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
| P1-P4 background margins | **done** -- exact fill from the level structures (see below) |
| P7-P8 cull + OAM emitter | not done |
| P9-P12 spawn | not done |
| P13 stage-trigger bias | superseded for margins -- exact fill needs no early staging |
| P16 4:3 regression gate | native region measured bit-identical margins on/off |

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

## Staging sources LOCATED (measured 2026-07-26)

Found with the **always-on** VRAM byte-write ring (`vwring_get <lo> <hi> [n]`,
`debug_server.c` — records every VRAM byte write, PIO and DMA alike, never
armed). Method, which is reusable and does not rely on catching a moment:

1. `loadstate` a gameplay state, walk the camera briefly (staging only fires
   while scrolling — an earlier attempt sampled a static stage-select screen and
   saw only CHR paging), then `clear_controller`.
2. Query the ring backward for byte writes into BG1 `$A000-$AFFF` (word `$5000`)
   and BG2 `$B000-$BFFF` (word `$5800`). The ring records the VALUE written.
3. Reconstruct a burst's payload in address order and search a WRAM snapshot
   from the SAME frame for that exact byte sequence. Whatever contains it is the
   source. (Match against a contemporaneous snapshot — a first pass used one
   ~3000 frames later and the BG2 buffer had already been reused.)

Two write shapes, measured directly:

* **2048-byte bursts** = 1024 words = one full 32x32 screen — the whole-half
  section staging.
* **128 bytes/frame while scrolling** = per-column streaming.

Sources found — note this is **multi-source**, not one buffer:

    BG1  whole-half 2068B -> $A7EC   from WRAM $7E:83FF  (~$7E:8400)
    BG1  column      56B  -> $A008   from WRAM $7E:F004
    BG2  column     128B  -> $BC00   from WRAM $7F:B000
    BG1  column     128B  -> $A000   NOT in WRAM -- ROM-sourced

`$7E:F0xx` is independently corroborated by DMA sampling during the same walk
(`$7E:F088`, `$7E:F110`, `$7E:F140` -> `$2118`). ROM sources seen in the same
window cluster in bank `$2D` at regular ~0x200-0x400 spacing, which is the CHR
stream, not tilemap.

A leading-edge prefill must therefore read more than one buffer, and some BG1
content never lands in WRAM at all.

**Note on tooling:** the writer-attribution field (`fn`) is `(none)` for all of
these — they are DMA, so there is no recomp-function context. Do not expect
`fn` to name a staging routine here. (The separate `s_vram_trace` ring IS
arm-based and answers `"recomp vram trace inactive"`; `vwring_get` is the
always-on one and is what to use.)

## No readable retained map found — this weakens the prefill plan

Tried to find a buffer a prefill could read *ahead of* the camera. Method: take
a streamed column upload's payload in **ring order** (which is DMA source order
— note a 64x32 column is STRIDED in VRAM, rows 64 bytes apart, so
longest-contiguous-run does not reconstruct a column and will mislead you), then
search for that byte sequence.

Result for BG1's steady-state 128-byte column uploads, across repeated walks:

    not present in WRAM (snapshot at the upload frame)
    not present in ROM  (whole 1.5MB headerless image, verbatim search)

Neither source holds the bytes. Together with the earlier partial hit (a 56-byte
BG1 run at `$7E:F004`) the likely explanation is that **X2 composes tilemap
columns from metatiles** — the level is stored as compressed/indexed metatile
references and the expanded tile entries exist only transiently while being
written. If so there is no MMX1-style retained map to point a prefill at.

**Consequence, and it changes the recommendation.** Prefill-first was chosen
because it is renderer-side and carries no simulation risk. That reasoning holds
only if the source data can simply be *read*. It appears it cannot: a prefill
would have to replicate X2's metatile expansion, which is a much larger job than
"read `$EC00` like MMX1 does" and is no longer obviously cheaper or safer than
P13. **Re-decide between prefill and P13 before building either.**

Not disproven, still worth one check: the whole-half 2048-byte staging burst DID
match WRAM `$7E:83FF`. That path may still be readable even if the per-column
streaming is not — but a whole-half buffer only helps at section boundaries, not
during the continuous scrolling that produces the reported symptom.

## CORRECTION + real mechanism: it is a REQUEST QUEUE, not a camera trigger

The section below claimed `$00:CF80 -> $00:CB05` is the upload choke point and
that CF80 is CB05's only caller. **That was wrong**, and the error was a bad
attribution script: an awk pass that only recognised `RecompReturn <fn>(`
definitions skipped over CB05's `void bank_00_CB05(...)` mode-alias wrapper and
credited a line inside it (`bank00_part09_v2.c:3024`, `case 3: _r =
bank_00_CB05_M1X1(cpu);`) to the preceding function. That line is CB05
dispatching to *itself* by M/X mode, not CF80 calling CB05.

Verified corrections:

* **CF80 has ZERO direct callers in generated C.** It is reached only through
  `g_dispatch_table` (`dispatch_v2.c:5307`). Its two real callers are ROM
  `$00:A7D9` (main loop) and `$00:CF49`, both of which run on the interpreter
  tier. Confirmed against the ROM: exactly two `20 80 CF` byte sequences exist
  in the whole image, at file +0x0027D9 and +0x004F49.
* **CF80 does not call CB05.** It dispatches indirectly to `$00:F833`. CB05
  JSLs `$08:E484` and likewise has no direct C caller.

**There is no camera-line compare to bias.** CF80 runs every frame and is a
no-op unless a request is queued. The gate is a counter at WRAM **`$0AE8`**:
`bank00_part09_v2.c:2719` sets `D = $0AE8`, `:2742` reads it, `:2747` branches
to `L_CF93` (skip everything) when it is zero. Verified by direct read.

Producers of `$0AE8`:

    INC $0AE8 at ROM $01:CE17   bank01_part09_v2.c:8960
        guarded by stage ID $1FAD != #$0B (cmp :8879, bne :8885)
        reached via object-AI $00:FDE0 -> $01:CD45 -> $01:CD98 -> $01:CDB5,
        which tests object flag byte D+$0F bits 7 and 6
    bitmask reload at ROM $08:C335/$08:C34C   bank08_part02_v2.c:2019-2055
        consumes the $1FD0 bitmask that the chain above sets
    cleared to 0 at ROM $08:A695              bank08_part04_v2.c:7301 (level init)

So X2 stages scenery from a **request queue driven by object/trigger logic**,
not from a camera crossing a line. "Fire the trigger early" (P13 as MMX1 does
it) does not map onto this design as a one-value change. Making uploads happen
sooner means making the queue get *populated* sooner, which lives in the object
AI that sets the trigger object's flag bits — not yet traced.

**Tooling trap found while doing this:** the harness `Grep` tool returns ZERO
matches inside `src/gen/` because that directory is gitignored (`/src/gen/*`)
and ripgrep honours ignore files. Generated code must be searched with plain
`grep`, or you will conclude a symbol does not exist when it does.

## The scenery-upload routine, found statically (2026-07-26) — SEE CORRECTION ABOVE

Owner steer: any approach is acceptable provided it does not cause frame lag or
crash risk, and a game-specific override is fine for now. That favours the
"make the game stage earlier" route (P13) over reconstructing the level data.

Found by reading the generated C — no runtime tracing needed, and only possible
because the AOT profile harvest put these banks in `src/gen`:

    bank_00_CB05   ROM $00:CB05   THE VRAM upload routine.
                                  Writes $4300 (DMA control), $4302 (source),
                                  $4305 (size), $2116 (VRAM dest).
                                  First delegates to $08:E484.
    bank_00_CF80   ROM $00:CF80   its ONLY caller (verified: exactly one
                                  call site in all of src/gen).

So every tilemap upload funnels through `$00:CF80 -> $00:CB05`. That is the
choke point to bias.

Still to find: the compare that decides *when* CF80 runs — i.e. the camera-line
trigger. It is upstream of CF80; CF80 itself is a call sequence, not the
decision. Once found, bias it earlier by the margin width, gated on widescreen,
and keep the lead <= margin or CHR paging garbles (P13).

## Not yet measured

* The camera-line compare upstream of `$00:CF80`, and which WRAM address holds
  the camera position it tests.
* Whether `$7E:8400` leads the camera or is filled just-in-time (the
  retained-vs-scratch test never caught a whole-half burst in the walk window).
* X2's metatile format and expansion routine — only needed if the prefill route
  is revived.

## Measured since (answers to earlier open questions)

* *Whether BG1/BG2 need different treatment* — **yes.** BG2 is never periodic and
  is a half-rate parallax layer; BG1 is camera-rate with occasional periodic
  floor bands. They need different margin sources.
* *Whether BG3 becomes active in other scenes* — **yes.** Slot 4 renders with
  `screenEnabled main = 0x17` (BG1+BG2+BG3+OBJ), not the `0x13` seen elsewhere.

---

# Level format DECODED + BG margins IMPLEMENTED (2026-07-26)

The "no readable retained map" conclusion above was answered by decoding the
game's own column composer instead of searching for its output. Found by
running the always-on write-log on the `$7E:F0xx` staging queue
(`SNESRECOMP_WLOG_ADDR=F000:F1FF` + `SNESRECOMP_WLOG_STATE=1`) during the
owner's walk-left repro: every staged byte is written by AOT function
`bank_00_B449` (the constant `IPC=00CF26` on 28k+ writes is the interpreter's
last PC — the `JSR $DDDC` pump site — proving the stores are AOT-side, where
the `fn` tag is live).

## The composer, decoded ($00:B449 + $00:B78E)

One call composes one 16px metatile column (two VRAM tile columns) into two
0x44-byte queue entries at `$7E:F000+X` (4-byte header: flags `$81`, VRAM
word address masked `& $FC1F`, count `$40`; queue cursor at `$00A6`, +=
`$88`/call). The data walk, verified 100.000% against live frame VRAM on
both layers before anything was built on it:

    screen id = layout[((wy>>8)&$1F)*32 + ((wx>>8)&$1F)]   1 byte / 256px screen
    block id  = screenDefs[sid*512 + ((wy>>4)&$F)*$20 + ((wx>>4)&$F)*2]
    map entry = metatileTable[block*8 + ((wy>>3)&1)*4 + ((wx>>3)&1)*2]
                ROM, 4 words TL,TR,BL,BR; 16-bit pointer wrap, bank fixed

World -> VRAM is straight parity ($00:B78E): map half = world-X bit 8, row =
world-Y tile mod 32. No rolling anchor.

## Per-layer sources

Two 0x40-byte stream contexts drive the pump: BG1 at D=`$1E58` (via
`$00:DDDC`), BG2 at D=`$1E98` (via `$00:DEDC`; `$00:D228` derives its camera
from BG1's — the half-rate parallax link). Before each compose the caller
loads a shared cluster `$1FDE-$1FEF` from per-layer initializers
`$00:B7CC` / `$00:B803`:

           layout     screenDefs   metatile ptr     world anchor
    BG1    $7E:E800   $7E:2800     24-bit [$09C5]   $1E5D / $1E60
    BG2    $7E:EC00   $7E:A600     24-bit [$09C8]   $1E9D / $1EA0

`$00:B83A` fills `$09C5`/`$09C8` per stage from ROM tables at `$00:89D5` /
`$00:8AB3` (+stage*3). The layout windows hold 32x32 screen ids.

## The margin fill (src/x2_rtl.c X2ConfigureWsBgMargins)

Per frame, for each layer: snap the stream anchor onto the PPU scroll phase
(scroll registers are the pixel-phase authority), then `WsShadowForceTile`
every gutter cell with the walk's exact entry — both sides, 31 rows, ~7
columns per side. History cannot cover the leading gutter and edge-repeat
was owner-rejected; the exact walk covers everything, every frame, and a
stale capture can never outlive one frame.

Gate, fail-safe by construction: raw `$2105 & $37 == 1` (mode 1, 8x8 BG1/BG2
tiles — the raw byte is `$09`, bit 3 is BG3 priority) + `BG1SC == $51` +
`BG2SC == $59`, then **self-validation**: the walk must reproduce 11/12
sampled tiles of the live native view or the layer stands down to authentic
map wrap for that frame. Menus, cutscenes and mid-staging frames all fail
the sample. Kill-switch: `SNESRECOMP_WS_BG_MARGINS=0`; gate diagnostics:
`SNESRECOMP_WS_BG_MARGINS_DEBUG=1` (stderr).

## Measured (2026-07-26, walk repro on slot 5 + all owner states)

* Native 256px region: **bit-identical** margins on vs off (0 / 57,344
  sampled pixels).
* West gutter vs the native view that later reveals the same world columns:
  **0.00% mismatch**, BG1-only and BG2-only isolation
  (`SNESRECOMP_LAYER_MASK=1`/`2`).
* East gutter likewise **0.00%** (slot 0; comparisons in Wire Sponge's
  stage confound on its weather palette cycling — compare shape, or use
  another stage).
* `ws_shadow_stats` (new debug-server command, always-on counters): both
  layers active with **zero margin misses** across attract + all five save
  states; slots 0-2 prove the high world bits (worldX 5888/6144 ≫ the
  10-bit PPU scroll).
* 4:3 (`Widescreen = 0`): shadow inactive, zero counters, 256x224.

Caveats: (1) west of world 0 the fill leaves authentic wrap (no authored
content exists); (2) margins can show adjacent-layout rooms beyond camera
clamps — real level data, "wrong-but-plausible", revisit only if the owner
flags it; (3) `$2105` bit-4/5 scenes (16x16 tiles) deliberately stand down.

## Object-layer scenes: the diversity gate (owner-reported half-culling)

Some scenes repurpose a BG as a mostly-transparent OBJECT layer: the
X-Hunter tower lifts live in the **BG2 tilemap** and move by *scroll*, not
rewrites (zero tilemap writes in the vwring while a lift moves). There the
provider's "level data" is blank, matches a blank native sample trivially,
and the margin fill ERASED the lift outside the native 256 (the owner's
half-culled platforms, cut exactly at the native boundary). Fix, two parts:

* `x2_bg_stream_valid` now also requires **sample diversity** (modal native
  entry <= 9 of 12): a near-uniform native view proves nothing, so the
  layer stands down and authentic map wrap serves the object correctly —
  measured: the lift renders fully across the west gutter, BG1 stays
  exact-filled with 0 misses.
* Engine `WsShadowSetRespectGameWrites(layer, 60)` (ws_shadow.c): ForceTile
  yields to world cells the game itself wrote within 60 frames, so objects
  genuinely DRAWN into a diverse tilemap can't be erased by the refill
  either. Stamps ride the previously-dead per-cell `cooldown` buffer,
  fed from WsShadowOnVramWrite.

Also fixed here: the fill's row range now covers the full wrapped-Y fold
(anchor-256 .. anchor+491) — the tower's HDMA parallax bands consulted BG2
rows far from the frame vScroll and racked up millions of margin misses
against the old 30-row fill (found via `ws_shadow_stats`).

## Rocket platforms (rain stage): spawn pop-in — OPEN, lead recorded

The flying platform type at `$07:DC5A` (trampoline `$00:FD36`): its CULL
routes through `$07:DEA0`, which the window sweep already widened (matches
the owner's "they cull in 16:9"). Its SPAWN position source is NOT the
swept idiom — slot inits come via `bank_07_DCD6`/`DD4B` (and a
`bank_03_EBD7` path), and the `#$100` in DCD6 is a dp$1C timer compare,
not a camera offset. Next step needs a survivable repro (the probe X dies
in the spike pit): either a save state standing before the pit with full
health, or owner riding one while `SNESRECOMP_WLOG_ADDR=1818:1D17` runs —
then trace the +$05 world-X store back to its source.

Note: the "slot 4 = stage-select menu" line in the periodicity table above
is stale — the owner's save slots have changed; slot 4 is now Wire Sponge
gameplay (capsule tower). The margin gate self-validates per frame, so save
contents cannot mislead it.

---

# Object system + spawn/visibility windows (2026-07-26) — P7-P12 phase 1

## The object arrays (measured: snapshot diff + WLOG 1700:1AFF + $00:D008)

Per-frame AI pump at `$00:CF00` runs direct-page object arrays; each loop
TCDs through slots and dispatches `JSR ($F653,X)` (or table siblings):

    $0B48-$0CC7  stride $20  via $00:D107/D124   (shots/effects)
    $10D8-$1317  stride $40  via $00:D0A0        (large actors)
    $1818-$1D17  stride $20  via $00:D008/D02D   (enemies)
    $1D18-$1E17  stride $10  via $00:D05E/D07F   (small effects)

Enemy struct: +$00 flag, +$05 world X (16-bit), +$08 world Y, +$0E per-frame
draw flag ($81 = emit metasprite, cleared each frame by the pump), +$11
state bits. Spawn-init burst example: the bee generator type ($07:A653, an
AI-driven emitter) allocates via `JSL $00:DA97` and fills a slot in one
frame (caught with `SNESRECOMP_WLOG_ADDR=1700:1AFF`).

**X2 has no MMX1-style camera-anchored record walk.** Sections pre-populate
object structs; everything else is gated by shared window checks.

## The three shared window checks — WIDENED (tools/apply_overrides.py)

All keyed to the same `$1E5D`/`$1E60` camera anchor the BG margins use:

    $00:D813  activation  (objX - cam + $40) < $180   cam-64..+320
    $00:D834  visibility  (objX - cam + $60) < $1C0   sets dp$0E=$81 / 0
    $00:D859  draw        (objX - cam + $20) < $140   common AI tail

`tools/apply_overrides.py` (new; MMX1's marker-injection discipline, wired
into tools/regen.sh incl. the strict-idempotent path) reroutes each body's
X-axis add/limit constants through `X2WsObjWinAdd/Limit` (x2_rtl.c): widened
by `margin + 32` per side. The +32 slack is required — margin alone moves
the pop-in to the outermost VISIBLE wide column (owner-observed; the same
"+32 rule" MMX1 documented). Y windows untouched. Vanilla-identical when
widescreen is off; kill-switch `SNESRECOMP_WS_SPAWN=0`.

Verified visually: enemies + spawned bees fully rendered and animating in
the east gutter (slot 5, Wire Sponge). The Cx4 OAM conversion (below) and
the PPU 9-bit X band handle margin sprites without a separate P8 patch on
the right side.

## The OAM pipeline is Cx4-authored in gameplay

The intro-scene writer census above does NOT hold in gameplay: the CPU only
(a) resets/parks HUD slots ($00:D4BB, $00:D5xx HUD bar builders) and
(b) appends per-object records — world X/Y, flags, metasprite def pointer
from the `$0D:8000` table — to a display list at `$6220+` ($00:D42A,
counter $6620). The Cx4 transforms that list into OAM entries; its writes
go through cx4_bus_write and are invisible to the CPU write log. Any future
P8 work is either Cx4-side or a host post-pass over the display list.

## `$09DD` is NOT a spawn frontier — earlier hypothesis DISPROVEN

An earlier draft of this section claimed `$09DD` was a "stream frontier"
gating enemy wake-ups at the native edge. A full ROM census killed it:
**296 accesses**, including `dp$05 - $09DD` signed-distance computations
($00:8529) and `LDA #$20 / STA $09DD` initialization ($00:90DF), and the
measured steady state is camera+128 = mid-screen. `$09DD`/`$09E0` are the
**player/attention world X/Y** (camera-clamped in $00:E08F). The
`LDA $09DD / CMP $05` shapes in enemy AI are facing/behavior triggers, not
spawn gates. Do not bias them — that changes AI behavior, not visibility.

Measured after the margin+32 window widening (OAM first-appearance probe,
slot 5 sweep): the enemy cluster's sprites are already present when their
world positions scroll into the wide view — **no pop-in observed at the
16:9 edge** in the surveyed area. Any future pop-in report should be
answered by finding that enemy's own window-check variant (below), not by
revisiting `$09DD`.

## Inlined window-check copies: swept generically

Four enemy/projectile handlers inline their own copy of the window idiom
instead of calling the shared helpers: `bank_02_EB99` ($40/$180),
`bank_03_C66E` ($20/$140), `bank_07_D695` ($40/$180), `bank_07_DEA0`
($40/$180). tools/apply_overrides.py finds ALL of them structurally: after
a `$1E5D` (camera X) read, the next add-constant {$20,$40,$60} AND next
limit-constant {$140,$180,$1C0} are widened — **only as a confirmed pair**
(a lone add after an anchor read is some other camera computation; the
first generic pass wrongly hit four of those — bank_00_DC50, bank_01_CC61,
bank_08_AC32, bank_29_9FFF — and the pair requirement exists because of
them). `$1E60` (camera Y) reads disarm the tracker, keeping Y windows
authentic — necessary because D834's Y pair reuses the $180 constant.
22 sites total at current AOT coverage; the injector fails loudly if a
regen changes the emitted shapes.

## Weather overlays: measured + FIXED (owner rain save, slot 8)

The rain is NOT sprites and NOT HDMA: it is **BG3 alone on the subscreen**
(TS=$04, TM=$1B lacks BG3), a static 32x32 streak texture at BG3SC=$0C
animated purely by fast diagonal BG3 scroll, blended over the scene via
color math. Some rain is also baked into the BG1/BG2 level tiles (CHR
animated), which the margin fill already carried into the gutters — the
missing part was the subscreen overlay, clamped by the engine's default
BG3 policy (`PpuSetWidescreenBg3Widen(g_ppu, 0)`).

Fix: widen BG3 exactly on the overlay signature (subscreen==BG3-only AND
main screen without BG3) in `X2Display_PreparePpuFrame`. The 32-wide map
wraps in the margins, which tiles the repeating rain texture seamlessly.
Menus (BG3 on main) keep the authentic clamp. A/B: east-gutter bright
rain pixels 478 (on) vs 198 (off), native region identical. Kill-switch
`SNESRECOMP_WS_BG3=0`. The heat shimmer is expected to be the same
mechanism (unverified in play).

### BG3 surveyed (2026-07-26)

Slot 4 is the **stage-select menu** (boss portrait grid, "Weather Control Stage
/ Boss: Wire Sponge") — a static screen: every layer sits at `hScroll=vScroll=0`.

    BG3: base $0800, 32x64, uniform=8 periodic=0 aperiodic=20

Two things fall out, and the second is the one that bites:

1. BG3 is a **menu** layer here, and a gameplay gate excludes menus anyway. Add
   an explicit `main & 0x04` stand-down regardless rather than relying on that
   correlation holding in every scene.
2. **Map geometry is scene-dependent, not fixed.** In slot 4 BG1 is `32x64`,
   while in gameplay (slots 0/5) the same layer is `64x32`. Margin code MUST
   read the live `BGnSC` size bits per frame — anything that hardcodes 64x32
   will index the wrong screen half on menu screens. BG3 at 32x64 is only 32
   columns wide, so it has no second horizontal screen at all: its margins wrap
   onto the visible columns rather than exposing a stale half.
