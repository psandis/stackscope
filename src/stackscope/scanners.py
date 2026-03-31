from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .model import Blueprint, Component, Relationship
from .utils import slugify


def scan_path(root: str | Path) -> Blueprint:
    root_path = Path(root).resolve()
    blueprint = Blueprint(name=root_path.name, root_path=str(root_path))
    files = [path for path in sorted(root_path.rglob("*")) if path.is_file()]
    scanner_order = (
        _is_docker_compose,
        _is_package_json,
        _is_github_actions,
        _is_terraform,
        _is_nginx,
        _is_kubernetes,
        _is_env_example,
    )

    for matcher in scanner_order:
        for path in files:
            if not matcher(path, root_path):
                continue

            relative = str(path.relative_to(root_path))
            text = _read_text(path)
            if text is None:
                continue

            if _is_docker_compose(path, root_path):
                scan_docker_compose(blueprint, relative, text)
            elif _is_package_json(path, root_path):
                scan_package_json(blueprint, relative, text)
            elif _is_github_actions(path, root_path):
                scan_github_actions(blueprint, relative, text)
            elif _is_terraform(path, root_path):
                scan_terraform(blueprint, relative, text)
            elif _is_nginx(path, root_path):
                scan_nginx(blueprint, relative, text)
            elif _is_kubernetes(path, root_path):
                scan_kubernetes(blueprint, relative, text)
            elif _is_env_example(path, root_path):
                scan_env_example(blueprint, relative, text)

    reconcile_components(blueprint)
    return blueprint


def scan_docker_compose(blueprint: Blueprint, source_path: str, text: str) -> None:
    in_services = False
    current_service: str | None = None
    in_depends_on = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped == "services:":
            in_services = True
            current_service = None
            in_depends_on = False
            continue

        if not in_services:
            continue

        service_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if service_match:
            current_service = service_match.group(1)
            in_depends_on = False
            technology = _infer_service_technology(current_service)
            service_type = "datastore" if technology in {"postgres", "redis", "mysql", "mongodb"} else "service"
            blueprint.add_component(
                Component(
                    id=slugify(current_service),
                    name=current_service,
                    type=service_type,
                    technology=technology,
                    source_path=source_path,
                    tags=["docker-compose"],
                )
            )
            continue

        if current_service is None:
            continue

        if stripped.startswith("depends_on:"):
            in_depends_on = True
            continue

        if in_depends_on:
            dep_match = re.match(r"^\s*-\s*([A-Za-z0-9_-]+)\s*$", stripped)
            if dep_match:
                dependency = slugify(dep_match.group(1))
                blueprint.add_relationship(
                    Relationship(
                        source=slugify(current_service),
                        target=dependency,
                        type="depends_on",
                        label="depends_on",
                        metadata={"source_path": source_path},
                    )
                )
                continue
            in_depends_on = False


def scan_package_json(blueprint: Blueprint, source_path: str, text: str) -> None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return

    app_name = payload.get("name") or Path(source_path).parent.name or "application"
    app_id = slugify(app_name)
    blueprint.add_component(
        Component(
            id=app_id,
            name=app_name,
            type="application",
            technology="node",
            source_path=source_path,
            tags=["package-manifest"],
            metadata={"version": payload.get("version")},
        )
    )

    for package_name in sorted((payload.get("dependencies") or {}).keys()):
        dependency_id = f"pkg_{slugify(package_name)}"
        blueprint.add_component(
            Component(
                id=dependency_id,
                name=package_name,
                type="library",
                technology="npm",
                source_path=source_path,
                tags=["package-manifest"],
            )
        )
        blueprint.add_relationship(
            Relationship(
                source=app_id,
                target=dependency_id,
                type="uses_library",
                label="uses",
                metadata={"source_path": source_path},
            )
        )


def scan_github_actions(blueprint: Blueprint, source_path: str, text: str) -> None:
    workflow_name = "GitHub Actions Workflow"
    for line in text.splitlines():
        match = re.match(r"^name:\s*(.+?)\s*$", line.strip())
        if match:
            workflow_name = match.group(1).strip("\"'")
            break

    workflow_id = f"github_actions_{slugify(workflow_name)}"
    blueprint.add_component(
        Component(
            id=workflow_id,
            name=workflow_name,
            type="pipeline",
            technology="github-actions",
            source_path=source_path,
            tags=["ci-cd"],
        )
    )

    for uses in re.findall(r"uses:\s*([A-Za-z0-9_./@-]+)", text):
        action_id = f"action_{slugify(uses)}"
        blueprint.add_component(
            Component(
                id=action_id,
                name=uses,
                type="automation",
                technology="github-action",
                source_path=source_path,
                tags=["ci-cd"],
            )
        )
        blueprint.add_relationship(
            Relationship(
                source=workflow_id,
                target=action_id,
                type="uses_action",
                label="uses",
                metadata={"source_path": source_path},
            )
        )

    for component in list(blueprint.components.values()):
        if component.type in {"application", "service"}:
            blueprint.add_relationship(
                Relationship(
                    source=workflow_id,
                    target=component.id,
                    type="builds",
                    label="builds",
                    metadata={"source_path": source_path},
                )
            )


