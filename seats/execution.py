import json
from dataclasses import dataclass

from release.provenance import CueOrigin
from routing.dispatch import DispatchRecord
from routing.shows import ApiError
from seats.playback_history import append_playback, find_original
from seats.queue import PlaybackCommand, check_playable, get_command, has_amendment_command, mark_consumed, put_command
from seats.receipts import PlayReceipt, find_play_receipt, save_play_receipt


@dataclass(frozen=True)
class AmendmentInstruction:
    show_id: str
    amendment_id: str
    origin: CueOrigin
    corrected_text: str
    erratum_text: str


@dataclass(frozen=True)
class AmendmentAcceptance:
    token: str
    kind: str
    receipt: PlayReceipt | None
    original_seq: int | None


def _original_command(store, dispatch):
    if dispatch.seat != store.seat:
        raise ApiError(404, 'unknown_play_token')
    return PlaybackCommand(dispatch.token, dispatch.show_id, dispatch.seat, dispatch.origin, dispatch.text, 'original')


def play(store, show_id, token, request_id, dispatch=None):
    with store.transaction() as db:
        prior = find_play_receipt(db, request_id)
        if prior is not None:
            if (prior.playback.show_id, prior.playback.token) != (show_id, token):
                raise ApiError(409, 'request_mismatch')
            return prior

        # A dispatch may have committed even if its response never reached the seat.
        if dispatch is not None:
            put_command(db, _original_command(store, dispatch))
        command = get_command(db, token)
        if command is None or command.show_id != show_id:
            raise ApiError(404, 'unknown_play_token')
        check_playable(db, command)
        # Once this seat accepted a correction for the cue, any original token
        # loses first-play eligibility, however it was obtained.
        if command.kind == 'original' and has_amendment_command(db, show_id, command.origin.cue_id):
            raise ApiError(409, 'stale_original')
        entry = append_playback(db, command)
        mark_consumed(db, command.token)
        return save_play_receipt(db, request_id, entry)


def accept_seat_instruction(store, instruction):
    with store.transaction() as db:
        if isinstance(instruction, DispatchRecord):
            return put_command(db, _original_command(store, instruction))

        token = json.dumps(['amendment', instruction.show_id, store.seat, instruction.amendment_id], separators=(',', ':'))
        original = find_original(db, instruction.show_id, instruction.origin.cue_id)
        original_seq = original.seq if original is not None else None
        prior = get_command(db, token)
        if prior is not None:
            return AmendmentAcceptance(token, prior.kind, read_play_receipt(db, token), original_seq)
        # A seat that already played the original keeps it and adds an erratum;
        # a seat that has not played it only broadcasts the corrected word.
        kind = 'erratum' if original is not None else 'replacement'
        text = instruction.erratum_text if kind == 'erratum' else instruction.corrected_text
        put_command(db, PlaybackCommand(
            token, instruction.show_id, store.seat, instruction.origin,
            text, kind, instruction.amendment_id,
        ))
        return AmendmentAcceptance(token, kind, None, original_seq)


def read_play_receipt(db, token):
    return find_play_receipt(db, token=token)
