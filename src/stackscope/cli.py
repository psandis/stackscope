from __future__ import annotations

import argparse
import json
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .persistence import build_default_view_state, load_blueprint, load_view_state, save_blueprint, save_view_state
from .renderers import render_html, render_json, render_markdown, render_mermaid, render_svg
from .scanners import query_blueprint, scan_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stackscope", description="Architecture discovery and blueprinting CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a path and print a summary")
    scan_parser.add_argument("source", help="Directory to scan")
    scan_parser.add_argument("--json-out", help="Write JSON model to a file")
    scan_parser.add_argument("--view-out", help="Write editable view-state JSON to a file")
    scan_parser.add_argument("--bundle-out", help="Write a combined blueprint+view JSON bundle to a file")
    scan_parser.add_argument("--markdown-out", help="Write markdown summary to a file")
    scan_parser.add_argument("--mermaid-out", help="Write Mermaid diagram to a file")

    draw_parser = subparsers.add_parser("draw", help="Draw the inferred architecture")
    draw_parser.add_argument("source", help="Directory to scan or saved blueprint/bundle JSON to load")
    draw_parser.add_argument("--format", choices=["mermaid", "markdown", "html", "svg"], default="mermaid")
    draw_parser.add_argument("--view", help="Optional view-state JSON to load")
    draw_parser.add_argument("--out", help="Write the rendered output to a file")

    export_parser = subparsers.add_parser("export", help="Export a rendered blueprint")
    export_parser.add_argument("source", help="Directory to scan or saved blueprint/bundle JSON to load")
    export_parser.add_argument("--format", choices=["json", "view", "bundle", "markdown", "mermaid", "html", "svg"], default="json")
    export_parser.add_argument("--view", help="Optional view-state JSON to load")
    export_parser.add_argument("--out", help="Write the exported output to a file")

    preview_parser = subparsers.add_parser("preview", help="Serve a browser preview of the inferred architecture")
    preview_parser.add_argument("source", help="Directory to scan or saved blueprint/bundle JSON to load")
    preview_parser.add_argument("--view", help="Optional view-state JSON to load")
    preview_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the preview server to")
    preview_parser.add_argument("--port", type=int, default=5123, help="Port to bind the preview server to")

    query_parser = subparsers.add_parser("query", help="Query the inferred model")
    query_parser.add_argument("source", help="Directory to scan or saved blueprint/bundle JSON to load")
    query_parser.add_argument("query", help="Query expression such as components, relationships, type:service")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    blueprint = _load_source(args.source)
    view_state = _load_view_state_arg(args.source, getattr(args, "view", None), blueprint)

    if args.command == "scan":
        if args.json_out:
            save_blueprint(args.json_out, blueprint)
        if args.view_out:
            save_view_state(args.view_out, view_state)
        if args.bundle_out:
            _write_output(Path(args.bundle_out), _render_bundle(blueprint, view_state))
        if args.markdown_out:
            _write_output(Path(args.markdown_out), render_markdown(blueprint))
        if args.mermaid_out:
            _write_output(Path(args.mermaid_out), render_mermaid(blueprint))

        summary = {
            "name": blueprint.name,
            "root_path": blueprint.root_path,
            "component_count": len(blueprint.components),
            "relationship_count": len(blueprint.relationships),
            "component_types": sorted({component.type for component in blueprint.components.values()}),
        }
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "draw":
        rendered = _render_output(blueprint, args.format, view_state)
        if args.out:
            _write_output(Path(args.out), rendered)
        else:
            print(rendered)
        return 0

    if args.command == "export":
        rendered = _render_output(blueprint, args.format, view_state)
        if args.out:
            _write_output(Path(args.out), rendered)
        else:
            print(rendered)
        return 0

    if args.command == "preview":
        return _serve_preview(blueprint, view_state, args.host, args.port)

    rows = query_blueprint(blueprint, args.query)
    print(json.dumps(rows, indent=2))
    return 0


def _write_output(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _render_output(blueprint, output_format: str, view_state=None) -> str:
    if output_format == "json":
        return render_json(blueprint)
    if output_format == "view":
        return json.dumps(view_state.to_dict(), indent=2)
    if output_format == "bundle":
        return _render_bundle(blueprint, view_state)
    if output_format == "markdown":
        return render_markdown(blueprint)
    if output_format == "html":
        return render_html(blueprint, view_state)
    if output_format == "svg":
        return render_svg(blueprint, view_state)
    return render_mermaid(blueprint)


def _serve_preview(blueprint, view_state, host: str, port: int) -> int:
    with tempfile.TemporaryDirectory(prefix="stackscope-preview-") as temp_dir:
        output_path = Path(temp_dir) / "index.html"
        output_path.write_text(render_html(blueprint, view_state), encoding="utf-8")
        handler = partial(SimpleHTTPRequestHandler, directory=temp_dir)
        with ThreadingHTTPServer((host, port), handler) as server:
            print(f"Preview available at http://{host}:{port}")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    return 0


def _load_source(source: str):
    source_path = Path(source)
    if source_path.is_file() and source_path.suffix.lower() == ".json":
        return load_blueprint(source_path)
    return scan_path(source)


def _load_view_state_arg(source: str, view_path: str | None, blueprint):
    if view_path:
        return load_view_state(view_path)
    source_path = Path(source)
    if source_path.is_file() and source_path.suffix.lower() == ".json":
        loaded = load_view_state(source_path)
        if loaded.nodes:
            return loaded
    return build_default_view_state(blueprint)


def _render_bundle(blueprint, view_state) -> str:
    return json.dumps(
        {
            "blueprint": blueprint.to_dict(),
            "view_state": view_state.to_dict(),
        },
        indent=2,
    )


if __name__ == "__main__":
    raise SystemExit(main())
