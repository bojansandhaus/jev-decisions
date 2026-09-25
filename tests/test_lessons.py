"""Tests for the learned-correction store.

Design adapted from psygns/osENV.io (see lessons.py). These tests pin the
lifecycle that was actually borrowed: severity escalation on repeats, catch and
escape accounting, credibility weighted ranking, noise retirement, and pack
transfer. They also pin the boundary of the deterministic matcher, because that
boundary is a documented limitation rather than an accident.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def lessons(monkeypatch, tmp_path):
    import ledger
    monkeypatch.setattr(ledger, "get_hermes_home", lambda: str(tmp_path))
    import lessons as module
    monkeypatch.setattr(module, "append_ledger", ledger.append)
    return module


@pytest.fixture
def store(lessons, tmp_path):
    return lessons.LessonStore(root=str(tmp_path / "jev"))


LITERAL = "rm -rf /tmp/jevs-decision-store"
PARAPHRASE = "clear out the temporary decision folder with a recursive delete"


# -- adding --------------------------------------------------------------


def test_add_creates_a_nudge_by_default(store):
    result = store.add(text="Check the port is free before starting the server", detect="a start with no port check")
    assert result["how"] == "added"
    lesson = result["lesson"]
    assert lesson["id"] == "L1"
    assert lesson["severity"] == "nudge"
    assert lesson["status"] == "active"
    assert lesson["catches"] == 0 and lesson["escapes"] == 0 and lesson["surfaced"] == 0


def test_add_requires_text(store):
    with pytest.raises(ValueError):
        store.add(text="   ")


def test_owner_rule_is_a_hard_stop_from_day_one(store):
    result = store.add(text="Never loosen a test to make it pass", source="owner", detect="a test assertion weakened")
    assert result["lesson"]["severity"] == "kick"
    assert "never retired" in result["lesson"]["why"]


# -- escapes and escalation ---------------------------------------------


def test_a_repeat_sharpens_instead_of_copying(store):
    a = store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect in PowerShell")
    b = store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect in PowerShell")
    assert b["how"] == "merged"
    assert b["lesson"]["id"] == a["lesson"]["id"]
    assert len(store.all()) == 1


def test_first_repeat_keeps_severity_at_nudge(store):
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    merged = store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    assert merged["lesson"]["escapes"] == 1
    assert merged["lesson"]["severity"] == "nudge"


def test_second_repeat_escalates_to_a_kick(store):
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    third = store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    assert third["lesson"]["escapes"] == 2
    assert third["lesson"]["severity"] == "kick"


def test_escalation_stops_at_kick(store):
    for _ in range(5):
        store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    lesson = store.get("L1")
    assert lesson.severity == "kick"
    assert lesson.escapes == 4


def test_a_different_correction_is_a_new_lesson(store):
    store.add(text="Check the port is free before starting the server", detect="start with no check")
    other = store.add(text="Money in Decimal, never a bare float", detect="a float used for money")
    assert other["how"] == "added"
    assert len(store.all()) == 2


# -- catches and surfacing ----------------------------------------------


def test_record_caught_increments_catches(store):
    store.add(text="Check the port is free before starting the server")
    store.record_caught(["L1", "L1", "L404"])
    assert store.get("L1").catches == 2


def test_record_surfaced_increments_surfaced(store):
    store.add(text="Check the port is free before starting the server")
    store.record_surfaced(["L1"])
    assert store.get("L1").surfaced == 1


def test_credibility_falls_when_a_lesson_surfaces_without_catching(store):
    store.add(text="Check the port is free before starting the server")
    fresh = store.get("L1").credibility()
    for _ in range(40):
        store.record_surfaced(["L1"])
    assert store.get("L1").credibility() < fresh


def test_credibility_rises_with_a_catch(store):
    store.add(text="Check the port is free before starting the server")
    store.record_surfaced(["L1"])
    before = store.get("L1").credibility()
    store.record_caught(["L1"])
    assert store.get("L1").credibility() > before


# -- retirement ----------------------------------------------------------


def test_sweep_retires_noise(store):
    store.add(text="Check the port is free before starting the server")
    for _ in range(40):
        store.record_surfaced(["L1"])
    gone = store.sweep()
    assert gone == ["L1"]
    assert store.get("L1").status == "retired"
    assert "never caught" in store.get("L1").why
    assert store.all() == []


def test_sweep_keeps_a_lesson_that_ever_caught_something(store):
    store.add(text="Check the port is free before starting the server")
    for _ in range(40):
        store.record_surfaced(["L1"])
    store.record_caught(["L1"])
    assert store.sweep() == []
    assert store.get("L1").status == "active"


def test_sweep_keeps_a_lesson_that_ever_escaped(store):
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    for _ in range(40):
        store.record_surfaced(["L1"])
    assert store.sweep() == []


def test_sweep_never_retires_an_owner_rule(store):
    store.add(text="Never loosen a test to make it pass", source="owner")
    for _ in range(40):
        store.record_surfaced(["L1"])
    assert store.sweep() == []
    assert store.get("L1").status == "active"


def test_an_owner_rule_cannot_be_retired_by_hand(store):
    store.add(text="Never loosen a test to make it pass", source="owner")
    with pytest.raises(ValueError):
        store.retire("L1")


def test_retire_by_hand_works_for_a_normal_lesson(store):
    store.add(text="Check the port is free before starting the server")
    assert store.retire("L1")["lesson"]["status"] == "retired"


def test_sweep_ignores_a_young_lesson(store):
    store.add(text="Check the port is free before starting the server")
    for _ in range(39):
        store.record_surfaced(["L1"])
    assert store.sweep() == []


# -- editing -------------------------------------------------------------


def test_edit_can_undo_a_wrong_escalation(store):
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    assert store.get("L1").severity == "kick"
    fixed = store.edit("L1", severity="nudge", escapes=0)
    assert fixed["lesson"]["severity"] == "nudge" and fixed["lesson"]["escapes"] == 0


def test_edit_can_mark_a_false_catch(store):
    store.add(text="Check the port is free before starting the server")
    store.record_caught(["L1"])
    assert store.edit("L1", catches=0)["lesson"]["catches"] == 0


def test_edit_rejects_unknown_lesson(store):
    with pytest.raises(ValueError):
        store.edit("L404", severity="kick")


# -- matching boundaries -------------------------------------------------


def test_a_literal_match_clears_the_kick_floor(store, lessons):
    store.add(text=LITERAL, detect=LITERAL, source="owner")
    hits = store.local_kicks(LITERAL)
    assert [h[0].id for h in hits] == ["L1"]
    assert hits[0][1] >= lessons.KICK_FLOOR


# The paraphrase family used to be a documented miss. It is now matched, because
# the matcher canonicalises the words that name the same action, so these pin the
# new reach rather than describing its absence.

PARAPHRASES_THAT_MUST_FIRE = [
    "clear out the temporary decision folder with a recursive delete",
    "wipe the temp dir for jevs decision store",
    "remove the decision store directory recursively",
    "force erase of temporary jevs store folder",
]


@pytest.mark.parametrize("paraphrase", PARAPHRASES_THAT_MUST_FIRE)
def test_a_paraphrase_clears_the_kick_floor(store, lessons, paraphrase):
    store.add(text=LITERAL, detect=LITERAL, source="owner")
    hits = store.local_kicks(paraphrase)
    assert [h[0].id for h in hits] == ["L1"], paraphrase
    assert hits[0][1] >= lessons.KICK_FLOOR


def test_a_distant_paraphrase_still_misses(store, lessons):
    """The residual limit, pinned so it cannot be quietly claimed as fixed.

    Canonical words cover the families written into the table. A rephrasing that
    shares no canonical word with the lesson cannot be caught locally, which is
    exactly why the review path exists.
    """
    store.add(text=LITERAL, detect=LITERAL, source="owner")
    assert store.local_kicks("get rid of the scratch area used for the decisions work") == []
    assert lessons._lexical_overlap(
        "terminal {\"command\": \"get rid of the scratch area used for the decisions work\"}",
        LITERAL,
    ) < lessons.KICK_FLOOR


def test_an_unrelated_lesson_never_kicks(store, lessons):
    """A false kick blocks real work, so precision is asserted, not assumed."""
    store.add(text="Money in Decimal, never a bare float", detect="a float used for money", source="owner")
    store.add(text="Check the port is free before starting the server", detect="a start with no port check", source="owner")
    store.add(text="Read the file before editing it", detect="an edit to an unread file", source="owner")
    assert store.local_kicks(LITERAL) == []


def test_a_delete_of_a_different_target_does_not_kick(store):
    """Sharing the verb is not sharing the mistake."""
    store.add(text=LITERAL, detect=LITERAL, source="owner")
    assert store.local_kicks("rm -rf /var/backups/production-database") == []


def test_a_one_word_lesson_cannot_kick_a_long_action(store, lessons):
    """The shared word count is an independent gate, not decoration.

    Containment alone would let a single shared word reach the floor against a
    long action, which is the cheapest way to block something by accident.
    """
    store.add(text="delete", detect="delete", source="owner")
    hits = store.local_kicks(LITERAL)
    assert hits == []
    assert lessons._shared_count(LITERAL, "delete") < lessons.KICK_MIN_SHARED


def test_a_literal_match_still_scores_at_the_top(store):
    """Better reach must not have cost the near literal case its certainty."""
    store.add(text=LITERAL, detect=LITERAL, source="owner")
    assert store.local_kicks(LITERAL)[0][1] == pytest.approx(1.0, abs=0.05)


def test_candidates_rank_the_closest_first(store):
    store.add(text="Check the port is free before starting the server", detect="a start with no port check")
    store.add(text="Money in Decimal, never a bare float", detect="a float used for money")
    # floor=0.0 keeps both, so this asserts ordering rather than the cut.
    ranked = store.candidates("Check the port is free before starting the server", limit=2, floor=0.0)
    assert len(ranked) == 2
    assert ranked[0][0].id == "L1"
    assert ranked[0][1] > ranked[1][1]


def test_relevance_is_bounded_and_symmetric_for_identical_text(store):
    store.add(text="Check the port is free before starting the server")
    lesson = store.get("L1")
    score = lesson.relevance(f"{lesson.text} {lesson.detect}")
    assert 0.0 < score <= 1.0


def test_an_unrelated_action_scores_zero(store):
    store.add(text="Check the port is free before starting the server")
    assert store.candidates("unrelated", limit=4) == []


# -- packs ---------------------------------------------------------------


def test_export_pack_carries_only_proven_global_lessons(store):
    store.add(text="Check the port is free before starting the server")
    store.record_caught(["L1"])
    store.add(text="Never loosen a test to make it pass", source="owner")
    pack = store.export_pack(source="test-kit")
    assert [row["text"] for row in pack["lessons"]] == ["Check the port is free before starting the server"]
    assert pack["lessons"][0]["catches"] == 1
    assert pack["from"] == "test-kit"


def test_pack_round_trip_preserves_severity_and_records_provenance(store, lessons, tmp_path):
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.add(text="Save PowerShell output with Out-File and utf8", detect="a bare > redirect")
    store.record_caught(["L1"])
    pack = store.export_pack(source="windows-kit")
    assert pack["lessons"][0]["severity"] == "kick"

    imported = lessons.LessonStore(root=str(tmp_path / "second"))
    result = imported.import_pack(pack)
    assert result["count"] == 1
    row = imported.get(result["imported"][0])
    assert row.severity == "kick"
    assert row.catches == 0, "an imported lesson starts with no local track record"
    assert "windows-kit" in row.why
    assert row.source.startswith("imported:")


def test_import_rejects_a_malformed_pack(store):
    with pytest.raises(ValueError):
        store.import_pack({"lessons": "not a list"})


def test_import_clamps_an_unknown_severity(store):
    result = store.import_pack({"from": "x", "made": "2026-01-01", "lessons": [
        {"text": "Some rule", "detect": "some action", "severity": "catastrophic"},
    ]})
    assert store.get(result["imported"][0]).severity == "nudge"


# -- persistence ---------------------------------------------------------


def test_store_reloads_from_disk(lessons, tmp_path):
    first = lessons.LessonStore(root=str(tmp_path / "jev"))
    first.add(text="Check the port is free before starting the server")
    first.record_caught(["L1"])

    second = lessons.LessonStore(root=str(tmp_path / "jev"))
    assert second.get("L1").catches == 1


def test_ids_are_not_reused_after_a_retire(lessons, tmp_path):
    store = lessons.LessonStore(root=str(tmp_path / "jev"))
    store.add(text="Check the port is free before starting the server")
    store.retire("L1")
    second = store.add(text="Money in Decimal, never a bare float")
    assert second["lesson"]["id"] == "L2"


def test_writes_leave_no_temporary_file_behind(lessons, tmp_path):
    store = lessons.LessonStore(root=str(tmp_path / "jev"))
    store.add(text="Check the port is free before starting the server")
    store.record_surfaced(["L1"])
    leftovers = list((tmp_path / "jev").glob("*.tmp"))
    assert leftovers == []


def test_the_store_file_is_valid_json(lessons, tmp_path):
    store = lessons.LessonStore(root=str(tmp_path / "jev"))
    store.add(text="Check the port is free before starting the server")
    document = json.loads((tmp_path / "jev" / "lessons.json").read_text())
    assert isinstance(document, list) and document[0]["id"] == "L1"


# -- stats ---------------------------------------------------------------


def test_stats_summarise_the_store(store):
    store.add(text="Check the port is free before starting the server")
    store.add(text="Never loosen a test to make it pass", source="owner")
    store.record_caught(["L1"])
    stats = store.stats()
    assert stats["active"] == 2
    assert stats["owner_rules"] == 1
    assert stats["kicks"] == 1
    assert stats["catches"] == 1
    assert "owner" in stats["by_source"]
