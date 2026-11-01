"""Small reference-pose primitives. Model directions require hardware validation."""
import math
from expressive_routines import geometry, tilt


def build_basic(p, kind):
    home = p['poses'][p['roles']['Rest']].copy()
    _, heading = geometry(p, home)
    down = 1 if math.cos(math.radians(heading)) >= 0 else -1
    base = p.get('base_position', {})
    front = base.get('front', 90)

    def yaw(angle):
        angle = max(0, min(180, angle))
        return round(500 + (180-angle if base.get('reverse', False) else angle)*2000/180)

    def row(name, pulse, pause=0, base_pulse=None):
        result = dict(name=name, pulse=pulse.copy(), seconds=.8, pause=pause,
                      sound=-1, easing='quintic', delays=[0, 0, 0], gesture_speed=300)
        if base_pulse is not None:
            result['base_pulse'] = base_pulse
        return result

    low = tilt(p, home, down*10, home)
    high = tilt(p, home, -down*8, home)
    if kind == 'nod':
        return [row('Reference pose', home), row('Nod down', low, .15),
                row('Lift head', high, .1), row('Return to reference', home)]
    if kind == 'head_down':
        return [row('Reference pose', home), row('Lower head and hold', low)]
    if kind == 'head_up':
        return [row('Reference pose', home), row('Raise head and hold', high)]
    if kind == 'shake':
        # Base direction labels are model-relative, not verified anatomical left/right.
        return [row('Reference pose and front', home, base_pulse=yaw(front)),
                row('Turn to first side', home, .1, yaw(front-12)),
                row('Turn to opposite side', home, .1, yaw(front+12)),
                row('Return to front', home, base_pulse=yaw(front))]
    if kind == 'return_rest':
        return [row('Return to reference and front', home, base_pulse=yaw(front))]
    raise ValueError('Unknown basic action: '+kind)
