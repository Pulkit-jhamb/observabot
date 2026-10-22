from pathlib import Path

from observabot.runbooks import excerpt, load_runbooks, search_runbooks

RUNBOOKS = Path(__file__).resolve().parent.parent / "runbooks"


def test_loads_titles_and_skips_readme():
    titles = {rb.slug: rb.title for rb in load_runbooks(RUNBOOKS)}
    assert "README" not in titles
    assert titles["high-error-rate"] == "High Error Rate (HighErrorRate)"


def test_alert_name_finds_its_runbook_first():
    results = search_runbooks(load_runbooks(RUNBOOKS), "HighErrorRate")
    assert results[0].slug == "high-error-rate"


def test_symptom_search_matches_body_text():
    results = search_runbooks(load_runbooks(RUNBOOKS), "service is unreachable scrape")
    assert results[0].slug == "service-down"


def test_no_match_returns_empty_list():
    assert search_runbooks(load_runbooks(RUNBOOKS), "kubernetes billing invoice") == []


def test_empty_query_returns_empty_list():
    assert search_runbooks(load_runbooks(RUNBOOKS), "   ") == []


def test_excerpt_truncates_long_runbooks(tmp_path):
    (tmp_path / "long.md").write_text("# Long\n" + "word " * 1000, encoding="utf-8")
    rb = load_runbooks(tmp_path)[0]
    text = excerpt(rb)
    assert text.endswith("[truncated]")
    assert len(text) < 1600
