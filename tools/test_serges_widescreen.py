#!/usr/bin/env python3
"""Replay the original Serges approach in an isolated, muted trace build.

Requires SNESRECOMP_ENABLE_TRACE=ON and SNESRECOMP_REVERSE_DEBUG=ON.
The only progression assists bypass the unfinished introduction and select
the original stage/checkpoint loader. The test never writes encounter actors,
level-record live flags, arena limits, boss health, or defeat/progression flags.
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
              'assists': ['bypass interrupted intro control state',
                          'select original fortress stage 10/checkpoint 1',
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
            driver.command('break_add 009fe9')
            for address, value in ((0x1fad, 10), (0x1fae, 1), (0x1ebf, 1),
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
            driver.byte(0x1fb4, 1)
            driver.command('break_clear')
            driver.step(1)
            driver.until(0xd1, b'\x04', 3000)
            driver.until(0xd2, b'\x04', 3000)
            driver.step(120)
            assert driver.byte(0x1fad) == 10 and driver.byte(0x1fb4) == 1
            for buttons, frames in (('right+y', 240), ('0', 480)):
                for _ in range(frames // 30):
                    driver.byte(0x9ff, 32)
                    driver.step(30, buttons)
            driver.command('screenshot serges.bmp')
            width, height = struct.unpack_from('<ii', (out / 'serges.bmp').read_bytes(), 18)
            result['presentation_size'] = [width, abs(height)]
            assert (width == 256) if args.stock else (width > 256), width
            ram = driver.read(0, 0x20000)
            (out / 'serges.wram').write_bytes(ram)
            actors = []
            for address in range(0xd18, 0x1518, 0x40):
                if ram[address] and ram[address + 10] == 0x61:
                    actors.append({'address': f'{address:04x}',
                                   'state': ram[address:address + 4].hex(),
                                   'subtype': ram[address + 11],
                                   'health': ram[address + 0x27]})
            result['serges_actors'] = actors
            result['camera'] = [int.from_bytes(ram[a:a + 2], 'little')
                                for a in (0x1e5d, 0x1e60)]
            assert any(a['subtype'] == 0 and a['health'] > 0 for a in actors), actors
            assert sum(a['subtype'] == 2 and a['health'] > 0 for a in actors) == 4, actors
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
