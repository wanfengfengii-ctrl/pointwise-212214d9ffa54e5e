from dataclasses import dataclass

from release.editions import freeze_edition
from routing.enrollment import register_enabled_seats
from routing.shows import ApiError, bind_show, control_write
from script.cues import Cue
from script.proofs import get_passed_revision


@dataclass(frozen=True)
class PublicationReceipt:
    show_id: str
    edition_id: str
    draft_id: str
    revision: int
    seats: tuple[str, ...]
    cues: tuple[Cue, ...]


def publish(db, draft_id, revision, show_id, seats):
    with control_write(db):
        if db.execute('SELECT 1 FROM shows WHERE show_id = ?', (show_id,)).fetchone():
            raise ApiError(409, 'show_already_bound')
        passed = get_passed_revision(db, draft_id, revision)
        if passed is None:
            raise ApiError(409, 'revision_not_proved')
        edition = freeze_edition(db, 'edition:' + show_id, passed)
        bind_show(db, show_id, edition.edition_id)
        register_enabled_seats(db, show_id, seats)
        return PublicationReceipt(show_id, edition.edition_id, draft_id, revision, tuple(seats), edition.cues)
