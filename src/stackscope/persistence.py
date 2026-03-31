from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import Blueprint, Component, Relationship


GROUPS: list[tuple[str, set[str]]] = [
    ("Delivery", {"pipeline", "automation"}),
    ("Application", {"application", "service", "gateway"}),
    ("Data", {"datastore", "storage"}),
    ("Platform", {"cloud", "infrastructure", "configuration"}),
    ("Edge", {"integration", "library"}),
]


@dataclass(slots=True)
class ViewNode:
    id: str
    x: int
    y: int
    group: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "x": self.x, "y": self.y}
        if self.group:
            payload["group"] = self.group
        return payload


@dataclass(slots=True)
class ViewState:
    blueprint_name: str
    root_path: str
    nodes: dict[str, ViewNode] = field(default_factory=dict)
    hidden_components: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_name": self.blueprint_name,
            "root_path": self.root_path,
            "nodes": [self.nodes[node_id].to_dict() for node_id in sorted(self.nodes)],
            "hidden_components": sorted(set(self.hidden_components)),
            "metadata": self.metadata,
        }


def blueprint_from_dict(payload: dict[str, Any]) -> Blueprint:
    if "blueprint" in payload and isinstance(payload["blueprint"], dict):
        payload = payload["blueprint"]
    blueprint = Blueprint(name=str(payload.get("name", "blueprint")), root_path=str(payload.get("root_path", "")))
    for item in payload.get("components", []):
        blueprint.add_component(
            Component(
                id=str(item["id"]),
                name=str(item.get("name", item["id"])),
                type=str(item.get("type", "application")),
                technology=item.get("technology"),
                source_path=item.get("source_path"),
                tags=[str(tag) for tag in item.get("tags", [])],
                metadata=dict(item.get("metadata", {})),
            )
        )
    for item in payload.get("relationships", []):
        blueprint.add_relationship(
            Relationship(
                source=str(item["source"]),
                target=str(item["target"]),
                type=str(item.get("type", "connects_to")),
                label=item.get("label"),
                metadata=dict(item.get("metadata", {})),
            )
        )
    for item in payload.get("evidence", []):
        blueprint.evidence.append(dict(item))
    return blueprint


def load_blueprint(path: str | Path) -> Blueprint:
    return blueprint_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_blueprint(path: str | Path, blueprint: Blueprint) -> None:
    Path(path).write_text(json.dumps(blueprint.to_dict(), indent=2), encoding="utf-8")


def view_state_from_dict(payload: dict[str, Any]) -> ViewState:
    if "view_state" in payload and isinstance(payload["view_state"], dict):
        payload = payload["view_state"]
    nodes = {
        str(item["id"]): ViewNode(
            id=str(item["id"]),
            x=int(item.get("x", 0)),
            y=int(item.get("y", 0)),
            group=str(item["group"]) if item.get("group") else None,
        )
        for item in payload.get("nodes", [])
    }
    return ViewState(
        blueprint_name=str(payload.get("blueprint_name", "")),
        root_path=str(payload.get("root_path", "")),
        nodes=nodes,
        hidden_components=[str(item) for item in payload.get("hidden_components", [])],
        metadata=dict(payload.get("metadata", {})),
    )


def load_view_state(path: str | Path) -> ViewState:
    return view_state_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_view_state(path: str | Path, view_state: ViewState) -> None:
    Path(path).write_text(json.dumps(view_state.to_dict(), indent=2), encoding="utf-8")


def build_default_view_state(blueprint: Blueprint) -> ViewState:
    nodes: dict[str, ViewNode] = {}
    margins = {"left": 72, "top": 72}
    column_width = 272
    row_gap = 152
    grouped: set[str] = set()

    ordered_groups: list[tuple[str, list[Component]]] = []
    for title, component_types in GROUPS:
        members = [
            component
            for component in sorted(blueprint.components.values(), key=lambda item: item.id)
            if component.type in component_types
        ]
        if members:
            ordered_groups.append((title, members))
            grouped.update(component.id for component in members)

    ungrouped = [
        component
        for component in sorted(blueprint.components.values(), key=lambda item: item.id)
        if component.id not in grouped
    ]
    if ungrouped:
        ordered_groups.append(("Other", ungrouped))

    for column_index, (title, members) in enumerate(ordered_groups):
        base_x = margins["left"] + column_index * column_width
        for row_index, component in enumerate(members):
            nodes[component.id] = ViewNode(
                id=component.id,
                x=base_x + _node_width(component) // 2,
                y=margins["top"] + row_index * row_gap + _node_height(component) // 2,
                group=title,
            )

    return ViewState(
        blueprint_name=blueprint.name,
        root_path=blueprint.root_path,
        nodes=nodes,
        metadata={"generated_by": "stackscope"},
    )


def _node_width(component: Component) -> int:
    if component.type == "cloud":
        return 188
    if component.type == "gateway":
        return 188
    if component.type == "storage":
        return 184
    if component.type == "datastore":
        return 184
    return 184


def _node_height(component: Component) -> int:
    if component.type == "cloud":
        return 92
    if component.type == "gateway":
        return 88
    if component.type == "storage":
        return 82
    if component.type == "datastore":
        return 92
    return 84
