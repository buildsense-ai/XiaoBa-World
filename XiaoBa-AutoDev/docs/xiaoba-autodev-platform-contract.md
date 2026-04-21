# XiaoBa-AutoDev Platform Contract

## Goal

XiaoBa-AutoDev is a case-driven automation platform for turning runtime logs and conversation traces into a closed loop:

1. inspect the problem
2. implement a fix or extract a skill
3. review the result and close or reopen the case

The platform owns:

- case state
- agent orchestration
- artifact metadata
- event timeline
- human-visible closure progress

The agents own:

- analysis
- implementation
- validation and closure

## Agent Roles

### 1. Inspector

Responsibility:

- read runtime logs or conversation jsonl
- identify the dominant problem type
- collect evidence
- produce the assessment document
- decide the recommended next lane

Problem categories:

- `runtime_bug`
- `new_skill_candidate`
- `skill_fix`
- `insufficient_signal`

Outputs:

- assessment artifact
- evidence summary
- recommended action for engineer

### 2. Engineer

Responsibility:

- fix runtime bugs
- extract a new skill from the case
- repair an existing skill
- produce implementation artifacts and implementation document

Outputs:

- code patch, skill files, config changes, or no-op explanation
- implementation artifact
- implementation summary

### 3. Reviewer

Responsibility:

- verify whether the engineer output actually resolves the case
- judge whether the produced skill is usable
- close or reopen the case
- produce the closure document

Outputs:

- review artifact
- closure decision
- reopen reason if needed

## Case Lifecycle

Canonical states:

- `new`
- `inspecting`
- `fixing`
- `reviewing`
- `closed`
- `reopened`
- `blocked`

Allowed transitions:

- `new -> inspecting`
- `inspecting -> fixing`
- `inspecting -> blocked`
- `fixing -> reviewing`
- `fixing -> blocked`
- `reviewing -> closed`
- `reviewing -> reopened`
- `reopened -> fixing`
- `blocked -> inspecting`
- `blocked -> fixing`

State ownership:

- `inspecting`: Inspector
- `fixing`: Engineer
- `reviewing`: Reviewer
- `closed`: Reviewer
- `reopened`: Reviewer

## Artifact Types

Each case can have multiple artifacts.

Core artifact types:

- `raw_log`
- `raw_jsonl`
- `assessment`
- `implementation`
- `review`
- `patch`
- `skill_bundle`
- `verification_report`
- `closure_note`
- `attachment`

Artifact stages:

- `input`
- `analysis`
- `execution`
- `verification`
- `closure`

Artifact storage principle:

- file body lives in local workdir or object storage
- platform stores artifact metadata and links

## Core Data Model

### Case

```json
{
  "case_id": "case-20260420-001",
  "title": "send_to_inspector repeated failure in runtime",
  "status": "inspecting",
  "category": "runtime_bug",
  "source": "xiaoba_runtime",
  "source_session_id": "group:oc_xxx",
  "source_user_id": "ou_xxx",
  "created_at": "2026-04-20T10:00:00Z",
  "updated_at": "2026-04-20T10:05:00Z",
  "priority": "normal",
  "summary": "User repeatedly triggered a failing tool.",
  "current_owner_agent": "inspector",
  "recommended_next_action": "runtime_fix",
  "labels": ["runtime", "tool-failure"]
}
```

### Artifact

```json
{
  "artifact_id": "art-20260420-001",
  "case_id": "case-20260420-001",
  "type": "assessment",
  "stage": "analysis",
  "title": "Inspector assessment",
  "format": "markdown",
  "storage_mode": "local",
  "storage_path": "cases/case-20260420-001/assessment.md",
  "produced_by_agent": "inspector",
  "version": 1,
  "created_at": "2026-04-20T10:06:00Z",
  "metadata": {
    "recommended_action": "runtime_fix"
  }
}
```

### Event

```json
{
  "event_id": "evt-20260420-001",
  "case_id": "case-20260420-001",
  "kind": "state_changed",
  "actor_type": "agent",
  "actor_id": "inspector",
  "created_at": "2026-04-20T10:06:10Z",
  "payload": {
    "from": "new",
    "source_status": "new",
    "to": "inspecting",
    "target_status": "inspecting"
  }
}
```

`from` / `to` are the canonical fields. `source_status` / `target_status` are compatibility aliases for downstream consumers that compute loop metrics from state transition events.

## Shared Platform APIs

These are platform-owned APIs. Agents should not talk to each other directly by file path conventions alone.

### 1. Create Case

`POST /api/cases`

Input:

```json
{
  "title": "User runtime log review",
  "source": "xiaoba_runtime",
  "source_session_id": "group:oc_xxx",
  "source_user_id": "ou_xxx",
  "summary": "User asked why send_to_inspector failed repeatedly.",
  "priority": "normal",
  "labels": ["runtime", "feishu"]
}
```

Output:

```json
{
  "case_id": "case-20260420-001",
  "status": "new",
  "created_at": "2026-04-20T10:00:00Z"
}
```

### 2. Append Artifact

`POST /api/cases/:caseId/artifacts`

Input:

```json
{
  "type": "raw_log",
  "stage": "input",
  "title": "17-10-53_feishu.log",
  "format": "text",
  "storage_mode": "local",
  "storage_path": "cases/case-20260420-001/files/17-10-53_feishu.log",
  "produced_by_agent": "system",
  "metadata": {
    "kind": "runtime_log"
  }
}
```

Output:

