# Stackscope Product Spec

Stackscope is a lightweight architecture discovery and blueprinting CLI. Its core job is to scan engineering artifacts, infer a simplified model of the environment, and draw a big-picture architecture view from that model.

## Problem

Architects and technical leads often inherit repos and environments with incomplete or stale documentation. The useful signals already exist in source repos and delivery configuration, but they are distributed across many files and formats.

## Mission

Help architects understand an existing setup quickly by turning engineering evidence into:

- a scan-derived architecture model
- a drawn ecosystem view with visible relationships
- a markdown summary
- a simple query surface for exploration
- a JSON representation that other tooling can consume

## Primary Workflow

1. scan a repo or project directory
2. infer components, dependencies, integrations, data stores, pipelines, and cloud signals
3. normalize them into one internal blueprint model
4. draw the architecture from that model
5. query or export the same model as needed

## Inputs, Model, Outputs

- Inputs are source files such as YAML, JSON, Terraform, nginx config, and env examples.
- The internal blueprint model is the source of truth inside Stackscope.
- Drawing is generated from the blueprint model, not directly from raw input files.
- JSON is the V1 machine-readable export of that model.
- Mermaid is the V1 drawing output.

## Non-Goals

- manual diagram authoring
- full CMDB replacement
- runtime observability or RPA orchestration
- perfect semantic parsing of every infrastructure format in V1

## V1 Outcomes

- run `scan` against a repo and get a useful summary
- run `draw` and generate a Mermaid architecture diagram from the same scan-derived model
- detect common components and relationships from a handful of high-value files
- export Mermaid, markdown, and JSON from one internal model
- support a simple query command for quick exploration

## V1 Product Shape

- CLI-first
- Python implementation for speed of iteration
- scanner-first architecture
- Mermaid as the initial drawing format
- markdown and JSON as parallel outputs from the same model
