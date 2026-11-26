import json
from dataclasses import dataclass

from release.provenance import CueOrigin
from routing.dispatch import DispatchRecord
from routing.shows import ApiError
from seats.playback_history import append_playback, find_original
from seats.queue import PlaybackCommand, check_playable, get_command, mark_consumed, put_command
from seats.receipts import PlayReceipt, find_play_receipt, save_play_receipt


@dataclass(frozen=True)
class AmendmentInstruction:
    show_id: str
    amendment_id: str
    origin: CueOrigin
    text: str
    kind: str


@dataclass(frozen=True)
class AmendmentAcceptance:
    token: str | None
    receipt: PlayReceipt | None


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
        entry = append_playback(db, command)
        mark_consumed(db, command.token)
        return save_play_receipt(db, request_id, entry)


def accept_seat_instruction(store, instruction):
    with store.transaction() as db:
        if isinstance(instruction, DispatchRecord):
            return put_command(db, _original_command(store, instruction))

        token = json.dumps(['amendment', instruction.show_id, store.seat, instruction.amendment_id], separators=(',', ':'))
        prior = get_command(db, token)
        if prior is not None:
            return AmendmentAcceptance(token, read_play_receipt(db, token))
        if find_original(db, instruction.show_id, instruction.origin.cue_id) is not None:
            return AmendmentAcceptance(None, None)
        put_command(db, PlaybackCommand(
            token, instruction.show_id, store.seat, instruction.origin,
            instruction.text, instruction.kind, instruction.amendment_id,
        ))
        return AmendmentAcceptance(token, None)


def read_play_receipt(db, token):
    return find_play_receipt(db, token=token)
