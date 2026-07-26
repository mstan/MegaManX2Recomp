#!/usr/bin/env python3
"""Identify which OAM slots hold the HUD, from live gameplay.

Method: sample OAM, inject a short movement so the camera and the player move,
sample again. A HUD sprite is one whose SCREEN position does not change while the
world scrolls under it. Everything else -- player, enemies, effects -- moves,
despawns, or reshuffles.

Why not do this from the intro: an intro capture has no HUD at all, so slot
ranges that merely *look* like a HUD fingerprint there (a fixed low slot range
written every frame) are just as likely to be cutscene actors. This needs
gameplay, which is why it is its own tool.

Input discipline: every press is followed by an explicit release and the
controller is cleared on exit even on exception -- injection latches across
interrupts.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time

PORT = int(os.environ.get('DBG_PORT', '4383'))


class Dbg:
    def __init__(self, port=PORT):
        self.s = socket.create_connection(('127.0.0.1', port), 15)
        self.s.settimeout(30)

    def q(self, cmd: str) -> str:
        self.s.sendall((cmd + '\n').encode())
        buf = b''
        while b'\n' not in buf:
            c = self.s.recv(1 << 20)
            if not c:
                raise ConnectionError('server closed')
            buf += c
        return buf.split(b'\n')[0].decode()

    def frame(self) -> int:
        return int(self.q('ping').split('"frame":')[1].rstrip('}'))

    def wait(self, n, timeout=30.0):
        a = self.frame(); t0 = time.time()
        while self.frame() - a < n:
            if time.time() - t0 > timeout:
                raise TimeoutError(f'only {self.frame()-a}/{n} frames advanced')
            time.sleep(0.02)

    def oam(self):
        """(sprites, high) -- 128 x (x, y, tile, attr) plus the 32-byte high table."""
        r = self.q('dump_oam')
        if '"hex"' not in r:
            raise RuntimeError(r)
        hexs = r.split('"hex":"')[1].split('"')[0]
        b = bytes.fromhex(hexs)
        assert len(b) == 544, len(b)
        sprites = [(b[i * 4], b[i * 4 + 1], b[i * 4 + 2], b[i * 4 + 3])
                   for i in range(128)]
        return sprites, b[512:]

    def press(self, btn, hold, gap):
        self.q(f'set_controller {btn}')
        self.wait(hold)
        self.q('clear_controller')
        self.wait(gap)

    def hold(self, btn):
        self.q(f'set_controller {btn}')

    def release(self):
        self.q('clear_controller')

    def close(self):
        try:
            self.q('clear_controller')
        except Exception:
            pass
        try:
            self.s.close()
        except Exception:
            pass


def xhi(high, slot):
    """X bit 8 for a slot, from the 2-bits-per-sprite high table."""
    return (high[slot >> 2] >> ((slot & 3) * 2)) & 1


def size_bit(high, slot):
    return (high[slot >> 2] >> ((slot & 3) * 2 + 1)) & 1


def full_x(spr, high, slot):
    return spr[slot][0] | (xhi(high, slot) << 8)


def visible(spr, slot):
    """Y == 0xF0/0xE0 is the usual parked/off-screen convention."""
    y = spr[slot][1]
    return y not in (0xE0, 0xF0) and y < 0xE0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--move', default='right')
    ap.add_argument('--hold', type=int, default=24)
    ap.add_argument('--samples', type=int, default=3)
    args = ap.parse_args()

    d = Dbg()
    try:
        # Sample WHILE the button is held, not after releasing it.
        #
        # First attempt sampled only at rest and reported MOVING=0 -- because a
        # side-scroller re-centres the player on screen once he stops, so
        # press/release/settle leaves his OAM identical. Worse, the player sprite
        # is screen-static while the world scrolls, which is the SAME signature as
        # a HUD element. Holding the input is what separates them: mid-motion the
        # player's screen position changes and the HUD's does not.
        snaps = []
        print(f'sampling OAM WHILE holding "{args.move}" '
              f'({args.hold} frames between samples, {args.samples} samples)')
        spr, high = d.oam()
        snaps.append((d.frame(), spr, high))
        d.hold(args.move)
        try:
            for _ in range(args.samples - 1):
                d.wait(args.hold)
                spr, high = d.oam()
                snaps.append((d.frame(), spr, high))
        finally:
            d.release()
        print(f'  frames sampled: {[s[0] for s in snaps]}')

        # A slot is STATIC if it is visible in every sample and its full X, Y,
        # size bit are identical throughout.
        static, moving, parked = [], [], []
        for slot in range(128):
            vis = [visible(s[1], slot) for s in snaps]
            if not any(vis):
                parked.append(slot)
                continue
            if not all(vis):
                moving.append(slot)
                continue
            keys = {(full_x(s[1], s[2], slot), s[1][slot][1],
                     size_bit(s[2], slot)) for s in snaps}
            (static if len(keys) == 1 else moving).append(slot)

        def runs(xs):
            out = []
            for v in xs:
                if out and v == out[-1][1] + 1:
                    out[-1][1] = v
                else:
                    out.append([v, v])
            return ', '.join(f'{a}' if a == b else f'{a}-{b}' for a, b in out)

        print()
        print(f'STATIC  ({len(static):3d}): {runs(static)}')
        print(f'MOVING  ({len(moving):3d}): {runs(moving)}')
        print(f'PARKED  ({len(parked):3d}): {runs(parked)}')

        print()
        print('static slots in detail (HUD candidates):')
        print('  slot   X    Y  tile attr  sizebit')
        spr, high = snaps[-1][1], snaps[-1][2]
        for slot in static:
            print('  %4d %4d %4d  0x%02X 0x%02X   %d'
                  % (slot, full_x(spr, high, slot), spr[slot][1],
                     spr[slot][2], spr[slot][3], size_bit(high, slot)))

        if static:
            xs = [full_x(spr, high, s) for s in static]
            ys = [spr[s][1] for s in static]
            print()
            print('  screen extent: X %d..%d   Y %d..%d'
                  % (min(xs), max(xs), min(ys), max(ys)))
            left = [s for s in static if full_x(spr, high, s) < 64]
            right = [s for s in static if full_x(spr, high, s) > 192]
            print('  LEFT-anchored  (X < 64):  %s' % (runs(left) or '-'))
            print('  RIGHT-anchored (X > 192): %s' % (runs(right) or '-'))
            # Palette/priority is a second, independent signal: HUD sprites
            # normally share an attr distinct from actors.
            import collections
            byattr = collections.defaultdict(list)
            for s in static:
                byattr[spr[s][3]].append(s)
            print('  grouped by attr byte (palette+priority):')
            for a, ss in sorted(byattr.items()):
                print('    attr 0x%02X: %s' % (a, runs(ss)))
        return 0
    finally:
        d.close()


if __name__ == '__main__':
    sys.exit(main())
