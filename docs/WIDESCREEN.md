# 16:9 widescreen — Mega Man X2

## Status: HUD + BG margins done; slot-3 spawn repro fixed; broad playtest pending.

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
  wired into regen.sh). `x2_rtl.c` applies the identical rewrites to the
  private runtime ROM copy, covering interpreter M/X fallbacks and routines
  with no generated body. Enemies act and render in the gutters
  (screenshot-verified). Kill-switch `SNESRECOMP_WS_SPAWN=0`.

* **Dynamic record frontier** — the slot-3 frog exposed a separate gate:
  `$00:DC50` scans 32-pixel level-record buckets and `$00:DCE9` allocates the
  large actor only after its bucket reaches the native camera frontier.
  Four exact generated hooks now widen DC50's left/right probes and its
  vertical sweep. At 342 pixels the live `margin+32` budget rounds outward to
  96 pixels and the sweep grows from 10 to 15 buckets. A separate,
  fail-closed signature patch applies the same values to the private runtime
  ROM, including a cycle-exact seven-byte left-arm rewrite, so interpreter
  tail-JMP and full-LLE execution are covered too. The on-disk ROM is never
  changed.

* **Weather overlays (rain, and by signature the heat shimmer)** — the
  weather is BG3 alone on the SUBSCREEN blended via color math (measured
  from the owner's rain save: BG3SC=$0C 32x32 static streak texture,
  animated purely by scroll). `X2Display_PreparePpuFrame` widens BG3
  exactly for that signature (sub==$04, main lacks BG3); menus keep the
  clamp. A/B-measured: 478 vs 198 bright rain pixels in the east gutter,
  native identical. Kill-switch `SNESRECOMP_WS_BG3=0`.

* **Inlined window copies swept** — apply_overrides.py recognizes symmetric
  pairs through `$A0/$240` and centered-distance checks whose first add and
  final limit must both grow. The current generated coverage has 40
  object-window rewrites plus four DC50 streamer rewrites. The runtime
  object-window census has 38 source-ROM operands plus six
  power-of-two cart mirrors, including `$00:DDB5`, which has no emitted body.
  DC50 has an independent exact-signature gate.
  The earlier "$09DD frontier" hypothesis is
  DISPROVEN ($09DD = player/attention X — see OAM_SURVEY.md); the
  first-appearance probe shows no pop-in at the 16:9 edge in the surveyed
  area.

* **Camera-trigger family swept** (pass 3): dormant per-type wake lines
  (`camera + K` followed by an actual `CMP dp+$05`) widen only their frontier.
  A plain read of `$05` no longer qualifies. Centered windows widen both the
  leading offset and final limit, avoiding the earlier whole-window shift.
  This covers pickup/rocket-style "spawns at 4:3" behavior; the frog proved
  to be the separate dynamic-record frontier above. Weather margins now use
  the line-REPEAT policy instead of map wrap.

* **Sparse vertical margins** — the exact BG provider now proves sparse level
  sources with six non-modal native-view matches instead of standing down on
  a mostly empty sample. The retained slot-0 vertical-fall replay keeps both
  layers active with zero west/east shadow misses; wrapped stale rows are
  absent.

Still open before calling the implementation broadly validated:
* heat-shimmer visual confirmation in play (same mechanism as rain, so the
  BG3 gate should cover it — unverified);
* owner playtest across stages and both travel directions. The deterministic
  slot-3 frog repro is fixed, but other record types may have additional
  per-type wake consumers and should be traced by type if one still pops.

The shipped default is native 256x224. Widescreen is a built-in,
default-disabled package on the launcher's **Mods** page. The generic Settings
toggle remains hidden (`gi.widescreen_supported = 0`) so the mod package is the
single authoritative activation path. `NoSpriteLimits` is a separate renderer
setting and remains enabled by default.

An earlier iteration set `Widescreen = 1` while every hook was inert. The
current package instead activates the surveyed implementation explicitly and
returns to authentic 4:3 whenever the feature is disabled.

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

## Remaining validation — what to measure, with what

The major address families are now recorded above. These always-on rings remain
the right tools for finding stage-specific exceptions; query them, do not
arm-then-run:

| question | tool |
|---|---|
| which routines write OAM, and the HUD slot range | `oam_write_get`, `oam_render_get` |
| the live gameplay-state discriminator | `read_ram`, `set_wram_watch` across mode changes |
| camera X location in WRAM | `trace_wram` while scrolling |
| which code culls/spawns | `SNESRECOMP_WRITE_WATCH` on an object slot, then the reported function |
| per-layer scroll authority | `get_ppu_state` (`hScroll`/`vScroll`) vs the WRAM mirror |

Reaching live gameplay requires a human at the controls — the standing rule is
that gameplay verdicts are the owner's, not the agent's.

## Activation and release gate

The default-disabled `.snesmod` package is the supported activation path. Keep
the embedded `Widescreen = 0` fallback and
`gi.widescreen_supported = 0`; enabling the generic Settings toggle would
create a second, conflicting owner for the same feature.

Before describing the implementation as broadly validated:

1. play every stage in both travel directions;
2. confirm the heat-shimmer signature in live play;
3. capture and diff the authentic 4:3 regression baseline; and
4. record any stage-specific exceptions and their kill-switches in this file.
