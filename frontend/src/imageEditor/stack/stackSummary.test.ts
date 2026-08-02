import assert from 'node:assert/strict'
import test from 'node:test'

import { summarizeStack } from './stackSummary.ts'

const names: Record<string, string> = {
  'builtin:darkroom-develop': 'Develop',
  'runware:klein': 'Klein',
  'topaz:gigapixel': 'Gigapixel',
}
const toolName = (id: string | null | undefined) => names[String(id)] || String(id || '')

test('an absent or malformed record summarizes to nothing', () => {
  assert.deepEqual(summarizeStack(undefined).steps, [])
  assert.deepEqual(summarizeStack(null).steps, [])
  assert.deepEqual(summarizeStack('{}' as any).steps, [])
  assert.equal(summarizeStack([]).total, 0)
})

test('steps read newest first, the order the Edits list uses', () => {
  const summary = summarizeStack([
    { class: 'parametric', label: 'Crop', exec: { kind: 'crop' }, params: {} },
    { class: 'parametric', label: 'Light', exec: { kind: 'adjust' }, params: {} },
  ])
  assert.deepEqual(summary.steps.map(step => step.name), ['Light', 'Crop'])
  assert.equal(summary.total, 2)
})

test('a generative step names its verb and carries its prompt', () => {
  const [step] = summarizeStack([
    {
      class: 'patch',
      label: 'Remove the parked car',
      exec: { kind: 'tool', tool_id: 'runware:klein', task_type: 'inpaint-image' },
      operation: 'remove',
      params: { prompt: 'empty asphalt' },
      job_id: 'job-1',
    },
  ], toolName).steps
  assert.equal(step.name, 'Remove the parked car')
  // The model that made the pixels is provenance, not identity: it is the
  // same for a whole session's rows and says nothing about the step.
  assert.equal(step.detail, 'Remove')
  assert.equal(step.note, 'empty asphalt')
})

test('the verb is not repeated when it is already the step name', () => {
  const [step] = summarizeStack([
    {
      class: 'patch',
      label: 'Repaint',
      exec: { kind: 'tool', tool_id: 'runware:klein', task_type: 'inpaint-image' },
      operation: 'repaint',
      params: {},
      reference_images: [{ media_id: 3 }, { media_id: 4 }],
    },
  ], toolName).steps
  assert.equal(step.detail, '2 references')
})

test('a save made before the verb was recorded reads it off the task type', () => {
  const [step] = summarizeStack([
    {
      class: 'patch',
      label: 'Sign',
      exec: { kind: 'tool', tool_id: 'runware:klein', task_type: 'erase-image' },
      params: {},
    },
  ], toolName).steps
  assert.equal(step.detail, 'Erase')
})

test('a Retouch container stays one row and counts what it holds', () => {
  const [step] = summarizeStack([
    {
      class: 'container',
      label: 'Retouch',
      exec: { kind: 'retouch-regions', version: 1 },
      params: {
        regions: [
          { kind: 'heal', settings: {} },
          { kind: 'heal', settings: {} },
          { kind: 'clone', settings: {} },
        ],
      },
    },
  ]).steps
  assert.equal(step.name, 'Retouch')
  assert.equal(step.detail, '')
  assert.equal(step.note, '3 regions')
})

test('a scoped adjustment is one region wearing a row, so it counts nothing', () => {
  const [step] = summarizeStack([
    {
      class: 'container',
      label: 'Grading',
      exec: { kind: 'retouch-regions', version: 1 },
      params: { regions: [{ kind: 'grade', settings: {} }] },
    },
  ]).steps
  assert.equal(step.name, 'Grading')
  assert.equal(step.detail, '')
  assert.equal(step.note, '')
})

test('crop reports the rotation and flips a reader cannot infer', () => {
  const [rotated] = summarizeStack([
    {
      class: 'parametric', label: 'Crop', exec: { kind: 'crop' },
      params: { rect: { x: 0.5, y: 0.5, width: 0.6, height: 0.6 }, rotation90: 1, flipX: true },
    },
  ]).steps
  assert.equal(rotated.detail, '90° · Flipped')

  const [straight] = summarizeStack([
    {
      class: 'parametric', label: 'Crop', exec: { kind: 'crop' },
      params: { rect: { x: 0.5, y: 0.5, width: 0.6, height: 0.6 }, rotation90: 0, cropRotation: 0 },
    },
  ]).steps
  assert.equal(straight.detail, '')
})

test('a Darkroom filter step names the tool that ran', () => {
  const [step] = summarizeStack([
    {
      class: 'parametric', label: 'Develop',
      exec: { kind: 'backend-filter', tool_id: 'builtin:darkroom-develop' },
      params: { grain: 20 },
    },
  ], toolName).steps
  assert.equal(step.detail, 'Develop')
})

test('annotations count their shapes', () => {
  const [step] = summarizeStack([
    { class: 'container', label: 'Text', exec: { kind: 'annotate' }, params: { shapes: [{}, {}] } },
  ]).steps
  assert.equal(step.detail, '2 shapes')
})

test('the output stage reads as the operation it is, and names its upscaler', () => {
  const photo = summarizeStack([
    {
      class: 'output', label: 'Output',
      exec: { kind: 'tool', tool_id: 'topaz:gigapixel', task_type: 'upscale-image' },
      params: { method: 'photo', scaleFactor: 4 },
    },
  ], toolName)
  assert.equal(photo.steps[0].name, 'Upscale')
  assert.equal(photo.steps[0].detail, '4× · Gigapixel')

  const resample = summarizeStack([
    {
      class: 'output', label: 'Output', exec: { kind: 'resample' },
      params: { method: 'resample', resolutionMode: 'pixels', targetResolution: 2160 },
    },
  ], toolName)
  assert.equal(resample.steps[0].name, 'Resample')
  assert.equal(resample.steps[0].detail, '2160px')
})
