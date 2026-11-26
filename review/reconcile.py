from collections import defaultdict
from dataclasses import dataclass

from review.obligations import build_obligations
from review.receipts import collect_receipts
from seats.playback_history import PlaybackEntry


@dataclass(frozen=True)
class Readiness:
    pending: list[dict]
    playback: dict[str, list[PlaybackEntry]]


def reconcile(db, store_for, show):
    obligations = build_obligations(db, show)
    seats = tuple(dict.fromkeys(item.seat for item in obligations))
    evidence = collect_receipts(store_for, show.show_id, seats)
    by_cue = defaultdict(list)
    for seat, facts in evidence.items():
        for entry in facts.playback:
            by_cue[seat, entry.origin.cue_id].append(entry)

    pending = []
    for item in obligations:
        entries = by_cue.pop((item.seat, item.origin.cue_id), [])
        if item.expected is None:
            reason = 'amendment_pending'
        elif len(entries) != len(item.expected):
            reason = 'missing_playback' if len(entries) < len(item.expected) else 'unexpected_playback'
        elif any(
            entry.seat != item.seat or entry.origin != item.origin
            or entry.token not in evidence[item.seat].confirmed or not expected.matches(entry)
            for entry, expected in zip(entries, item.expected)
        ):
            reason = 'playback_evidence_mismatch'
        else:
            continue
        pending.append({
            'seat': item.seat, 'cue_id': item.origin.cue_id, 'amendment_id': item.amendment_id, 'reason': reason,
        })
    for seat, cue_id in by_cue:
        pending.append({'seat': seat, 'cue_id': cue_id, 'amendment_id': None, 'reason': 'unexpected_playback'})

    if pending:
        return Readiness(pending, {})
    # The evidence lists already have each seat's actual sequence order.
    return Readiness([], {seat: evidence[seat].playback for seat in seats})
