# 16:9 widescreen — Mega Man X2

## Status: HUD + BG margins DONE; spawn/cull (parts 3-4) still open.

Done, measured, and documented in `docs/OAM_SURVEY.md`:
* **HUD anchoring** (part 2) — signature-gated, owner-validated.
* **Background margins on both layers** (part 1) — exact per-frame fill from
  the game's own layout/screen/metatile structures, decoded from the column
  composer `$00:B449`. Both gutters show real level data (0.00% mismatch vs
  the native view in layer-isolated measurement), the leading edge included.
  Self-validating gate; kill-switch `SNESRECOMP_WS_BG_MARGINS=0`.

* **Object windows (parts 3-4, phase 1)** — the three shared bank-00
  activation/visibility/draw window checks are widened by margin+32 via
  `tools/apply_overrides.py` (marker-injected into src/gen, restorable,
  wired into regen.sh). Enemies act and render in the gutters
  (screenshot-verified). Kill-switch `SNESRECOMP_WS_SPAWN=0`.

* **Weather overlays (rain, and by signature the heat shimmer)** — the
  weather is BG3 alone on the SUBSCREEN blended via color math (measured
  from the owner's rain save: BG3SC=$0C 32x32 static streak texture,
  animated purely by scroll). `X2Display_PreparePpuFrame` widens BG3
  exactly for that signature (sub==$04, main lacks BG3); menus keep the
  clamp. A/B-measured: 478 vs 198 bright rain pixels in the east gutter,
  native identical. Kill-switch `SNESRECOMP_WS_BG3=0`.

* **Inlined window copies swept** — apply_overrides.py now finds every
  camera-window idiom structurally (pair-confirmed $1E5D + add + limit),
  covering the four per-enemy inlined variants in banks 02/03/07 alongside
  the shared helpers (22 sites). The earlier "$09DD frontier" hypothesis is
  DISPROVEN ($09DD = player/attention X — see OAM_SURVEY.md); the
  first-appearance probe shows no pop-in at the 16:9 edge in the surveyed
  area.

Still open before the toggle ships:
* heat-shimmer visual confirmation in play (same mechanism as rain, so the
  BG3 gate should cover it — unverified);
* owner playtest across stages: any residual enemy pop-in now means that
  enemy's own exotic window variant — find it by type, not by revisiting
  $09DD.

The shipped default is native 256x224. `Widescreen` and `NoSpriteLimits` are both
**0** in the embedded default inside `src/main.c` (that string, not the repo-root
`config.ini`, is what a fresh run writes and reads), and the launcher toggle is
hidden (`gi.widescreen_supported = 0`).

An earlier iteration shipped `Widescreen = 1` while every hook was inert — 16:9 on
with nothing adapted to it. Do not flip any of this back on until the four parts
below are done and the 4:3 regression gate passes.

## Read `snesrecomp/docs/WIDESCREEN_PATTERNS.md` FIRST

That is engine-level doctrine: sixteen invariants (P1-P16), each one a defect
Mega Man X 1 actually hit, the invariant that prevents it, and how to measure
you have it. They are PATTERNS, so they transfer even though no address does.
Skipping it means rediscovering X1's bugs in X1's order. It also gives the
recommended ORDER of work, which matters because a later step's symptoms mimic
an earlier step's bug.

## Mega Man X 1 is the reference — the SHAPES port, the ADDRESSES do not

`MegamanXRecomp` has a working, surveyed 16:9. Its hooks live in
`src/mmx_rtl.c` and are injected into the *generated* C by
`tools/apply_overrides.py`, which pattern-matches emitted code at specific
ROM-derived sites and rewrites a value or a flag in place:

```
/*WS-CULL*/  { cpu->_flag_C = MmxWsCullVerdictX((uint16)(_v12)); }
/*WS-OAM*/   { _v7 = MmxWsOamRightLimit(_v7); }
```

Every MMX1 site is an MMX1 fact: `bank_02_806E` (enemy cull), `bank_82_80B4`
(shot cull), `bank_00_DC36`/`DCDB` (spawn scan + record walk), `bank_00_D76A`
(metasprite X gate), `bank_82_B964` (enemy activation), `bank_03_FDD3` (camera
line triggers), and WRAM `$00D1`/`$00D2` (gameplay gate), `$1E4D` (scan anchor),
`$0BAD` (camera X). **None of those transfer.** Survey Mega Man X2's own routines
first; reuse the formulas below, never the constants.

## The four parts

### 1. Background scrolling on EVERY layer

Per layer, and it must be every layer the game uses, not just the surveyed one:

* The added margin columns must be **populated before they are shown**, or
  first-visit margins display stale or wrapped tiles. MMX1 does this by reading
  the game's own retained level map to seed the margin (`WsShadowPrefillTile`).
* **Per-line PPU scroll registers are the authority for pixel phase — never a
  WRAM camera mirror.** The mirror is off by one against the PPU and produces the
  "feature sliced in half at the margin" artefact. This bit MMX1 once and is
  worth not repeating.
* HDMA-driven per-scanline effects must continue across the margins.
* Periodic/parallax layers should **fold** by their proven period
  (`WsShadowSetPeriodicFold`) rather than serving stale history.
* Stage-trigger lead must not exceed the margin, or CHR paging garbles.