def scan_kubernetes(blueprint: Blueprint, source_path: str, text: str) -> None:
    documents = text.split("---")
    for document in documents:
        kind_match = re.search(r"^\s*kind:\s*([A-Za-z]+)", document, flags=re.MULTILINE)
        name_match = re.search(r"^\s*name:\s*([A-Za-z0-9._-]+)", document, flags=re.MULTILINE)
        if not kind_match or not name_match:
            continue

        kind = kind_match.group(1)
        resource_name = name_match.group(1)
        component_type = {
            "Deployment": "service",
            "StatefulSet": "service",
            "Service": "integration",
            "Ingress": "gateway",
            "ConfigMap": "configuration",
            "Secret": "configuration",
        }.get(kind, "infrastructure")

        blueprint.add_component(
            Component(
                id=slugify(resource_name),
                name=resource_name,
                type=component_type,
                technology=f"kubernetes-{kind.lower()}",
                source_path=source_path,
                tags=["kubernetes"],
                metadata=_kubernetes_metadata(kind, document),
            )
        )


def scan_terraform(blueprint: Blueprint, source_path: str, text: str) -> None:
    providers = set(re.findall(r'provider\s+"([a-z0-9_]+)"', text))
    for provider in providers:
        provider_id = f"cloud_{slugify(provider)}"
        blueprint.add_component(
            Component(
                id=provider_id,
                name=provider.upper(),
                type="cloud",
                technology=provider,
                source_path=source_path,
                tags=["terraform"],
            )
        )

    for resource_type, resource_name in re.findall(r'resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"', text):
        component_name = f"{resource_type}.{resource_name}"
        component_id = slugify(component_name)
        technology = resource_type
        component_type = _terraform_component_type(resource_type)
        blueprint.add_component(
            Component(
                id=component_id,
                name=component_name,
                type=component_type,
                technology=technology,
                source_path=source_path,
                tags=["terraform"],
            )
        )
        cloud_name = resource_type.split("_", 1)[0]
        cloud_id = f"cloud_{slugify(cloud_name)}"
        if cloud_id in blueprint.components:
            blueprint.add_relationship(
                Relationship(
                    source=component_id,
                    target=cloud_id,
                    type="hosted_on",
                    label="hosted_on",
                    metadata={"source_path": source_path},
                )
            )


def scan_nginx(blueprint: Blueprint, source_path: str, text: str) -> None:
    gateway_id = "nginx_gateway"
    blueprint.add_component(
        Component(
            id=gateway_id,
            name="nginx",
            type="gateway",
            technology="nginx",
            source_path=source_path,
            tags=["nginx"],
        )
    )

    for upstream in re.findall(r"upstream\s+([A-Za-z0-9_-]+)", text):
        upstream_id = slugify(upstream)
        blueprint.add_component(
            Component(
                id=upstream_id,
                name=upstream,
                type="service",
                technology="upstream",
                source_path=source_path,
                tags=["nginx"],
            )
        )
        blueprint.add_relationship(
            Relationship(
                source=gateway_id,
                target=upstream_id,
                type="routes_to",
                label="routes_to",
                metadata={"source_path": source_path},
            )
        )

    for target in re.findall(r"proxy_pass\s+http://([A-Za-z0-9_.:-]+)", text):
        target_id = slugify(target.split(":")[0])
        blueprint.add_relationship(
            Relationship(
                source=gateway_id,
                target=target_id,
                type="proxies_to",
                label="proxies_to",
                metadata={"source_path": source_path},
            )
        )


def scan_env_example(blueprint: Blueprint, source_path: str, text: str) -> None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key_upper = key.upper()
        if "DATABASE" in key_upper:
            _attach_env_reference(blueprint, "database", value, source_path)
        elif "REDIS" in key_upper:
            _attach_env_reference(blueprint, "redis", value, source_path)
        elif "STRIPE" in key_upper:
            _attach_env_reference(blueprint, "stripe", value, source_path)
        elif key_upper.startswith("AWS_"):
            _attach_env_reference(blueprint, "aws", value, source_path, component_type="cloud")
        elif key_upper.endswith("_URL") or key_upper.endswith("_HOST"):
            _attach_env_reference(blueprint, key_lower_to_name(key_upper), value, source_path)


