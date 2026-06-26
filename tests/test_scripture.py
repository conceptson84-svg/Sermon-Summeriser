"""Scripture validator tests (eng review T3 — keeps wrong refs off the broadcast)."""

from sermon_summarizer.slides.scripture import validate_reference, is_valid_reference


def test_valid_common_reference():
    assert validate_reference("John 3:16") == "John 3:16"
    assert validate_reference("Genesis 1:1") == "Genesis 1:1"
    assert validate_reference("Psalm 23") == "Psalms 23"


def test_numbered_books():
    assert validate_reference("1 Corinthians 13:4") == "1 Corinthians 13:4"
    assert validate_reference("1Corinthians 13") == "1 Corinthians 13"
    assert validate_reference("first john 4:8") == "1 John 4:8"


def test_aliases_normalize():
    assert validate_reference("Rom 8:28") == "Romans 8:28"
    assert validate_reference("Matt 5:9") == "Matthew 5:9"
    assert validate_reference("eph 2:8") == "Ephesians 2:8"


def test_verse_range():
    assert validate_reference("Psalm 23:1-6") == "Psalms 23:1"  # range keeps the starting verse
    assert is_valid_reference("John 3:16-18")


def test_rejects_fake_book():
    # The failure this whole module exists to prevent.
    assert validate_reference("Hesitations 3:16") is None
    assert validate_reference("Gospel of Steve 1:1") is None


def test_rejects_out_of_range_chapter():
    assert validate_reference("John 99:1") is None      # John has 21 chapters
    assert validate_reference("Jude 2") is None         # Jude has 1 chapter
    assert validate_reference("Obadiah 5") is None      # Obadiah has 1 chapter


def test_rejects_garbage():
    assert validate_reference("") is None
    assert validate_reference("   ") is None
    assert validate_reference("just some words") is None
    assert validate_reference("12345") is None


def test_chapter_only_reference():
    assert validate_reference("Romans 8") == "Romans 8"
