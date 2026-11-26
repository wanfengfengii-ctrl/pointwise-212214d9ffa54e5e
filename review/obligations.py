from dataclasses import dataclass

from release.editions import get_edition
from release.provenance import CueOrigin, make_cue_origin
from release.status import list_show_amendment_status
from routing.enrollment import list_enabled_seats


@dataclass(frozen=True)
class ExpectedPlay:
    kind: str
    text: str
    amendment_id: str | None = None
    seq: int | None = None
    token: str | None = None

    def matches(self, entry):
        return (
            (entry.kind, entry.text, entry.amendment_id) == (self.kind, self.text, self.amendment_id)
            and (self.seq is None or entry.seq == self.seq)
            and (self.token is None or entry.token == self.token)
        )


@dataclass(frozen=True)
class Obligation:
    seat: str
    origin: CueOrigin
    expected: tuple[ExpectedPlay, ...] | None
    amendment_id: str | None = None


def build_obligations(db, show):
    edition = get_edition(db, show.edition_id)
    orders = {order['origin']['cue_id']: order for order in list_show_amendment_status(db, show.show_id)}
    obligations = []
    for seat in list_enabled_seats(db, show.show_id):
        for cue in edition.cues:
            origin = make_cue_origin(edition, cue)
            order = orders.get(cue.cue_id)
            if order is None:
                obligations.append(Obligation(seat, origin, (ExpectedPlay('original', cue.text),)))
                continue

            amendment_id = order['amendment_id']
            state = order['seats'][seat]
            if state['status'] == 'pending':
                expected = None
            elif state['status'] == 'replacement_played':
                expected = (ExpectedPlay(
                    'replacement', order['corrected_text'], amendment_id, state['amendment_seq'], state['play_token'],
                ),)
            else:
                expected = (
                    ExpectedPlay('original', cue.text, seq=state['original_seq']),
                    ExpectedPlay('erratum', order['erratum_text'], amendment_id, state['amendment_seq'], state['play_token']),
                )
            obligations.append(Obligation(seat, origin, expected, amendment_id))
    return obligations
