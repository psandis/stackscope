from __future__ import annotations

import base64
import json
from html import escape
from functools import lru_cache
from pathlib import Path, PurePath

from .model import Blueprint
from .persistence import ViewState, build_default_view_state


def render_json(blueprint: Blueprint) -> str:
    return json.dumps(blueprint.to_dict(), indent=2)


def render_markdown(blueprint: Blueprint) -> str:
    lines = [
        f"# Architecture Summary: {blueprint.name}",
        "",
        f"Root path: `{blueprint.root_path}`",
        "",
        "## Components",
        "",
        "| ID | Name | Type | Technology | Source |",
        "| --- | --- | --- | --- | --- |",
    ]

    for component in sorted(blueprint.components.values(), key=lambda item: item.id):
        lines.append(
            f"| {component.id} | {component.name} | {component.type} | {component.technology or ''} | {component.source_path or ''} |"
        )

    lines.extend(["", "## Relationships", "", "| Source | Target | Type | Label |", "| --- | --- | --- | --- |"])
    for relationship in blueprint.relationships:
        lines.append(
            f"| {relationship.source} | {relationship.target} | {relationship.type} | {relationship.label or ''} |"
        )

    return "\n".join(lines)


def render_mermaid(blueprint: Blueprint) -> str:
    lines = ["graph TD"]
    groups = {
        "Delivery": {"pipeline", "automation"},
        "Application": {"application", "service", "gateway"},
        "Data": {"datastore", "storage"},
        "Platform": {"cloud", "infrastructure", "configuration"},
        "Edge": {"integration", "library"},
    }

    grouped_ids: set[str] = set()
    for title, component_types in groups.items():
        members = [
            component
            for component in sorted(blueprint.components.values(), key=lambda item: item.id)
            if component.type in component_types
        ]
        if not members:
            continue
        lines.append(f"  subgraph {title}")
        for component in members:
            label = _mermaid_component_label(component)
            lines.append(f"    {_mermaid_node(component, label)}")
            grouped_ids.add(component.id)
        lines.append("  end")

    for component in sorted(blueprint.components.values(), key=lambda item: item.id):
        if component.id in grouped_ids:
            continue
        label = _mermaid_component_label(component)
        lines.append(f"  {_mermaid_node(component, label)}")

    for relationship in blueprint.relationships:
        label = relationship.label or relationship.type
        lines.append(f"  {relationship.source} -->|{label}| {relationship.target}")

    classes: dict[str, list[str]] = {}
    for component in sorted(blueprint.components.values(), key=lambda item: item.id):
        for class_name in _mermaid_component_classes(component):
            classes.setdefault(class_name, []).append(component.id)

    class_defs = {
        "cloud-aws": "fill:#fff7ed,stroke:#c2410c,color:#9a3412,stroke-width:1.5px",
        "cloud-azure": "fill:#eff6ff,stroke:#1d4ed8,color:#1e3a8a,stroke-width:1.5px",
        "cloud-gcp": "fill:#ecfeff,stroke:#0891b2,color:#155e75,stroke-width:1.5px",
        "cloud-generic": "fill:#f8fafc,stroke:#64748b,color:#334155,stroke-width:1.5px",
        "storage-node": "fill:#effdf5,stroke:#16a34a,color:#14532d,stroke-width:1.5px",
        "datastore-node": "fill:#f0fdf4,stroke:#22c55e,color:#166534,stroke-width:1.5px",
        "gateway-node": "fill:#eff6ff,stroke:#2563eb,color:#1d4ed8,stroke-width:1.5px",
    }
    for class_name, definition in class_defs.items():
        if class_name in classes:
            lines.append(f"  classDef {class_name} {definition}")
    for class_name, component_ids in classes.items():
        if component_ids:
            lines.append(f"  class {','.join(component_ids)} {class_name}")

    return "\n".join(lines)


def render_svg(blueprint: Blueprint, view_state: ViewState | None = None) -> str:
    resolved_view = view_state or build_default_view_state(blueprint)
    visible_components = sorted(blueprint.components.values(), key=lambda item: item.id)
    positions, width, height, group_titles = _svg_layout(blueprint, resolved_view)
    relationship_items = [
        {
            "key": f"{relationship.source}|{relationship.type}|{relationship.target}",
            "source": relationship.source,
            "target": relationship.target,
            "label": relationship.label or relationship.type,
        }
        for relationship in blueprint.relationships
        if relationship.source in positions and relationship.target in positions
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(blueprint.name)} architecture diagram">',
        "<defs>",
        '<marker id="arrowhead" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#47667b"></path></marker>',
        "</defs>",
        "<style>",
        ".group-title { font: 700 12px ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; letter-spacing: 0.14em; text-transform: uppercase; fill: #4f6775; }",
        ".group-band { fill: rgba(255,255,255,0.38); stroke: rgba(148,163,184,0.24); stroke-dasharray: 6 8; }",
        ".edge-path { fill: none; stroke: #47667b; stroke-width: 1.8; marker-end: url(#arrowhead); }",
        ".edge-label { font: 11px ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #3f5563; }",
        ".node-label { font: 700 14px ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #10212b; }",
        ".node-subtitle { font: 11px ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #4f6775; }",
        ".provider-badge { font: 700 10px ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #355468; }",
        "</style>",
    ]

    for group in group_titles:
        parts.append(f'<text class="group-title" x="{group["x"]}" y="28">{escape(group["title"])}</text>')
        parts.append(f'<rect class="group-band" x="{group["x"] - 16}" y="40" width="224" height="{height - 88}" rx="24"></rect>')

    for relationship in relationship_items:
        source = positions[relationship["source"]]
        target = positions[relationship["target"]]
        start_x = source["x"] + source["width"]
        start_y = source["center_y"]
        end_x = target["x"]
        end_y = target["center_y"]
        curve = max(40, abs(end_x - start_x) * 0.35)
        path_d = f"M {start_x} {start_y} C {start_x + curve} {start_y}, {end_x - curve} {end_y}, {end_x} {end_y}"
        label_x = round((source["x"] + source["width"] + target["x"]) / 2)
        label_y = round((source["center_y"] + target["center_y"]) / 2) - 8
        parts.append(f'<path class="edge-path" d="{path_d}"></path>')
        parts.append(f'<text class="edge-label" x="{label_x}" y="{label_y}" text-anchor="middle">{escape(relationship["label"])}</text>')

    for component in visible_components:
        position = positions.get(component.id)
        if position is None:
            continue
        parts.append(_svg_node_markup(component, position))

    parts.append("</svg>")
    return "\n".join(parts)


