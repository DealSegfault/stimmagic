import assert from 'node:assert/strict'
import test from 'node:test'
import {
  loraOptionsForTool,
  loraUploadConfigForTool,
  toolSupportsLoras,
} from './loraSchema.ts'

const tool = {
  parameter_schema: {
    properties: {
      loras: {
        type: 'array',
        'x-accept-upload': { extensions: ['.safetensors'], max_size: 42 },
        items: {
          properties: {
            path: { enum: ['z/ink_style.safetensors', 'a/photo.safetensors'] },
            name: { enum: ['Ink', 'Photo'] },
          },
        },
      },
    },
  },
}

test('editor LoRA options use the same paired schema enums as ToolView', () => {
  assert.equal(toolSupportsLoras(tool), true)
  assert.deepEqual(loraOptionsForTool(tool), [
    { path: 'a/photo.safetensors', name: 'Photo' },
    { path: 'z/ink_style.safetensors', name: 'Ink' },
  ])
})

test('editor LoRA upload support follows the provider schema', () => {
  assert.deepEqual(loraUploadConfigForTool(tool), {
    extensions: ['.safetensors'],
    max_size: 42,
  })
})
