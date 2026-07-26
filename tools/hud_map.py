#!/usr/bin/env python3
"""Build X2's HUD OAM slot map from owner-supplied save states.

  slot 0 : health + weapon bars, X idle, safe
  slot 1 : boss fight opening -- health + weapon + boss bar. HOSTILE: the boss is
           attacking, so X dies if left alone.

Two different discriminators, because the two states allow different things:

  slot 0 (safe)   hold a direction and sample mid-motion. A HUD element's SCREEN
                  position is invariant while the world scrolls; the player's is
                  not. Sampling at rest does NOT work -- a side-scroller
                  re-centres the player, so his OAM looks identical, and he is
                  screen-static while scrolling, i.e. the same signature as HUD.

  slot 1 (hostile) no motion, no waiting. RELOAD before every sample so each one
                   is taken at a fixed, early offset from a known state -- X never
                   has time to die, and the samples are directly comparable. Then
                   diff against slot 0's HUD set: slots that are HUD-like here but
                   absent there are the boss bar.
"""
from __future__ import annotations

import collections
import socket
import sys
import time

PORT = 4383


class Dbg:
    def __init__(self):
        self.s = socket.create_connection(('127.0.0.1', PORT), 20)
        self.s.settimeout(60)

    def q(self, c):
        self.s.sendall((c + '\n').encode())
        b = b''
        while b'\n' not in b:
            ch = self.s.recv(1 << 20)
            if not ch:
                raise ConnectionError('closed')
            b += ch
        return b.split(b'\n')[0].decode()

    def frame(self):
        return int(self.q('ping').split('"frame":')[1].rstrip('}'))

    def wait(self, n, timeout=30):
        a = self.frame(); t0 = time.time()
        while self.frame() - a < n:
            if time.time() - t0 > timeout:
                return
            time.sleep(0.02)

    def oam(self):
        h = self.q('dump_oam').split('"hex":"')[1].split('"')[0]
        b = bytes.fromhex(h)
        spr = [(b[i * 4], b[i * 4 + 1], b[i * 4 + 2], b[i * 4 + 3])
               for i in range(128)]
        return spr, b[512:]

    def close(self):
        try:
            self.q('clear_controller')
        except Exception:
            pass
        self.s.close()


def xhi(high, s):
    return (high[s >> 2] >> ((s & 3) * 2)) & 1


def szbit(high, s):
    return (high[s >> 2] >> ((s & 3) * 2 + 1)) & 1


def fx(spr, high, s):
    return spr[s][0] | (xhi(high, s) << 8)


def vis(spr, s):
    return spr[s][1] < 0xE0


def runs(xs):
    out = []
    for v in sorted(xs):
        if out and v == out[-1][1] + 1:
            out[-1][1] = v
        else:
            out.append([v, v])
    return ', '.join(f'{a}' if a == b else f'{a}-{b}' for a, b in out) or '-'


def classify(snaps):
    static, moving, parked = [], [], []
    for s in range(128):
        v = [vis(sn[0], s) for sn in snaps]
        if not any(v):
            parked.append(s); continue
        if not all(v):
            moving.append(s); continue
        keys = {(fx(sn[0], sn[1], s), sn[0][s][1], szbit(sn[1], s))
                for sn in snaps}
        (static if len(keys) == 1 else moving).append(s)
    return static, moving, parked


def table(spr, high, slots, label):
    print(f'  {label}')
    print('    slot    X    Y  tile attr size')
    for s in slots:
        print('    %4d %4d %4d  0x%02X 0x%02X   %d'
              % (s, fx(spr, high, s), spr[s][1], spr[s][2], spr[s][3],
                 szbit(high, s)))