def render_html(blueprint: Blueprint, view_state: ViewState | None = None) -> str:
    mermaid = render_mermaid(blueprint)
    title = escape(f"Stackscope Architecture: {blueprint.name}")
    summary = escape(
        f"{len(blueprint.components)} components, {len(blueprint.relationships)} relationships"
    )
    blueprint_name_json = json.dumps(blueprint.name)
    blueprint_root_json = json.dumps(blueprint.root_path)
    blueprint_root_display = escape(_display_root_path(blueprint.root_path))
    resolved_view = view_state or build_default_view_state(blueprint)
    initial_view_payload = json.dumps(resolved_view.to_dict())
    component_payload = json.dumps(
        [
            {
                "id": component.id,
                "name": component.name,
                "display_name": _component_display_name(component),
                "type": component.type,
                "technology": component.technology or "",
                "provider": _component_provider(component),
                "icon_uri": _icon_data_uri(component),
                "source_path": component.source_path or "",
                "tags": component.tags,
                "metadata": component.metadata,
            }
            for component in sorted(blueprint.components.values(), key=lambda item: (item.type, item.name))
        ]
    )
    relationship_payload = json.dumps(
        [
            {
                "key": f"{relationship.source}|{relationship.type}|{relationship.target}",
                "source": relationship.source,
                "target": relationship.target,
                "type": relationship.type,
                "label": relationship.label or relationship.type,
                "metadata": relationship.metadata,
            }
            for relationship in blueprint.relationships
        ]
    )
    evidence_payload = json.dumps(blueprint.evidence)
    component_type_counts: dict[str, int] = {}
    source_tag_counts: dict[str, int] = {}
    for component in blueprint.components.values():
        component_type_counts[component.type] = component_type_counts.get(component.type, 0) + 1
        for tag in component.tags:
            source_tag_counts[tag] = source_tag_counts.get(tag, 0) + 1
    type_pills = "".join(
        f'<li><button class="type-filter" type="button" data-component-type="{escape(component_type)}"><span>{escape(component_type)}</span><strong>{count}</strong></button></li>'
        for component_type, count in sorted(component_type_counts.items())
    )
    source_pills = "".join(
        f'<li><button class="source-filter" type="button" data-source-tag="{escape(source_tag)}"><span>{escape(source_tag)}</span><strong>{count}</strong></button></li>'
        for source_tag, count in sorted(source_tag_counts.items())
    )
    component_items = "".join(
        (
            f'<li><button class="component-item" type="button" data-component-id="{escape(component.id)}">'
            f"<strong>{escape(component.name)}</strong>"
            f"<span>{escape(component.type)}"
            + (f" · {escape(component.technology)}" if component.technology else "")
            + "</span>"
            "</button></li>"
        )
        for component in sorted(blueprint.components.values(), key=lambda item: (item.type, item.name))
    )
    relationship_items = "".join(
        (
            f'<li><button class="relationship-item" type="button" data-relationship-key="{escape(f"{relationship.source}|{relationship.type}|{relationship.target}")}">'
            f"<strong>{escape(relationship.source)}</strong>"
            f"<span>{escape(relationship.label or relationship.type)}</span>"
            f"<strong>{escape(relationship.target)}</strong>"
            "</button></li>"
        )
        for relationship in blueprint.relationships[:12]
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef4f8;
      --bg-accent: #d9e8f2;
      --panel: rgba(250, 253, 255, 0.88);
      --panel-strong: #ffffff;
      --ink: #10212b;
      --muted: #4f6775;
      --line: #bfd0db;
      --accent: #0f766e;
      --accent-2: #2563eb;
      --shadow: rgba(28, 55, 74, 0.12);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        linear-gradient(rgba(37, 99, 235, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(37, 99, 235, 0.05) 1px, transparent 1px),
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.16) 0, transparent 24%),
        radial-gradient(circle at top right, rgba(37, 99, 235, 0.14) 0, transparent 28%),
        linear-gradient(180deg, #f7fbfd 0%, var(--bg) 100%);
      background-size: 32px 32px, 32px 32px, auto, auto, auto;
      min-height: 100vh;
    }}
    main {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 28px 20px 44px;
    }}
    .hero {{
      display: grid;
      gap: 10px;
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 3vw, 3.4rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
      font-weight: 800;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 0.98rem;
      max-width: 60ch;
    }}
    .panel {{
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(246, 250, 252, 0.94)),
        var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      box-shadow:
        0 16px 48px var(--shadow),
        inset 0 1px 0 rgba(255, 255, 255, 0.7);
      backdrop-filter: blur(10px);
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .workspace-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .workspace-actions {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .action-group {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .zoom-readout {{
      min-width: 3.5rem;
      text-align: center;
      color: var(--muted);
      font-size: 0.82rem;
      font-variant-numeric: tabular-nums;
    }}
    .workspace-title {{
      margin: 0;
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 700;
    }}
    .sidebar-toggle {{
      border: 1px solid rgba(37, 99, 235, 0.18);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(232, 242, 248, 0.96));
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 12px;
      font: inherit;
      font-size: 0.86rem;
      cursor: pointer;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
    }}
    .secondary-action {{
      border: 1px solid rgba(15, 118, 110, 0.16);
      background: rgba(255, 255, 255, 0.76);
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 12px;
      font: inherit;
      font-size: 0.86rem;
      cursor: pointer;
    }}
    .status-chip {{
      min-height: 1.5rem;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.08);
      border: 1px solid rgba(15, 118, 110, 0.12);
      color: var(--accent);
      font-size: 0.78rem;
      display: inline-flex;
      align-items: center;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      border-radius: 999px;
      background: linear-gradient(180deg, rgba(15, 118, 110, 0.08), rgba(37, 99, 235, 0.06));
      border: 1px solid rgba(37, 99, 235, 0.12);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 16px;
      align-items: start;
    }}
    .layout.is-sidebar-collapsed {{
      grid-template-columns: minmax(0, 1fr);
    }}
    .diagram {{
      overflow: auto;
      padding: 12px;
      min-height: 460px;
      border-radius: 18px;
      border: 1px solid rgba(191, 208, 219, 0.8);
      background:
        linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
        linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(242, 248, 251, 0.94));
      background-size: 24px 24px, 24px 24px, auto;
      position: relative;
    }}
    .coordinate-hud {{
      position: sticky;
      top: 0;
      left: 0;
      z-index: 3;
      display: inline-flex;
      gap: 10px;
      align-items: center;
      margin: 0 0 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(191, 208, 219, 0.9);
      color: var(--muted);
      font-size: 0.78rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      backdrop-filter: blur(8px);
    }}
    .coordinate-hud strong {{
      color: var(--ink);
      font-weight: 700;
    }}
    .diagram-inner {{
      display: inline-block;
      min-width: 100%;
      transform-origin: top left;
    }}
    #diagram-root {{
      min-width: 960px;
    }}
    .sidebar {{
      display: grid;
      gap: 12px;
    }}
    .sidebar[hidden] {{
      display: none !important;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(242, 248, 251, 0.92));
      border: 1px solid rgba(191, 208, 219, 0.84);
      border-radius: 18px;
      padding: 14px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
    }}
    .type-list,
    .entity-list {{
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    .type-list li,
    .entity-list li {{
      padding: 8px 0;
      border-top: 1px solid rgba(191, 208, 219, 0.65);
    }}
    .type-list li:first-child,
    .entity-list li:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .type-list strong,
    .entity-list strong {{
      font-size: 0.92rem;
      font-weight: 700;
      color: var(--ink);
    }}
    .type-filter,
    .source-filter,
    .component-item {{
      width: 100%;
      border: 0;
      background: transparent;
      padding: 0;
      color: inherit;
      text-align: left;
      cursor: pointer;
    }}
    .relationship-item {{
      width: 100%;
      border: 0;
      background: transparent;
      padding: 0;
      color: inherit;
      text-align: left;
      cursor: pointer;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 4px;
    }}
    .type-filter {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
    }}
    .source-filter {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
    }}
    .component-item {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 2px;
    }}
    .type-filter.is-active span,
    .source-filter.is-active span,
    .component-item.is-active strong,
    .relationship-item.is-active strong {{
      color: var(--accent-2);
    }}
    .entity-list span,
    .type-list span {{
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .entity-list li {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 2px;
      justify-content: start;
    }}
    .relationship-list li {{
      grid-template-columns: minmax(0, 1fr);
      gap: 4px;
    }}
    .relationship-list span {{
      display: inline-flex;
      width: fit-content;
      padding: 3px 8px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.08);
      border: 1px solid rgba(15, 118, 110, 0.12);
      color: var(--accent);
    }}
    .search {{
      width: 100%;
      border: 1px solid rgba(191, 208, 219, 0.84);
      border-radius: 12px;
      padding: 10px 12px;
      font: inherit;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.8);
      margin-bottom: 10px;
    }}
    .search:focus {{
      outline: 2px solid rgba(37, 99, 235, 0.18);
      border-color: rgba(37, 99, 235, 0.42);
    }}
    .inspector-empty {{
      color: var(--muted);
      font-size: 0.9rem;
      margin: 0;
    }}
    .inspector-title {{
      margin: 0 0 4px;
      font-size: 1.05rem;
      font-weight: 700;
    }}
    .inspector-subtitle {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .inspector-meta {{
      display: grid;
      gap: 8px;
      margin: 0;
    }}
    .inspector-meta div {{
      display: grid;
      gap: 2px;
    }}
    .inspector-meta dt {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .inspector-meta dd {{
      margin: 0;
      font-size: 0.9rem;
      color: var(--ink);
      word-break: break-word;
    }}
    .inspector-section {{
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid rgba(191, 208, 219, 0.7);
    }}
    .inspector-section h4 {{
      margin: 0 0 8px;
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
    }}
    .inspector-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 8px;
    }}
    .inspector-list li {{
      display: grid;
      gap: 4px;
      padding: 8px 10px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.62);
      border: 1px solid rgba(191, 208, 219, 0.65);
    }}
    .inspector-list code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .diagram svg .node.is-selected rect,
    .diagram svg .node.is-selected path,
    .diagram svg .node.is-selected polygon,
    .diagram svg .node.is-selected ellipse,
    .diagram svg .node.is-selected circle {{
      stroke: #2563eb !important;
      stroke-width: 3px !important;
      filter: drop-shadow(0 0 12px rgba(37, 99, 235, 0.18));
    }}
    .diagram svg .node.is-dragging {{
      opacity: 0.85;
    }}
    .diagram svg .node.is-dimmed,
    .diagram svg .edgePath.is-dimmed,
    .diagram svg .edgeLabel.is-dimmed {{
      opacity: 0.22;
    }}
    .diagram svg .edgePath.is-selected path {{
      stroke: #0f766e !important;
      stroke-width: 2.5px !important;
    }}
    .diagram svg .edgeLabel.is-selected span,
    .diagram svg .edgeLabel.is-selected p {{
      color: #0f766e !important;
      font-weight: 700;
    }}
    .toggle-row {{
      display: grid;
      gap: 8px;
    }}
    .toggle {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--ink);
      font-size: 0.88rem;
    }}
    .toggle input {{
      accent-color: var(--accent-2);
    }}
    .source {{
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.85rem;
      white-space: pre-wrap;
    }}
    .render-error {{
      margin: 0;
      padding: 16px;
      border-radius: 14px;
      background: #fff1f0;
      color: #8a1c1c;
      border: 1px solid #f0b6b2;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: pre-wrap;
    }}
    @media (max-width: 900px) {{
      main {{
        padding: 18px 14px 28px;
      }}
      .panel {{
        padding: 16px;
        border-radius: 18px;
      }}
      .layout {{
        grid-template-columns: 1fr;
      }}
      #diagram-root {{
        min-width: 760px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>{escape(blueprint.name)}</h1>
      <p class="subtitle">Architecture view generated from the Stackscope blueprint model.</p>
    </section>
    <section class="panel">
      <div class="meta">
        <span class="pill">{summary}</span>
        <span class="pill">{blueprint_root_display}</span>
      </div>
      <div class="workspace-bar">
        <p class="workspace-title">Explorer Workspace</p>
        <div class="workspace-actions">
          <span id="share-status" class="status-chip" aria-live="polite">Ready</span>
          <div class="action-group">
            <button id="copy-link" class="secondary-action" type="button">Copy Link</button>
            <button id="reset-view" class="secondary-action" type="button">Reset View</button>
          </div>
          <div class="action-group">
            <button id="zoom-out" class="secondary-action" type="button">-</button>
            <span id="zoom-readout" class="zoom-readout">100%</span>
            <button id="zoom-in" class="secondary-action" type="button">+</button>
            <button id="zoom-reset" class="secondary-action" type="button">Reset Zoom</button>
          </div>
          <div class="action-group">
            <button id="export-mermaid" class="secondary-action" type="button">Export Mermaid</button>
            <button id="export-html" class="secondary-action" type="button">Export HTML</button>
            <button id="export-view" class="secondary-action" type="button">Export View</button>
            <button id="export-json" class="secondary-action" type="button">Export JSON</button>
          </div>
          <button id="sidebar-toggle" class="sidebar-toggle" type="button" aria-expanded="true">Hide Tools</button>
        </div>
      </div>
      <div class="layout">
        <div class="diagram">
          <div id="coordinate-hud" class="coordinate-hud" aria-live="polite">
            <span>Node X <strong id="coord-x">-</strong></span>
            <span>Node Y <strong id="coord-y">-</strong></span>
          </div>
          <div id="diagram-inner" class="diagram-inner">
            <div id="diagram-root" aria-label="architecture-diagram"></div>
          </div>
        </div>
        <aside id="preview-sidebar" class="sidebar">
          <section class="card">
            <h2>Component Types</h2>
            <ul class="type-list">{type_pills}</ul>
          </section>
          <section class="card">
            <h2>Sources</h2>
            <ul class="type-list">{source_pills}</ul>
          </section>
          <section class="card">
            <h2>View</h2>
            <div class="toggle-row">
              <label class="toggle"><input id="toggle-hide-libraries" type="checkbox" /> Hide libraries</label>
              <label class="toggle"><input id="toggle-hide-delivery" type="checkbox" /> Hide CI and automation</label>
            </div>
          </section>
          <section class="card">
            <h2>Components</h2>
            <input class="search" id="component-search" type="search" placeholder="Filter components" />
            <ul class="entity-list">{component_items}</ul>
          </section>
          <section class="card">
            <h2>Inspector</h2>
            <div id="inspector-panel">
              <p class="inspector-empty">Select a component to inspect its metadata and relationships.</p>
            </div>
          </section>
          <section class="card">
            <h2>Relationships</h2>
            <ul class="entity-list relationship-list">{relationship_items}</ul>
          </section>
        </aside>
      </div>
      <div class="source">Generated from scan-derived blueprint data. Preview uses an explicit SVG layout and Mermaid remains available as an export format.</div>
    </section>
  </main>
  <script>
    const components = {component_payload};
    const relationships = {relationship_payload};
    const evidence = {evidence_payload};
    const initialView = {initial_view_payload};
    const groups = [
      ["Delivery", new Set(["pipeline", "automation"])],
      ["Application", new Set(["application", "service", "gateway"])],
      ["Data", new Set(["datastore", "storage"])],
      ["Platform", new Set(["cloud", "infrastructure", "configuration"])],
      ["Edge", new Set(["integration", "library"])]
    ];
    const diagramInner = document.getElementById("diagram-inner");
    const root = document.getElementById("diagram-root");
    const coordX = document.getElementById("coord-x");
    const coordY = document.getElementById("coord-y");
    const layout = document.querySelector(".layout");
    const sidebar = document.getElementById("preview-sidebar");
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const copyLinkButton = document.getElementById("copy-link");
    const resetViewButton = document.getElementById("reset-view");
    const exportMermaidButton = document.getElementById("export-mermaid");
    const exportHtmlButton = document.getElementById("export-html");
    const exportViewButton = document.getElementById("export-view");
    const exportJsonButton = document.getElementById("export-json");
    const zoomOutButton = document.getElementById("zoom-out");
    const zoomInButton = document.getElementById("zoom-in");
    const zoomResetButton = document.getElementById("zoom-reset");
    const zoomReadout = document.getElementById("zoom-readout");
    const shareStatus = document.getElementById("share-status");
    const inspectorPanel = document.getElementById("inspector-panel");
    const searchInput = document.getElementById("component-search");
    const hideLibrariesToggle = document.getElementById("toggle-hide-libraries");
    const hideDeliveryToggle = document.getElementById("toggle-hide-delivery");
    const componentButtons = Array.from(document.querySelectorAll(".component-item"));
    const typeButtons = Array.from(document.querySelectorAll(".type-filter"));
    const sourceButtons = Array.from(document.querySelectorAll(".source-filter"));
    const relationshipButtons = Array.from(document.querySelectorAll(".relationship-item"));
    const params = new URLSearchParams(window.location.search);
    const cloneSeedMap = (source) => new Map(Array.from(source.entries()).map(([id, node]) => [id, {{ ...node }}]));
    const initialNodeSeeds = new Map((initialView.nodes || []).map((node) => [node.id, {{ ...node }}]));
    let seededViewNodes = cloneSeedMap(initialNodeSeeds);
    let selectedComponentId = params.get("component");
    let activeTypeFilter = params.get("type");
    let activeSourceFilter = params.get("source");
    let selectedRelationshipKey = params.get("relationship");
    let isSidebarCollapsed = params.get("tools") === "0";
    hideLibrariesToggle.checked = params.get("hideLibraries") === "1";
    hideDeliveryToggle.checked = params.get("hideDelivery") === "1";
    let currentSvg = null;
    let layoutPositions = new Map();
    let renderCounter = 0;
    let dragState = null;
    let suppressNodeClick = false;
    let pendingRender = 0;
    const blueprintName = {blueprint_name_json};
    const blueprintRootPath = {blueprint_root_json};
    let statusTimer = null;
    let zoomLevel = Number.parseFloat(params.get("zoom") || "1");
    if (!Number.isFinite(zoomLevel) || zoomLevel <= 0) zoomLevel = 1;

    function setStatus(message) {{
      shareStatus.textContent = message;
      if (statusTimer) window.clearTimeout(statusTimer);
      statusTimer = window.setTimeout(() => {{
        shareStatus.textContent = "Ready";
      }}, 1600);
    }}

    function syncUrl() {{
      const next = new URLSearchParams();
      if (selectedComponentId) next.set("component", selectedComponentId);
      if (selectedRelationshipKey) next.set("relationship", selectedRelationshipKey);
      if (activeTypeFilter) next.set("type", activeTypeFilter);
      if (activeSourceFilter) next.set("source", activeSourceFilter);
      if (searchInput.value.trim()) next.set("search", searchInput.value.trim());
      if (isSidebarCollapsed) next.set("tools", "0");
      if (hideLibrariesToggle.checked) next.set("hideLibraries", "1");
      if (hideDeliveryToggle.checked) next.set("hideDelivery", "1");
      if (Math.abs(zoomLevel - 1) > 0.001) next.set("zoom", zoomLevel.toFixed(2));
      const query = next.toString();
      const nextUrl = query ? (window.location.pathname + "?" + query) : window.location.pathname;
      window.history.replaceState(null, "", nextUrl);
    }}

    function syncZoom() {{
      const clamped = Math.min(2.5, Math.max(0.4, zoomLevel));
      zoomLevel = Math.round(clamped * 100) / 100;
      diagramInner.style.transform = "scale(" + zoomLevel + ")";
      zoomReadout.textContent = Math.round(zoomLevel * 100) + "%";
    }}

    function syncCoordinateHud() {{
      if (selectedComponentId && layoutPositions.has(selectedComponentId)) {{
        const position = layoutPositions.get(selectedComponentId);
        coordX.textContent = String(position.x);
        coordY.textContent = String(position.y);
        return;
      }}
      coordX.textContent = "-";
      coordY.textContent = "-";
    }}

    function syncSidebarState() {{
      sidebar.hidden = isSidebarCollapsed;
      layout.classList.toggle("is-sidebar-collapsed", isSidebarCollapsed);
      sidebarToggle.textContent = isSidebarCollapsed ? "Show Tools" : "Hide Tools";
      sidebarToggle.setAttribute("aria-expanded", String(!isSidebarCollapsed));
    }}

    function renderInspector(component, relationship) {{
      if (relationship) {{
        const source = components.find((item) => item.id === relationship.source);
        const target = components.find((item) => item.id === relationship.target);
        inspectorPanel.innerHTML = `
          <h3 class="inspector-title">${{source ? source.name : relationship.source}} → ${{target ? target.name : relationship.target}}</h3>
          <p class="inspector-subtitle">${{relationship.label}}</p>
          <dl class="inspector-meta">
            <div><dt>Source</dt><dd>${{relationship.source}}</dd></div>
            <div><dt>Target</dt><dd>${{relationship.target}}</dd></div>
            <div><dt>Type</dt><dd>${{relationship.type}}</dd></div>
            <div><dt>Evidence</dt><dd>${{relationship.metadata && relationship.metadata.source_path ? relationship.metadata.source_path : "Unknown"}}</dd></div>
          </dl>
        `;
        return;
      }}
      if (!component) {{
        inspectorPanel.innerHTML = '<p class="inspector-empty">Select a component to inspect its metadata and relationships.</p>';
        return;
      }}
      const outgoing = relationships.filter((relationship) => relationship.source === component.id);
      const incoming = relationships.filter((relationship) => relationship.target === component.id);
      const supportingEvidence = evidence.filter((item) => item.details && item.details.component_id === component.id);
      const layoutPosition = layoutPositions.get(component.id) || null;
      const metadata = component.metadata && Object.keys(component.metadata).length ? JSON.stringify(component.metadata, null, 2) : "None";
      const relationshipMarkup = (items, direction) => {{
        if (!items.length) return '<p class="inspector-empty">None</p>';
        return `<ul class="inspector-list">${{items.map((item) => `
          <li>
            <strong>${{direction === "out" ? item.target : item.source}}</strong>
            <span>${{item.label}}</span>
            <code>${{item.metadata && item.metadata.source_path ? item.metadata.source_path : "Unknown source"}}</code>
          </li>
        `).join("")}}</ul>`;
      }};
      const evidenceMarkup = supportingEvidence.length
        ? `<ul class="inspector-list">${{supportingEvidence.map((item) => `
            <li>
              <strong>${{item.kind}}</strong>
              <code>${{item.source_path}}</code>
            </li>
          `).join("")}}</ul>`
        : '<p class="inspector-empty">No direct evidence entries recorded.</p>';
      inspectorPanel.innerHTML = `
        <h3 class="inspector-title">${{component.name}}</h3>
        <p class="inspector-subtitle">${{component.type}}${{component.technology ? ` · ${{component.technology}}` : ""}}</p>
        <dl class="inspector-meta">
          <div><dt>Source</dt><dd>${{component.source_path || "Unknown"}}</dd></div>
          <div><dt>Tags</dt><dd>${{component.tags.length ? component.tags.join(", ") : "None"}}</dd></div>
          <div><dt>Outgoing</dt><dd>${{outgoing.length}}</dd></div>
          <div><dt>Incoming</dt><dd>${{incoming.length}}</dd></div>
          <div><dt>Layout</dt><dd>${{layoutPosition ? `x=${{layoutPosition.x}}, y=${{layoutPosition.y}}` : "Not captured"}}</dd></div>
          <div><dt>Metadata</dt><dd><pre class="render-error" style="margin:0; background:#f7fbff; color:#29465a; border-color:#bfd0db;">${{metadata}}</pre></dd></div>
        </dl>
        <section class="inspector-section">
          <h4>Outgoing</h4>
          ${{relationshipMarkup(outgoing, "out")}}
        </section>
        <section class="inspector-section">
          <h4>Incoming</h4>
          ${{relationshipMarkup(incoming, "in")}}
        </section>
        <section class="inspector-section">
          <h4>Evidence</h4>
          ${{evidenceMarkup}}
        </section>
      `;
    }}

    function escapeHtml(value) {{
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }}

    function nodeMap() {{
      const map = new Map();
      if (!currentSvg) return map;
      currentSvg.querySelectorAll("g.node").forEach((node) => {{
        if (node.dataset.componentId) map.set(node.dataset.componentId, node);
      }});
      return map;
    }}

    function edgeElementsFor(componentId) {{
      if (!currentSvg) return {{ edges: [], labels: [] }};
      const edgePaths = Array.from(currentSvg.querySelectorAll("g.edgePath"));
      const edgeLabels = Array.from(currentSvg.querySelectorAll("g.edgeLabel"));
      return {{
        edges: edgePaths.filter((edge) => edge.dataset.source === componentId || edge.dataset.target === componentId),
        labels: edgeLabels.filter((label) => label.dataset.source === componentId || label.dataset.target === componentId),
      }};
    }}

    function filteredComponents() {{
      const searchTerm = searchInput.value.trim().toLowerCase();
      return components.filter((component) => {{
        const matchesSearch = !searchTerm || `${{component.name}} ${{component.type}} ${{component.technology}} ${{component.source_path}}`.toLowerCase().includes(searchTerm);
        const matchesType = !activeTypeFilter || component.type === activeTypeFilter;
        const matchesSource = !activeSourceFilter || component.tags.includes(activeSourceFilter);
        const matchesLibraries = !hideLibrariesToggle.checked || component.type !== "library";
        const matchesDelivery = !hideDeliveryToggle.checked || !["pipeline", "automation"].includes(component.type);
        return matchesSearch && matchesType && matchesSource && matchesLibraries && matchesDelivery;
      }});
    }}

    function filteredComponentIds() {{
      return new Set(filteredComponents().map((component) => component.id));
    }}

    function visibleRelationships() {{
      const visibleIds = filteredComponentIds();
      return relationships.filter((relationship) => visibleIds.has(relationship.source) && visibleIds.has(relationship.target));
    }}

    function visibleEvidence() {{
      const visibleIds = filteredComponentIds();
      return evidence.filter((item) => {{
        const componentId = item.details && item.details.component_id;
        return !componentId || visibleIds.has(componentId);
      }});
    }}

    function buildGraphDefinition() {{
      const visibleComponents = filteredComponents();
      const visibleIds = new Set(visibleComponents.map((component) => component.id));
      const visibleRelationshipsList = relationships.filter((relationship) => visibleIds.has(relationship.source) && visibleIds.has(relationship.target));
      const lines = ["graph TD"];
      const groupedIds = new Set();

      for (const [title, componentTypes] of groups) {{
        const members = visibleComponents
          .filter((component) => componentTypes.has(component.type))
          .sort((left, right) => left.id.localeCompare(right.id));
        if (!members.length) continue;
        lines.push(`  subgraph ${{title}}`);
        for (const component of members) {{
          const label = `${{component.display_name}}\\n(${{component.type}})`;
          lines.push(`    ${{nodeDeclaration(component, label)}}`);
          groupedIds.add(component.id);
        }}
        lines.push("  end");
      }}

      for (const component of visibleComponents.sort((left, right) => left.id.localeCompare(right.id))) {{
        if (groupedIds.has(component.id)) continue;
        const label = `${{component.display_name}}\\n(${{component.type}})`;
        lines.push(`  ${{nodeDeclaration(component, label)}}`);
      }}

      for (const relationship of visibleRelationshipsList) {{
        lines.push(`  ${{relationship.source}} -->|${{relationship.label}}| ${{relationship.target}}`);
      }}

      const classMap = new Map();
      for (const component of visibleComponents) {{
        componentClasses(component).forEach((className) => {{
          if (!classMap.has(className)) classMap.set(className, []);
          classMap.get(className).push(component.id);
        }});
      }}
      const classDefs = {{
        "cloud-aws": "fill:#fff7ed,stroke:#c2410c,color:#9a3412,stroke-width:1.5px",
        "cloud-azure": "fill:#eff6ff,stroke:#1d4ed8,color:#1e3a8a,stroke-width:1.5px",
        "cloud-gcp": "fill:#ecfeff,stroke:#0891b2,color:#155e75,stroke-width:1.5px",
        "cloud-generic": "fill:#f8fafc,stroke:#64748b,color:#334155,stroke-width:1.5px",
        "storage-node": "fill:#effdf5,stroke:#16a34a,color:#14532d,stroke-width:1.5px",
        "datastore-node": "fill:#f0fdf4,stroke:#22c55e,color:#166534,stroke-width:1.5px",
        "gateway-node": "fill:#eff6ff,stroke:#2563eb,color:#1d4ed8,stroke-width:1.5px"
      }};
      Object.entries(classDefs).forEach(([className, definition]) => {{
        if (classMap.has(className)) lines.push(`  classDef ${{className}} ${{definition}}`);
      }});
      classMap.forEach((ids, className) => {{
        if (ids.length) lines.push(`  class ${{ids.join(",")}} ${{className}}`);
      }});

      return lines.join("\\n");
    }}

    function currentViewStatePayload() {{
      return {{
        blueprint_name: blueprintName,
        root_path: blueprintRootPath,
        nodes: Array.from(layoutPositions.entries()).map(([id, position]) => ({{
          id,
          x: position.x,
          y: position.y,
        }})),
        hidden_components: [],
        metadata: {{
          exported_from: "preview",
          zoom: zoomLevel,
        }},
      }};
    }}

    function currentViewPayload() {{
      return {{
        name: blueprintName,
        root_path: blueprintRootPath,
        components: filteredComponents(),
        relationships: visibleRelationships(),
        evidence: visibleEvidence(),
      }};
    }}

    function currentViewBundle() {{
      return {{
        blueprint: currentViewPayload(),
        view_state: currentViewStatePayload(),
      }};
    }}

    function componentClasses(component) {{
      const classes = [];
      if (component.type === "gateway") classes.push("gateway-node");
      if (component.type === "storage") classes.push("storage-node");
      if (component.type === "datastore") classes.push("datastore-node");
      if (component.type === "cloud") {{
        if (component.provider === "aws") classes.push("cloud-aws");
        else if (component.provider === "azure") classes.push("cloud-azure");
        else if (component.provider === "gcp") classes.push("cloud-gcp");
        else classes.push("cloud-generic");
      }}
      return classes;
    }}

    function nodeDeclaration(component, label) {{
      if (component.type === "cloud") return `${{component.id}}(["${{label}}"])`;
      if (component.type === "storage") return `${{component.id}}[/"${{label}}"/]`;
      if (component.type === "datastore") return `${{component.id}}[("${{label}}")]`;
      if (component.type === "gateway") return `${{component.id}}{{"${{label}}"}}`;
      return `${{component.id}}["${{label}}"]`;
    }}

    function captureLayoutPositions(positions) {{
      layoutPositions = positions;
    }}

    function computeLayout(visibleComponents) {{
      const ordered = groups.map(([title, types], columnIndex) => {{
        const members = visibleComponents
          .filter((component) => types.has(component.type))
          .sort((left, right) => left.id.localeCompare(right.id));
        return {{ title, columnIndex, members }};
      }});
      const ungrouped = visibleComponents
        .filter((component) => !ordered.some((group) => group.members.some((item) => item.id === component.id)))
        .sort((left, right) => left.id.localeCompare(right.id));
      if (ungrouped.length) ordered.push({{ title: "Other", columnIndex: ordered.length, members: ungrouped }});

      const positions = new Map();
      const margins = {{ left: 72, top: 72, right: 88, bottom: 88 }};
      const columnWidth = 272;
      const rowGap = 152;

      ordered.forEach((group, index) => {{
        const baseX = margins.left + index * columnWidth;
        group.members.forEach((component, rowIndex) => {{
          const size = nodeSize(component);
          const seededNode = seededViewNodes.get(component.id);
          const centerX = seededNode && Number.isFinite(seededNode.x) ? seededNode.x : baseX + size.width / 2;
          const centerY = seededNode && Number.isFinite(seededNode.y) ? seededNode.y : margins.top + rowIndex * rowGap + size.height / 2;
          const x = Math.round(centerX - size.width / 2);
          const y = Math.round(centerY - size.height / 2);
          positions.set(component.id, {{
            x,
            y,
            width: size.width,
            height: size.height,
            centerX: x + size.width / 2,
            centerY: y + size.height / 2,
            group: group.title,
          }});
        }});
      }});

      const widths = Array.from(positions.values()).map((item) => item.x + item.width);
      const heights = Array.from(positions.values()).map((item) => item.y + item.height);
      return {{
        positions,
        width: Math.max(960, (widths.length ? Math.max(...widths) : 0) + margins.right),
        height: Math.max(560, (heights.length ? Math.max(...heights) : 0) + margins.bottom),
        groupTitles: ordered.map((group, index) => {{
          const x = margins.left + index * columnWidth;
          return {{ title: group.title, x }};
        }}),
      }};
    }}

    function nodeSize(component) {{
      if (component.icon_uri) return {{ width: 184, height: 112 }};
      if (component.type === "cloud") return {{ width: 188, height: 92 }};
      if (component.type === "gateway") return {{ width: 188, height: 88 }};
      if (component.type === "storage") return {{ width: 184, height: 82 }};
      if (component.type === "datastore") return {{ width: 184, height: 92 }};
      return {{ width: 184, height: 84 }};
    }}

    function edgePath(source, target) {{
      const startX = source.x + source.width;
      const startY = source.centerY;
      const endX = target.x;
      const endY = target.centerY;
      const horizontalGap = endX - startX;
      const verticalGap = endY - startY;
      if (horizontalGap > 120) {{
        const elbowX = startX + Math.min(90, Math.max(42, horizontalGap * 0.28));
        return [
          `M ${{startX}} ${{startY}}`,
          `L ${{elbowX}} ${{startY}}`,
          `C ${{elbowX + 24}} ${{startY}}, ${{endX - 32}} ${{endY}}, ${{endX}} ${{endY}}`
        ].join(" ");
      }}
      if (Math.abs(verticalGap) > 120) {{
        const midX = startX + 44;
        const midY = startY + verticalGap / 2;
        return [
          `M ${{startX}} ${{startY}}`,
          `C ${{midX}} ${{startY}}, ${{midX}} ${{midY}}, ${{midX}} ${{midY}}`,
          `S ${{endX - 28}} ${{endY}}, ${{endX}} ${{endY}}`
        ].join(" ");
      }}
      const curve = Math.max(40, Math.abs(endX - startX) * 0.35);
      return `M ${{startX}} ${{startY}} C ${{startX + curve}} ${{startY}}, ${{endX - curve}} ${{endY}}, ${{endX}} ${{endY}}`;
    }}

    function edgeLabelPosition(source, target) {{
      const startX = source.x + source.width;
      const endX = target.x;
      const horizontalGap = endX - startX;
      const centerY = Math.round((source.centerY + target.centerY) / 2);
      return {{
        x: horizontalGap > 120
          ? Math.round(startX + Math.min(70, Math.max(32, horizontalGap * 0.22)))
          : Math.round((source.x + source.width + target.x) / 2),
        y: centerY - (Math.abs(source.centerY - target.centerY) > 120 ? 16 : 12),
      }};
    }}

    function nodeMarkup(component, position) {{
      const hasOfficialIcon = Boolean(component.icon_uri);
      const providerBadge = component.provider
        && !hasOfficialIcon
        ? `<g class="provider-badge"><rect x="${{position.x + position.width - 52}}" y="${{position.y + 10}}" width="40" height="18" rx="9" fill="#ffffff" fill-opacity="0.86" stroke="rgba(15,35,45,0.14)"></rect><text x="${{position.x + position.width - 32}}" y="${{position.y + 23}}" text-anchor="middle" font-size="10" font-weight="700" fill="#355468">${{escapeHtml(component.provider.toUpperCase())}}</text></g>`
        : "";
      const title = `<title>${{escapeHtml(component.id)}}</title>`;
      const subtitleY = hasOfficialIcon ? position.y + position.height - 10 : position.y + position.height - 16;
      const subtitle = `<text x="${{position.centerX}}" y="${{subtitleY}}" text-anchor="middle" font-size="${{hasOfficialIcon ? 10 : 11}}" fill="#4f6775">${{escapeHtml(component.type)}}</text>`;
      const iconMarkup = hasOfficialIcon
        ? `<circle cx="${{position.centerX}}" cy="${{position.y + 38}}" r="34" fill="#ffffff" fill-opacity="0.94" stroke="rgba(15,35,45,0.18)" stroke-width="1.5"></circle><image href="${{component.icon_uri}}" x="${{position.centerX - 30}}" y="${{position.y + 8}}" width="60" height="60" preserveAspectRatio="xMidYMid meet"></image>`
        : "";
      const labelY = hasOfficialIcon ? position.y + 84 : position.y + 34;
      const label = `<text x="${{position.centerX}}" y="${{labelY}}" text-anchor="middle" font-size="${{hasOfficialIcon ? 13 : 14}}" font-weight="700" fill="#10212b">${{escapeHtml(component.display_name)}}</text>`;
      if (hasOfficialIcon) {{
        return `<g class="node node-icon" data-component-id="${{escapeHtml(component.id)}}">${{title}}<rect x="${{position.x + 18}}" y="${{position.y + 4}}" width="${{position.width - 36}}" height="${{position.height - 8}}" rx="28" fill="transparent" stroke="none"></rect>${{iconMarkup}}${{label}}${{subtitle}}</g>`;
      }}
      if (component.type === "cloud") {{
        const d = `M ${{position.x + 30}} ${{position.y + 62}} C ${{position.x + 18}} ${{position.y + 62}}, ${{position.x + 12}} ${{position.y + 50}}, ${{position.x + 22}} ${{position.y + 42}} C ${{position.x + 22}} ${{position.y + 26}}, ${{position.x + 38}} ${{position.y + 18}}, ${{position.x + 54}} ${{position.y + 22}} C ${{position.x + 62}} ${{position.y + 10}}, ${{position.x + 90}} ${{position.y + 8}}, ${{position.x + 108}} ${{position.y + 24}} C ${{position.x + 126}} ${{position.y + 18}}, ${{position.x + 148}} ${{position.y + 28}}, ${{position.x + 150}} ${{position.y + 46}} C ${{position.x + 162}} ${{position.y + 50}}, ${{position.x + 168}} ${{position.y + 62}}, ${{position.x + 156}} ${{position.y + 70}} L ${{position.x + 32}} ${{position.y + 70}} C ${{position.x + 24}} ${{position.y + 70}}, ${{position.x + 20}} ${{position.y + 66}}, ${{position.x + 30}} ${{position.y + 62}} Z`;
        return `<g class="node node-cloud" data-component-id="${{escapeHtml(component.id)}}">${{title}}<path d="${{d}}" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></path>${{providerBadge}}${{label}}${{subtitle}}</g>`;
      }}
      if (component.type === "gateway") {{
        const points = `${{position.x + 26}},${{position.y}} ${{position.x + position.width - 26}},${{position.y}} ${{position.x + position.width}},${{position.y + position.height / 2}} ${{position.x + position.width - 26}},${{position.y + position.height}} ${{position.x + 26}},${{position.y + position.height}} ${{position.x}},${{position.y + position.height / 2}}`;
        return `<g class="node node-gateway" data-component-id="${{escapeHtml(component.id)}}">${{title}}<polygon points="${{points}}" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></polygon>${{providerBadge}}${{label}}${{subtitle}}</g>`;
      }}
      if (component.type === "storage") {{
        const points = `${{position.x + 18}},${{position.y + 18}} ${{position.x + position.width - 18}},${{position.y + 18}} ${{position.x + position.width - 34}},${{position.y + position.height - 14}} ${{position.x + 34}},${{position.y + position.height - 14}}`;
        return `<g class="node node-storage" data-component-id="${{escapeHtml(component.id)}}">${{title}}<path d="M ${{position.x + 14}} ${{position.y + 20}} L ${{position.x + 58}} ${{position.y + 20}} L ${{position.x + 70}} ${{position.y + 10}} L ${{position.x + position.width - 14}} ${{position.y + 10}} L ${{position.x + position.width - 24}} ${{position.y + position.height - 12}} L ${{position.x + 24}} ${{position.y + position.height - 12}} Z" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></path>${{providerBadge}}${{label}}${{subtitle}}</g>`;
      }}
      if (component.type === "datastore") {{
        return `<g class="node node-datastore" data-component-id="${{escapeHtml(component.id)}}">${{title}}<ellipse cx="${{position.centerX}}" cy="${{position.y + 18}}" rx="${{(position.width - 28) / 2}}" ry="12" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></ellipse><rect x="${{position.x + 14}}" y="${{position.y + 18}}" width="${{position.width - 28}}" height="${{position.height - 34}}" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></rect><ellipse cx="${{position.centerX}}" cy="${{position.y + position.height - 16}}" rx="${{(position.width - 28) / 2}}" ry="12" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></ellipse>${{providerBadge}}${{label}}${{subtitle}}</g>`;
      }}
      return `<g class="node node-standard" data-component-id="${{escapeHtml(component.id)}}">${{title}}<rect x="${{position.x}}" y="${{position.y}}" width="${{position.width}}" height="${{position.height}}" rx="20" fill="var(--node-fill)" stroke="var(--node-stroke)" stroke-width="2"></rect>${{providerBadge}}${{label}}${{subtitle}}</g>`;
    }}

    function downloadFile(filename, content, mimeType) {{
      const blob = new Blob([content], {{ type: mimeType }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }}

    function pointerToSvg(event) {{
      if (!currentSvg) return {{ x: 0, y: 0 }};
      const rect = currentSvg.getBoundingClientRect();
      const viewBox = currentSvg.viewBox.baseVal;
      const x = ((event.clientX - rect.left) / rect.width) * viewBox.width;
      const y = ((event.clientY - rect.top) / rect.height) * viewBox.height;
      return {{ x, y }};
    }}

    function scheduleRender() {{
      if (pendingRender) return;
      pendingRender = window.requestAnimationFrame(() => {{
        pendingRender = 0;
        renderDiagram();
      }});
    }}

    function updateSeedPosition(componentId, x, y) {{
      const existing = seededViewNodes.get(componentId) || {{ id: componentId }};
      seededViewNodes.set(componentId, {{
        ...existing,
        id: componentId,
        x: Math.round(x),
        y: Math.round(y),
      }});
    }}

    function bindDrag(node, componentId) {{
      node.addEventListener("pointerdown", (event) => {{
        if (event.button !== 0) return;
        const position = layoutPositions.get(componentId);
        if (!position) return;
        selectedRelationshipKey = null;
        selectedComponentId = componentId;
        const pointer = pointerToSvg(event);
        dragState = {{
          componentId,
          offsetX: pointer.x - position.x,
          offsetY: pointer.y - position.y,
          moved: false,
        }};
        node.classList.add("is-dragging");
        syncUrl();
        applySelection();
        event.preventDefault();
      }});
    }}

    function handleDragMove(event) {{
      if (!dragState) return;
      const pointer = pointerToSvg(event);
      const nextX = Math.max(80, pointer.x - dragState.offsetX);
      const nextY = Math.max(60, pointer.y - dragState.offsetY);
      dragState.moved = true;
      updateSeedPosition(dragState.componentId, nextX, nextY);
      layoutPositions.set(dragState.componentId, {{ x: Math.round(nextX), y: Math.round(nextY) }});
      syncCoordinateHud();
      scheduleRender();
    }}

    function handleDragEnd() {{
      if (!dragState) return;
      suppressNodeClick = dragState.moved;
      dragState = null;
      syncUrl();
      scheduleRender();
      setStatus("Layout updated");
    }}

    function buildExportHtml() {{
      const mermaidSource = buildGraphDefinition();
      const escapedMermaid = mermaidSource
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      return [
        "<!DOCTYPE html>",
        "<html lang=\\"en\\">",
        "<head>",
        "  <meta charset=\\"utf-8\\">",
        "  <meta name=\\"viewport\\" content=\\"width=device-width, initial-scale=1\\">",
        "  <title>Stackscope Export: " + blueprintName + "</title>",
        "  <style>",
        "    body {{ margin: 0; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, \\"Segoe UI\\", sans-serif; background: #f5fbff; color: #10212b; }}",
        "    main {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}",
        "    h1 {{ margin: 0 0 8px; font-size: 2.4rem; letter-spacing: -0.04em; }}",
        "    p {{ margin: 0 0 16px; color: #4f6775; }}",
        "    .frame {{ border: 1px solid #bfd0db; border-radius: 18px; padding: 16px; background: white; overflow: auto; }}",
        "  </style>",
        "</head>",
        "<body>",
        "  <main>",
        "    <h1>" + blueprintName + "</h1>",
        "    <p>Exported current Stackscope view from " + blueprintRootPath + "</p>",
        "    <div class=\\"frame\\">",
        "      <div class=\\"mermaid\\">" + escapedMermaid + "</div>",
        "    </div>",
        "  </main>",
        "  <script src=\\"https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js\\"><\\/script>",
        "  <script>",
        "    mermaid.initialize({{ startOnLoad: true, theme: \\"base\\", flowchart: {{ useMaxWidth: false, htmlLabels: true }} }});",
        "  <\\/script>",
        "</body>",
        "</html>"
      ].join("\\n");
    }}

    function applySelection() {{
      const map = nodeMap();
      const allNodes = Array.from(map.values());
      const allEdges = currentSvg ? Array.from(currentSvg.querySelectorAll("g.edgePath")) : [];
      const allEdgeLabels = currentSvg ? Array.from(currentSvg.querySelectorAll("g.edgeLabel")) : [];
      const visibleIds = filteredComponentIds();
      const visibleRelationshipKeys = new Set(visibleRelationships().map((relationship) => relationship.key));
      if (selectedComponentId && !visibleIds.has(selectedComponentId)) selectedComponentId = null;
      if (selectedRelationshipKey && !visibleRelationshipKeys.has(selectedRelationshipKey)) selectedRelationshipKey = null;

      allNodes.forEach((node) => node.classList.remove("is-selected", "is-dimmed"));
      allEdges.forEach((edge) => edge.classList.remove("is-selected", "is-dimmed"));
      allEdgeLabels.forEach((edge) => edge.classList.remove("is-selected", "is-dimmed"));
      componentButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.componentId === selectedComponentId));
      typeButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.componentType === activeTypeFilter));
      sourceButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.sourceTag === activeSourceFilter));
      relationshipButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.relationshipKey === selectedRelationshipKey));

      const selectedRelationship = relationships.find((item) => item.key === selectedRelationshipKey) || null;
      if (selectedRelationship) {{
        const edgeIndex = relationships.findIndex((item) => item.key === selectedRelationship.key);
        const sourceNode = map.get(selectedRelationship.source);
        const targetNode = map.get(selectedRelationship.target);
        if (sourceNode) sourceNode.classList.add("is-selected");
        if (targetNode) targetNode.classList.add("is-selected");
        allNodes.forEach((node) => {{
          if (node !== sourceNode && node !== targetNode) node.classList.add("is-dimmed");
        }});
        if (allEdges[edgeIndex]) allEdges[edgeIndex].classList.add("is-selected");
        if (allEdgeLabels[edgeIndex]) allEdgeLabels[edgeIndex].classList.add("is-selected");
        allEdges.forEach((edge, index) => {{
          if (index !== edgeIndex) edge.classList.add("is-dimmed");
        }});
        allEdgeLabels.forEach((label, index) => {{
          if (index !== edgeIndex) label.classList.add("is-dimmed");
        }});
        renderInspector(null, selectedRelationship);
        syncCoordinateHud();
        return;
      }}

      if (!selectedComponentId || !map.has(selectedComponentId)) {{
        renderInspector(components.find((component) => component.id === selectedComponentId) || null, null);
        syncCoordinateHud();
        return;
      }}

      const selectedNode = map.get(selectedComponentId);
      const {{ edges, labels }} = edgeElementsFor(selectedComponentId);
      allNodes.forEach((node) => {{
        if (node !== selectedNode) node.classList.add("is-dimmed");
      }});
      allEdges.forEach((edge) => {{
        if (!edges.includes(edge)) edge.classList.add("is-dimmed");
      }});
      allEdgeLabels.forEach((label) => {{
        if (!labels.includes(label)) label.classList.add("is-dimmed");
      }});
      selectedNode.classList.add("is-selected");
      edges.forEach((edge) => edge.classList.add("is-selected"));
      labels.forEach((label) => label.classList.add("is-selected"));
      renderInspector(components.find((component) => component.id === selectedComponentId) || null, null);
      syncCoordinateHud();
    }}

    function applyFilters() {{
      const visibleIds = filteredComponentIds();
      componentButtons.forEach((button) => {{
        button.parentElement.hidden = !visibleIds.has(button.dataset.componentId);
      }});
      relationshipButtons.forEach((button) => {{
        const relationship = relationships.find((item) => item.key === button.dataset.relationshipKey);
        button.parentElement.hidden = !(relationship && visibleIds.has(relationship.source) && visibleIds.has(relationship.target));
      }});
      syncUrl();
      renderDiagram();
    }}

    function renderDiagram() {{
      const visibleComponents = filteredComponents();
      const visibleRelationshipsList = visibleRelationships();
      const layoutData = computeLayout(visibleComponents);
      captureLayoutPositions(new Map(Array.from(layoutData.positions.entries()).map(([componentId, position]) => [componentId, {{
        x: Math.round(position.centerX),
        y: Math.round(position.centerY),
      }}])));

      const svgParts = [
        `<svg width="${{layoutData.width}}" height="${{layoutData.height}}" viewBox="0 0 ${{layoutData.width}} ${{layoutData.height}}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="architecture-diagram">`,
        `<defs><marker id="arrowhead" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#47667b"></path></marker></defs>`,
        `<style>
          .group-title {{ font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; fill: #4f6775; font-weight: 700; }}
          .group-band {{ fill: rgba(255,255,255,0.38); stroke: rgba(148,163,184,0.24); stroke-dasharray: 6 8; }}
          .node {{ cursor: pointer; --node-fill: #ffffff; --node-stroke: #7aa4bd; }}
          .node-standard {{ --node-fill: #ffffff; --node-stroke: #7aa4bd; }}
          .node-gateway {{ --node-fill: #edf4ff; --node-stroke: #2563eb; }}
          .node-storage {{ --node-fill: #eefcf4; --node-stroke: #16a34a; }}
          .node-datastore {{ --node-fill: #effcf2; --node-stroke: #22c55e; }}
          .node-cloud[data-provider="aws"] {{ --node-fill: #fff7ed; --node-stroke: #c2410c; }}
          .node-cloud[data-provider="gcp"] {{ --node-fill: #ecfeff; --node-stroke: #0891b2; }}
          .node-cloud[data-provider="azure"] {{ --node-fill: #eff6ff; --node-stroke: #1d4ed8; }}
          .node-cloud {{ --node-fill: #f8fafc; --node-stroke: #64748b; }}
          .edgePath path {{ fill: none; stroke: #47667b; stroke-width: 1.8; marker-end: url(#arrowhead); }}
          .edgeLabel text {{ font-size: 11px; fill: #3f5563; }}
        </style>`
      ];

      layoutData.groupTitles.forEach((group) => {{
        svgParts.push(`<text class="group-title" x="${{group.x}}" y="28">${{escapeHtml(group.title)}}</text>`);
        svgParts.push(`<rect class="group-band" x="${{group.x - 16}}" y="40" width="224" height="${{layoutData.height - 88}}" rx="24"></rect>`);
      }});

      visibleRelationshipsList.forEach((relationship) => {{
        const source = layoutData.positions.get(relationship.source);
        const target = layoutData.positions.get(relationship.target);
        if (!source || !target) return;
        const labelPosition = edgeLabelPosition(source, target);
        svgParts.push(`<g class="edgePath" data-relationship-key="${{escapeHtml(relationship.key)}}" data-source="${{escapeHtml(relationship.source)}}" data-target="${{escapeHtml(relationship.target)}}"><title>${{escapeHtml(relationship.key)}}</title><path d="${{edgePath(source, target)}}"></path></g>`);
        svgParts.push(`<g class="edgeLabel" data-relationship-key="${{escapeHtml(relationship.key)}}" data-source="${{escapeHtml(relationship.source)}}" data-target="${{escapeHtml(relationship.target)}}"><text x="${{labelPosition.x}}" y="${{labelPosition.y}}" text-anchor="middle">${{escapeHtml(relationship.label)}}</text></g>`);
      }});

      visibleComponents.forEach((component) => {{
        const position = layoutData.positions.get(component.id);
        if (!position) return;
        const markup = nodeMarkup(component, position).replace("node-cloud", `node-cloud" data-provider="${{escapeHtml(component.provider || "")}}`);
        svgParts.push(markup);
      }});
      svgParts.push("</svg>");

      root.innerHTML = svgParts.join("");
      currentSvg = root.querySelector("svg");
      syncZoom();
      const map = nodeMap();
      map.forEach((node, componentId) => {{
        bindDrag(node, componentId);
        node.addEventListener("click", () => {{
          if (suppressNodeClick) {{
            suppressNodeClick = false;
            return;
          }}
          selectedRelationshipKey = null;
          selectedComponentId = componentId === selectedComponentId ? null : componentId;
          syncUrl();
          applySelection();
        }});
      }});
      currentSvg.querySelectorAll("g.edgePath, g.edgeLabel").forEach((edgeElement) => {{
        edgeElement.addEventListener("click", () => {{
          selectedComponentId = null;
          const relationshipKey = edgeElement.dataset.relationshipKey || null;
          selectedRelationshipKey = relationshipKey === selectedRelationshipKey ? null : relationshipKey;
          syncUrl();
          applySelection();
        }});
      }});
      applySelection();
    }}
    if (document.readyState === "loading") {{
      document.addEventListener("DOMContentLoaded", renderDiagram, {{ once: true }});
    }} else {{
      renderDiagram();
    }}
    componentButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        selectedRelationshipKey = null;
        selectedComponentId = button.dataset.componentId === selectedComponentId ? null : button.dataset.componentId;
        syncUrl();
        applySelection();
      }});
    }});
    relationshipButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        selectedComponentId = null;
        selectedRelationshipKey = button.dataset.relationshipKey === selectedRelationshipKey ? null : button.dataset.relationshipKey;
        syncUrl();
        applySelection();
      }});
    }});
    typeButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        activeTypeFilter = button.dataset.componentType === activeTypeFilter ? null : button.dataset.componentType;
        applyFilters();
      }});
    }});
    sourceButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        activeSourceFilter = button.dataset.sourceTag === activeSourceFilter ? null : button.dataset.sourceTag;
        applyFilters();
      }});
    }});
    copyLinkButton.addEventListener("click", async () => {{
      syncUrl();
      try {{
        await navigator.clipboard.writeText(window.location.href);
        setStatus("Link copied");
      }} catch (error) {{
        setStatus("Copy failed");
      }}
    }});
    resetViewButton.addEventListener("click", () => {{
      selectedComponentId = null;
      selectedRelationshipKey = null;
      activeTypeFilter = null;
      activeSourceFilter = null;
      isSidebarCollapsed = false;
      seededViewNodes = cloneSeedMap(initialNodeSeeds);
      searchInput.value = "";
      hideLibrariesToggle.checked = false;
      hideDeliveryToggle.checked = false;
      syncSidebarState();
      applyFilters();
      setStatus("View reset");
    }});
    exportMermaidButton.addEventListener("click", () => {{
      downloadFile("stackscope-view.mmd", buildGraphDefinition(), "text/plain;charset=utf-8");
      setStatus("Mermaid exported");
    }});
    exportHtmlButton.addEventListener("click", () => {{
      downloadFile("stackscope-view.html", buildExportHtml(), "text/html;charset=utf-8");
      setStatus("HTML exported");
    }});
    exportViewButton.addEventListener("click", () => {{
      downloadFile("view.json", JSON.stringify(currentViewStatePayload(), null, 2), "application/json;charset=utf-8");
      setStatus("View exported");
    }});
    exportJsonButton.addEventListener("click", () => {{
      downloadFile("stackscope-view.json", JSON.stringify(currentViewBundle(), null, 2), "application/json;charset=utf-8");
      setStatus("JSON exported");
    }});
    zoomOutButton.addEventListener("click", () => {{
      zoomLevel -= 0.1;
      syncZoom();
      syncUrl();
    }});
    zoomInButton.addEventListener("click", () => {{
      zoomLevel += 0.1;
      syncZoom();
      syncUrl();
    }});
    zoomResetButton.addEventListener("click", () => {{
      zoomLevel = 1;
      syncZoom();
      syncUrl();
    }});
    sidebarToggle.addEventListener("click", () => {{
      isSidebarCollapsed = !isSidebarCollapsed;
      syncSidebarState();
      syncUrl();
    }});
    searchInput.addEventListener("input", applyFilters);
    hideLibrariesToggle.addEventListener("change", applyFilters);
    hideDeliveryToggle.addEventListener("change", applyFilters);
    window.addEventListener("pointermove", handleDragMove);
    window.addEventListener("pointerup", handleDragEnd);
    window.addEventListener("pointercancel", handleDragEnd);
    searchInput.value = params.get("search") || "";
    syncZoom();
    syncSidebarState();
    applyFilters();
  </script>
