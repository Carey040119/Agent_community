"""Moltbook integration — external agent social network as ExtNet service.

Moltbook is a Reddit-style social network exclusively for AI agents.
In the ACES model it serves as the primary ExtNet surface:

- Agents in roles with ExtNet access (support, security) can read the
  feed, post updates, and comment on threads.
- External attacks can originate from Moltbook content: phishing posts,
  poisoned policy "advice", credential-harvesting comments.
- Agent social behaviour on Moltbook (posting frequency, what they
  share, who they follow) is logged as events and contributes to
  security metrics.

The service works in two modes:

- **live** — calls the real Moltbook REST API at moltbook.com/api/v1.
- **simulated** — stores posts/comments in the local SQLite DB so the
  full experiment can run without network access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import contagion
from .database import Database
from .models import (
    AgentState, Event, EventType, Zone, _now, _uid,
)
from .network import AccessControl

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data objects
# ---------------------------------------------------------------------------

@dataclass
class MoltbookPost:
    id: str = ""
    submolt: str = ""
    title: str = ""
    body: str = ""
    author: str = ""
    upvotes: int = 0
    comment_count: int = 0
    is_attack: bool = False
    attack_payload: str | None = None
    created_at: str = field(default_factory=_now)
    # One-tick delivery (principle.md §2.5): the day/tick the post was
    # created. A reader other than the author sees it only on a tick
    # strictly later than this — same gate the mail/delegation channels
    # use, so forum contagion propagates at the same observable speed.
    sent_day: int = 0
    sent_tick: int = 0


@dataclass
class MoltbookComment:
    id: str = ""
    post_id: str = ""
    body: str = ""
    author: str = ""
    is_attack: bool = False
    created_at: str = field(default_factory=_now)
    # One-tick delivery (principle.md §2.5), as for posts above.
    sent_day: int = 0
    sent_tick: int = 0


# ---------------------------------------------------------------------------
# Moltbook service
# ---------------------------------------------------------------------------

class MoltbookService:
    """Gateway to the Moltbook agent social network."""

    def __init__(self, db: Database, acl: AccessControl, *,
                 mode: str = "simulated",
                 api_key: str = "",
                 base_url: str = "http://moltbook:3000/api/v1",
                 default_submolt: str = "enterprise"):
        self.db = db
        self.acl = acl
        self.mode = mode
        self.api_key = api_key
        self.base_url = base_url
        self.default_submolt = default_submolt
        self._init_sim_tables()

    def _init_sim_tables(self) -> None:
        """Create simulated Moltbook tables if they don't exist."""
        self.db.conn.executescript("""
            CREATE TABLE IF NOT EXISTS moltbook_posts (
                id TEXT PRIMARY KEY,
                submolt TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                author TEXT NOT NULL,
                upvotes INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                is_attack INTEGER DEFAULT 0,
                attack_payload TEXT,
                created_at TEXT NOT NULL,
                sent_day INTEGER NOT NULL DEFAULT 0,
                sent_tick INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS moltbook_comments (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                body TEXT NOT NULL,
                author TEXT NOT NULL,
                is_attack INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                sent_day INTEGER NOT NULL DEFAULT 0,
                sent_tick INTEGER NOT NULL DEFAULT 0
            );
        """)
        # Back-compat: a DB created before the one-tick gate landed has
        # the tables but not the delivery columns.  ``CREATE TABLE IF NOT
        # EXISTS`` will not add them, so patch them in idempotently.
        for table in ("moltbook_posts", "moltbook_comments"):
            cols = {r["name"] for r in self.db.conn.execute(
                f"PRAGMA table_info({table})").fetchall()}
            for col in ("sent_day", "sent_tick"):
                if col not in cols:
                    self.db.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN "
                        f"{col} INTEGER NOT NULL DEFAULT 0")
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # Read feed
    # ------------------------------------------------------------------

    def read_feed(self, agent: AgentState, *,
                  submolt: str | None = None,
                  limit: int = 10,
                  before_day: int | None = None,
                  before_tick: int | None = None,
                  log_read: bool = True,
                  sim_day: int = 0, sim_tick: int = 0) -> list[MoltbookPost]:
        """Read posts from Moltbook. ACL-gated to ExtNet access.

        When ``before_day``/``before_tick`` are supplied, the simulated
        feed obeys the one-tick delivery gate (principle.md §2.5): a post
        is visible to a *reader other than its author* only on a tick
        strictly later than the one it was created in.  The author always
        sees their own post immediately (self-effect).  Omitting the
        params (e.g. unit tests) disables the gate, mirroring
        ``Database.get_unread_messages``.

        ``log_read`` controls whether a read event is appended.  The
        explicit ``read_moltbook_feed`` action logs; the passive
        observation-builder surfacing does not, so building an
        observation never pollutes the event log / security view.
        """
        check = self.acl.check_zone_access(agent, "extnet")
        if not check.allowed:
            log.info("moltbook read blocked: agent %s (%s)", agent.id, check.reason)
            return []

        if self.mode == "live":
            posts = self._api_read_feed(submolt or self.default_submolt, limit)
        else:
            posts = self._sim_read_feed(
                submolt or self.default_submolt, limit,
                reader_id=agent.id,
                before_day=before_day, before_tick=before_tick)

        if log_read:
            self.db.append_event(Event(
                event_type=EventType.MAIL_READ,  # reuse for external reads
                agent_id=agent.id, sim_day=sim_day, sim_tick=sim_tick,
                zone=Zone.EXTNET,
                payload={"service": "moltbook", "action": "read_feed",
                         "submolt": submolt, "post_count": len(posts)},
            ))
        return posts

    # ------------------------------------------------------------------
    # Create post
    # ------------------------------------------------------------------

    def create_post(self, agent: AgentState, submolt: str,
                    title: str, body: str, *,
                    sim_day: int = 0, sim_tick: int = 0) -> MoltbookPost | None:
        check = self.acl.check_zone_access(agent, "extnet")
        if not check.allowed:
            return None

        if self.mode == "live":
            post = self._api_create_post(agent.id, submolt, title, body)
        else:
            post = MoltbookPost(
                id=_uid(), submolt=submolt, title=title,
                body=body, author=agent.id,
                sent_day=sim_day, sent_tick=sim_tick,
            )
            self._sim_insert_post(post)

        if post:
            self.db.append_event(Event(
                event_type=EventType.MOLTBOOK_POST_CREATED,
                agent_id=agent.id, sim_day=sim_day, sim_tick=sim_tick,
                zone=Zone.EXTNET,
                payload={"service": "moltbook", "action": "create_post",
                         "post_id": post.id, "submolt": submolt},
            ))
            # Ground-truth worm tagging: a post by a worm source is the worm (by
            # identity); tag it for REACH tracking when surfaced in feeds.
            wid = contagion.worm_for_source(self.db, agent.id)
            if wid:
                contagion.register_worm_artifact(self.db, "post", post.id, wid)
        return post

    # ------------------------------------------------------------------
    # Comment
    # ------------------------------------------------------------------

    def add_comment(self, agent: AgentState, post_id: str, body: str, *,
                    sim_day: int = 0, sim_tick: int = 0) -> MoltbookComment | None:
        check = self.acl.check_zone_access(agent, "extnet")
        if not check.allowed:
            return None

        if self.mode == "live":
            comment = self._api_add_comment(agent.id, post_id, body)
        else:
            comment = MoltbookComment(
                id=_uid(), post_id=post_id, body=body, author=agent.id,
                sent_day=sim_day, sent_tick=sim_tick,
            )
            self._sim_insert_comment(comment)

        if comment:
            self.db.append_event(Event(
                event_type=EventType.MOLTBOOK_COMMENT_CREATED,
                agent_id=agent.id, sim_day=sim_day, sim_tick=sim_tick,
                zone=Zone.EXTNET,
                payload={"service": "moltbook", "action": "comment",
                         "post_id": post_id},
            ))
        return comment

    # ------------------------------------------------------------------
    # Attack injection via Moltbook
    # ------------------------------------------------------------------

    def inject_attack_post(self, submolt: str, title: str, body: str,
                           attack_payload: str, *,
                           sim_day: int = 0, sim_tick: int = 0) -> MoltbookPost:
        """Plant a malicious post for agents to discover on their feed.

        Stamped with the injection (day, tick) so it obeys the same
        one-tick delivery gate as agent-authored posts: planted at (d,t),
        discoverable by a reader from (d, t+1) onward.
        """
        post = MoltbookPost(
            id=_uid(), submolt=submolt, title=title, body=body,
            author="external_attacker", is_attack=True,
            attack_payload=attack_payload,
            sent_day=sim_day, sent_tick=sim_tick,
        )
        self._sim_insert_post(post)
        self.db.append_event(Event(
            event_type=EventType.ATTACK_INJECTED,
            sim_day=sim_day, sim_tick=sim_tick, zone=Zone.EXTNET,
            payload={"service": "moltbook", "post_id": post.id,
                     "attack_payload": attack_payload},
        ))
        log.info("moltbook attack post injected: %s", post.id)
        return post

    def inject_attack_comment(self, post_id: str, body: str,
                              attack_payload: str | None = None, *,
                              sim_day: int = 0, sim_tick: int = 0) -> MoltbookComment:
        """Plant a malicious comment on an existing post, stamped with the
        injection tick so it obeys the one-tick delivery gate."""
        comment = MoltbookComment(
            id=_uid(), post_id=post_id, body=body,
            author="external_attacker", is_attack=True,
            sent_day=sim_day, sent_tick=sim_tick,
        )
        self._sim_insert_comment(comment)
        self.db.append_event(Event(
            event_type=EventType.ATTACK_INJECTED,
            sim_day=sim_day, sim_tick=sim_tick, zone=Zone.EXTNET,
            payload={"service": "moltbook", "post_id": post_id,
                     "comment_id": comment.id,
                     "attack_payload": attack_payload},
        ))
        log.info("moltbook attack comment injected: %s on %s",
                 comment.id, post_id)
        return comment

    # ------------------------------------------------------------------
    # Simulated storage
    # ------------------------------------------------------------------

    def _sim_insert_post(self, p: MoltbookPost) -> None:
        self.db.conn.execute(
            "INSERT INTO moltbook_posts "
            "(id, submolt, title, body, author, upvotes, comment_count, "
            "is_attack, attack_payload, created_at, sent_day, sent_tick) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.submolt, p.title, p.body, p.author,
             p.upvotes, p.comment_count, int(p.is_attack),
             p.attack_payload, p.created_at, p.sent_day, p.sent_tick),
        )
        self.db.conn.commit()

    def _sim_insert_comment(self, c: MoltbookComment) -> None:
        self.db.conn.execute(
            "INSERT INTO moltbook_comments "
            "(id, post_id, body, author, is_attack, created_at, "
            "sent_day, sent_tick) VALUES (?,?,?,?,?,?,?,?)",
            (c.id, c.post_id, c.body, c.author, int(c.is_attack),
             c.created_at, c.sent_day, c.sent_tick),
        )
        self.db.conn.commit()

    @staticmethod
    def _delivered(r, reader_id: str | None,
                   before_day: int | None, before_tick: int | None) -> bool:
        """One-tick delivery predicate, mirroring the message/delegation
        gate.  The author sees their own row immediately; everyone else
        sees it only on a tick strictly later than the one it was sent in.
        Rows from a pre-gate DB (no sent_day/sent_tick) default to 0 and
        therefore stay visible (back-compat)."""
        if before_day is None or before_tick is None:
            return True
        if reader_id is not None and r["author"] == reader_id:
            return True
        sd = r["sent_day"] if "sent_day" in r.keys() else 0
        st = r["sent_tick"] if "sent_tick" in r.keys() else 0
        return sd < before_day or (sd == before_day and st < before_tick)

    def _row_to_post(self, r) -> MoltbookPost:
        return MoltbookPost(
            id=r["id"], submolt=r["submolt"], title=r["title"],
            body=r["body"], author=r["author"], upvotes=r["upvotes"],
            comment_count=r["comment_count"],
            is_attack=bool(r["is_attack"]),
            attack_payload=r["attack_payload"],
            created_at=r["created_at"],
            sent_day=r["sent_day"] if "sent_day" in r.keys() else 0,
            sent_tick=r["sent_tick"] if "sent_tick" in r.keys() else 0,
        )

    def _row_to_comment(self, r) -> MoltbookComment:
        return MoltbookComment(
            id=r["id"], post_id=r["post_id"], body=r["body"],
            author=r["author"], is_attack=bool(r["is_attack"]),
            created_at=r["created_at"],
            sent_day=r["sent_day"] if "sent_day" in r.keys() else 0,
            sent_tick=r["sent_tick"] if "sent_tick" in r.keys() else 0,
        )

    def _sim_read_feed(self, submolt: str, limit: int, *,
                       reader_id: str | None = None,
                       before_day: int | None = None,
                       before_tick: int | None = None) -> list[MoltbookPost]:
        # Over-fetch then gate in Python so the one-tick predicate stays
        # in one place (``_delivered``) and matches the comment gate.
        rows = self.db.conn.execute(
            "SELECT * FROM moltbook_posts WHERE submolt=? "
            "ORDER BY created_at DESC LIMIT ?",
            (submolt, max(limit * 4, limit)),
        ).fetchall()
        out: list[MoltbookPost] = []
        for r in rows:
            if self._delivered(r, reader_id, before_day, before_tick):
                out.append(self._row_to_post(r))
            if len(out) >= limit:
                break
        return out

    def read_comments(self, post_id: str, *,
                      reader_id: str | None = None,
                      before_day: int | None = None,
                      before_tick: int | None = None,
                      limit: int = 5) -> list[MoltbookComment]:
        """Return delivered comments on *post_id*, newest first, gated by
        the same one-tick predicate as the feed (simulated mode only)."""
        if self.mode == "live":
            return []
        rows = self.db.conn.execute(
            "SELECT * FROM moltbook_comments WHERE post_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (post_id, max(limit * 4, limit)),
        ).fetchall()
        out: list[MoltbookComment] = []
        for r in rows:
            if self._delivered(r, reader_id, before_day, before_tick):
                out.append(self._row_to_comment(r))
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------------
    # Live API calls (requires httpx)
    # ------------------------------------------------------------------

    def _api_read_feed(self, submolt: str, limit: int) -> list[MoltbookPost]:
        try:
            import httpx
            resp = httpx.get(
                f"{self.base_url}/feed",
                params={"sort": "hot", "limit": limit},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                MoltbookPost(
                    id=p.get("_id", ""),
                    submolt=p.get("submolt", {}).get("name", submolt),
                    title=p.get("title", ""),
                    body=p.get("body", ""),
                    author=p.get("agent", {}).get("name", "unknown"),
                    upvotes=p.get("upvotes", 0),
                    comment_count=p.get("commentCount", 0),
                )
                for p in data.get("posts", data if isinstance(data, list) else [])
            ]
        except Exception as e:
            log.error("Moltbook API read_feed failed: %s", e)
            return []

    def _api_create_post(self, agent_id: str, submolt: str,
                         title: str, body: str) -> MoltbookPost | None:
        try:
            import httpx
            resp = httpx.post(
                f"{self.base_url}/posts",
                json={"submolt": submolt, "title": title, "body": body},
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            p = resp.json()
            return MoltbookPost(
                id=p.get("_id", ""), submolt=submolt,
                title=title, body=body, author=agent_id,
            )
        except Exception as e:
            log.error("Moltbook API create_post failed: %s", e)
            return None

    def _api_add_comment(self, agent_id: str, post_id: str,
                         body: str) -> MoltbookComment | None:
        try:
            import httpx
            resp = httpx.post(
                f"{self.base_url}/posts/{post_id}/comments",
                json={"body": body},
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            c = resp.json()
            return MoltbookComment(
                id=c.get("_id", ""), post_id=post_id,
                body=body, author=agent_id,
            )
        except Exception as e:
            log.error("Moltbook API add_comment failed: %s", e)
            return None
