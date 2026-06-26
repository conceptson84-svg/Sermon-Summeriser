"""Claude response parsing tests (eng review T2 + #4 scripture drop)."""

from sermon_summarizer.summarize.parsing import parse_points


def test_parses_clean_json():
    raw = '[{"point": "Grace is a gift", "scripture": "Ephesians 2:8"}]'
    points = parse_points(raw)
    assert len(points) == 1
    assert points[0].text == "Grace is a gift"
    assert points[0].scripture == "Ephesians 2:8"


def test_parses_point_without_scripture():
    points = parse_points('[{"point": "Faith without action stays theory"}]')
    assert len(points) == 1
    assert points[0].scripture is None


def test_strips_markdown_fences():
    raw = '```json\n[{"point": "Love your neighbor", "scripture": "Mark 12:31"}]\n```'
    points = parse_points(raw)
    assert points[0].text == "Love your neighbor"
    assert points[0].scripture == "Mark 12:31"


def test_extracts_array_amid_prose():
    raw = 'Here are the points: [{"point": "Be still"}] hope that helps'
    points = parse_points(raw)
    assert len(points) == 1
    assert points[0].text == "Be still"


def test_invalid_scripture_dropped_but_point_kept():
    raw = '[{"point": "Trust the process", "scripture": "Hesitations 3:16"}]'
    points = parse_points(raw)
    assert len(points) == 1
    assert points[0].text == "Trust the process"
    assert points[0].scripture is None  # bad ref dropped, never reaches the screen


def test_malformed_json_returns_empty():
    assert parse_points("not json at all") == []
    assert parse_points('[{"point": "broken"', ) == []
    assert parse_points("") == []


def test_non_list_returns_empty():
    assert parse_points('{"point": "single object not array"}') == []


def test_skips_items_without_point_text():
    raw = '[{"scripture": "John 3:16"}, {"point": ""}, {"point": "Real one"}]'
    points = parse_points(raw)
    assert len(points) == 1
    assert points[0].text == "Real one"
