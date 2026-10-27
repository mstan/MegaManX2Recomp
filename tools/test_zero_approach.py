"""Replay the final-stage Zero door from a current-build approach snapshot.

The caller runs a muted debug host. The snapshot must precede the door and
encounter allocation. --rescued supplies earlier X-Hunter collection
prerequisites; the check never edits Zero, camera, control or result flags.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys


def run_case(driver, profile, state, rescued=False, label='zero-approach'):
    profile = Path(profile)
    (profile / 'saves').mkdir(exist_ok=True)
    shutil.copy2(state, profile / 'saves/save0.sav')
    driver.command('clear_controller')
    driver.command('loadstate 0')
    for _ in range(3):
        driver.command('step 1')

    def encounter():
        pool = driver.read(0xd18, 0x800)
        return [dict(address=0xd18+i, id=pool[i+10],
                     state=pool[i:i+4].hex(), hp=pool[i+0x27])
                for i in range(0, len(pool), 64)
                if pool[i] and pool[i+10] in (8, 0x68)]

    assert driver.byte(0x1fad) == 5 and driver.byte(0x1fae) == 4
    assert driver.byte(0xd1) == 4 and driver.byte(0xd2) == 4
    assert 0xd30 <= driver.word(0x9dd) < 0xd68
    assert not encounter(), 'Snapshot already contains the encounter'
    assert driver.byte(0x9da) < 0x1c
    if rescued:
        driver.write(0x1fd6, b'\x80\x80\x80')
    else:
        assert driver.read(0x1fd6, 3) == b'\0\0\0'
    samples = []
    for frame in range(10, 241, 10):
        driver.byte(0x9ff, 32)
        driver.step(10, 'right')
        samples.append(dict(frame=frame, x=driver.word(0x9dd),
                            camera=[driver.word(0x1e5d), driver.word(0x1e60)],
                            control=driver.byte(0x9da), actors=encounter()))
    driver.command('screenshot ' + label + '.bmp')
    last = samples[-1]
    passed = (last['camera'] == [0xe00, 0x110]
              and last['control'] >= 0x1c
              and len(last['actors']) == 1
              and last['actors'][0]['id'] == 0x68)
    result = dict(passed=passed, rescued=rescued, samples=samples,
                  scope='Native door/camera handoff and live Zero intro; fight and aftermath are separate checks',
                  assists=['Current-build pre-door snapshot; player health and right input',
                           'Earlier collection eligibility supplied before allocation' if rescued else 'No collection assist'])
    (profile / (label + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    assert passed, last
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--rescued', action='store_true')
    parser.add_argument('--framework', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'snesrecomp')
    args = parser.parse_args()
    sys.path.insert(0, str(args.framework / 'tools'))
    from sneslib.client import DebugClient
    from sneslib.route import FrameDriver
    driver = FrameDriver(DebugClient(args.port, timeout=20), args.profile)
    try:
        print(json.dumps(run_case(driver, args.profile, args.state, args.rescued)))
    finally:
        driver.close()


if __name__ == '__main__':
    main()
