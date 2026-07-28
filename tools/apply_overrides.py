#!/usr/bin/env python3
"""Apply the widescreen gen-code patch layer for Mega Man X2 (marker-injected,
restorable -- same discipline as MMX1's tools/apply_overrides.py).

Runs AFTER regen, BEFORE compilation. Injection is marked and idempotent;
--restore strips every marked line, returning gen to pristine output.

WS-OBJ-WIN -- widen the shared object window checks (X axis only).
  Resident objects use structs at $1818+ (stride $20, world coords at
  dp$05/$08), and three tiny bank-00 helpers gate them by comparing object
  world X/Y against the BG1 stream anchor $1E5D/$1E60:

    $00:D813  activation window  (objX - cam + $40) < $180   cam-64..+320
    $00:D834  wide visibility    (objX - cam + $60) < $1C0   cam-96..+352
    $00:D859  draw window        (objX - cam + $20) < $140   cam-32..+288
              (the common AI tail: sets dp$0E=$81 "emit metasprite" or 0)

  Every ordinary enemy runs these via JSL/JMP, so widening the three X
  windows by the live margin moves activation AND visibility to the 16:9
  edges in one place. The Y-axis windows are untouched (widescreen adds no
  vertical margin). In each emitted body the X test precedes the Y test, so
  the FIRST occurrence of the add/limit constant is the X axis; D834's Y
  limit is $180 (same value as D813's X limit), which is why matching is
  scoped per function and first-occurrence-only.

  Helpers X2WsObjWinAdd/X2WsObjWinLimit live in src/x2_rtl.c: identical to
  vanilla when widescreen is off (g_ws_active false) or when the spawn
  widening is kill-switched (SNESRECOMP_WS_SPAWN=0).

WS-SPAWN-STREAM -- widen $00:DC50's 32-pixel dynamic record frontier.
  Large actors are not resident until this routine asks $00:DCE9 to allocate
  their level record. Four exact hooks move its left/right probes and widen
  its vertical sweep. src/x2_rtl.c applies the equivalent signature-gated
  rewrite to the private runtime ROM for interpreter and full-LLE execution.

Usage:
    python tools/apply_overrides.py [--gen-dir src/gen] [--check] [-v]
    python tools/apply_overrides.py --restore [--gen-dir src/gen] [-v]
"""
import argparse
import glob
import os
import re
import sys

OBJ_MARKER = "/*WS-OBJ-WIN*/"
STREAM_MARKER = "/*WS-SPAWN-STREAM*/"
DISPATCH_MARKER = "/*WS-SPAWN-DISPATCH*/"
MARKERS = (OBJ_MARKER, STREAM_MARKER, DISPATCH_MARKER)

RE_FUNC = re.compile(r"^RecompReturn (bank_[0-9A-Fa-f]{2}_[0-9A-F]{4})_M\dX\d"
                     r"\(CpuState")
# The camera-anchor reads. $1E5D = world X (the window idiom subtracts it
# from the object's dp$05); $1E60 = world Y — a Y read DISARMS the tracker
# because the Y windows reuse the $180 limit constant (D834's Y pair is
# $50/$180) and must stay authentic (widescreen adds no vertical margin).
RE_ANCHOR_X = re.compile(
    r"cpu_read16\(cpu, (?:cpu->DB|0x7e), \(uint16\)\(0x1e5d\)\)", re.I)
RE_ANCHOR_Y = re.compile(
    r"cpu_read16\(cpu, (?:cpu->DB|0x7e), \(uint16\)\(0x1e60\)\)", re.I)
RE_CONST = re.compile(r"^(\s*)uint16 (_v\d+) = (0x[0-9a-f]+);\s*$")

