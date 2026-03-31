# V1 Scope

## Included

- Python CLI
- filesystem scanning for common architecture-relevant artifacts
- normalized architecture model
- formal JSON schema for the blueprint model
- draw command for Mermaid and browser HTML architecture output
- markdown summary renderer
- JSON export
- editable view-state JSON export
- simple query command
- browser preview with SVG graph rendering
- sample project and tests

## Scanner Coverage

- `docker-compose.yml`
- `package.json`
- `.github/workflows/*.yml`
- Kubernetes YAML files
- Terraform `.tf`
- `nginx.conf`
- `.env.example` and similar env sample files

## Explicit Constraints

- heuristic parsing is acceptable
- no database required
- no full frontend application in V1
- no runtime discovery
- no multi-repo federation
- no attempt to support every YAML dialect perfectly

## Acceptance Criteria

- a user can run the CLI against `examples/sample-app`
- the scan discovers at least services, datastores, CI, cloud resources, and a few relationships
- the draw command emits Mermaid and HTML output that reflect discovered relationships
- the query command returns filtered results
- Mermaid, HTML, and markdown output are readable without manual edits
- JSON export contains the full normalized model
- view-state JSON contains editable node `x` and `y` positions
