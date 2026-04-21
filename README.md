# XiaoBa World

> A repo-aware data flywheel built on top of `XiaoBa Runtime`.

`XiaoBa World` is not a random code-fixing playground. It is the outer world around `XiaoBa Runtime`: the place where runtime logs, agent roles, inspection, implementation, verification, and world-level evolution are organized into a single loop.

## What This Repo Is

This repository defines the world around XiaoBa:

- `XiaoBa-CLI`
  - the runtime kernel
  - included here as a submodule
- `XiaoBa-AutoDev`
  - the case platform for log archive, artifacts, state transitions, and loop visibility
- world-level docs
  - worldview
  - agent loop design
  - product and architecture notes

In short:

```text
XiaoBa-CLI runtime
  -> produces logs and session traces
  -> sends signals into XiaoBa-AutoDev
  -> Inspector / Engineer / Reviewer loop runs
  -> validated fixes and skills flow back into the world
```

## Why XiaoBa World Exists

Most agent systems stop at "one assistant, many prompts".

`XiaoBa World` takes a different route:

- one runtime kernel
- specialized roles instead of duplicated bots
- real logs above abstract assumptions
- closed-loop evolution instead of static prompting

That makes this repository the home of:

- the loop definition
- the system worldview
- the world-facing docs and planning assets
- the AutoDev platform used to process real cases

## Architecture

```text
User / Platform
  -> XiaoBa-CLI runtime
  -> logs / session jsonl
  -> XiaoBa-AutoDev
  -> Inspector
  -> Engineer
  -> Reviewer
  -> validated writeback
  -> next generation of XiaoBa World
```

## Repository Layout

| Path | Purpose |
| --- | --- |
| `XiaoBa-CLI/` | Runtime kernel and role execution layer. This repo is tracked as a Git submodule. |
| `XiaoBa-AutoDev/` | Case platform for log ingestion, artifacts, events, state, and review chain. |
| `AGENT_LOOP_XIAOBA_WORLD.md` | End-to-end agent loop design. |
| `XIAOBA_WORLD_WORLDVIEW.md` | Worldview and system philosophy. |
| `docs/` | Product, architecture, and implementation notes for world-level modules. |

## Quick Start

### 1. Clone the world

```bash
git clone https://github.com/buildsense-ai/XiaoBa-World.git
cd XiaoBa-World
git submodule update --init --recursive
```

### 2. Prepare local config

```bash
cp XiaoBa-AutoDev/.env.example XiaoBa-AutoDev/.env
cp XiaoBa-CLI/.env.example XiaoBa-CLI/.env
```

Fill secrets locally. Do not commit them.

### 3. Start the case platform

```bash
cd XiaoBa-AutoDev
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --app-dir .
```

### 4. Start the runtime

```bash
cd ../XiaoBa-CLI
npm install
npm run dev -- chat -i
```

## Security and Repo Hygiene

This repository is intentionally set up so local secrets and runtime residue do not get published:

- `.env`, `.env.runtime`, `.env.inspector`, and similar local config files are ignored
- logs, session traces, caches, temp files, and AutoDev local case data are ignored
- IDE state and machine-specific files are ignored

If you add a new service with local credentials, add its secret-bearing files to `.gitignore` before pushing.

## Core Documents

- [Agent Loop Design](./AGENT_LOOP_XIAOBA_WORLD.md)
- [Worldview](./XIAOBA_WORLD_WORLDVIEW.md)
- [CatVis Architecture](./docs/CATVIS_ARCHITECTURE.md)
- [CatVis PRD](./docs/CATVIS_PRD.md)
- [CatVis Technical Breakdown](./docs/CATVIS_TECH_BREAKDOWN.md)

## Design Position

`XiaoBa World` is a world built on `XiaoBa Runtime`, not a generic patch bot.

That means:

- the runtime remains the execution kernel
- the world defines how roles cooperate
- the data flywheel is grounded in real runtime evidence
- fixes, skills, and docs are routed back into the right target instead of being sprayed into arbitrary code

## Status

This repository is the coordination layer for a living system.

The runtime evolves in `XiaoBa-CLI`.
The case loop runs through `XiaoBa-AutoDev`.
The world definition, docs, and orchestration logic live here.
