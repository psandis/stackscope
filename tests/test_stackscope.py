from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

from src.stackscope.persistence import build_default_view_state, save_blueprint, save_view_state
from src.stackscope.renderers import render_html, render_markdown, render_mermaid, render_svg
from src.stackscope.scanners import query_blueprint, scan_path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_APP = ROOT / "examples" / "sample-app"
SAMPLE_BLUEPRINT = SAMPLE_APP / "blueprint.json"
SAMPLE_VIEW = SAMPLE_APP / "view.json"
SAMPLE_BUNDLE = SAMPLE_APP / "bundle.json"


class StackscopeTests(TestCase):
    def test_blueprint_json_export_has_expected_top_level_shape(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.stackscope.cli", "export", str(SAMPLE_APP), "--format", "json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(
            sorted(payload.keys()),
            ["components", "evidence", "name", "relationships", "root_path"],
        )
        self.assertIsInstance(payload["components"], list)
        self.assertIsInstance(payload["relationships"], list)

    def test_scan_discovers_expected_components_and_relationships(self) -> None:
        blueprint = scan_path(SAMPLE_APP)

        self.assertIn("postgres", blueprint.components)
        self.assertIn("redis", blueprint.components)
        self.assertIn("github_actions_ci", blueprint.components)
        self.assertIn("sample_app", blueprint.components)
        self.assertNotIn("app", blueprint.components)
        self.assertNotIn("app_upstream", blueprint.components)
        self.assertEqual(blueprint.components["redis"].type, "datastore")
        self.assertEqual(blueprint.components["redis"].technology, "redis")
        self.assertIn("app", blueprint.components["sample_app"].metadata.get("aliases", []))
        self.assertIn("app_upstream", blueprint.components["sample_app"].metadata.get("aliases", []))
        self.assertTrue(any(rel.type == "depends_on" for rel in blueprint.relationships))
        self.assertTrue(any(component.type == "cloud" for component in blueprint.components.values()))
        self.assertNotIn("aws", blueprint.components)
        self.assertIn("cloud_aws", blueprint.components)

    def test_renderers_include_expected_content(self) -> None:
        blueprint = scan_path(SAMPLE_APP)

        mermaid = render_mermaid(blueprint)
        markdown = render_markdown(blueprint)
        html = render_html(blueprint)
        svg = render_svg(blueprint)

        self.assertIn("graph TD", mermaid)
        self.assertIn("Architecture Summary", markdown)
        self.assertIn("postgres", markdown)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<svg", svg)
        self.assertIn("AWS Cloud", svg)
        self.assertIn("data:image/svg+xml;base64", svg)
        self.assertIn("mermaid.min.js", html)
        self.assertIn('id="diagram-root"', html)
        self.assertIn("sample-app", html)
        self.assertIn("Component Types", html)
        self.assertIn("Sources", html)
        self.assertIn("View", html)
        self.assertIn("Relationships", html)
        self.assertIn('id="sidebar-toggle"', html)
        self.assertIn('id="preview-sidebar"', html)
        self.assertIn("Hide Tools", html)
        self.assertIn('id="copy-link"', html)
        self.assertIn('id="reset-view"', html)
        self.assertIn('id="share-status"', html)
        self.assertIn('id="export-view"', html)
        self.assertIn('id="zoom-in"', html)
        self.assertIn('id="zoom-out"', html)
        self.assertIn('id="zoom-reset"', html)
        self.assertIn('id="coordinate-hud"', html)
        self.assertIn('id="component-search"', html)
        self.assertIn('id="inspector-panel"', html)
        self.assertIn('id="toggle-hide-libraries"', html)
        self.assertIn('id="toggle-hide-delivery"', html)
        self.assertIn("docker-compose", html)
        self.assertIn("window.history.replaceState", html)
        self.assertIn("URLSearchParams", html)
        self.assertIn("explicit SVG layout", html)
        self.assertIn("Select a component to inspect its metadata and relationships.", html)
        self.assertIn("Outgoing", html)
        self.assertIn("Incoming", html)
        self.assertIn("Evidence", html)
        self.assertIn("relationship-item", html)
        self.assertIn('sample_app["sample-app\\n(application)"]', mermaid)
        self.assertNotIn('app["app\\n(service)"]', mermaid)

    def test_query_supports_type_filter(self) -> None:
        blueprint = scan_path(SAMPLE_APP)
        rows = query_blueprint(blueprint, "type:datastore")

        self.assertTrue(any(row["name"] == "postgres" for row in rows))

    def test_cli_scan_outputs_summary(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.stackscope.cli", "scan", str(SAMPLE_APP)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(result.stdout)
        self.assertGreaterEqual(payload["component_count"], 5)

    def test_cli_draw_outputs_mermaid(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.stackscope.cli", "draw", str(SAMPLE_APP)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("graph TD", result.stdout)
        self.assertIn("depends_on", result.stdout)

    def test_cli_draw_outputs_html(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.stackscope.cli", "draw", str(SAMPLE_APP), "--format", "html"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("<!DOCTYPE html>", result.stdout)
        self.assertIn("Architecture view generated from the Stackscope blueprint model.", result.stdout)

    def test_cli_draw_writes_html_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "architecture.html"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.stackscope.cli",
                    "draw",
                    str(SAMPLE_APP),
                    "--format",
                    "html",
                    "--out",
                    str(output_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue(output_path.exists())
            self.assertIn("<!DOCTYPE html>", output_path.read_text(encoding="utf-8"))

    def test_cli_draw_outputs_svg(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.stackscope.cli", "draw", str(SAMPLE_APP), "--format", "svg"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("<svg", result.stdout)
        self.assertIn("AWS Cloud", result.stdout)

    def test_cli_scan_writes_view_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            view_path = Path(temp_dir) / "view.json"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.stackscope.cli",
                    "scan",
                    str(SAMPLE_APP),
                    "--view-out",
                    str(view_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(view_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["blueprint_name"], "sample-app")
            self.assertTrue(any(node["id"] == "sample_app" for node in payload["nodes"]))

    def test_cli_scan_writes_bundle_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle.json"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.stackscope.cli",
                    "scan",
                    str(SAMPLE_APP),
                    "--bundle-out",
                    str(bundle_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(bundle_path.read_text(encoding="utf-8"))
            self.assertIn("blueprint", payload)
            self.assertIn("view_state", payload)
            self.assertEqual(payload["blueprint"]["name"], "sample-app")
            self.assertTrue(any(node["id"] == "sample_app" for node in payload["view_state"]["nodes"]))

    def test_cli_draw_accepts_saved_blueprint_and_view(self) -> None:
        blueprint = scan_path(SAMPLE_APP)
        view_state = build_default_view_state(blueprint)

        with tempfile.TemporaryDirectory() as temp_dir:
            blueprint_path = Path(temp_dir) / "blueprint.json"
            view_path = Path(temp_dir) / "view.json"
            save_blueprint(blueprint_path, blueprint)
            save_view_state(view_path, view_state)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.stackscope.cli",
                    "draw",
                    str(blueprint_path),
                    "--format",
                    "html",
                    "--view",
                    str(view_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("<!DOCTYPE html>", result.stdout)
            self.assertIn('"blueprint_name": "sample-app"', result.stdout)

    def test_cli_preview_artifacts_round_trip_from_checked_in_sample_files(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.stackscope.cli",
                "export",
                str(SAMPLE_BLUEPRINT),
                "--format",
                "html",
                "--view",
                str(SAMPLE_VIEW),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("<!DOCTYPE html>", result.stdout)
        self.assertIn("AWS Cloud", result.stdout)
        self.assertIn('"root_path": "examples/sample-app"', result.stdout)

    def test_cli_export_view_and_bundle_formats(self) -> None:
        view_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.stackscope.cli",
                "export",
                str(SAMPLE_BLUEPRINT),
                "--format",
                "view",
                "--view",
                str(SAMPLE_VIEW),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        bundle_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.stackscope.cli",
                "export",
                str(SAMPLE_BLUEPRINT),
                "--format",
                "bundle",
                "--view",
                str(SAMPLE_VIEW),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        view_payload = json.loads(view_result.stdout)
        bundle_payload = json.loads(bundle_result.stdout)
        self.assertEqual(view_payload["blueprint_name"], "sample-app")
        self.assertIn("blueprint", bundle_payload)
        self.assertIn("view_state", bundle_payload)

    def test_checked_in_bundle_file_renders_html(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.stackscope.cli",
                "draw",
                str(SAMPLE_BUNDLE),
                "--format",
                "html",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("<!DOCTYPE html>", result.stdout)
        self.assertIn("AWS Cloud", result.stdout)
