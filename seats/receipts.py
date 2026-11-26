from dataclasses import dataclass

from seats.playback_history import PlaybackEntry, find_playback


@dataclass(frozen=True)
class PlayReceipt:
    request_id: str
    playback: PlaybackEntry


def find_play_receipt(db, request_id=None, *, token=None):
    if token is None:
        row = db.execute('SELECT request_id, token FROM play_receipts WHERE request_id = ?', (request_id,)).fetchone()
    else:
        row = db.execute('SELECT request_id, token FROM play_receipts WHERE token = ?', (token,)).fetchone()
    if row is None:
        return None
    playback = find_playback(db, row['token'])
    if playback is None:
        raise RuntimeError('play receipt has no playback')
    return PlayReceipt(row['request_id'], playback)


def save_play_receipt(db, request_id, playback):
    db.execute('INSERT INTO play_receipts VALUES (?, ?)', (request_id, playback.token))
    return PlayReceipt(request_id, playback)
