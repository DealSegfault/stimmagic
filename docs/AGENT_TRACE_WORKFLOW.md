# Agent run traces

Stimma records one generic `AgentRun` for each v2 chat execution. The trace is
available to every project, not only Maya, and is exposed from the chat with
the **Agent trace** button.

## What the trace records

Each run is a chronological list of operational steps:

1. LLM request: model, turn number, context estimate, returned tool names and
   a safe decision summary.
2. World-state and reference resolution: the tool inputs, resolved output and
   explicit `sequence / scene / shot` context when a script table is present.
3. Prompt or code execution: whether the action is an image generation, video
   generation, skill activation, evaluation or Python execution; the bounded
   prompt/code preview; reference media ids; and any discovered generation
   job/media ids.
4. Evaluation and continuity updates: inspection, validation, memory or scene
   changes.
5. Failure, pause, cancellation and completion status, including the error
   category and duration timestamps.

Inputs and outputs are bounded and redacted. Secrets are removed, and private
chain-of-thought fields are replaced with an omission marker. The trace is
intended to answer “what happened and which artifact caused it?”, not to dump
hidden model reasoning.

## API

- `GET /api/chats/{chat_id}/agent-runs`
- `GET /api/projects/{project_id}/agent-runs`
- `GET /api/agent-runs/{run_id}`

WebSocket updates are emitted as `agent_run_started`, `agent_run_step`, and
`agent_run_finished`. The UI polls while the trace modal is open so a running
loop can be inspected without a page refresh.

## Next-plan smoke test

Use a fresh chat attached to the next scene/plan:

1. Open **Agent trace** before sending the request.
2. Confirm the first steps show the current project world state and canonical
   reference ids, with deprecated media excluded.
3. Confirm the prompt step contains the exact prompt sent to the image/video
   provider and the expected reference order.
4. Confirm the generation step exposes the job id and resulting media id.
5. If the candidate is wrong, keep the run id, edit the prompt, and compare
   the next run’s references and decision summaries with the first run.
6. For a failed provider call, verify the failed step remains visible. A
   retry should create a new run that can be compared with the failed run;
   the original evidence must remain available.

The first acceptance gate is trace completeness: every stage must have a
status, a human-readable summary, and either an input/output id or an explicit
reason why the stage was skipped.

## Script numbering contract

Direction scenes and script shots are different coordinates. For example,
`sequence 1 / scene 1 / shot 4` means the fourth row inside the first scene's
shot map; it does not mean Direction `scene_number=4`. The World State tool now
returns `shot_context.current`, `shot_context.previous`, and
`shot_context.next` when it can resolve a `Plan N` or `Shot N` row. The previous
accepted last frame is a semantic continuity anchor; an independent cut may
change framing, but it must not revert the action state or use a stale frame.

The generation contract must also persist the accepted output and its extracted
last frame against these coordinates. A later shot should never guess a prior
frame from a generic project asset list.
