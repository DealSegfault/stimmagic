# Maya — Stimma generation workflow

This is the reusable production contract for Maya's image and video generation work. It is intentionally split into two layers:

- this document contains stable workflow rules;
- the Stimma project memory and World State contain the current locations, props, revisions, continuity frames, and shot handoffs.

## Start every new shot

1. Read the project memory and call `get_world_state` before planning or generating.
2. Resolve the requested sequence/scene and list the active `@char_`, `@loc_`, and `@prop_` references.
3. Inspect the actual canonical media. Never rely on a filename or an old chat description alone.
4. Build a reference map before writing the prompt. Every `<Picture N>` must have exactly one declared role and the input order must match the prompt order.
5. Check for missing references. If a key location, character, prop, or continuity frame is missing, create or select it before rendering video.

## Reference roles

| Role | What it controls | What it must not control |
| --- | --- | --- |
| Global location | Apartment geography, materials, global light and palette | Exact prop design or a close-up composition |
| Close location | Local architecture, countertop, cabinet and surface relationships | Character identity or prop redesign |
| Character sheet | Face, hair, body, wardrobe and scale | Apartment geometry |
| Prop viewsheet | Exact shape, material, proportions and markings | Background architecture |
| Previous canonical last frame | Pose, sleeve/hand continuity, direction of light and raccord | Redesigning the location |
| Blocking keyframe | Approved shot composition and action staging | Becoming a new canonical location before QA |

Do not mix roles silently. A generated keyframe is a candidate until it passes visual QA and is registered as the current blocking reference.

## Asset loop

Every key prop needs a durable Stimma element, an approved Asset revision, a viewsheet, and the prompt that created or edited that revision.

```text
short creative idea
  -> asset prompt
  -> Nano Banana / Agy generation
  -> visual QA
  -> correction request with the reference image and original prompt
  -> revised prompt
  -> new generation
  -> QA and approval
  -> Stimma Asset revision + project Element
```

For an environment edit, send the canonical location and the exact asset reference together. Keep the original asset prompt available; an edit without both the reference image and its prompt is not reproducible.

## Keyframe gate

Before sending a keyframe to H3, verify:

- the camera angle is physically possible in the canonical location;
- surfaces, doors, windows, cabinets and sink/stove relationships still match;
- the prop has the approved identity, scale and contact shadow;
- the hand, sleeve and lighting agree with the previous canonical frame;
- no phone, dossier, prop from another scene or invented furniture has entered the image;
- the keyframe is one cinematic frame, not a viewsheet or collage.

If the keyframe fails because the asset is wrong, fix the asset revision. Do not ask the scene prompt to repair an unapproved asset and the location at the same time.

## H3 mode selection

- 0 visual references: T2V.
- 1 starting image: I2V/FL2VA as appropriate.
- 2 or more active visual references: R2V/Ref2VA.
- One semantic anchor that should not lock frame 0: R2V.

Never use I2V with multiple independent references. For an object insert that needs a location, props and a continuity anchor, use R2VA and explicitly map the references.

## Prompt contract

Every video prompt contains:

1. `subject_definitions` with the exact `<Picture N>` mapping;
2. a short shot summary;
3. retention rules — what stays unchanged;
4. timed motion beats and camera behavior;
5. lighting and material continuity;
6. explicit exclusions;
7. `overall_soundscape` and `non_diegetic_music`;
8. a Chinese consistency supplement at the very end, without replacing the English H3 structure.

For object-only shots, state `no dialogue` and describe only the required diegetic object sounds. Keep reference order in the manifest and prompt synchronized.

## Evaluation loop

Evaluate every render in five passes: identity, spatial continuity, motion/physics, temporal stability, and audio. Mark the result as candidate, accepted, or rejected in the project handoff. Keep rejected and deprecated references explicitly labelled so a new chat cannot accidentally reuse them.

## New-chat handoff

The project memory should always expose this compact state:

```text
CURRENT PROJECT / SEQUENCE / SHOT:
CANONICAL LOCATION ELEMENTS:
ACTIVE CHARACTER ELEMENTS:
ACTIVE PROP ELEMENTS:
PREVIOUS CANONICAL LAST FRAME:
APPROVED BLOCKING FRAME:
LATEST ACCEPTED RENDER:
DO_NOT_USE:
VIDEO MODE:
AUDIO RULES:
ACCEPTANCE CRITERIA:
```

The next chat must read this state, call `get_world_state`, inspect the referenced media, and only then generate. This makes the workflow independent of the previous conversation.
