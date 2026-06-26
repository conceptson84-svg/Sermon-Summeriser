"""Rolling deck tests (eng review #3 — slide overflow handling)."""

from sermon_summarizer.slides.deck import Deck, Point, MAX_POINTS_PER_SLIDE

# Distinct, non-overlapping content words so the near-duplicate check never
# collapses them — each is a genuinely different point.
DISTINCT = [
    "faith", "grace", "mercy", "power", "glory", "wisdom",
    "kindness", "patience", "courage", "freedom", "healing", "wonder",
]


def test_starts_with_one_empty_slide():
    d = Deck()
    assert d.slide_count == 1
    assert d.point_count == 0


def test_rolls_to_new_slide_when_full():
    d = Deck()
    for i in range(MAX_POINTS_PER_SLIDE + 1):
        d.add_point(Point(DISTINCT[i]))
    assert d.slide_count == 2
    assert len(d.slides[0].points) == MAX_POINTS_PER_SLIDE
    assert len(d.slides[1].points) == 1


def test_latest_slide_is_current():
    d = Deck()
    for i in range(MAX_POINTS_PER_SLIDE + 2):
        d.add_point(Point(DISTINCT[i]))
    assert d.latest_slide() is d.slides[-1]


def test_dedupes_identical_text():
    d = Deck()
    assert d.add_point(Point("Be still")) is True
    assert d.add_point(Point("be still")) is False  # case-insensitive dupe
    assert d.point_count == 1


def test_ignores_blank_points():
    d = Deck()
    assert d.add_point(Point("   ")) is False
    assert d.point_count == 0


def test_add_points_returns_added_count():
    d = Deck()
    added = d.add_points([Point("a"), Point("b"), Point("a")])
    assert added == 2


def test_near_duplicate_reworded_point_dropped():
    d = Deck()
    assert d.add_point(Point("You are chosen to make God's glory visible")) is True
    # Same idea, a few words added — should be caught as a near-duplicate.
    assert d.add_point(Point("You are chosen to make God's glory visible today")) is False
    assert d.add_point(Point("You are chosen to make God's glory visible through your life")) is False
    assert d.point_count == 1


def test_emphasis_with_different_words_kept():
    d = Deck()
    assert d.add_point(Point("You are loved by God")) is True
    # Genuine emphasis with fresh words and new meaning — should pass.
    assert d.add_point(Point("God treasures you deeply")) is True
    assert d.point_count == 2


def test_distinct_points_not_falsely_merged():
    d = Deck()
    assert d.add_point(Point("Walk by faith not by sight")) is True
    assert d.add_point(Point("Your breakthrough is on the way")) is True
    assert d.add_point(Point("Christ is the image of God")) is True
    assert d.point_count == 3


def test_force_add_bypasses_dedupe():
    d = Deck()
    d.add_point(Point("You are chosen to make God's glory visible"))
    # Same idea normally dropped, but a manual force-add keeps it.
    assert d.add_point(Point("You are chosen to make God's glory visible today"),
                       force=True) is True
    assert len(d.all_points()) == 2


def test_all_points_spans_slides():
    d = Deck()
    for i in range(MAX_POINTS_PER_SLIDE + 3):
        d.add_point(Point(DISTINCT[i]))
    assert len(d.all_points()) == MAX_POINTS_PER_SLIDE + 3
