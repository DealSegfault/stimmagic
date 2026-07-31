import assert from 'node:assert/strict'
import test from 'node:test'
import {
  extractParameters,
  positionalImageMediaIds,
  type PayloadBuilderConfig,
  type PayloadBuilderState,
} from '../../composables/useJobPayloadBuilder.ts'

function state(): PayloadBuilderState {
  return {
    globalPrefs: {
      prompt: 'Use the material from reference 1',
      negative_prompt: '',
      folder_path: '',
      // Editor composites are uploaded staging inputs, not existing Media.
      inputImages: [{ path: '/staging/composite.png' }],
      inpaintRefImages: [
        { path: '42', mediaId: 42 },
        { path: '84', mediaId: 84 },
      ],
      inputVideos: [],
      inputAudios: [],
    },
    modelParams: {},
    videoImages: { startImage: null, endImage: null },
    maskDataUrl: 'data:image/png;base64,mask',
    enabledLoras: [],
    inputImageWidth: 1024,
    inputImageHeight: 1024,
  }
}

const config: PayloadBuilderConfig = {
  tool: {
    generator: 'test',
    model: 'test',
    task_type: 'inpaint-image',
    full_tool_id: 'test:inpaint',
    parameter_schema: {
      properties: {
        prompt: { type: 'string' },
        input_images: { type: 'array', maxItems: 3 },
        mask: { type: 'string' },
      },
    },
  },
  generatorInstanceId: 'test',
  autoDeleteDuration: 0,
}

test('inpaint references follow the edited target in payload order', () => {
  const parameters = extractParameters(config, state())
  assert.deepEqual(parameters.input_images, [
    '/staging/composite.png',
    '42',
    '84',
  ])
})

test('lineage keeps a null target slot so reference ids cannot shift roles', () => {
  assert.deepEqual(positionalImageMediaIds(state()), [null, 42, 84])
  assert.deepEqual(extractParameters(config, state()).input_media_ids, [null, 42, 84])
})