Renderer-side surface already available, no per-game code needed to *call* it:
`PpuSetExtraSpace`, `PpuSetWidescreenBg3Widen`, `PpuSetWidescreenLineEnhancer`,
`WsShadowFrame` / `WsShadowSetWorld` / `WsShadowSetPeriodicFold` /
`WsShadowPrefillTile`.

### 2. HUD anchored to 16:9 bounds

MMX1 reserves OAM slots 0-15 for HUD sprites and shifts them outward with one
renderer call, gated on real gameplay:

```c
bool in_stage = g_ws_active && <game-state discriminator>;
PpuSetWsHudOamShift(g_ppu, in_stage ? 16 : 0);
```

Two requirements:
* Gate on a **verified game-state discriminator**, not on an HDMA-enable mirror.
  MMX1 originally gated partly on `$00C3` (an HDMAEN mirror) and the HUD snapped
  back to native placement during any effect that toggled HDMA channels.
* Menus, intros and mode-7 scenes must keep native placement.

Survey needed: which OAM slots Mega Man X2 uses for HUD, and which WRAM byte
reliably means "in live stage gameplay".

### 3. Enemy spawning respects 16:9 bounds

Spawn scanning is anchored to a camera column. Widen the anchor so enemies enter
the world before the widescreen edge reveals them:

```
right anchor:  v + (margin + 32)
left  anchor:  max(0, v - (margin + 32))
```

The `+32` matters: an anchor of exactly the margin lands spawns on the outermost
*visible* wide column, i.e. visible pop-in.

**The dual-pass trick is the important part.** Widening the anchor for everything
makes stage controllers, camera staging and minibosses fire early. MMX1 runs the
record walk twice: the widened pass admits **only ordinary enemy records**, then a
second pass at the **unmodified 4:3 anchor** admits everything else, so
progression-critical records keep authentic timing. Per-record flags make an
already-created enemy a no-op in the native pass.

```c
int WsSpawnRecordAllowed(uint16 dpage, uint8 type);   /* wide pass: type only */
void WsSpawnRunNativePass(CpuState *cpu);             /* balanced synthetic JSR */
```

The native pass must be a **balanced** call that preserves all guest registers and
cycle accounting (`cpu_dispatch_call_pc`, save/restore `CpuState`), or it corrupts
the stack.

Survey needed: the spawn-scan routine, the record-descriptor type nibble, and
which types are ordinary enemies versus controllers.

### 4. Enemy culling respects 16:9 bounds

The mirror of (3) — cull keyed to the native edge deletes things still visible in
the margins. Widen the scroll-off verdict symmetrically:

```
vanilla:  carry = (objX - camX + 0x40) >= 0x180          /* keep cam-64..+320 */
widened:  carry = (v + margin) >= (0x180 + 2*margin)
```

Projectiles use the same shape with the game's own tighter base window (MMX1:
`0x20` / `0x140`). Then the OAM emitter, which is a separate gate and easy to
miss:

* the metasprite X **reject limit** must be widened (`vanilla_limit + margin`);
* the reject **compare** must be replaced, because it is a single *unsigned*
  test — negative screen X wraps high and always rejects, so sprites still vanish
  at the native left edge no matter how far the limit is widened:

```c
uint16 WsOamXReject(uint16 x_plus_16, uint16 widened_limit) {
  if (x_plus_16 < widened_limit) return 0;               /* right window */
  if (m && x_plus_16 >= (uint16)(0u - (uint16)m)) return 0; /* left margin */
  return 1;
}
```

Also widen per-enemy **activation distance** for large objects, or a big sprite's
controller only wakes when its centre reaches the widened edge and its outer tiles
pop in.

## Non-negotiables

* **Camera, collision, AI, RNG and save-state data unchanged.** 16:9 is
  presentation plus spawn/cull bounds. If it alters simulation, it is wrong.
* **4:3 must stay bit-identical with the enhancement off.** That is the
  regression gate: capture frames at `Widescreen = 0` before and after, and diff.
  The engine has `PPU frame-diff` tooling for exactly this.
* Every widening gets its own env kill-switch (MMX1: `SNESRECOMP_WS_SPAWN`,
  `SNESRECOMP_WS_STAGE`) so a misbehaving part can fall back to authentic 4:3
  independently, with the rest still active.

## Survey plan — what to measure, with what

Nothing here can be written without Mega Man X2's addresses. All of these are
always-on rings; query them, do not arm-then-run:

| question | tool |
|---|---|
| which routines write OAM, and the HUD slot range | `oam_write_get`, `oam_render_get` |
| the live gameplay-state discriminator | `read_ram`, `set_wram_watch` across mode changes |
| camera X location in WRAM | `trace_wram` while scrolling |
| which code culls/spawns | `SNESRECOMP_WRITE_WATCH` on an object slot, then the reported function |
| per-layer scroll authority | `get_ppu_state` (`hScroll`/`vScroll`) vs the WRAM mirror |

Reaching live gameplay requires a human at the controls — the standing rule is
that gameplay verdicts are the owner's, not the agent's.

## Turning it on

Only after 1-4 are done and the 4:3 gate passes:
1. `gi.widescreen_supported = 1` in `src/main.c`;
2. optionally flip the embedded default's `Widescreen` to 1;
3. record what was surveyed **in this file**, so the next person knows what is
   proven versus assumed.