```json
{
  "artifact_id": "art-20260420-raw-1",
  "case_id": "case-20260420-001"
}
```

### 3. Append Event

`POST /api/cases/:caseId/events`

Input:

```json
{
  "kind": "artifact_created",
  "actor_type": "agent",
  "actor_id": "inspector",
  "payload": {
    "artifact_id": "art-20260420-assessment-1"
  }
}
```

Output:

```json
{
  "event_id": "evt-20260420-001"
}
```

### 4. Update State

`POST /api/cases/:caseId/state`

Input:

```json
{
  "from": "inspecting",
  "to": "fixing",
  "actor_id": "inspector",
  "reason": "Assessment complete. Forwarding to engineer."
}
```

Output:

```json
{
  "case_id": "case-20260420-001",
  "status": "fixing",
  "updated_at": "2026-04-20T10:10:00Z"
}
```

### 5. Get Case Detail

`GET /api/cases/:caseId`

Output:

```json
{
  "case": {},
  "artifacts": [],
  "events": []
}
```

## Agent Contracts

The platform only needs to define agent input and output contracts. Internal reasoning is agent-specific.

### Inspector Contract

Input:

```json
{
  "case": {
    "case_id": "case-20260420-001",
    "status": "inspecting",
    "category": null,
    "summary": "User asked why send_to_inspector failed repeatedly."
  },
  "inputs": {
    "artifacts": [
      {
        "type": "raw_log",
        "storage_path": "cases/case-20260420-001/files/17-10-53_feishu.log"
      },
      {
        "type": "raw_jsonl",
        "storage_path": "cases/case-20260420-001/files/session.jsonl"
      }
    ]
  }
}
```

Output:

```json
{
  "category": "runtime_bug",
  "recommended_next_action": "runtime_fix",
  "assessment_artifact": {
    "type": "assessment",
    "stage": "analysis",
    "title": "Inspector assessment",
    "format": "markdown",
    "storage_path": "cases/case-20260420-001/assessment.md"
  },
  "evidence_summary": {
    "root_cause_hypothesis": "Tool call path failed due to network reachability.",
    "confidence": "high",
    "signals": [
      "repeated timeout",
      "user mentioned security group"
    ]
  },
  "next_state": "fixing"
}
```

### Engineer Contract

Input:

```json
{
  "case": {
    "case_id": "case-20260420-001",
    "status": "fixing",
    "category": "runtime_bug"
  },
  "assessment": {
    "artifact_type": "assessment",
    "storage_path": "cases/case-20260420-001/assessment.md"
  },
  "inputs": {
    "artifacts": [
      {
        "type": "raw_log",
        "storage_path": "cases/case-20260420-001/files/17-10-53_feishu.log"
      }
    ]
  }
}
```

Output:

```json
{
  "implementation_artifacts": [
    {
      "type": "patch",
      "stage": "execution",
      "title": "runtime-fix.patch",
      "format": "diff",
      "storage_path": "cases/case-20260420-001/runtime-fix.patch"
    },
    {
      "type": "implementation",
      "stage": "execution",
      "title": "Engineer implementation note",
      "format": "markdown",
      "storage_path": "cases/case-20260420-001/implementation.md"
    }
  ],
  "implementation_summary": {
    "action_taken": "patched runtime retry and fallback handling",
    "result_type": "runtime_fix",
    "risk_level": "medium"
  },
  "next_state": "reviewing"
}
```

For `new_skill_candidate`, the engineer returns `skill_bundle` instead of `patch`.

For `skill_fix`, the engineer returns a patched skill bundle and implementation note.

### Reviewer Contract

Input:

```json
{
  "case": {
    "case_id": "case-20260420-001",
    "status": "reviewing",
    "category": "runtime_bug"
  },
  "assessment": {
    "storage_path": "cases/case-20260420-001/assessment.md"
  },
  "implementation_artifacts": [
    {
      "type": "patch",
      "storage_path": "cases/case-20260420-001/runtime-fix.patch"
    },
    {
      "type": "implementation",
      "storage_path": "cases/case-20260420-001/implementation.md"
    }
  ]
}
```

Output:

```json
{
  "review_artifacts": [
    {
      "type": "review",
      "stage": "verification",
      "title": "Reviewer validation report",
      "format": "markdown",
      "storage_path": "cases/case-20260420-001/review.md"
    },
    {
      "type": "closure_note",
      "stage": "closure",
      "title": "Closure summary",
      "format": "markdown",
      "storage_path": "cases/case-20260420-001/closure.md"
    }
  ],
  "decision": "closed",
  "decision_reason": "Fix validated against the case evidence and expected behavior.",
  "next_state": "closed"
}
```

If review fails:

```json
{
  "decision": "reopened",
  "decision_reason": "Implementation does not cover the observed failure mode.",
  "next_state": "reopened"
}
```

## Frontend Views

The frontend should expose the case loop clearly to a human operator.

### Case List

Show:

- case id
- title
- status
- category
- current owner agent
- last updated time
- priority

### Case Detail

Show:

- summary card
- source context
- current state
- recommended next action
- artifact list
- event timeline

### Closure View

Show:

- assessment document
- implementation document
- review document
- final decision
- reopen reason if any

## Minimal Design Rules

- agents must exchange state through the platform, not implicit chat history
- every major step must emit an event
- every major output must become an artifact
- only the reviewer can close a case
- the engineer can modify code or skills, but cannot self-close
- if evidence is insufficient, the inspector must explicitly mark `insufficient_signal`
