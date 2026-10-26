#!/usr/bin/env python3
"""Replay original fortress encounters in an isolated, muted trace build.

Requires SNESRECOMP_ENABLE_TRACE=ON and SNESRECOMP_REVERSE_DEBUG=ON.
Progression assists bypass the unfinished introduction and select the original
stage/checkpoint loader. Entry checks never write encounter actors, level-record
live flags or arena limits. The Boss Rush combat check reduces health before
actual projectile damage; it never writes the rematch result or return state.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--exe', required=True, type=Path)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path,
                    help='New disposable profile/evidence directory; must not exist')
    ap.add_argument('--framework', type=Path,
                    default=Path(__file__).resolve().parents[1] / 'snesrecomp')
    ap.add_argument('--stock', action='store_true')
    ap.add_argument('--encounter', choices=('serges', 'bossrush'), default='serges')
    ap.add_argument('--window', default='1280x720')
    ap.add_argument('--pure', action='store_true',
                    help='Use the interpreter without native dispatch bounces')
    args = ap.parse_args()
    sys.path.insert(0, str(args.framework.resolve() / 'tools'))
    from sneslib.client import DebugClient
    from sneslib.route import FrameDriver

    exe, rom, out = args.exe.resolve(), args.rom.resolve(), args.out.resolve()
    if not exe.is_file() or not rom.is_file():
        ap.error('Executable and ROM must exist')
    out.mkdir(parents=True, exist_ok=False)
    for path in exe.parent.iterdir():
        if path.is_file() and (path == exe or path.suffix.lower() == '.dll'):
            shutil.copy2(path, out / path.name)
    for name in ('mods', 'assets', 'shaders'):
        if (exe.parent / name).is_dir():
            shutil.copytree(exe.parent / name, out / name)
    config = out / 'config.ini'
    config.write_text(
        '[General]\nAutosave=0\nSkipLauncher=1\nDisableFrameDelay=1\nRunAhead=0\n'
        '[Graphics]\nWindowScale=2\nWindowSize=' + args.window + '\n'
        'Fullscreen=0\nVSync=0\nRenderer=software\nNewRenderer=1\n'
        '[Sound]\nEnableAudio=1\nVolume=0\n'
        '[GamepadMap]\nEnableGamepad1=false\nEnableGamepad2=false\n',
        encoding='utf-8')
    (out / 'mods/preloaded/state.toml').write_text(
        'format_version = 1\n[[feature]]\n'
        'package_id = "megaman-x2.enhancement.widescreen"\n'
        'id = "widescreen"\nenabled = ' + str(not args.stock).lower() + '\n',
        encoding='utf-8')
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith('SNESRECOMP_')}
    env.update(SDL_AUDIODRIVER='dummy', SDL_AUDIO_DRIVER='dummy',
               SDL_VIDEODRIVER='dummy', SDL_VIDEO_DRIVER='dummy',
               SNESRECOMP_DEBUG_PORT=str(port), SNESRECOMP_NO_LAUNCHER='1')
    if args.pure:
        env.update(SNESRECOMP_EXECUTION_MODE='off', SNESRECOMP_LLE_BOUNCE='0')
    result = {'source_executable': str(exe), 'stock': args.stock,
              'window': args.window, 'pure': args.pure, 'passed': False,
              'encounter': args.encounter,
              'assists': ['bypass interrupted intro control state',
                          'select original fortress stage/checkpoint loader',
                          'refill player health during approach']}
    client = DebugClient(port, timeout=20)
    driver = None
    process = None
    try:
        with (out / 'run.log').open('wb') as log:
            process = subprocess.Popen(
                [str(out / exe.name), '--config', str(config), str(rom)],
                cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic() + 90
            while not client.is_alive():
                if process.poll() is not None:
                    raise RuntimeError(f'Host exited: {process.returncode}')
                if time.monotonic() > deadline:
                    raise TimeoutError('TCP server did not start')
                time.sleep(.1)
            driver = FrameDriver(client, out)
            driver.wait_started()
            driver.step(600)
            for _ in range(4):
                driver.step(6, 'start')
                driver.step(120)
            driver.until(0xd1, b'\x04', 3000)
            driver.until(0xd2, b'\x04', 3000)
            driver.step(240)
            driver.write(0x1f00, bytes(0x50))
            driver.byte(0x1faf, 0x40)
            driver.byte(0x1fd2, 1)
            stage, variant, checkpoint = (10, 1, 1) if args.encounter == 'serges' else (12, 3, 3)
            result.update(stage=stage, checkpoint=checkpoint)
            if args.encounter == 'bossrush':
                for address in range(0x1fba, 0x1fca, 2):
                    driver.word(address, 0xdc00)
                result['assists'].append('eight prior Mavericks marked complete as rematch prerequisites; rematch result flags untouched')
            driver.command('break_add 009fe9')
            for address, value in ((0x1fad, stage), (0x1fae, variant), (0x1ebf, 1),
                                   (0x1fb2, 0), (0xd0, 2), (0xd1, 2),
                                   (0xd2, 4), (0xd3, 0)):
                driver.byte(address, value)
            driver.command('continue')
            deadline = time.monotonic() + 40
            while True:
                parked = driver.command('parked')
                if parked.get('parked'):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError('Original loader instruction stop was not reached')
                time.sleep(.02)
            assert int(parked['pc'], 16) == 0x9fe9, parked
            driver.byte(0x1fb4, checkpoint)
            driver.command('break_clear')
            driver.step(1)
            driver.until(0xd1, b'\x04', 3000)
            driver.until(0xd2, b'\x04', 3000)
            driver.step(120)
            assert driver.byte(0x1fad) == stage and driver.byte(0x1fb4) == checkpoint
            for buttons, frames in (('right+y', 240), ('0', 480)):
                for _ in range(frames // 30):
                    driver.byte(0x9ff, 32)
                    driver.step(30, buttons)
            driver.command('screenshot encounter.bmp')
            width, height = struct.unpack_from('<ii', (out / 'encounter.bmp').read_bytes(), 18)
            result['presentation_size'] = [width, abs(height)]
            # The packed rematch stage intentionally uses native framing:
            # the owner requested black bars instead of adjacent-room garbage.
            native_frame = args.stock or args.encounter == 'bossrush'
            assert (width == 256) if native_frame else (width > 256), width
            result['native_framing'] = native_frame
            ram = driver.read(0, 0x20000)
            (out / 'encounter.wram').write_bytes(ram)
            actors = []
            for address in range(0xd18, 0x1518, 0x40):
                if ram[address]:
                    actors.append({'address': f'{address:04x}',
                                   'id': ram[address + 10],
                                   'state': ram[address:address + 4].hex(),
                                   'subtype': ram[address + 11],
                                   'health': ram[address + 0x27]})
            result['actors'] = actors
            result['camera'] = [int.from_bytes(ram[a:a + 2], 'little')
                                for a in (0x1e5d, 0x1e60)]
            if args.encounter == 'serges':
                serges = [a for a in actors if a['id'] == 0x61]
                assert any(a['subtype'] == 0 and a['health'] > 0 for a in serges), actors
                assert sum(a['subtype'] == 2 and a['health'] > 0 for a in serges) == 4, actors
            else:
                assert any(a['id'] == 0x23 and a['health'] > 0 for a in actors), actors
                boss_ids = {0x1d, 0x1e, 0x23, 0x34, 0x35, 0x38, 0x3b, 0x3c, 0x4b}
                assert not any(a['id'] in boss_ids - {0x23} for a in actors), actors
                assert not driver.byte(0x1fd9) & 2
                result['assists'].append('reduce Wire Sponge health before real projectile damage')
                for _ in range(36):
                    if driver.byte(0x1fd9) & 2:
                        break
                    for address in range(0xd18, 0x1518, 0x40):
                        obj = driver.read(address, 0x28)
                        if obj[0] and obj[1] == 2 and obj[10] == 0x23 and 0 < obj[0x27] < 128:
                            driver.byte(address + 0x27, 1)
                            x, y = int.from_bytes(obj[5:7], 'little'), int.from_bytes(obj[8:10], 'little')
                            driver.word(0x9dd, max(0x318, min(0x3d0, x - 64)))
                            driver.word(0x9e0, max(0x418, min(0x4d0, y + 14)))
                    driver.byte(0x9ff, 32)
                    driver.step(1, 'right')
                    driver.step(12, 'y')
                    driver.step(12)
                driver.step(1200)
                result['rematch_flags'] = driver.byte(0x1fd9)
                result['return_checkpoint'] = driver.byte(0x1fb4)
                driver.command('screenshot returned.bmp')
                assert result['rematch_flags'] & 2 and result['return_checkpoint'] == 1, result
            result['passed'] = True
    except Exception as error:
        result['error'] = repr(error)
    finally:
        try:
            if driver:
                driver.close()
            else:
                client.close()
        except Exception as error:
            result['cleanup_error'] = repr(error)
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
