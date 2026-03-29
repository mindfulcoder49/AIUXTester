from datetime import date

from scenario_runner import parse_structured_summary, render_markdown_report, select_daily_scenarios
from scenarios import expand_scenarios, load_scenario_bank


def test_publicdatawatch_bank_loads_and_expands():
    scenarios = load_scenario_bank("publicdatawatch")
    assert len(scenarios) >= 15

    expanded = expand_scenarios(scenarios)
    assert len(expanded) > len(scenarios)
    assert any(item.device == "mobile" for item in expanded)
    assert any("skeptical" in item.tags for item in expanded)


def test_daily_selection_is_deterministic_for_same_date():
    expanded = expand_scenarios(load_scenario_bank("publicdatawatch"))

    first = select_daily_scenarios(expanded, for_date=date(2026, 3, 29), count=6)
    second = select_daily_scenarios(expanded, for_date=date(2026, 3, 29), count=6)

    assert [item.run_id for item in first] == [item.run_id for item in second]


def test_daily_selection_can_filter_by_tag():
    expanded = expand_scenarios(load_scenario_bank("publicdatawatch"))
    selected = select_daily_scenarios(
        expanded,
        for_date=date(2026, 3, 29),
        count=5,
        include_tags=["mobile"],
    )

    assert selected
    assert all("mobile" in item.tags for item in selected)


def test_parse_structured_summary_extracts_findings():
    summary = parse_structured_summary(
        """Verdict: The page is understandable.\nFindings:\n- Search is clear.\n- Pricing is still vague.\nNext step: Tighten pricing copy."""
    )

    assert summary.verdict == "The page is understandable."
    assert summary.findings == ("Search is clear.", "Pricing is still vague.")
    assert summary.next_step == "Tighten pricing copy."


def test_render_markdown_report_includes_run_details():
    summary = parse_structured_summary(
        """Verdict: Good first impression.\nFindings:\n- Hero is clear.\nNext step: Test the search flow."""
    )

    from scenario_runner import ScenarioRunResult

    report = render_markdown_report(
        bank_name="publicdatawatch",
        for_date=date(2026, 3, 29),
        selected_count=1,
        results=[
            ScenarioRunResult(
                run_id="homepage-first-impression:desktop",
                scenario_id="homepage-first-impression",
                title="Homepage First Impression",
                entry_url="https://publicdatawatch.com/",
                surface="homepage",
                device="desktop",
                tags=("homepage", "desktop"),
                session_id="session-123",
                status="completed",
                end_reason="done",
                verdict=summary.verdict,
                findings=summary.findings,
                next_step=summary.next_step,
                action_count=1,
                started_at="2026-03-29T00:00:00+00:00",
                completed_at="2026-03-29T00:00:10+00:00",
                duration_seconds=10.0,
                postmortem_id=1,
            )
        ],
    )

    assert "# publicdatawatch Scenario Run Report" in report
    assert "Homepage First Impression" in report
    assert "Hero is clear." in report
    assert "Test the search flow." in report
