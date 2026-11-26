import json
from dataclasses import asdict, dataclass

from release.provenance import CueOrigin
from routing.shows import ApiError


@dataclass(frozen=True)
class PlaybackCommand:
    token: str
    show_id: str
    seat: str
    origin: CueOrigin
    text: str
    kind: str
    amendment_id: str | None = None


def put_command(db, command):
    prior = get_command(db, command.token)
    if prior is not None:
        if prior != command:
            raise ApiError(409, 'token_mismatch')
        return prior
    db.execute('INSERT INTO commands (token, body) VALUES (?, ?)', (command.token, json.dumps(asdict(command))))
    return command


def get_command(db, token):
    row = db.execute('SELECT body FROM commands WHERE token = ?', (token,)).fetchone()
    if row is None:
        return None
    body = json.loads(row[0])
    body['origin'] = CueOrigin(**body['origin'])
    return PlaybackCommand(**body)


def check_playable(db, command):
    consumed = db.execute('SELECT consumed FROM commands WHERE token = ?', (command.token,)).fetchone()[0]
    if consumed:
        raise ApiError(409, 'command_already_played')


def has_amendment_command(db, show_id, cue_id):
    for (body,) in db.execute('SELECT body FROM commands'):
        command = json.loads(body)
        origin = command.get('origin') or {}
        if (
            command.get('show_id') == show_id
            and origin.get('cue_id') == cue_id
            and command.get('amendment_id') is not None
        ):
            return True
    return False


def mark_consumed(db, token):
    db.execute('UPDATE commands SET consumed = 1 WHERE token = ?', (token,))
