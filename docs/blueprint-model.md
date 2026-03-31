# Blueprint Model

Stackscope has three distinct layers in V1:

## 1. Inputs

These are source artifacts discovered in a target repo:

- YAML such as `docker-compose.yml`, Kubernetes manifests, and GitHub Actions workflows
- JSON such as `package.json`
- Terraform `.tf`
- nginx configuration
- env example files

These files are evidence. They are not the architecture diagram format.

## 2. Internal Blueprint Model

Scanners normalize evidence into one shared blueprint model. That model is the contract between discovery and output generation.

Core entities:

- `components`
- `relationships`
- `evidence`

This means Stackscope does not draw directly from raw YAML or raw JSON. It draws from the normalized blueprint.

For blueprinting work after the scan, Stackscope can also use a separate `view.json` file. That file stores layout-oriented data such as node `x` and `y` positions without mutating the scan-derived blueprint.

## 3. Outputs

Outputs are generated from the blueprint model:

- browser SVG preview from blueprint plus optional view state
- Mermaid for diagrams
- markdown for architecture summaries
- JSON for machine-readable export

## Why This Matters

- scanners can evolve without rewriting renderers
- one scan can support many outputs
- query and draw stay consistent because they use the same model
- the internal representation is inspectable and testable