def query_blueprint(blueprint: Blueprint, query: str) -> list[dict[str, str]]:
    normalized = query.strip().lower()
    if normalized == "components":
        return [_component_row(component) for component in sorted(blueprint.components.values(), key=lambda item: item.id)]
    if normalized == "relationships":
        return [
            {"source": rel.source, "target": rel.target, "type": rel.type, "label": rel.label or ""}
            for rel in blueprint.relationships
        ]
    if normalized == "cloud":
        return [_component_row(component) for component in blueprint.components.values() if component.type == "cloud"]
    if normalized == "pipelines":
        return [_component_row(component) for component in blueprint.components.values() if component.type == "pipeline"]
    if normalized.startswith("find:"):
        term = normalized.split(":", 1)[1]
        return [
            _component_row(component)
            for component in blueprint.components.values()
            if term in component.name.lower() or term in component.id.lower()
        ]
    if normalized.startswith("type:"):
        target_type = normalized.split(":", 1)[1]
        return [_component_row(component) for component in blueprint.components.values() if component.type == target_type]
    return [{"error": f"Unsupported query: {query}"}]


def _component_row(component: Component) -> dict[str, str]:
    return {
        "id": component.id,
        "name": component.name,
        "type": component.type,
        "technology": component.technology or "",
        "source_path": component.source_path or "",
    }


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _infer_service_technology(service_name: str) -> str:
    lowered = service_name.lower()
    if "postgres" in lowered:
        return "postgres"
    if "redis" in lowered:
        return "redis"
    if "mysql" in lowered:
        return "mysql"
    if "mongo" in lowered:
        return "mongodb"
    return "container"


def _terraform_component_type(resource_type: str) -> str:
    lowered = resource_type.lower()
    if "db" in lowered:
        return "datastore"
    if "bucket" in lowered or "storage" in lowered:
        return "storage"
    if "lambda" in lowered or "function" in lowered:
        return "service"
    return "infrastructure"


def _add_env_integration(
    blueprint: Blueprint,
    name: str,
    value: str,
    source_path: str,
    component_type: str = "integration",
) -> Component:
    component_id = slugify(name)
    return blueprint.add_component(
        Component(
            id=component_id,
            name=name,
            type=component_type,
            technology=name,
            source_path=source_path,
            tags=["env"],
            metadata={"example": value},
        )
    )


def _attach_env_reference(
    blueprint: Blueprint,
    name: str,
    value: str,
    source_path: str,
    component_type: str = "integration",
) -> None:
    target_component = _resolve_env_component(blueprint, name, value, component_type)
    if target_component is None:
        target_component = _add_env_integration(blueprint, name, value, source_path, component_type)
    else:
        target_component.tags = sorted(set(target_component.tags) | {"env"})
        target_component.metadata = {
            **target_component.metadata,
            "env_example": value,
        }

    blueprint.add_evidence(
        "env_reference",
        source_path,
        {"name": name, "value": value, "component_id": target_component.id},
    )


def _resolve_env_component(
    blueprint: Blueprint,
    name: str,
    value: str,
    component_type: str,
) -> Component | None:
    parsed = urlparse(value)
    host = parsed.hostname
    if host:
        host_id = slugify(host)
        if host_id in blueprint.components:
            return blueprint.components[host_id]

    normalized_name = slugify(name)
    if normalized_name in blueprint.components:
        return blueprint.components[normalized_name]

    if component_type == "cloud":
        for component in blueprint.components.values():
            if component.type == "cloud" and component.technology == name:
                return component

    return None


def _is_docker_compose(path: Path, root_path: Path) -> bool:
    return path.name.lower() in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}


def _is_package_json(path: Path, root_path: Path) -> bool:
    return path.name.lower() == "package.json"


def _is_github_actions(path: Path, root_path: Path) -> bool:
    relative = str(path.relative_to(root_path)).replace("\\", "/")
    return ".github/workflows/" in relative and path.name.lower().endswith((".yml", ".yaml"))


def _is_terraform(path: Path, root_path: Path) -> bool:
    return path.name.lower().endswith(".tf")


def _is_nginx(path: Path, root_path: Path) -> bool:
    return path.name.lower() == "nginx.conf"


def _is_kubernetes(path: Path, root_path: Path) -> bool:
    relative = str(path.relative_to(root_path)).lower()
    return path.name.lower().endswith((".yml", ".yaml")) and any(part in relative for part in ("k8s", "kubernetes"))


def _is_env_example(path: Path, root_path: Path) -> bool:
    name = path.name.lower()
    return name.startswith(".env") or "env.example" in name