def main():
    d = Dbg()
    try:
        # ---------- slot 0: safe, use motion ----------
        print('=' * 66)
        print('SLOT 0  (health + weapon, safe, X idle) -- motion discriminator')
        print('=' * 66)
        # `loadstate <slot>` (no underscore) queues a load through
        # RtlSaveLoad on the main thread, which runs the game's own
        # X2StateLoadExtra / X2OnStateLoaded hooks and therefore restores
        # the LLE resume cursor. `load_state <file>` is a different thing --
        # a raw L3 snapshot keyed by literal FILENAME, which silently wrote a
        # file called '9' during an earlier test and never touched saves/.
        print(' load:', d.q('loadstate 0')[:90])
        d.wait(20)   # asynchronous: applied at the next frame boundary
        snaps = [d.oam()]
        d.q('set_controller right')
        try:
            for _ in range(3):
                d.wait(14)
                snaps.append(d.oam())
        finally:
            d.q('clear_controller')
        st0, mv0, pk0 = classify(snaps)
        print(f'  STATIC {len(st0):3d}: {runs(st0)}')
        print(f'  MOVING {len(mv0):3d}: {runs(mv0)}')
        print(f'  PARKED {len(pk0):3d}: {runs(pk0)}')
        spr, high = snaps[0]
        table(spr, high, st0, 'static slots (HUD):')

        # ---------- slot 1: hostile, reload per sample ----------
        print()
        print('=' * 66)
        print('SLOT 1  (boss fight opening) -- reload-per-sample, no motion')
        print('=' * 66)
        print(' load:', d.q('loadstate 1')[:90])
        d.wait(20)
        bsnaps = [d.oam()]
        # Hold a direction so the player moves. Without this the idle player is
        # indistinguishable from HUD -- the first attempt reported slots 16-23 as
        # a 'boss bar' when they were X standing still on the right of the screen
        # (same attr 0x62 as the player elsewhere). Keep the whole window short so
        # the boss cannot kill X before sampling finishes.
        d.q('set_controller right')
        try:
            for i in range(3):
                d.wait(8)
                bsnaps.append(d.oam())
                print(f'  sample {i + 2}: frame={d.frame()}')
        finally:
            d.q('clear_controller')
        st1, mv1, pk1 = classify(bsnaps)
        print(f'  STATIC {len(st1):3d}: {runs(st1)}')
        print(f'  MOVING {len(mv1):3d}: {runs(mv1)}')
        print(f'  PARKED {len(pk1):3d}: {runs(pk1)}')
        bspr, bhigh = bsnaps[-1]
        table(bspr, bhigh, st1, 'static slots (HUD candidates):')

        # ---------- differential ----------
        print()
        print('=' * 66)
        print('DIFFERENTIAL')
        print('=' * 66)
        only1 = sorted(set(st1) - set(st0))
        both = sorted(set(st1) & set(st0))
        only0 = sorted(set(st0) - set(st1))
        print(f'  static in BOTH states      : {runs(both)}   <- always-on HUD')
        print(f'  static ONLY in boss state  : {runs(only1)}   <- boss bar candidate')
        print(f'  static ONLY in slot 0      : {runs(only0)}')
        if only1:
            table(bspr, bhigh, only1, 'boss-state-only static slots:')
        print()
        print('  anchoring (screen X of each static slot):')
        for lbl, spr_, high_, slots in (('slot0', spr, high, st0),
                                        ('slot1', bspr, bhigh, st1)):
            L = [s for s in slots if fx(spr_, high_, s) < 64]
            R = [s for s in slots if fx(spr_, high_, s) > 192]
            M = [s for s in slots if 64 <= fx(spr_, high_, s) <= 192]
            print(f'    {lbl}  LEFT(<64): {runs(L)}   MID: {runs(M)}   '
                  f'RIGHT(>192): {runs(R)}')
        print()
        print('  attr grouping (palette+priority) in the boss state:')
        g = collections.defaultdict(list)
        for s in st1:
            g[bspr[s][3]].append(s)
        for a, ss in sorted(g.items()):
            print(f'    attr 0x{a:02X}: {runs(ss)}')
        return 0
    finally:
        d.close()


if __name__ == '__main__':
    sys.exit(main())
