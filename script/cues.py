from dataclasses import dataclass


@dataclass(frozen=True)
class Cue:
    cue_id: str
    channel: str
    start: int
    duration: int
    text: str
    position: int


class CueFieldError(ValueError):
    def __init__(self, issues):
        super().__init__('invalid cues')
        self.issues = issues


def valid_text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def parse_cues(raw):
    if not isinstance(raw, list) or not raw:
        raise CueFieldError([{'field': 'cues', 'code': 'nonempty_list_required'}])

    issues = []
    cues = []
    seen = set()
    for position, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            issues.append({'position': position, 'field': 'cue', 'code': 'object_required'})
            continue

        previous_count = len(issues)
        for field in ('cue_id', 'channel', 'text'):
            if not valid_text(item.get(field)):
                issues.append({'position': position, 'field': field, 'code': 'text_required'})
        for field, minimum in (('start', 0), ('duration', 1)):
            value = item.get(field)
            if type(value) is not int or value < minimum:
                issues.append({'position': position, 'field': field, 'code': 'invalid_beat'})

        cue_id = item.get('cue_id')
        if valid_text(cue_id):
            if cue_id in seen:
                issues.append({'position': position, 'field': 'cue_id', 'code': 'duplicate'})
            seen.add(cue_id)

        if len(issues) == previous_count:
            cues.append(Cue(cue_id, item['channel'], item['start'], item['duration'], item['text'], position))

    if issues:
        raise CueFieldError(issues)
    return tuple(cues)
