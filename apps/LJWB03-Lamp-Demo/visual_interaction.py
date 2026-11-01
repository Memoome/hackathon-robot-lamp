"""One Water per sedentary episode; never replay stale or blocked events."""
import time

class SedentaryTrigger:
    def __init__(self):
        self.fired = False
        self.last_update = None

    def update(self, snapshot, ready, now=None):
        now = time.time() if now is None else now
        p = snapshot.get('presence') or {}
        updated = p.get('updated')
        if not snapshot.get('active') or not isinstance(updated, (int, float)):
            return False
        if not 0 <= now - updated <= 3 or updated == self.last_update:
            return False
        self.last_update = updated
        states = p.get('states') or {}
        # Only the board's rest/reset starts a new episode, not brief occlusion.
        if p.get('sit_s') == 0 and states.get('sedentary') == 'ok':
            self.fired = False
        eligible = (p.get('present') is True and p.get('stable') is True
                    and states.get('away') is False and states.get('standing') is False
                    and states.get('sedentary') == 'alert' and p.get('sit_s', 0) >= 10)
        if not eligible or self.fired:
            return False
        self.fired = True  # Busy/released events are consumed, never queued for later.
        return bool(ready)


class HeadDownTrigger:
    """Require fresh consecutive head-down observations spanning five seconds."""
    def __init__(self):
        self.since = None
        self.last_update = None
        self.fired = False

    def update(self, snapshot, ready, now=None):
        now = time.time() if now is None else now
        pose = snapshot.get('pc_pose') or {}
        updated = pose.get('updated')
        if (not snapshot.get('active') or not isinstance(updated, (int, float))
                or not 0 <= now - updated <= 3):
            self.since = None
            return False
        if updated == self.last_update:
            return False
        if self.last_update is not None and (updated < self.last_update or updated-self.last_update > 4):
            self.since = None
        self.last_update = updated
        verdict = pose.get('posture') or {}
        level = (verdict.get('levels') or {}).get('head_down', 'unknown')
        if not verdict.get('calibrated') or verdict.get('calibrating') or level == 'unknown':
            self.since = None
            return False
        if level == 'ok':
            self.since = None
            self.fired = False
            return False
        if level not in ('watch', 'alert'):
            self.since = None
            return False
        # Movement/preview must not accumulate evidence for a later action.
        if not ready:
            self.since = None
            return False
        if self.since is None:
            self.since = updated
        if self.fired or updated-self.since < 5:
            return False
        self.fired = True
        return True


class VisualActionTrigger:
    def __init__(self):
        self.sedentary = SedentaryTrigger()
        self.head_down = HeadDownTrigger()

    def update(self, snapshot, ready, now=None):
        stretch = self.head_down.update(snapshot, ready, now)
        water = self.sedentary.update(snapshot, ready and not stretch, now)
        return 'Stretch' if stretch else 'Water' if water else None


class PresenceLight:
    """Warm breathing when a fresh person is visible; black in standby."""
    def __init__(self):
        self.started = None

    def rgb(self, present, now):
        import math
        if not present:
            self.started = None
            return [0, 0, 0]
        if self.started is None:
            self.started = now
        # Immediately visible, then a smooth four-second cycle (5–25%).
        level = .05 + .20 * (1-math.cos(2*math.pi*(now-self.started)/4))/2
        return [round(channel*level) for channel in (255, 213, 154)]


def visible_person(snapshot, now=None):
    now = time.time() if now is None else now
    p = snapshot.get('presence') or {}
    updated = p.get('updated')
    return bool(snapshot.get('active') and isinstance(updated, (int, float))
                and 0 <= now-updated <= 3 and p.get('present') is True)