# The shared helpers use $20/$40/$60. Several per-type copies use the same
# symmetric formula with wider native padding:
#
#     (objX - camX + add) < (0x100 + 2 * add)
#
# Keep those emitted bodies on the same dynamic-margin path too. The runtime
# ROM scan in x2_rtl.c supplies identical coverage when a body is interpreted.
ADD_CONSTS = {"0x20", "0x40", "0x60", "0x80", "0xa0"}
LIMIT_CONSTS = {"0x140", "0x180", "0x1c0", "0x200", "0x240"}
# Camera-relative TRIGGER idiom: $1E5D read -> add-const -> CMP against the
# object's own dp$05 world X (a memory compare, invisible to the window
# pass above). Per-type wake/attack lines tuned to the native view; the
# Pickup/rocket-style per-type pop-ins use this family. The slot-3 frog was
# later traced to the separate DC50 record streamer below.
TRIG_ADDS = {"0x20", "0x40", "0x60", "0x80", "0xa0", "0xc0", "0x100",
             "0x110", "0x120", "0x140"}
RE_DP5 = re.compile(
    r"cpu_read16\(cpu, 0x00, \(uint16\)\(cpu->D \+ 0x0005\)\)")
RE_CMP_TEMP = re.compile(r"\buint32 _tc\d+_\d+ =")
# These symmetric distance checks subtract dp+$05 between their first add and
# immediate limit. Their emitted arithmetic is longer than an ordinary pair,
# but the first add and final limit still require the normal +m/+2m rewrite.
CENTERED_PAIRS = {
    "bank_04_CBE8": ("0x80", "0x1c0"),
    "bank_29_85F1": ("0x80", "0x1c0"),
}
CENTERED_FUNCS = set(CENTERED_PAIRS)
# Emitted-line budgets: in every observed body the add constant lands within
# a few lines of the anchor read (the ADC follows the SBC immediately) and
# the limit within the CMP that follows. A generous budget still rejects
# far-away unrelated constants.
ADD_BUDGET = 60
LIMIT_BUDGET = 40
CENTERED_LIMIT_BUDGET = 180
# Recursive-exit analysis also materializes five bank-$03 LoROM mirrors of
# already-audited trigger shapes at E357/E35E/E3AF/E3B3/E665. They need the
# same generated-C rewrite; the private-ROM interpreter pass still patches
# their shared physical bytes once.
EXPECTED_SITES = 45
EXPECTED_PAIRS = 17
EXPECTED_STREAM_SITES = 4
EXPECTED_DISPATCH_SITES = 0


def win_snippet(indent, var, kind, const):
    fn = "X2WsObjWinAdd" if kind == "add" else "X2WsObjWinLimit"
    return (f"{indent}{OBJ_MARKER} {{ extern uint16 {fn}(uint16); "
            f"{var} = {fn}({const}); }}\n")


def spawn_stream_snippet(indent, var, kind):
    helpers = {
        "left": "X2WsSpawnStreamLeft",
        "right": "X2WsSpawnStreamRightAdd",
        "grid_pad": "X2WsSpawnStreamGridPad",
        "columns": "X2WsSpawnStreamColumns",
    }
    fn = helpers[kind]
    return (f"{indent}{STREAM_MARKER} {{ extern uint16 {fn}(uint16); "
            f"{var} = {fn}({var}); }}\n")


