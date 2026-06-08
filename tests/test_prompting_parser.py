"""Action parser robustness regressions."""

from __future__ import annotations

from aces.models import NoOpAction, TransferTokensAction
from aces.prompting import parse_action_response


def test_parser_skips_bad_item_and_keeps_good_actions():
    actions = parse_action_response(
        "eng_kevin",
        """
        draft:
        [not json]
        [
          {"action": "transfer_tokens", "recipient_id": "eng_julia",
           "amount": "$10", "note": "bad amount"},
          {"action": "transfer_tokens", "recipient_id": "eng_julia",
           "amount": 10, "note": "ok"},
          {"action": "noop", "reason": "done"}
        ]
        trailing [text]
        """,
    )
    assert len(actions) == 2
    assert isinstance(actions[0], TransferTokensAction)
    assert actions[0].amount == 10
    assert isinstance(actions[1], NoOpAction)
