"""One-tick cross-agent delivery invariant (principle.md §2.5).

A message sent at tick (d, t) must become visible to the recipient only on a
tick strictly later than (d, t) — never the same tick. This is the
race-protection invariant: within a tick all agents observe a consistent
snapshot, and effects they produce land next tick. Exercised at the DB layer
with an in-memory database.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aces.database import Database
from aces.models import Message


def _msg(recipient: str, sent_day: int, sent_tick: int) -> Message:
    return Message(
        sender_id="alice", recipient_id=recipient,
        subject="hi", body="payload",
        sent_day=sent_day, sent_tick=sent_tick,
    )


class DeliveryLatencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database(":memory:")

    def test_same_tick_not_delivered(self):
        self.db.insert_message(_msg("bob", sent_day=1, sent_tick=2))
        # Observer at the exact tick it was sent: not yet visible.
        self.assertEqual(self.db.get_unread_messages("bob", 1, 2), [])

    def test_next_tick_delivered(self):
        self.db.insert_message(_msg("bob", sent_day=1, sent_tick=2))
        got = self.db.get_unread_messages("bob", 1, 3)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].body, "payload")

    def test_next_day_delivered(self):
        self.db.insert_message(_msg("bob", sent_day=1, sent_tick=5))
        self.assertEqual(len(self.db.get_unread_messages("bob", 2, 0)), 1)

    def test_future_message_not_visible(self):
        # A message sent "later" than the observer's tick stays hidden.
        self.db.insert_message(_msg("bob", sent_day=3, sent_tick=0))
        self.assertEqual(self.db.get_unread_messages("bob", 1, 9), [])

    def test_ungated_call_is_backward_compatible(self):
        # Direct call with no tick gate returns all unread (legacy API used
        # by tests that assert content, not timing).
        self.db.insert_message(_msg("bob", sent_day=9, sent_tick=9))
        self.assertEqual(len(self.db.get_unread_messages("bob")), 1)

    def test_sent_tick_round_trips(self):
        self.db.insert_message(_msg("bob", sent_day=4, sent_tick=7))
        got = self.db.get_unread_messages("bob")[0]
        self.assertEqual((got.sent_day, got.sent_tick), (4, 7))


class DelegationLatencyTest(unittest.TestCase):
    """Same one-tick invariant for delegation requests."""

    def setUp(self) -> None:
        from aces.models import AgentRole, AgentState, Zone
        self.db = Database(":memory:")
        # Delegations FK to agents(id), so the two parties must exist.
        self.db.insert_agent(AgentState(id="req", name="req", role=AgentRole.MANAGER, zone=Zone.CORPNET))
        self.db.insert_agent(AgentState(id="dlg", name="dlg", role=AgentRole.ENGINEER, zone=Zone.CORPNET))

    def _deleg(self, sent_day: int, sent_tick: int):
        from aces.models import Delegation, DelegationType
        return Delegation(
            requester_id="req", delegate_id="dlg",
            delegation_type=DelegationType.TASK, description="do a thing",
            sent_day=sent_day, sent_tick=sent_tick,
        )

    def test_same_tick_not_delivered(self):
        self.db.insert_delegation(self._deleg(2, 3))
        self.assertEqual(self.db.get_pending_delegations("dlg", 2, 3), [])

    def test_next_tick_delivered(self):
        self.db.insert_delegation(self._deleg(2, 3))
        self.assertEqual(len(self.db.get_pending_delegations("dlg", 2, 4)), 1)

    def test_ungated_call_is_backward_compatible(self):
        self.db.insert_delegation(self._deleg(2, 3))
        self.assertEqual(len(self.db.get_pending_delegations("dlg")), 1)


if __name__ == "__main__":
    unittest.main()
