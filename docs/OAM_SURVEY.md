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
