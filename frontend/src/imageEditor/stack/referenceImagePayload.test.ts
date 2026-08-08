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

test('hidden frame-picker state cannot override the visible image picker', () => {
  const pickerState = state()
  pickerState.globalPrefs.inputImages = [{ path: '/visible/replacement.png', mediaId: 22 }]
  pickerState.globalPrefs.inpaintRefImages = []
  pickerState.videoImages.startImage = { path: '/hidden/stale.png', mediaId: 11 }

  const parameters = extractParameters(config, pickerState)
  assert.deepEqual(parameters.input_images, ['/visible/replacement.png'])
  assert.deepEqual(parameters.input_media_ids, [22])
})

test('declared frame picker still submits its positioned frame state', () => {
  const pickerState = state()
  pickerState.globalPrefs.inputImages = [{ path: '/hidden/generic.png', mediaId: 22 }]
  pickerState.globalPrefs.inpaintRefImages = []
  pickerState.videoImages.startImage = { path: '/visible/start.png', mediaId: 11 }
  pickerState.videoImages.endImage = { path: '/visible/end.png', mediaId: 12 }
  const frameConfig: PayloadBuilderConfig = {
    ...config,
    tool: {
      ...config.tool,
      parameter_schema: {
        properties: {
          input_images: { type: 'array', 'x-control': 'video_frame_picker' },
        },
      },
    },
  }

  const parameters = extractParameters(frameConfig, pickerState)
  assert.deepEqual(parameters.input_images, ['/visible/start.png', '/visible/end.png'])
  assert.deepEqual(parameters.input_media_ids, [11, 12])
})

test('video inputs carry internal media ids even when the provider schema omits them', () => {
  const videoState = state()
  videoState.globalPrefs.inputImages = []
  videoState.globalPrefs.inpaintRefImages = []
  videoState.globalPrefs.inputVideos = [
    { path: '/staging/path-only.mp4' },
    { path: '/library/generated.mp4', mediaId: 52 },
  ]
  const videoConfig: PayloadBuilderConfig = {
    ...config,
    tool: {
      ...config.tool,
      task_type: 'upscale-video',
      parameter_schema: {
        properties: {
          input_videos: { type: 'array', 'x-control': 'video_picker' },
        },
      },
    },
  }

  const parameters = extractParameters(videoConfig, videoState)
  assert.deepEqual(parameters.input_videos, [
    '/staging/path-only.mp4',
    '/library/generated.mp4',
  ])
  assert.deepEqual(parameters.input_video_media_ids, [null, 52])
})
