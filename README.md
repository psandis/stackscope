# Stackscope

Stackscope is a lightweight architecture discovery and blueprinting CLI for existing engineering environments. It scans common engineering artifacts, infers components and relationships, builds a normalized blueprint model, and renders a big-picture architecture view from that model.

It is built for solution and enterprise architects who need to understand an unfamiliar setup quickly without starting in a manual diagramming tool.

## Mission

Stackscope is built around one flow:

- scan engineering artifacts
- infer a normalized architecture blueprint
- preview and adjust the resulting view
- export documentation and diagram artifacts from the same model

It is not a manual diagramming canvas first. It is a scan-first discovery and blueprinting tool.

## Inputs, Model, Outputs

Stackscope keeps a strict boundary between scan sources, normalized model, and rendered outputs.

- Inputs: `docker-compose.yml`, `package.json`, GitHub Actions workflows, Kubernetes YAML, Terraform, `nginx.conf`, and env examples
- Internal model: a normalized blueprint containing `components`, `relationships`, and `evidence`
- Saved view state: editable node layout data with `x` and `y` positions
- Outputs: browser preview, SVG, Mermaid, Markdown, blueprint JSON, view JSON, and bundle JSON

That means Stackscope does not draw directly from raw YAML or raw JSON. It scans those files, builds the blueprint, and draws from the blueprint plus optional view state.

## What V1 Does

- scans a repo for common architecture-relevant artifacts
- normalizes findings into components, relationships, cloud usage, pipelines, and integrations
- supports simple model queries
- serves a browser preview with filtering, inspection, shareable URL state, and drag-to-move layout editing
- exports Mermaid, SVG, HTML, Markdown, blueprint JSON, view JSON, and bundle JSON
- ships with a sample app and checked-in saved artifacts for round-trip testing

## Repo Structure

```text
.
├── .codex/
├── docs/
├── examples/
├── src/
├── tests/
├── PRODUCT_SPEC.md
├── README.md
└── pyproject.toml
```

Relevant docs:

- `docs/vision.md`
- `docs/v1-scope.md`
- `docs/blueprint-model.md`
- `docs/blueprint.schema.json`

## Quick Start

Scan the sample app and inspect the summary:

```bash
python3 -m src.stackscope.cli scan examples/sample-app
```

Generate saved artifacts:

```bash
python3 -m src.stackscope.cli scan examples/sample-app \
  --json-out blueprint.json \
  --view-out view.json \
  --bundle-out bundle.json
```

Preview directly from source:

```bash
python3 -m src.stackscope.cli preview examples/sample-app --port 5123
```

Preview from saved files:

```bash
python3 -m src.stackscope.cli preview blueprint.json --view view.json --port 5123
python3 -m src.stackscope.cli preview examples/sample-app/bundle.json --port 5123
```

Draw and export:

```bash
python3 -m src.stackscope.cli draw examples/sample-app
python3 -m src.stackscope.cli draw examples/sample-app --format svg --out architecture.svg
python3 -m src.stackscope.cli draw blueprint.json --format html --view view.json --out architecture.html
python3 -m src.stackscope.cli export bundle.json --format view
```

## Install

```bash
pip install -e .
```

Then use:

```bash
stackscope scan examples/sample-app
stackscope preview examples/sample-app --port 5123
stackscope draw examples/sample-app --format svg --out architecture.svg
```

## Saved Artifact Types

Stackscope supports three saved formats:

- `blueprint.json`: normalized scan result
- `view.json`: editable layout state with node `x` and `y`
- `bundle.json`: both blueprint and view state in one file

The sample project ships with all three:

- [examples/sample-app/blueprint.json](/Users/petrisandholm/Projects/psandis-projects/stackscope/examples/sample-app/blueprint.json)
- [examples/sample-app/view.json](/Users/petrisandholm/Projects/psandis-projects/stackscope/examples/sample-app/view.json)
- [examples/sample-app/bundle.json](/Users/petrisandholm/Projects/psandis-projects/stackscope/examples/sample-app/bundle.json)

That means you can test the full round-trip workflow immediately without rescanning first.

