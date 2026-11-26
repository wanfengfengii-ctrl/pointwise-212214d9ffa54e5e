from dataclasses import dataclass


@dataclass(frozen=True)
class CueInterval:
    cue_id: str
    channel: str
    position: int
    start: int
    end: int


def build_intervals(cues):
    return [
        CueInterval(cue.cue_id, cue.channel, cue.position, cue.start, cue.start + cue.duration)
        for cue in cues
    ]


def find_conflicts(intervals):
    conflicts = []
    active = []
    channel = None
    scan = sorted(intervals, key=lambda interval: (interval.channel, interval.start, interval.position))
    for current in scan:
        if current.channel != channel:
            channel = current.channel
            active.clear()
        active = [prior for prior in active if prior.end > current.start]
        for prior in active:
            conflicts.append({'channel': channel, 'first': prior.cue_id, 'second': current.cue_id})
        active.append(current)
    return conflicts
