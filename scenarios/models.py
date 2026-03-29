from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


DeviceMode = Literal["desktop", "mobile"]


class ScenarioVariant(BaseModel):
    id_suffix: str
    label: str
    goal_append: Optional[str] = None
    extra_constraints: list[str] = Field(default_factory=list)
    extra_tags: list[str] = Field(default_factory=list)
    force_device: Optional[DeviceMode] = None


class ScenarioDefinition(BaseModel):
    id: str
    title: str
    persona: str
    entry_url: str
    surface: str
    tags: list[str]
    goal: str
    success_question: str
    constraints: list[str] = Field(default_factory=list)
    devices: list[DeviceMode] = Field(default_factory=lambda: ["desktop"])
    variants: list[ScenarioVariant] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_devices_unique(self):
        self.devices = list(dict.fromkeys(self.devices))
        return self


class ExpandedScenario(BaseModel):
    run_id: str
    scenario_id: str
    title: str
    persona: str
    entry_url: str
    surface: str
    device: DeviceMode
    tags: list[str]
    goal: str
    success_question: str
    constraints: list[str] = Field(default_factory=list)
    variant_label: Optional[str] = None