</body>
</html>
"""


def _display_root_path(root_path: str) -> str:
    path = PurePath(root_path)
    parts = list(path.parts)
    if len(parts) <= 3:
        return str(path)
    return "/".join(parts[-3:])


def _component_provider(component) -> str:
    technology = (component.technology or "").lower()
    name = component.name.lower()
    if technology.startswith("aws") or name.startswith("aws"):
        return "aws"
    if technology.startswith(("google", "gcp")) or name.startswith(("google", "gcp")):
        return "gcp"
    if technology.startswith("azurerm") or technology.startswith("azure") or name.startswith("azure"):
        return "azure"
    return ""


def _component_display_name(component) -> str:
    if component.type == "cloud":
        provider = _component_provider(component)
        if provider == "aws":
            return "AWS Cloud"
        if provider == "gcp":
            return "GCP Cloud"
        if provider == "azure":
            return "Azure Cloud"
        return component.name

    technology = (component.technology or "").lower()
    provider = _component_provider(component)
    if provider == "aws":
        if technology.startswith("aws_s3_bucket"):
            return "AWS S3 Bucket"
        if technology.startswith("aws_db_instance"):
            return "AWS RDS Instance"
        if technology.startswith("aws_lambda"):
            return "AWS Lambda"
        if technology.startswith("aws_ecs_service"):
            return "AWS ECS Service"
        if technology.startswith("aws_eks_cluster"):
            return "AWS EKS Cluster"
        if technology.startswith(("aws_lb", "aws_alb", "aws_elb")):
            return "AWS Load Balancer"
        if technology.startswith("aws_sqs_queue"):
            return "AWS SQS Queue"
        if technology.startswith("aws_sns_topic"):
            return "AWS SNS Topic"
        if technology.startswith("aws_dynamodb_table"):
            return "AWS DynamoDB Table"
        if technology.startswith("aws_elasticache"):
            return "AWS ElastiCache"
    if provider == "gcp":
        if "storage_bucket" in technology:
            return "GCP Storage Bucket"
        if "sql_database" in technology:
            return "GCP SQL Database"
        if technology.startswith("google_cloud_run_service"):
            return "GCP Cloud Run Service"
        if technology.startswith("google_compute_instance"):
            return "GCP Compute Instance"
        if technology.startswith("google_pubsub_topic"):
            return "GCP Pub/Sub Topic"
        if technology.startswith("google_container_cluster"):
            return "GCP GKE Cluster"
    if provider == "azure":
        if "storage_account" in technology:
            return "Azure Storage Account"
        if technology.startswith("azurerm_linux_function_app") or technology.startswith("azurerm_function_app"):
            return "Azure Function App"
        if technology.startswith("azurerm_kubernetes_cluster"):
            return "Azure AKS Cluster"
        if technology.startswith("azurerm_mssql_server"):
            return "Azure SQL Server"
        if technology.startswith("azurerm_servicebus"):
            return "Azure Service Bus"
    return component.name


def _mermaid_component_label(component) -> str:
    return f"{_component_display_name(component)}\\n({component.type})"


def _mermaid_node(component, label: str) -> str:
    if component.type == "cloud":
        return f'{component.id}(["{label}"])'
    if component.type == "storage":
        return f'{component.id}[/"{label}"/]'
    if component.type == "datastore":
        return f'{component.id}[("{label}")]'
    if component.type == "gateway":
        return f'{component.id}{{"{label}"}}'
    return f'{component.id}["{label}"]'


def _mermaid_component_classes(component) -> list[str]:
    classes: list[str] = []
    if component.type == "gateway":
        classes.append("gateway-node")
    if component.type == "storage":
        classes.append("storage-node")
    if component.type == "datastore":
        classes.append("datastore-node")
    if component.type == "cloud":
        provider = _component_provider(component)
        if provider == "aws":
            classes.append("cloud-aws")
        elif provider == "gcp":
            classes.append("cloud-gcp")
        elif provider == "azure":
            classes.append("cloud-azure")
        else:
            classes.append("cloud-generic")
    return classes


def _svg_layout(blueprint: Blueprint, view_state: ViewState) -> tuple[dict[str, dict[str, int | str]], int, int, list[dict[str, int | str]]]:
    groups = [
        ("Delivery", {"pipeline", "automation"}),
        ("Application", {"application", "service", "gateway"}),
        ("Data", {"datastore", "storage"}),
        ("Platform", {"cloud", "infrastructure", "configuration"}),
        ("Edge", {"integration", "library"}),
    ]
    visible_components = list(blueprint.components.values())
    ordered_groups: list[tuple[str, list]] = []
    grouped_ids: set[str] = set()
    for title, types in groups:
        members = [component for component in sorted(visible_components, key=lambda item: item.id) if component.type in types]
        if members:
            ordered_groups.append((title, members))
            grouped_ids.update(component.id for component in members)
    ungrouped = [component for component in sorted(visible_components, key=lambda item: item.id) if component.id not in grouped_ids]
    if ungrouped:
        ordered_groups.append(("Other", ungrouped))

    seeded = view_state.nodes
    margins = {"left": 72, "top": 72, "right": 88, "bottom": 88}
    column_width = 272
    row_gap = 152
    positions: dict[str, dict[str, int | str]] = {}
    for column_index, (title, members) in enumerate(ordered_groups):
        base_x = margins["left"] + column_index * column_width
        for row_index, component in enumerate(members):
            size = _svg_node_size(component)
            seeded_node = seeded.get(component.id)
            center_x = seeded_node.x if seeded_node else base_x + size["width"] // 2
            center_y = seeded_node.y if seeded_node else margins["top"] + row_index * row_gap + size["height"] // 2
            x = round(center_x - size["width"] / 2)
            y = round(center_y - size["height"] / 2)
            positions[component.id] = {
                "x": x,
                "y": y,
                "width": size["width"],
                "height": size["height"],
                "center_x": round(x + size["width"] / 2),
                "center_y": round(y + size["height"] / 2),
                "group": title,
            }
    widths = [int(position["x"]) + int(position["width"]) for position in positions.values()]
    heights = [int(position["y"]) + int(position["height"]) for position in positions.values()]
    width = max(960, (max(widths) if widths else 0) + margins["right"])
    height = max(560, (max(heights) if heights else 0) + margins["bottom"])
    group_titles = [{"title": title, "x": margins["left"] + index * column_width} for index, (title, _) in enumerate(ordered_groups)]
    return positions, width, height, group_titles


def _svg_node_size(component) -> dict[str, int]:
    if component.type == "cloud":
        return {"width": 188, "height": 92}
    if component.type == "gateway":
        return {"width": 188, "height": 88}
    if component.type == "storage":
        return {"width": 184, "height": 82}
    if component.type == "datastore":
        return {"width": 184, "height": 92}
    return {"width": 184, "height": 84}


def _svg_node_colors(component) -> tuple[str, str]:
    provider = _component_provider(component)
    if component.type == "gateway":
        return "#edf4ff", "#2563eb"
    if component.type == "storage":
        return "#eefcf4", "#16a34a"
    if component.type == "datastore":
        return "#effcf2", "#22c55e"
    if component.type == "cloud":
        if provider == "aws":
            return "#fff7ed", "#c2410c"
        if provider == "gcp":
            return "#ecfeff", "#0891b2"
        if provider == "azure":
            return "#eff6ff", "#1d4ed8"
        return "#f8fafc", "#64748b"
    return "#ffffff", "#7aa4bd"


def _svg_node_markup(component, position: dict[str, int | str]) -> str:
    x = int(position["x"])
    y = int(position["y"])
    width = int(position["width"])
    height = int(position["height"])
    center_x = int(position["center_x"])
    fill, stroke = _svg_node_colors(component)
    label = escape(_component_display_name(component))
    subtitle = escape(component.type)
    provider = _component_provider(component).upper()
    icon_uri = _icon_data_uri(component)
    provider_markup = ""
    if provider and not icon_uri:
        badge_x = x + width - 52
        badge_y = y + 10
        provider_markup = (
            f'<rect x="{badge_x}" y="{badge_y}" width="40" height="18" rx="9" fill="#ffffff" fill-opacity="0.86" stroke="rgba(15,35,45,0.14)"></rect>'
            f'<text class="provider-badge" x="{badge_x + 20}" y="{badge_y + 13}" text-anchor="middle">{escape(provider)}</text>'
        )

    title = f"<title>{escape(component.id)}</title>"
    label_y = y + 34
    icon_markup = ""
    if icon_uri:
        icon_size = min(width - 72, 60)
        icon_x = center_x - icon_size / 2
        icon_y = y + 8
        halo_cx = center_x
        halo_cy = y + 38
        icon_markup = (
            f'<circle cx="{halo_cx}" cy="{halo_cy}" r="34" fill="#ffffff" fill-opacity="0.94" stroke="{stroke}" stroke-opacity="0.18" stroke-width="1.5"></circle>'
            f'<image href="{icon_uri}" x="{icon_x}" y="{icon_y}" width="{icon_size}" height="{icon_size}" preserveAspectRatio="xMidYMid meet"></image>'
        )
        label_y = y + 84
    subtitle_y = y + height - (10 if icon_uri else 16)
    label_markup = (
        f'<text class="node-label" x="{center_x}" y="{label_y}" text-anchor="middle"'
        + (f' style="font-size:13px;"' if icon_uri else "")
        + f">{label}</text>"
    )
    subtitle_markup = (
        f'<text class="node-subtitle" x="{center_x}" y="{subtitle_y}" text-anchor="middle"'
        + (f' style="font-size:10px;"' if icon_uri else "")
        + f">{subtitle}</text>"
    )

    if icon_uri:
        hitbox = f'<rect x="{x + 18}" y="{y + 4}" width="{width - 36}" height="{height - 8}" rx="28" fill="transparent" stroke="none"></rect>'
        return f"<g>{title}{hitbox}{icon_markup}{provider_markup}{label_markup}{subtitle_markup}</g>"

    if component.type == "cloud":
        d = (
            f"M {x + 30} {y + 62} C {x + 18} {y + 62}, {x + 12} {y + 50}, {x + 22} {y + 42} "
            f"C {x + 22} {y + 26}, {x + 38} {y + 18}, {x + 54} {y + 22} "
            f"C {x + 62} {y + 10}, {x + 90} {y + 8}, {x + 108} {y + 24} "
            f"C {x + 126} {y + 18}, {x + 148} {y + 28}, {x + 150} {y + 46} "
            f"C {x + 162} {y + 50}, {x + 168} {y + 62}, {x + 156} {y + 70} "
            f"L {x + 32} {y + 70} C {x + 24} {y + 70}, {x + 20} {y + 66}, {x + 30} {y + 62} Z"
        )
        shape = f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="2"></path>'
    elif component.type == "gateway":
        points = f"{x + 26},{y} {x + width - 26},{y} {x + width},{y + height // 2} {x + width - 26},{y + height} {x + 26},{y + height} {x},{y + height // 2}"
        shape = f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="2"></polygon>'
    elif component.type == "storage":
        d = (
            f"M {x + 14} {y + 20} L {x + 58} {y + 20} L {x + 70} {y + 10} "
            f"L {x + width - 14} {y + 10} L {x + width - 24} {y + height - 12} "
            f"L {x + 24} {y + height - 12} Z"
        )
        shape = f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="2"></path>'
    elif component.type == "datastore":
        rx = (width - 28) / 2
        shape = (
            f'<ellipse cx="{center_x}" cy="{y + 18}" rx="{rx}" ry="12" fill="{fill}" stroke="{stroke}" stroke-width="2"></ellipse>'
            f'<rect x="{x + 14}" y="{y + 18}" width="{width - 28}" height="{height - 34}" fill="{fill}" stroke="{stroke}" stroke-width="2"></rect>'
            f'<ellipse cx="{center_x}" cy="{y + height - 16}" rx="{rx}" ry="12" fill="{fill}" stroke="{stroke}" stroke-width="2"></ellipse>'
        )
    else:
        shape = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="20" fill="{fill}" stroke="{stroke}" stroke-width="2"></rect>'
    return f"<g>{title}{shape}{provider_markup}{label_markup}{subtitle_markup}</g>"


@lru_cache(maxsize=1)
def _icon_assets() -> dict[str, str]:
    root = Path(__file__).resolve().parent / "assets" / "icons"
    assets: dict[str, str] = {}
    for path in root.rglob("*.svg"):
        assets[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return assets


def _icon_data_uri(component) -> str | None:
    key = _icon_asset_key(component)
    if not key:
        return None
    svg = _icon_assets().get(key)
    if not svg:
        return None
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _icon_asset_key(component) -> str | None:
    technology = (component.technology or "").lower()
    provider = _component_provider(component)
    if provider == "aws":
        if component.type == "cloud":
            return "aws/cloud.svg"
        if technology.startswith("aws_s3_bucket"):
            return "aws/s3.svg"
        if technology.startswith("aws_db_instance"):
            return "aws/rds.svg"
        if technology.startswith("aws_elasticache"):
            return "aws/elasticache.svg"
    if provider == "gcp":
        if technology.startswith("google_storage") or "cloud_storage" in technology or "storage_bucket" in technology:
            return "gcp/cloud-storage.svg"
        if technology.startswith("google_sql") or "cloudsql" in technology or "cloud sql" in technology:
            return "gcp/cloud-sql.svg"
        if technology.startswith("google_cloud_run"):
            return "gcp/cloud-run.svg"
        if technology.startswith("google_container_cluster"):
            return "gcp/gke.svg"
    if provider == "azure":
        if technology.startswith("azurerm_storage_account"):
            return "azure/storage-account.svg"
        if technology.startswith("azurerm_function_app") or technology.startswith("azurerm_linux_function_app"):
            return "azure/function-app.svg"
        if technology.startswith("azurerm_kubernetes_cluster"):
            return "azure/kubernetes-services.svg"
        if technology.startswith("azurerm_mssql") or "azure sql" in technology:
            return "azure/azure-sql.svg"
    return None
