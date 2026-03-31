from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Component:
    id: str
    name: str
    type: str
    technology: str | None = None
    source_path: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Relationship:
    source: str
    target: str
    type: str
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Blueprint:
    name: str
    root_path: str
    components: dict[str, Component] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def add_component(self, component: Component) -> Component:
        existing = self.components.get(component.id)
        if existing is None:
            self.components[component.id] = component
            return component

        merged_tags = sorted(set(existing.tags) | set(component.tags))
        merged_metadata = {**existing.metadata, **component.metadata}
        existing.tags = merged_tags
        existing.metadata = merged_metadata
        if _source_priority(component) > _source_priority(existing):
            existing.name = component.name
            existing.type = component.type
            existing.technology = component.technology
            existing.source_path = component.source_path
        else:
            existing.technology = existing.technology or component.technology
            existing.source_path = existing.source_path or component.source_path
        return existing

    def add_relationship(self, relationship: Relationship) -> None:
        for current in self.relationships:
            if (
                current.source == relationship.source
                and current.target == relationship.target
                and current.type == relationship.type
                and current.label == relationship.label
            ):
                return
        self.relationships.append(relationship)

    def merge_components(self, source_id: str, target_id: str) -> None:
        if source_id == target_id:
            return

        source = self.components.get(source_id)
        target = self.components.get(target_id)
        if source is None or target is None:
            return

        merged = Component(
            id=target.id,
            name=target.name,
            type=target.type,
            technology=target.technology or source.technology,
            source_path=target.source_path or source.source_path,
            tags=sorted(set(target.tags) | set(source.tags)),
            metadata={
                **source.metadata,
                **target.metadata,
                "aliases": sorted(
                    {
                        *(_metadata_aliases(target)),
                        *(_metadata_aliases(source)),
                        source.id,
                        source.name,
                    }
                ),
            },
        )
        self.components[target_id] = merged

        updated_relationships: list[Relationship] = []
        for relationship in self.relationships:
            rewritten = Relationship(
                source=target_id if relationship.source == source_id else relationship.source,
                target=target_id if relationship.target == source_id else relationship.target,
                type=relationship.type,
                label=relationship.label,
                metadata=relationship.metadata,
            )
            if rewritten.source == rewritten.target:
                continue
            duplicate = any(
                current.source == rewritten.source
                and current.target == rewritten.target
                and current.type == rewritten.type
                and current.label == rewritten.label
                for current in updated_relationships
            )
            if not duplicate:
                updated_relationships.append(rewritten)

        self.relationships = updated_relationships
        for item in self.evidence:
            details = item.get("details", {})
            if details.get("component_id") == source_id:
                details["component_id"] = target_id

        del self.components[source_id]

    def add_evidence(self, kind: str, source_path: str, details: dict[str, Any]) -> None:
        self.evidence.append({"kind": kind, "source_path": source_path, "details": details})

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root_path": self.root_path,
            "components": [component.to_dict() for component in sorted(self.components.values(), key=lambda item: item.id)],
            "relationships": [relationship.to_dict() for relationship in self.relationships],
            "evidence": self.evidence,
        }


def _source_priority(component: Component) -> int:
    tags = set(component.tags)
    if "terraform" in tags:
        return 50
    if "kubernetes" in tags:
        return 45
    if "docker-compose" in tags:
        return 40
    if "nginx" in tags:
        return 35
    if "package-manifest" in tags:
        return 30
    if "ci-cd" in tags:
        return 25
    if "env" in tags:
        return 10
    return 0


def _metadata_aliases(component: Component) -> list[str]:
    aliases = component.metadata.get("aliases")
    if isinstance(aliases, list):
        return [str(item) for item in aliases]
    return []
