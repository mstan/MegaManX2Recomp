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

RE_FUNC = re.compile(r"^RecompReturn (bank_00_[0-9A-F]{4})_M\dX\d\(CpuState")

# (function, X-window add constant, X-window limit constant)
WIN_SITES = {
    "bank_00_D813": ("0x40", "0x180"),
    "bank_00_D834": ("0x60", "0x1c0"),
    "bank_00_D859": ("0x20", "0x140"),
}


def win_snippet(indent, var, kind, const):
    fn = "X2WsObjWinAdd" if kind == "add" else "X2WsObjWinLimit"
    return (f"{indent}/*WS-OBJ-WIN*/ {{ extern uint16 {fn}(uint16); "
            f"{var} = {fn}({const}); }}\n")


def apply_obj_windows(lines, verbose):
    out = []
    cur_fn = None
    pending = None  # (add_const, limit_const) still to patch in this body
    n = 0
    for line in lines:
        m = RE_FUNC.match(line)
        if m:
            cur_fn = m.group(1)
            pending = list(WIN_SITES.get(cur_fn, ())) or None
        elif line.startswith("RecompReturn "):
            cur_fn = None
            pending = None
        out.append(line)
        if not pending or cur_fn not in WIN_SITES:
            continue
        add_c, lim_c = WIN_SITES[cur_fn]
        m = re.match(rf"^(\s*)uint16 (_v\d+) = {add_c};\s*$", line)
        if m and add_c in pending:
            out.append(win_snippet(m.group(1), m.group(2), "add", add_c))
            pending.remove(add_c)
            n += 1
            if verbose:
                print(f"  WS-OBJ-WIN add {add_c} in {cur_fn}")
            continue
        m = re.match(rf"^(\s*)uint16 (_v\d+) = {lim_c};\s*$", line)
        if m and lim_c in pending:
            out.append(win_snippet(m.group(1), m.group(2), "limit", lim_c))
            pending.remove(lim_c)
            n += 1
            if verbose:
                print(f"  WS-OBJ-WIN limit {lim_c} in {cur_fn}")
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

    out, n = apply_obj_windows(lines, verbose)
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

    files = sorted(glob.glob(os.path.join(args.gen_dir, "bank00_*.c")))
    if not files:
        print(f"apply_overrides: no gen files under {args.gen_dir}",
              file=sys.stderr)
        return 1

    total = 0
    for path in files:
        total += process_file(path, args.restore, args.check, args.verbose)

    verb = "stripped" if args.restore else "injected"
    print(f"apply_overrides: {verb} {total} site(s)")
    # 3 functions x 2 constants x N M/X variants; require at least the three
    # canonical M1X1 bodies (6 sites) unless restoring or already applied.
    if not args.restore and total not in (0,) and total < 6:
        print("apply_overrides: FEWER SITES THAN EXPECTED -- emitted shapes "
              "may have changed; verify before building.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