def apply_obj_windows(lines, verbose, fname):
    """Generic pass, PAIR-CONFIRMED: after a $1E5D (camera X) read, find the
    next add-constant AND the next limit-constant of the window idiom; only
    a complete pair is injected. A lone add after an anchor read is some
    other camera computation and must stay untouched. $1E60 reads or budget
    exhaustion disarm the tracker."""
    # Phase 1: detect confirmed pairs -> line index -> (var, kind, const)
    inject = {}
    cur_fn = None
    state = None  # None | ("add", ttl) | ("limit", ttl, add_idx, add_m)
    n_pairs = 0
    for idx, line in enumerate(lines):
        m = RE_FUNC.match(line)
        if m:
            cur_fn = m.group(1)
            state = None
        elif line.startswith("RecompReturn "):
            cur_fn = None
            state = None
        if cur_fn is None:
            continue
        if RE_ANCHOR_X.search(line):
            state = ("add", ADD_BUDGET)
            continue
        if RE_ANCHOR_Y.search(line):
            state = None
            continue
        if state is None:
            continue
        ttl = state[1] - 1
        if ttl <= 0:
            state = None
            continue
        state = (state[0], ttl) + state[2:]
        m = RE_CONST.match(line)
        if not m:
            continue
        indent, var, const = m.groups()
        if state[0] == "add" and const in ADD_CONSTS:
            limit_budget = (CENTERED_LIMIT_BUDGET
                            if cur_fn in CENTERED_FUNCS else LIMIT_BUDGET)
            state = ("limit", limit_budget, idx, (indent, var, const))
        elif state[0] == "limit" and const in LIMIT_CONSTS:
            add_idx, add_m = state[2], state[3]
            add_value = int(add_m[2], 16)
            symmetric = int(const, 16) == 0x100 + 2 * add_value
            centered = CENTERED_PAIRS.get(cur_fn) == (add_m[2], const)
            if not symmetric and not centered:
                continue
            inject[add_idx] = (add_m[0], add_m[1], "add", add_m[2], cur_fn)
            inject[idx] = (indent, var, "limit", const, cur_fn)
            n_pairs += 1
            state = None

    # Detect camera-trigger sites: anchor -> add-const -> CMP dp$05.
    # Confirmed only by the dp$05 compare; the add is widened like a
    # window edge (fires when the WIDE view approaches, not the native).
    cur_fn = None
    state = None  # None | ("armed", ttl) | ("added", idx, m, ttl)
    for idx, line in enumerate(lines):
        m = RE_FUNC.match(line)
        if m:
            cur_fn = m.group(1)
            state = None
        elif line.startswith("RecompReturn "):
            cur_fn = None
            state = None
        if cur_fn is None:
            continue
        if RE_ANCHOR_X.search(line):
            state = ("armed", 40)
            continue
        if RE_ANCHOR_Y.search(line):
            state = None
            continue
        if state is None:
            continue
        ttl = state[-1] - 1
        if ttl <= 0:
            state = None
            continue
        state = state[:-1] + (ttl,)
        mc = RE_CONST.match(line)
        if mc and state[0] == "armed" and mc.group(3) in TRIG_ADDS \
                and idx not in inject:
            state = ("added", idx, mc.groups(), 30)
            continue
        # A dp+$05 read alone is not a trigger: SBC and LDA use the same
        # emitted read shape. Require the compare temporary that immediately
        # follows a generated CMP instruction.
        is_cmp = any(RE_CMP_TEMP.search(follow)
                     for follow in lines[idx + 1:idx + 6])
        if state[0] == "added" and RE_DP5.search(line) and is_cmp:
            add_idx, (indent, var, const) = state[1], state[2]
            if add_idx not in inject:
                inject[add_idx] = (indent, var, "add", const,
                                   cur_fn + " [trigger]")
            state = None

    # Phase 2: emit with snippets after each confirmed line.
    out = []
    n = 0
    for idx, line in enumerate(lines):
        out.append(line)
        if idx in inject:
            indent, var, kind, const, fn = inject[idx]
            out.append(win_snippet(indent, var, kind, const))
            n += 1
            if verbose:
                print(f"  WS-OBJ-WIN {kind} {const} in {fn} ({fname})")
    return out, n, n_pairs


def apply_spawn_stream(lines, verbose, fname):
    """Widen $00:DC50's dynamic object-record scan grid.

    This is separate from the resident-object windows above: DC50 decides
    when a level record is allocated at all. Its right-moving scan samples
    camera+$100, its left-moving scan samples camera, and its vertical scan
    covers ten 32-pixel columns from camera-$20.
    """
    inject = {}
    cur_fn = None
    block = None
    grid_pad_seen = False
    assign = re.compile(r"^(\s*)uint16 (_v\d+) =")
    label = re.compile(r"^\s*L_(DC70|DC86|DCC8)_M0X0:")

    for idx, line in enumerate(lines):
        match = RE_FUNC.match(line)
        if match:
            cur_fn = match.group(1)
            block = None
        elif line.startswith("RecompReturn "):
            cur_fn = None
            block = None
        if cur_fn != "bank_00_DC50":
            continue

        match = label.match(line)
        if match:
            block = match.group(1)
            grid_pad_seen = False
            continue

        if block == "DC70" and RE_ANCHOR_X.search(line):
            match = assign.match(line)
            if match:
                inject[idx] = (match.group(1), match.group(2), "left")
                block = None
            continue

        match = RE_CONST.match(line)
        if not match:
            continue
        indent, var, const = match.groups()
        if block == "DC86" and const == "0x100":
            inject[idx] = (indent, var, "right")
            block = None
        elif block == "DCC8" and not grid_pad_seen and const == "0x20":
            inject[idx] = (indent, var, "grid_pad")
            grid_pad_seen = True
        elif block == "DCC8" and grid_pad_seen and const == "0xa":
            inject[idx] = (indent, var, "columns")
            block = None

    out = []
    for idx, line in enumerate(lines):
        out.append(line)
        if idx in inject:
            indent, var, kind = inject[idx]
            out.append(spawn_stream_snippet(indent, var, kind))
            if verbose:
                print(f"  WS-SPAWN-STREAM {kind} in bank_00_DC50 ({fname})")
    return out, len(inject)


