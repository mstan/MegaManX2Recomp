#!/usr/bin/env python3
"""Apply the widescreen gen-code patch layer for Mega Man X2 (marker-injected,
restorable -- same discipline as MMX1's tools/apply_overrides.py).

Runs AFTER regen, BEFORE compilation. Injection is marked and idempotent;
--restore strips every marked line, returning gen to pristine output.

WS-OBJ-WIN -- widen the shared object window checks (X axis only).
  Unlike MMX1, X2 does not spawn enemies from a camera-anchored record walk:
  each section's objects are pre-populated as structs ($1818+, stride $20,
  world coords at dp$05/$08), and three tiny bank-00 helpers gate everything
  by comparing object world X/Y against the BG1 stream anchor $1E5D/$1E60
  (== camera; the same anchor the BG margin fill uses):

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

Usage:
    python tools/apply_overrides.py [--gen-dir src/gen] [--check] [-v]
    python tools/apply_overrides.py --restore [--gen-dir src/gen] [-v]
"""
import argparse
import glob
import os
import re
import sys

MARKERS = ("/*WS-OBJ-WIN*/",)

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

ADD_CONSTS = {"0x20", "0x40", "0x60"}
LIMIT_CONSTS = {"0x140", "0x180", "0x1c0"}
# Camera-relative TRIGGER idiom: $1E5D read -> add-const -> CMP against the
# object's own dp$05 world X (a memory compare, invisible to the window
# pass above). Per-type wake/attack lines tuned to the native view; the
# owner-reported frog/pickup/rocket pop-ins are this family.
TRIG_ADDS = {"0x20", "0x40", "0x60", "0x80", "0xa0", "0xc0", "0x100",
             "0x110", "0x120", "0x140"}
RE_DP5 = re.compile(
    r"cpu_read16\(cpu, 0x00, \(uint16\)\(cpu->D \+ 0x0005\)\)")
# Emitted-line budgets: in every observed body the add constant lands within
# a few lines of the anchor read (the ADC follows the SBC immediately) and
# the limit within the CMP that follows. A generous budget still rejects
# far-away unrelated constants.
ADD_BUDGET = 60
LIMIT_BUDGET = 40


def win_snippet(indent, var, kind, const):
    fn = "X2WsObjWinAdd" if kind == "add" else "X2WsObjWinLimit"
    return (f"{indent}/*WS-OBJ-WIN*/ {{ extern uint16 {fn}(uint16); "
            f"{var} = {fn}({const}); }}\n")


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
            state = ("limit", LIMIT_BUDGET, idx, (indent, var, const))
        elif state[0] == "limit" and const in LIMIT_CONSTS:
            add_idx, add_m = state[2], state[3]
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
        if state[0] == "added" and RE_DP5.search(line):
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
    return out, n


def process_file(path, restore, check, verbose):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    had_markers = any(any(mk in ln for mk in MARKERS) for ln in lines)
    if restore:
        if not had_markers:
            return 0
        kept = [ln for ln in lines if not any(mk in ln for mk in MARKERS)]
        if not check:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(kept)
        n = len(lines) - len(kept)
        if verbose:
            print(f"{os.path.basename(path)}: stripped {n} injected line(s)")
        return n

    if had_markers:
        if verbose:
            print(f"{os.path.basename(path)}: already injected, skipping")
        return 0

    out, n = apply_obj_windows(lines, verbose, os.path.basename(path))
    if n and not check:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(out)
    if n and verbose:
        print(f"{os.path.basename(path)}: injected {n} site(s)")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-dir", default="src/gen")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.gen_dir, "bank*_v2.c")))
    if not files:
        print(f"apply_overrides: no gen files under {args.gen_dir}",
              file=sys.stderr)
        return 1

    total = 0
    for path in files:
        total += process_file(path, args.restore, args.check, args.verbose)

    verb = "stripped" if args.restore else "injected"
    print(f"apply_overrides: {verb} {total} site(s)")
    # Known idiom population: the 3 shared helpers (7 M/X bodies) + 4 inlined
    # copies = 11 pairs = 22 sites at the 2026-07-26 coverage. Require at
    # least the shared helpers (14 sites) unless restoring or already applied.
    if not args.restore and total not in (0,) and total < 14:
        print("apply_overrides: FEWER SITES THAN EXPECTED -- emitted shapes "
              "may have changed; verify before building.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
