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

test('H3 reference settings and mixed media inputs survive payload capture', () => {
  const h3State = state()
  h3State.globalPrefs.inputImages = [{ path: '/library/style.png', mediaId: 101 }]
  h3State.globalPrefs.inpaintRefImages = []
  h3State.globalPrefs.inputVideos = [{ path: '/library/motion.mp4', mediaId: 202 }]
  h3State.modelParams = {
    width: 544,
    height: 960,
    duration: 7.5,
    generate_audio: false,
    model_precision: 'FP8',
    ref_image_size: 'max',
    sampler: 'res_multistep',
    scheduler: 'simple',
    seed: 42,
    spectrum: false,
    steps: 12,
  }

  const h3Config: PayloadBuilderConfig = {
    ...config,
    tool: {
      ...config.tool,
      task_type: 'reference-to-video',
      parameter_schema: {
        properties: {
          width: { type: 'integer' },
          height: { type: 'integer' },
          input_images: { type: 'array', maxItems: 9 },
          input_videos: { type: 'array', maxItems: 3 },
          duration: { type: 'number' },
          generate_audio: { type: 'boolean' },
          model_precision: { type: 'string' },
          ref_image_size: { type: 'string' },
          sampler: { type: 'string' },
          scheduler: { type: 'string' },
          seed: { type: 'integer' },
          spectrum: { type: 'boolean' },
          steps: { type: 'integer' },
        },
      },
    },
  }

  const parameters = extractParameters(h3Config, h3State)

  assert.deepEqual(parameters.input_images, ['/library/style.png'])
  assert.deepEqual(parameters.input_media_ids, [101])
  assert.deepEqual(parameters.input_videos, ['/library/motion.mp4'])
  assert.deepEqual(parameters.input_video_media_ids, [202])
  assert.equal(parameters.duration, 7.5)
  assert.equal(parameters.generate_audio, false)
  assert.equal(parameters.model_precision, 'FP8')
  assert.equal(parameters.ref_image_size, 'max')
  assert.equal(parameters.sampler, 'res_multistep')
  assert.equal(parameters.scheduler, 'simple')
  assert.equal(parameters.seed, 42)
  assert.equal(parameters.spectrum, false)
  assert.equal(parameters.steps, 12)
})
