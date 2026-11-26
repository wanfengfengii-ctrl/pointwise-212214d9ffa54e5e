from dataclasses import dataclass

from release.editions import get_edition


@dataclass(frozen=True)
class CueOrigin:
    edition_id: str
    draft_id: str
    revision: int
    cue_id: str
    position: int


def make_cue_origin(edition, cue):
    return CueOrigin(edition.edition_id, edition.draft_id, edition.revision, cue.cue_id, cue.position)


def resolve_original_cue(db, edition_id, cue_id):
    edition = get_edition(db, edition_id)
    for cue in edition.cues:
        if cue.cue_id == cue_id:
            return cue, make_cue_origin(edition, cue)
    return None
