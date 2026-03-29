from __future__ import annotations

import json
from pathlib import Path

from .models import ExpandedScenario, ScenarioDefinition


SCENARIO_DIR = Path(__file__).resolve().parent


def resolve_bank_path(bank: str) -> Path:
    candidate = Path(bank)
    if candidate.exists():
        return candidate

    normalized = bank if bank.endswith(".json") else f"{bank}.json"
    path = SCENARIO_DIR / normalized
    if path.exists():
        return path

    raise FileNotFoundError(f"Scenario bank not found: {bank}")


def load_scenario_bank(bank: str) -> list[ScenarioDefinition]:
    path = resolve_bank_path(bank)
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = [ScenarioDefinition.model_validate(item) for item in payload]
    ids = [scenario.id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("Scenario bank contains duplicate ids")
    return scenarios


def _compose_goal(
    scenario: ScenarioDefinition,
    *,
    device: str,
    goal_append: str | None = None,
    extra_constraints: list[str] | None = None,
) -> str:
    constraints = [*scenario.constraints, *(extra_constraints or [])]
    lines = [
        f"Persona: {scenario.persona}",
        f"Entry point: {scenario.entry_url}",
        f"Surface under test: {scenario.surface}",
        f"Device context: {device}",
        f"Primary job: {scenario.goal}",
        f"Success question: {scenario.success_question}",
    ]
    if constraints:
        lines.append("Constraints:")
        lines.extend(f"- {item}" for item in constraints)
    if goal_append:
        lines.append(goal_append)
    lines.append(
        "Inspect and navigate only as needed, then finish with a short findings report using the required Verdict / Findings / Next step format."
    )
    return "\n".join(lines)


def expand_scenarios(scenarios: list[ScenarioDefinition]) -> list[ExpandedScenario]:
    expanded: list[ExpandedScenario] = []
    for scenario in scenarios:
        base_variants = scenario.variants or []
        for device in scenario.devices:
            expanded.append(
                ExpandedScenario(
                    run_id=f"{scenario.id}:{device}",
                    scenario_id=scenario.id,
                    title=scenario.title,
                    persona=scenario.persona,
                    entry_url=scenario.entry_url,
                    surface=scenario.surface,
                    device=device,
                    tags=list(dict.fromkeys([*scenario.tags, device, "baseline"])),
                    goal=_compose_goal(scenario, device=device),
                    success_question=scenario.success_question,
                    constraints=scenario.constraints,
                    variant_label="baseline",
                )
            )

        for variant in base_variants:
            if variant.force_device is not None:
                variant_devices = [variant.force_device]
            else:
                variant_devices = scenario.devices
            for device in variant_devices:
                expanded.append(
                    ExpandedScenario(
                        run_id=f"{scenario.id}:{variant.id_suffix}:{device}",
                        scenario_id=scenario.id,
                        title=f"{scenario.title} ({variant.label})",
                        persona=scenario.persona,
                        entry_url=scenario.entry_url,
                        surface=scenario.surface,
                        device=device,
                        tags=list(
                            dict.fromkeys(
                                [
                                    *scenario.tags,
                                    *variant.extra_tags,
                                    device,
                                    variant.id_suffix,
                                ]
                            )
                        ),
                        goal=_compose_goal(
                            scenario,
                            device=device,
                            goal_append=variant.goal_append,
                            extra_constraints=variant.extra_constraints,
                        ),
                        success_question=scenario.success_question,
                        constraints=[*scenario.constraints, *variant.extra_constraints],
                        variant_label=variant.label,
                    )
                )

    run_ids = [item.run_id for item in expanded]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Expanded scenarios contain duplicate run ids")
    return expanded