## Commands

### `scan`

Scans a target directory, builds the normalized blueprint, and prints a summary. Optional artifacts can be written in one run.

```bash
stackscope scan ./my-repo \
  --json-out blueprint.json \
  --view-out view.json \
  --bundle-out bundle.json \
  --markdown-out architecture.md \
  --mermaid-out architecture.mmd
```

### `draw`

Renders the architecture from either a live scan or a saved blueprint/bundle.

Supported formats:

- `mermaid`
- `markdown`
- `html`
- `svg`

Examples:

```bash
stackscope draw ./my-repo
stackscope draw ./my-repo --format html
stackscope draw ./my-repo --format svg --out architecture.svg
stackscope draw blueprint.json --format html --view view.json
stackscope draw bundle.json --format svg --out architecture.svg
```

### `preview`

Serves the browser architecture preview. By default it binds to `127.0.0.1:5123`.

```bash
stackscope preview ./my-repo
stackscope preview ./my-repo --host 0.0.0.0 --port 5123
stackscope preview blueprint.json --view view.json --port 5123
stackscope preview bundle.json --port 5123
```

The preview uses an explicit SVG runtime graph, not Mermaid.

Current preview features:

- component and source filters
- searchable component list
- inspector with incoming, outgoing, and evidence views
- relationship focus
- shareable URL state
- hide/show tools
- zoom
- drag-to-move node layout
- `Export View` for updated `view.json`

### `query`

Runs a simple query against the inferred blueprint.

Supported V1 query values:

- `components`
- `relationships`
- `cloud`
- `pipelines`
- `find:<term>`
- `type:<component-type>`

Examples:

```bash
stackscope query ./my-repo components
stackscope query ./my-repo type:service
stackscope query blueprint.json cloud
stackscope query bundle.json find:postgres
```

### `export`

Prints a chosen artifact format to stdout or writes it to a file with `--out`.

Supported formats:

- `json`
- `view`
- `bundle`
- `markdown`
- `mermaid`
- `html`
- `svg`

Examples:

```bash
stackscope export ./my-repo --format json
stackscope export ./my-repo --format view
stackscope export ./my-repo --format bundle
stackscope export ./my-repo --format svg --out architecture.svg
stackscope export blueprint.json --format html --view view.json --out architecture.html
```

## Preview and Editing Workflow

The intended blueprinting flow after discovery is:

1. scan source artifacts into `blueprint.json`
2. generate `view.json`
3. open the browser preview
4. drag nodes to adjust the layout
5. export the updated `view.json`
6. redraw from `blueprint.json` plus the saved `view.json`

That keeps scan-derived architecture facts separate from human layout choices.

## Cloud Visuals

For mapped provider services, the preview and SVG export now use official vendor SVG assets rather than hand-drawn pseudo-icons.

Current mapped official icons include selected services for:

- AWS
- Azure
- Google Cloud

Unmapped services still fall back to neutral diagram nodes.

## Current V1 Coverage

- Docker Compose services and `depends_on`
- `package.json` app metadata and library dependencies
- GitHub Actions workflows and reused actions
- Kubernetes manifests with basic workload and service detection
- Terraform providers and resources with cloud inference
- nginx upstream and proxy relationships
- env example files with integration-oriented variables

The scanners are heuristic in V1. They aim for useful discovery quickly, not perfect semantic coverage.

## Example Output

The sample app demonstrates a mixed environment with:

- application service
- Postgres
- Redis
- GitHub Actions CI
- Kubernetes resources
- Terraform cloud resources
- nginx gateway

You can preview it immediately with:

```bash
stackscope preview examples/sample-app/bundle.json --port 5123
```

Or export a static SVG:

```bash
stackscope draw examples/sample-app/blueprint.json --format svg --view examples/sample-app/view.json --out architecture.svg
```

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

## Roadmap After V1

- richer query language
- deeper GitHub workflow modeling
- broader cloud resource mapping coverage
- better edge routing and diagram readability
- YAML support for blueprint and view files
- renderer modularization
- plugin scanner system
