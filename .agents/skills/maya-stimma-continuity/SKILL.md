---
name: maya-stimma-continuity
display_name: Maya Stimma Continuity
description: Generate and revise Maya cinematic assets and shots in Stimma while preserving location, prop, character, prompt, and last-frame continuity. Use for Nano Banana/Agy asset loops, keyframe blocking, H3 video generation, and cross-chat scene handoffs.
author: user
tags: [maya, continuity, nano-banana, minimax-h3, stimma]
---

# Maya / Stimma continuity

Use this skill for Maya scene production. The canonical workflow is documented in [`docs/MAYA_STIMMA_GENERATION_WORKFLOW.md`](../../../docs/MAYA_STIMMA_GENERATION_WORKFLOW.md).

## Required operating sequence

1. Call `get_world_state` for the requested project scene before generating.
2. Inspect the active canonical location, character, prop, and previous-last-frame media.
3. Build an explicit `<Picture N>` reference map. Keep the manifest order and prompt order identical.
4. Create missing props as viewsheets first. Preserve the original asset prompt and iterate with the reference image plus the requested change.
5. Generate one blocking keyframe. Treat it as a candidate until it passes the location, identity, scale, hand/sleeve, lighting, and contamination checks.
6. Select H3 mode from the reference count: T2V for none, I2V for one start image, and R2V/Ref2VA for multiple references or a semantic anchor. Never use I2V with multiple independent references.
7. For video prompts include `subject_definitions`, retention rules, timed motion, camera, lighting, negatives, object-only audio rules, and the Chinese supplement at the end.
8. Evaluate identity, geography, motion, temporal stability, and audio. Register accepted media and mark deprecated references explicitly in the project handoff.

## Continuity priorities

- A global location controls geography and material language.
- A close location controls local surface relationships.
- A viewsheet controls the exact asset identity.
- A previous canonical last frame controls raccord, not location redesign.
- A generated blocking frame never becomes a location master without visual QA.

When a prop is wrong, revise the prop asset. Do not make the scene prompt repair an unapproved asset and the environment simultaneously.