def apply_spawn_dispatch(lines, verbose, fname):
    """Strip the superseded dispatch experiment through MARKERS cleanup."""
    return lines, 0


def process_file(path, restore, check, verbose):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    old_markers = sum(
        any(marker in line for marker in MARKERS) for line in lines)
    if restore:
        if not old_markers:
            return 0, 0, 0, 0, 0, False
        kept = [ln for ln in lines if not any(mk in ln for mk in MARKERS)]
        if not check:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(kept)
        n = len(lines) - len(kept)
        if verbose:
            print(f"{os.path.basename(path)}: stripped {n} injected line(s)")
        return n, 0, 0, 0, 0, False

    clean = [
        line for line in lines
        if not any(marker in line for marker in MARKERS)
    ]
    out, obj_sites, pairs = apply_obj_windows(
        clean, verbose, os.path.basename(path))
    out, stream_sites = apply_spawn_stream(
        out, verbose, os.path.basename(path))
    out, dispatch_sites = apply_spawn_dispatch(
        out, verbose, os.path.basename(path))
    matches = lines == out
    stale = old_markers > 0 and not matches
    if not matches and not check:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(out)
    changed = max(
        0, obj_sites + stream_sites + dispatch_sites - old_markers)
    if verbose:
        if matches:
            print(f"{os.path.basename(path)}: injections verified")
        elif check:
            print(f"{os.path.basename(path)}: would normalize injections")
        else:
            print(f"{os.path.basename(path)}: normalized injections")
    return changed, obj_sites, pairs, stream_sites, dispatch_sites, stale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-dir", default="src/gen")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.gen_dir, "bank*_v2.c")))
    dispatch = os.path.join(args.gen_dir, "dispatch_v2.c")
    if os.path.isfile(dispatch):
        files.append(dispatch)
    if not files:
        print(f"apply_overrides: no gen files under {args.gen_dir}",
              file=sys.stderr)
        return 1

    total = 0
    obj_sites = 0
    pairs = 0
    stream_sites = 0
    dispatch_sites = 0
    stale_files = []
    for path in files:
        (changed, file_obj, file_pairs, file_stream, file_dispatch,
         stale) = process_file(
            path, args.restore, args.check, args.verbose)
        total += changed
        obj_sites += file_obj
        pairs += file_pairs
        stream_sites += file_stream
        dispatch_sites += file_dispatch
        if stale:
            stale_files.append(path)

    verb = "stripped" if args.restore else "injected"
    print(f"apply_overrides: {verb} {total} site(s)")
    # Recompute the expected marked output from clean generated code every
    # time. This validates shape and placement, not merely marker totals.
    if (not args.restore and
            (obj_sites != EXPECTED_SITES or pairs != EXPECTED_PAIRS or
             stream_sites != EXPECTED_STREAM_SITES or
             dispatch_sites != EXPECTED_DISPATCH_SITES)):
        print(f"apply_overrides: expected {EXPECTED_SITES} object sites/"
              f"{EXPECTED_PAIRS} pairs and {EXPECTED_STREAM_SITES} stream "
              f"sites/{EXPECTED_DISPATCH_SITES} dispatch sites, got "
              f"{obj_sites}/{pairs}, {stream_sites}, and {dispatch_sites} "
              "-- verify generated coverage before building.",
              file=sys.stderr)
        return 1
    if args.check and stale_files:
        print("apply_overrides: marked files do not match a clean structural "
              "reinjection: " + ", ".join(stale_files), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
