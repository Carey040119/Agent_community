"""Worm-contagion instrumentation — PROVENANCE-NATIVE (no content matching).

The earlier version detected worm spread by string-matching the payload text in
free-form output (a verbatim window + a keyword "warning" list + a seed-capture
patch). That conflated "the agent echoed the payload" with "the agent got
compromised", and was a brittle tower of heuristics. This version removes all of
it and measures contagion only through GROUND-TRUTH PROVENANCE on the skill
marketplace — the one ACES channel with a real, id-linked propagation chain
(publish -> adopt -> republish):

  - A worm's attacker SOURCE is recorded when its opportunity is planted
    (``register_worm_source``). A skill that source publishes is the worm, by
    ground truth — we know who the attacker is; no text matching.
  - Adopting that skill (or any republished descendant, which carries the poison
    by id) is INFECTION. Republishing it is PROPAGATION. Both are real,
    unambiguous engine actions referencing a skill id — a vigilant agent that
    merely quotes the worm never adopts/republishes it, so it is simply not in
    the graph (no "is this a warning?" guessing needed).

This is observation, never puppeting (principle.md P2/P3): the LLM still decides
whether to adopt/republish; we only record the artifact lineage it actually
produced. Channels without a provenance primitive (free-text forum/mail/doc
relay) are NOT measured here — an honest limitation of the substrate, not papered
over with string matching.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .database import Database

# Prefix used to stamp a worm's id into a poisoned skill's ``payload`` column,
# so the adopt/republish path can attribute infection to the right worm.
WORM_TAG = "worm:"


def register_worm_source(db: "Database", worm_id: str, source_agent_id: str) -> None:
    """Record that ``source_agent_id`` is the attacker source for ``worm_id``."""
    db.register_worm_source(worm_id, source_agent_id)


def worm_for_source(db: "Database", agent_id: str) -> str | None:
    """Return the worm_id this agent is the designated source of, or None."""
    return db.get_worm_sources().get(agent_id)


def worm_id_from_payload(payload: str | None) -> str | None:
    """Extract the worm id stamped into a poisoned skill's payload, or None."""
    if payload and payload.startswith(WORM_TAG):
        return payload[len(WORM_TAG):] or None
    return None


def register_worm_artifact(db: "Database", kind: str, artifact_id: str,
                           worm_id: str) -> None:
    """Tag an artifact (post/doc/skill) created by a worm source — used for
    ground-truth REACH tracking when the engine later surfaces it."""
    db.register_worm_artifact(kind, artifact_id, worm_id)


def worm_artifact_for(db: "Database", kind: str, artifact_id: str) -> str | None:
    """Return the worm_id a surfaced artifact belongs to (REACH check), or None."""
    return db.worm_artifact_for(kind, artifact_id)