def reconcile_components(blueprint: Blueprint) -> None:
    project_stem = _normalized_stem(blueprint.name)
    mergeable = [
        component
        for component in blueprint.components.values()
        if component.type in {"application", "service"}
    ]

    by_stem: dict[str, list[Component]] = {}
    for component in mergeable:
        by_stem.setdefault(_normalized_stem(component.name), []).append(component)

    for stem, group in list(by_stem.items()):
        if len(group) < 2:
            continue
        canonical_id = _select_canonical_component(group, project_stem)
        for component in list(group):
            if component.id != canonical_id and component.id in blueprint.components and canonical_id in blueprint.components:
                blueprint.merge_components(component.id, canonical_id)

    project_candidate = _find_project_component(blueprint, project_stem)
    if project_candidate is None:
        return

    generic_ids = [
        component.id
        for component in list(blueprint.components.values())
        if component.type in {"application", "service"}
        and component.id != project_candidate.id
        and _normalized_stem(component.name) in {"app", "application", "api", "web"}
    ]
    if len(generic_ids) == 1:
        blueprint.merge_components(generic_ids[0], project_candidate.id)

    upstream_ids = [
        component.id
        for component in list(blueprint.components.values())
        if component.type == "service"
        and _normalized_stem(component.name) in {"app", "application", "api", "web"}
        and "upstream" in component.name.lower()
    ]
    for upstream_id in upstream_ids:
        if upstream_id in blueprint.components and project_candidate.id in blueprint.components:
            blueprint.merge_components(upstream_id, project_candidate.id)

    _link_kubernetes_services(blueprint)


def _find_project_component(blueprint: Blueprint, project_stem: str) -> Component | None:
    candidates = [
        component
        for component in blueprint.components.values()
        if component.type in {"application", "service"} and _normalized_stem(component.name) == project_stem
    ]
    if not candidates:
        return None
    canonical_id = _select_canonical_component(candidates, project_stem)
    return blueprint.components.get(canonical_id)


def _select_canonical_component(components: list[Component], project_stem: str) -> str:
    ordered = sorted(
        components,
        key=lambda item: (
            _normalized_stem(item.name) != project_stem,
            item.type != "application",
            -len(item.name),
            item.id,
        ),
    )
    return ordered[0].id


def _normalized_stem(value: str) -> str:
    lowered = value.lower()
    for suffix in ("_service", "-service", "_upstream", "-upstream", " service", " upstream"):
        if lowered.endswith(suffix):
            lowered = lowered[: -len(suffix)]
    return re.sub(r"[^a-z0-9]+", "", lowered)


def _kubernetes_metadata(kind: str, document: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if kind != "Service":
        return metadata

    selectors = dict(re.findall(r"^\s{2,}([A-Za-z0-9._/-]+):\s*([A-Za-z0-9._-]+)\s*$", _service_selector_block(document), flags=re.MULTILINE))
    if selectors:
        metadata["selectors"] = selectors
    return metadata


def _service_selector_block(document: str) -> str:
    match = re.search(r"selector:\s*\n((?:\s{4,}.+\n?)*)", document, flags=re.MULTILINE)
    if not match:
        return ""
    return match.group(1)


def _link_kubernetes_services(blueprint: Blueprint) -> None:
    app_components = [
        component for component in blueprint.components.values() if component.type in {"application", "service"}
    ]
    for component in list(blueprint.components.values()):
        if component.technology != "kubernetes-service":
            continue

        target = _resolve_kubernetes_service_target(component, app_components)
        if target is None:
            continue

        blueprint.add_relationship(
            Relationship(
                source=component.id,
                target=target.id,
                type="exposes",
                label="exposes",
                metadata={"source_path": component.source_path or ""},
            )
        )


def _resolve_kubernetes_service_target(service_component: Component, app_components: list[Component]) -> Component | None:
    selectors = service_component.metadata.get("selectors", {})
    if isinstance(selectors, dict):
        selector_values = {_normalized_stem(str(value)) for value in selectors.values()}
        for app_component in app_components:
            app_stem = _normalized_stem(app_component.name)
            if app_stem in selector_values:
                return app_component
            aliases = app_component.metadata.get("aliases", [])
            if isinstance(aliases, list) and any(_normalized_stem(str(alias)) in selector_values for alias in aliases):
                return app_component

    service_stem = _normalized_stem(service_component.name)
    for app_component in app_components:
        candidate_stems = {_normalized_stem(app_component.name)}
        aliases = app_component.metadata.get("aliases", [])
        if isinstance(aliases, list):
            candidate_stems.update(_normalized_stem(str(alias)) for alias in aliases)
        if service_stem in candidate_stems:
            return app_component
    return None


def key_lower_to_name(key: str) -> str:
    base = key.lower().removesuffix("_url").removesuffix("_host")
    return base.replace("_", "-")
