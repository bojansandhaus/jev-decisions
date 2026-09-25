"""A learned-correction store with severity, escapes, and noise retirement.

Design adapted from the lesson model in **psygns/osENV.io**
(https://github.com/psygns/osENV.io), read at revision 0ef07457d4, version 0.3.0.
The upstream design carries these ideas:

  - a lesson is a written rule plus a precise description of the mistake as it is
    about to happen, not a topic or a category;
  - a lesson has a severity, and severity escalates: it starts as advice and
    becomes a hard stop once the same mistake has happened anyway enough times;
  - a lesson that keeps being judged relevant but never catches anything is
    noise, and noise retires;
  - proven lessons move between projects as a pack.

The upstream wording for the escalation rule, quoted for attribution:

  "the same mistake as an existing lesson? Then that lesson is sharpened, and
  escalates to a kick after 2 escapes, instead of a copy piling up."
      -- psygns, osENV.io README.md

  "Lessons that Jev keeps calling relevant but that never catch anything are
  noise: they retire."
      -- psygns, osENV.io learn.go

No code was copied from that project. There is no license file in the upstream
repository, so its source is all rights reserved; only the design was studied.
This module is an independent implementation in Python. It also differs in one
deliberate way: upstream ranks lessons with vector similarity, while this
implementation uses a deterministic lexical score, because the plugin must stay
dependency free and its ranking must be auditable line by line.

Local only. Nothing here contacts a provider.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from .ledger import append as append_ledger
    from .runtime import get_hermes_home
except ImportError:  # Standalone package use.
    from ledger import append as append_ledger
    from runtime import get_hermes_home

# Structural constants, matching the upstream design so escalation behaves the
# same way. They are named rather than inlined because the tests assert them.
REPEAT_MATCH = 0.7          # a new correction at or above this repeats an old lesson
ESCALATE_AT_ESCAPES = 2     # escapes needed to turn advice into a hard stop
RETIRE_AT_SURFACED = 40     # judgements of relevance before noise is retired
CREDIBILITY_SURFACED_DIVISOR = 20

SEVERITIES = ("nudge", "kick")
KINDS = ("lesson", "route")
STATUSES = ("active", "retired")
OWNER_SOURCE = "owner"

# Two floors, because the two jobs have opposite error costs.
#
# SURFACE_FLOOR pre-ranks candidates for a semantic judgement. It is deliberately
# permissive: a false candidate costs one line in a prompt, while a missed
# candidate loses the whole point of the lesson. Lexical overlap cannot see a
# paraphrase, so this is a prefilter, never a verdict. Upstream does the same job
# with vector similarity and still routes the real judgement to Jev.
SURFACE_FLOOR = 0.05
# KICK_FLOOR is the bar for a local hard stop with no provider call. It is set
# high on purpose: at this level the action and the lesson share most of their
# wording, so the match is close to literal. Expect high precision and low
# recall, and use an explicit review when a paraphrase must be caught.
KICK_FLOOR = 0.50

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "to", "of",
    "in", "on", "at", "by", "for", "with", "from", "as", "is", "are", "was",
    "were", "be", "been", "being", "it", "its", "this", "that", "these", "those",
    "you", "your", "we", "our", "they", "their", "i", "me", "my", "not", "no",
    "do", "does", "did", "done", "have", "has", "had", "will", "would", "can",
    "could", "should", "must", "may", "might", "into", "out", "up", "down",
    "when", "which", "who", "what", "how", "why", "there", "here", "all", "any",
    "one", "two", "only", "also", "just", "more", "most", "less", "least",
})
_TOKEN_RE = re.compile(r"[a-z0-9_./:+-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: Any) -> set[str]:
    """Content words, lowercased. Used for deterministic relevance and repeats."""
    return {t for t in _TOKEN_RE.findall(str(text or "").lower()) if t not in _STOPWORDS and len(t) > 1}


def _lexical_overlap(left: Any, right: Any) -> float:
    """Jaccard overlap of content words, 0 to 1.

    Deterministic and line-by-line auditable, which matters more here than
    semantic reach: this decides only whether a lesson is worth surfacing or
    whether a correction repeats an existing lesson. The semantic judgement
    stays with Jev when a review is actually worth a provider call.
    """
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class Lesson:
    """One written rule, with its precision description and its track record."""

    id: str
    text: str
    detect: str
    kind: str = "lesson"
    scope: str = "global"
    to: str = ""
    severity: str = "nudge"
    source: str = "stated"
    evidence: str = ""
    tags: list[str] = field(default_factory=list)
    made: str = ""
    surfaced: int = 0
    catches: int = 0
    escapes: int = 0
    status: str = "active"
    why: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "Lesson":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in row.items() if k in known})

    @property
    def owner(self) -> bool:
        return self.source == OWNER_SOURCE

    def credibility(self) -> float:
        """How much its track record should count, 0 to 1.

        A lesson judged relevant many times without ever catching anything loses
        ranking weight long before it retires.
        """
        proven = self.catches + self.escapes + 1
        return proven / (proven + self.surfaced / CREDIBILITY_SURFACED_DIVISOR)

    def relevance(self, action_text: str, tags: set[str] | None = None) -> float:
        """Deterministic relevance of this lesson to a described action."""
        overlap = _lexical_overlap(action_text, f"{self.text} {self.detect}")
        if not overlap:
            return 0.0
        own, given = set(self.tags), (tags or set())
        tag_boost = 0.15 * (len(own & given) / max(1, len(own | given)))
        return min(1.0, (overlap + tag_boost) * self.credibility())

    def as_pack_row(self) -> dict[str, Any]:
        """Proven lessons carry their track record into another install."""
        return {
            "text": self.text,
            "detect": self.detect,
            "severity": self.severity,
            "catches": self.catches,
            "escapes": self.escapes,
        }


class LessonStore:
    """Local, file backed lesson store. One JSON document plus a sequence file."""

    def __init__(self, root: str | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root
        self._path = ""
        self._seq_path = ""
        self._items: list[Lesson] = []
        self._seq = 0
        self._loaded = False

    # -- storage ---------------------------------------------------------

    def _paths(self) -> tuple[str, str]:
        base = self._root or os.path.join(str(get_hermes_home()), "jev")
        return os.path.join(base, "lessons.json"), os.path.join(base, "lessons-seq.json")

    def _load(self) -> None:
        if self._loaded:
            return
        self._path, self._seq_path = self._paths()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        for attr, path in (("_items", self._path), ("_seq", self._seq_path)):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except (OSError, ValueError):
                continue
            if attr == "_items" and isinstance(raw, list):
                self._items = [Lesson.from_dict(row) for row in raw if isinstance(row, dict)]
            elif attr == "_seq" and isinstance(raw, int):
                self._seq = raw
        self._loaded = True

    def _save(self) -> None:
        """Atomic write, so a crash cannot truncate the store."""
        for path, payload in (
            (self._path, json.dumps([item.as_dict() for item in self._items], ensure_ascii=True, sort_keys=True, indent=1)),
            (self._seq_path, json.dumps(self._seq)),
        ):
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)

    def reset(self, root: str | None = None) -> None:
        with self._lock:
            self._root = root
            self._loaded = False
            self._items = []
            self._seq = 0
            self._load()

    # -- reads -----------------------------------------------------------

    def all(self, include_retired: bool = False) -> list[Lesson]:
        with self._lock:
            self._load()
            return [i for i in self._items if include_retired or i.status == "active"]

    def get(self, lesson_id: str) -> Lesson | None:
        with self._lock:
            self._load()
            for item in self._items:
                if item.id == lesson_id:
                    return item
            return None

    def candidates(self, action_text: str, tags: set[str] | None = None, limit: int = 8, floor: float | None = None) -> list[tuple[Lesson, float]]:
        """Active lessons pre-ranked for a semantic judgement, above a floor.

        This is a shortlist, not an answer. The caller decides which of these
        actually match the action and records that with ``record_surfaced`` and
        ``record_caught``.
        """
        floor = SURFACE_FLOOR if floor is None else floor
        scored = []
        for item in self.all():
            score = item.relevance(action_text, tags)
            if score >= floor:
                scored.append((item, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[: max(1, limit)]

    def local_kicks(self, action_text: str, tags: set[str] | None = None) -> list[tuple[Lesson, float]]:
        """Kick lessons that match closely enough to stop an action locally.

        Local only and provider free. It fires on near literal matches and will
        miss a paraphrase, which is why an explicit review exists.
        """
        return [
            (item, score)
            for item, score in self.candidates(action_text, tags, limit=16, floor=KICK_FLOOR)
            if item.severity == "kick"
        ]

    def stats(self) -> dict[str, Any]:
        items = self.all(include_retired=True)
        active = [i for i in items if i.status == "active"]
        return {
            "total": len(items),
            "active": len(active),
            "retired": len(items) - len(active),
            "owner_rules": len([i for i in items if i.owner]),
            "kicks": len([i for i in active if i.severity == "kick"]),
            "nudges": len([i for i in active if i.severity == "nudge"]),
            "catches": sum(i.catches for i in items),
            "escapes": sum(i.escapes for i in items),
            "surfaced": sum(i.surfaced for i in items),
            "by_source": sorted({i.source for i in items}),
        }

    # -- writes ----------------------------------------------------------

    def add(
        self,
        *,
        text: str,
        detect: str = "",
        severity: str = "nudge",
        source: str = "stated",
        scope: str = "global",
        evidence: str = "",
        tags: list[str] | None = None,
        kind: str = "lesson",
    ) -> dict[str, Any]:
        """Record a correction.

        A correction that repeats an active lesson sharpens that lesson instead of
        adding a near copy, and that repeat is what escalates severity.
        """
        text = str(text or "").strip()
        if not text:
            raise ValueError("a lesson needs text")
        detect = str(detect or "").strip()
        with self._lock:
            self._load()
            repeat = self._match_repeat(text, detect)
            if repeat is not None:
                lesson, score = repeat
                # Each correction call is one occurrence of the mistake. A caller
                # holding several findings that map to the same lesson must
                # deduplicate them before calling, or the lesson escalates early.
                lesson.escapes += 1
                lesson.detect = detect or lesson.detect
                lesson.tags = sorted(set(lesson.tags) | _tokens(f"{text} {detect}"))
                if lesson.escapes >= ESCALATE_AT_ESCAPES and lesson.severity != "kick":
                    lesson.severity = "kick"
                if lesson.scope != "global":
                    lesson.scope = "global"
                lesson.why = f"{lesson.why} | merged {_now()[:16]} (same {score:.2f})".strip()
                self._save()
                append_ledger("lesson", {"action": "merged", "lesson_id": lesson.id, "escapes": lesson.escapes, "severity": lesson.severity})
                return {"lesson": lesson.as_dict(), "how": "merged", "score": round(score, 4)}

            self._seq += 1
            severity = severity if severity in SEVERITIES else "nudge"
            if source == OWNER_SOURCE:
                # An owner rule is a hard stop from the moment it is made.
                severity = "kick"
            item = Lesson(
                id=f"{'R' if kind == 'route' else 'L'}{self._seq}",
                text=text,
                detect=detect,
                kind=kind if kind in KINDS else "lesson",
                scope=scope,
                severity=severity,
                source=source,
                evidence=str(evidence or ""),
                tags=sorted(set(tags or []) | _tokens(f"{text} {detect}")),
                made=_now(),
                why="owner rule: a hard stop from day one, never retired" if source == OWNER_SOURCE else "",
            )
            self._items.append(item)
            self._save()
            append_ledger("lesson", {"action": "added", "lesson_id": item.id, "severity": item.severity, "source": item.source})
            return {"lesson": item.as_dict(), "how": "added"}

    def _match_repeat(self, text: str, detect: str) -> tuple[Lesson, float] | None:
        """The active lesson this correction repeats, if any.

        Similarity only, not the credibility weighted relevance: a repeat is
        about how alike the mistake is, not about the old lesson's record.
        """
        best: Lesson | None = None
        best_score = 0.0
        for item in self._items:
            if item.status != "active" or item.kind != "lesson":
                continue
            score = _lexical_overlap(f"{text} {detect}", f"{item.text} {item.detect}")
            if score >= REPEAT_MATCH and score > best_score:
                best, best_score = item, score
        if best is None:
            return None
        return best, best_score

    def record_surfaced(self, lesson_ids: list[str]) -> dict[str, int]:
        """Count that these lessons were judged relevant to an action.

        Only record this from a real judgement, meaning a local kick match or a
        review that returned which lessons applied. Counting prefilter candidates
        here would inflate the tally and retire good lessons as noise.
        """
        with self._lock:
            self._load()
            touched = {}
            for lesson_id in lesson_ids:
                item = self.get(lesson_id)
                if item is not None:
                    item.surfaced += 1
                    touched[item.id] = item.surfaced
            if touched:
                self._save()
            return touched

    def note_would_kick(self, lesson_id: str, *, tool_name: str = "", score: float = 0.0) -> None:
        """Record that a kick lesson matched while enforcement was off.

        Shadow mode must not change execution, so nothing was caught. This keeps
        the evidence of what enforcement would have done, and it deliberately does
        not touch the catch tally.
        """
        append_ledger("lesson_would_kick", {
            "lesson_id": lesson_id,
            "tool_name": str(tool_name or ""),
            "score": round(float(score), 4),
        })

    def record_caught(self, lesson_ids: list[str]) -> dict[str, int]:
        """Count a mistake caught before it happened."""
        with self._lock:
            self._load()
            touched = {}
            for lesson_id in lesson_ids:
                item = self.get(lesson_id)
                if item is not None:
                    item.catches += 1
                    touched[item.id] = item.catches
            if touched:
                self._save()
                append_ledger("lesson", {"action": "caught", "lesson_ids": sorted(touched)})
            return touched

    def edit(
        self,
        lesson_id: str,
        *,
        severity: str | None = None,
        escapes: int | None = None,
        catches: int | None = None,
        detect: str | None = None,
        text: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Correct a lesson by hand, keeping its record."""
        with self._lock:
            self._load()
            item = self.get(lesson_id)
            if item is None:
                raise ValueError(f"unknown lesson: {lesson_id}")
            if severity is not None:
                item.severity = severity if severity in SEVERITIES else item.severity
            if escapes is not None:
                item.escapes = max(0, int(escapes))
            if catches is not None:
                item.catches = max(0, int(catches))
            if detect is not None:
                item.detect = str(detect).strip()
            if text is not None:
                item.text = str(text).strip()
            if scope is not None:
                item.scope = str(scope)
            item.why = f"{item.why} | edited {_now()[:16]}".strip()
            self._save()
            return {"lesson": item.as_dict()}

    def retire(self, lesson_id: str, reason: str = "retired by hand") -> dict[str, Any]:
        with self._lock:
            self._load()
            item = self.get(lesson_id)
            if item is None:
                raise ValueError(f"unknown lesson: {lesson_id}")
            if item.owner:
                raise ValueError("an owner rule is never retired")
            item.status = "retired"
            item.why = f"{item.why} | {reason}".strip()
            self._save()
            append_ledger("lesson", {"action": "retired", "lesson_id": item.id, "reason": reason})
            return {"lesson": item.as_dict()}

    def sweep(self) -> list[str]:
        """Retire noise: lessons judged relevant many times that never caught anything."""
        with self._lock:
            self._load()
            gone = []
            for item in self._items:
                if (item.status == "active" and item.kind == "lesson" and not item.owner
                        and item.surfaced >= RETIRE_AT_SURFACED and item.catches == 0 and item.escapes == 0):
                    item.status = "retired"
                    item.why = f"{item.why} | retired as noise: surfaced {item.surfaced}, never caught".strip()
                    gone.append(item.id)
            if gone:
                self._save()
                append_ledger("lesson", {"action": "swept", "lesson_ids": gone})
            return gone

    # -- packs -----------------------------------------------------------

    def export_pack(self, *, source: str = "", min_catches: int = 1) -> dict[str, Any]:
        """Proven, global, non-owner lessons, ready for another install."""
        rows = [
            item.as_pack_row()
            for item in self.all()
            if item.kind == "lesson" and item.scope == "global" and not item.owner and item.catches >= min_catches
        ]
        return {"from": source or str(get_hermes_home()), "made": _now(), "lessons": rows}

    def import_pack(self, pack: dict[str, Any]) -> dict[str, Any]:
        """Load a pack. Imported lessons arrive with no local track record."""
        if not isinstance(pack, dict):
            raise ValueError("a pack must be an object")
        rows = pack.get("lessons")
        if not isinstance(rows, list):
            raise ValueError("a pack needs a lessons list")
        origin = str(pack.get("from") or "unknown")
        made = str(pack.get("made") or "")[:10]
        added = []
        with self._lock:
            self._load()
            for row in rows:
                if not isinstance(row, dict) or not str(row.get("text") or "").strip():
                    continue
                self._seq += 1
                raw_severity = str(row.get("severity") or "")
                severity = raw_severity if raw_severity in SEVERITIES else "nudge"
                item = Lesson(
                    id=f"L{self._seq}",
                    text=str(row["text"]).strip(),
                    detect=str(row.get("detect") or "").strip(),
                    severity=severity,
                    source=f"imported:{origin}",
                    tags=sorted(_tokens(f"{row.get('text', '')} {row.get('detect', '')}")),
                    made=_now(),
                    why=(f"imported from {origin}'s lesson pack ({made}): "
                         f"{int(row.get('catches') or 0)} catches, {int(row.get('escapes') or 0)} escapes there"),
                )
                self._items.append(item)
                added.append(item.id)
            self._save()
        if added:
            append_ledger("lesson", {"action": "imported", "from": origin, "lesson_ids": added})
        return {"imported": added, "count": len(added), "from": origin}


_DEFAULT: LessonStore | None = None
_DEFAULT_LOCK = threading.Lock()


def default_store() -> LessonStore:
    """Process wide lesson store used by the plugin."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = LessonStore()
        return _DEFAULT
