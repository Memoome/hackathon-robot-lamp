"""Polls the local viewer and logs board PRESENCE changes with host time, for in-person state tests."""
import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

KEYS = ('present', 'stable', 'calibrated')


def snapshot(p):
    st = p['states']
    return (st['away'], st['sedentary'], st['too_close'], st['standing'], p['calibrated'], p['present'])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=8768)
    ap.add_argument('--seconds', type=int, default=900)
    args = ap.parse_args()
    out = Path(__file__).resolve().parents[1] / 'evidence' / ('presence-test-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.jsonl')
    last = None
    start = time.time()
    with out.open('w', encoding='utf-8') as f:
        print(out, flush=True)
        while time.time() - start < args.seconds:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/presence', timeout=2) as r:
                    d = json.load(r)
            except OSError:
                time.sleep(1)
                continue
            p = d.get('presence')
            if p:
                snap = snapshot(p)
                if snap != last or p.get('event'):
                    rec = dict(host_t=round(time.time() - start, 2), seq=p['seq'], t_ms=p['t_ms'], states=p['states'],
                               present=p['present'], calibrated=p['calibrated'], sit_s=p['sit_s'], event=p.get('event'),
                               metrics=p['metrics'], main=p['main'], calib=d.get('calib'))
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    f.flush()
                    last = snap
            time.sleep(0.25)


if __name__ == '__main__':
    main()
