<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
  CheckIcon,
  DocumentDuplicateIcon,
  EyeIcon,
  EyeSlashIcon,
  PaintBrushIcon,
  PhotoIcon,
  PlusIcon,
  SparklesIcon,
  Square2StackIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import Button from '../ui/Button.vue'
import IconButton from '../ui/IconButton.vue'
import Tooltip from '../ui/Tooltip.vue'
import ImageCompareSlider from '../ImageCompareSlider.vue'
import { MediaImage } from '../media'
import { useMediaApi } from '../../composables/useMediaApi'
import { useAssetApi } from '../../composables/useAssetApi'
import { useToasts } from '../../composables/useToasts'
import {
  useProjectReferencesApi,
  type InpaintZoneInput,
  type ReferencePack,
} from '../../composables/useProjectReferencesApi'

interface ColorOption {
  name: string
  hex: string
}

const PRESET_COLORS: ColorOption[] = [
  { name: 'YELLOW', hex: '#FACC15' },
  { name: 'RED', hex: '#EF4444' },
  { name: 'BLUE', hex: '#3B82F6' },
  { name: 'GREEN', hex: '#22C55E' },
  { name: 'PURPLE', hex: '#A855F7' },
  { name: 'ORANGE', hex: '#F97316' },
  { name: 'CYAN', hex: '#06B6D4' },
  { name: 'MAGENTA', hex: '#EC4899' },
  { name: 'WHITE', hex: '#FFFFFF' },
]

interface ZoneData {
  id: string
  colorName: string
  colorHex: string
  target: string
  operation: string
  instruction: string
  referenceMediaId: number | null
}

const props = defineProps<{
  projectId?: number
  packs?: ReferencePack[]
}>()

const emit = defineEmits<{
  (e: 'asset-created', assetId: number): void
}>()

const mediaApi = useMediaApi()
const assetApi = useAssetApi()
const referencesApi = useProjectReferencesApi()
const { addToast } = useToasts()

// State
const sourceMediaId = ref<number | null>(null)
const sourceImageElement = ref<HTMLImageElement | null>(null)
const sourceImageUrl = ref<string | null>(null)
const imageDimensions = ref<{ width: number; height: number } | null>(null)

// Drawing Tools
type DrawingTool = 'pen' | 'eraser' | 'lasso' | 'square' | 'circle' | 'arrow'
const activeTool = ref<DrawingTool>('pen')
const activeColor = ref<ColorOption>(PRESET_COLORS[0])
const customColorHex = ref('#FACC15')
const brushSize = ref<number>(24)
const fillShape = ref<boolean>(true)
const isMaskVisible = ref<boolean>(true)

// Canvases
const canvasContainerRef = ref<HTMLDivElement | null>(null)
const maskCanvasRef = ref<HTMLCanvasElement | null>(null)
const previewCanvasRef = ref<HTMLCanvasElement | null>(null)

// Undo/Redo history
const historyStack = ref<ImageData[]>([])
const historyStep = ref<number>(-1)
const MAX_HISTORY = 20

// Zones
const zones = reactive<ZoneData[]>([
  {
    id: 'zone_1',
    colorName: 'YELLOW',
    colorHex: '#FACC15',
    target: 'apartment door @image1',
    operation: 'replace',
    instruction: 'use the exact design from reference @image2',
    referenceMediaId: null,
  },
])

// Prompt & Generation
const manualPromptOverride = ref<boolean>(false)
const customPromptText = ref<string>('')
const isGenerating = ref<boolean>(false)
const resultMediaId = ref<number | null>(null)
const resultImageUrl = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

// Asset selector modal
const showAssetPicker = ref<boolean>(false)
const assetPickerTargetZone = ref<ZoneData | null>(null)
const projectAssetsList = ref<any[]>([])
const loadingAssets = ref<boolean>(false)

// Auto-generated prompt
const autoCompiledPrompt = computed(() => {
  const lines: string[] = ['EDIT MAP\n']
  zones.forEach((zone, idx) => {
    lines.push(`ZONE ${idx + 1} — ${zone.colorName.toUpperCase()}`)
    lines.push(`Target: ${zone.target.trim() || '@image1'}`)
    lines.push(`Operation: ${zone.operation.trim() || 'modify'}`)
    if (zone.instruction.trim()) {
      lines.push(`Instruction: ${zone.instruction.trim()}`)
    }
    lines.push('')
  })
  lines.push('GLOBAL LOCK:')
  lines.push('Everything not selected by a zone remains unchanged.')
  return lines.join('\n')
})

const effectivePrompt = computed(() => {
  return manualPromptOverride.value ? customPromptText.value : autoCompiledPrompt.value
})

watch(autoCompiledPrompt, (val) => {
  if (!manualPromptOverride.value) {
    customPromptText.value = val
  }
})

// Drawing Interaction State
let isDrawing = false
let startX = 0
let startY = 0
let lassoPoints: { x: number; y: number }[] = []

function selectColor(color: ColorOption) {
  activeColor.value = color
  customColorHex.value = color.hex
  ensureZoneForColor(color)
}

function onCustomColorChange() {
  const hex = customColorHex.value.toUpperCase()
  const matched = PRESET_COLORS.find(c => c.hex.toUpperCase() === hex)
  activeColor.value = matched || { name: `COLOR ${zones.length + 1}`, hex }
  ensureZoneForColor(activeColor.value)
}

function ensureZoneForColor(color: ColorOption) {
  const exists = zones.some(z => z.colorHex.toUpperCase() === color.hex.toUpperCase())
  if (!exists) {
    zones.push({
      id: `zone_${Date.now()}`,
      colorName: color.name,
      colorHex: color.hex,
      target: `@image1`,
      operation: 'replace',
      instruction: '',
      referenceMediaId: null,
    })
  }
}

function addZone() {
  const unusedColor = PRESET_COLORS.find(
    c => !zones.some(z => z.colorHex.toUpperCase() === c.hex.toUpperCase())
  ) || { name: `CUSTOM ${zones.length + 1}`, hex: '#10B981' }

  zones.push({
    id: `zone_${Date.now()}`,
    colorName: unusedColor.name,
    colorHex: unusedColor.hex,
    target: `@image1`,
    operation: 'replace',
    instruction: '',
    referenceMediaId: null,
  })
}

function removeZone(index: number) {
  if (zones.length <= 1) return
  zones.splice(index, 1)
}

// Canvas Initialization
function initCanvases(width: number, height: number) {
  imageDimensions.value = { width, height }
  nextTick(() => {
    if (maskCanvasRef.value) {
      maskCanvasRef.value.width = width
      maskCanvasRef.value.height = height
      const ctx = maskCanvasRef.value.getContext('2d')
      if (ctx) ctx.clearRect(0, 0, width, height)
    }
    if (previewCanvasRef.value) {
      previewCanvasRef.value.width = width
      previewCanvasRef.value.height = height
      const ctx = previewCanvasRef.value.getContext('2d')
      if (ctx) ctx.clearRect(0, 0, width, height)
    }
    saveHistoryState()
  })
}

function getCanvasCoordinates(e: MouseEvent): { x: number; y: number } {
  if (!maskCanvasRef.value) return { x: 0, y: 0 }
  const rect = maskCanvasRef.value.getBoundingClientRect()
  const scaleX = maskCanvasRef.value.width / rect.width
  const scaleY = maskCanvasRef.value.height / rect.height
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY,
  }
}

function saveHistoryState() {
  const canvas = maskCanvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height)
  if (historyStep.value < historyStack.value.length - 1) {
    historyStack.value = historyStack.value.slice(0, historyStep.value + 1)
  }
  historyStack.value.push(data)
  if (historyStack.value.length > MAX_HISTORY) {
    historyStack.value.shift()
  }
  historyStep.value = historyStack.value.length - 1
}

function undo() {
  if (historyStep.value > 0) {
    historyStep.value--
    restoreHistory(historyStack.value[historyStep.value])
  }
}

function redo() {
  if (historyStep.value < historyStack.value.length - 1) {
    historyStep.value++
    restoreHistory(historyStack.value[historyStep.value])
  }
}

function restoreHistory(data: ImageData) {
  const canvas = maskCanvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.putImageData(data, 0, 0)
  }
}

function clearMask() {
  const canvas = maskCanvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    saveHistoryState()
  }
}

// Mouse Event Handlers
function onMouseDown(e: MouseEvent) {
  if (e.button !== 0 || !maskCanvasRef.value) return
  isDrawing = true
  const { x, y } = getCanvasCoordinates(e)
  startX = x
  startY = y

  const maskCtx = maskCanvasRef.value.getContext('2d')
  if (!maskCtx) return

  if (activeTool.value === 'pen' || activeTool.value === 'eraser') {
    maskCtx.beginPath()
    maskCtx.moveTo(x, y)
    maskCtx.lineCap = 'round'
    maskCtx.lineJoin = 'round'
    maskCtx.lineWidth = brushSize.value
    if (activeTool.value === 'eraser') {
      maskCtx.globalCompositeOperation = 'destination-out'
    } else {
      maskCtx.globalCompositeOperation = 'source-over'
      maskCtx.strokeStyle = activeColor.value.hex
    }
    maskCtx.lineTo(x + 0.1, y + 0.1)
    maskCtx.stroke()
  } else if (activeTool.value === 'lasso') {
    lassoPoints = [{ x, y }]
  }
}

function onMouseMove(e: MouseEvent) {
  if (!isDrawing || !maskCanvasRef.value || !previewCanvasRef.value) return
  const { x, y } = getCanvasCoordinates(e)
  const maskCtx = maskCanvasRef.value.getContext('2d')
  const prevCtx = previewCanvasRef.value.getContext('2d')
  if (!maskCtx || !prevCtx) return

  if (activeTool.value === 'pen' || activeTool.value === 'eraser') {
    maskCtx.lineTo(x, y)
    maskCtx.stroke()
  } else if (activeTool.value === 'lasso') {
    lassoPoints.push({ x, y })
    prevCtx.clearRect(0, 0, previewCanvasRef.value.width, previewCanvasRef.value.height)
    prevCtx.beginPath()
    prevCtx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
    for (let i = 1; i < lassoPoints.length; i++) {
      prevCtx.lineTo(lassoPoints[i].x, lassoPoints[i].y)
    }
    prevCtx.strokeStyle = activeColor.value.hex
    prevCtx.lineWidth = brushSize.value
    prevCtx.setLineDash([6, 6])
    prevCtx.stroke()
    prevCtx.setLineDash([])
  } else if (activeTool.value === 'square') {
    prevCtx.clearRect(0, 0, previewCanvasRef.value.width, previewCanvasRef.value.height)
    prevCtx.fillStyle = activeColor.value.hex
    prevCtx.strokeStyle = activeColor.value.hex
    prevCtx.lineWidth = brushSize.value
    const w = x - startX
    const h = y - startY
    if (fillShape.value) {
      prevCtx.fillRect(startX, startY, w, h)
    } else {
      prevCtx.strokeRect(startX, startY, w, h)
    }
  } else if (activeTool.value === 'circle') {
    prevCtx.clearRect(0, 0, previewCanvasRef.value.width, previewCanvasRef.value.height)
    prevCtx.fillStyle = activeColor.value.hex
    prevCtx.strokeStyle = activeColor.value.hex
    prevCtx.lineWidth = brushSize.value
    const rx = Math.abs(x - startX) / 2
    const ry = Math.abs(y - startY) / 2
    const cx = startX + (x - startX) / 2
    const cy = startY + (y - startY) / 2
    prevCtx.beginPath()
    prevCtx.ellipse(cx, cy, Math.max(1, rx), Math.max(1, ry), 0, 0, Math.PI * 2)
    if (fillShape.value) prevCtx.fill()
    else prevCtx.stroke()
  } else if (activeTool.value === 'arrow') {
    prevCtx.clearRect(0, 0, previewCanvasRef.value.width, previewCanvasRef.value.height)
    drawArrow(prevCtx, startX, startY, x, y, activeColor.value.hex, brushSize.value)
  }
}

function onMouseUp(e: MouseEvent) {
  if (!isDrawing || !maskCanvasRef.value || !previewCanvasRef.value) return
  isDrawing = false
  const { x, y } = getCanvasCoordinates(e)
  const maskCtx = maskCanvasRef.value.getContext('2d')
  const prevCtx = previewCanvasRef.value.getContext('2d')
  if (!maskCtx || !prevCtx) return

  prevCtx.clearRect(0, 0, previewCanvasRef.value.width, previewCanvasRef.value.height)
  maskCtx.globalCompositeOperation = 'source-over'

  if (activeTool.value === 'lasso' && lassoPoints.length > 2) {
    maskCtx.beginPath()
    maskCtx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
    for (let i = 1; i < lassoPoints.length; i++) {
      maskCtx.lineTo(lassoPoints[i].x, lassoPoints[i].y)
    }
    maskCtx.closePath()
    if (fillShape.value) {
      maskCtx.fillStyle = activeColor.value.hex
      maskCtx.fill()
    } else {
      maskCtx.strokeStyle = activeColor.value.hex
      maskCtx.lineWidth = brushSize.value
      maskCtx.stroke()
    }
    lassoPoints = []
  } else if (activeTool.value === 'square') {
    maskCtx.fillStyle = activeColor.value.hex
    maskCtx.strokeStyle = activeColor.value.hex
    maskCtx.lineWidth = brushSize.value
    const w = x - startX
    const h = y - startY
    if (fillShape.value) {
      maskCtx.fillRect(startX, startY, w, h)
    } else {
      maskCtx.strokeRect(startX, startY, w, h)
    }
  } else if (activeTool.value === 'circle') {
    maskCtx.fillStyle = activeColor.value.hex
    maskCtx.strokeStyle = activeColor.value.hex
    maskCtx.lineWidth = brushSize.value
    const rx = Math.abs(x - startX) / 2
    const ry = Math.abs(y - startY) / 2
    const cx = startX + (x - startX) / 2
    const cy = startY + (y - startY) / 2
    maskCtx.beginPath()
    maskCtx.ellipse(cx, cy, Math.max(1, rx), Math.max(1, ry), 0, 0, Math.PI * 2)
    if (fillShape.value) maskCtx.fill()
    else maskCtx.stroke()
  } else if (activeTool.value === 'arrow') {
    drawArrow(maskCtx, startX, startY, x, y, activeColor.value.hex, brushSize.value)
  }

  saveHistoryState()
}

function drawArrow(
  ctx: CanvasRenderingContext2D,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  color: string,
  width: number,
) {
  const headLength = Math.max(15, width * 2)
  const angle = Math.atan2(toY - fromY, toX - fromX)
  ctx.beginPath()
  ctx.moveTo(fromX, fromY)
  ctx.lineTo(toX, toY)
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.lineCap = 'round'
  ctx.stroke()

  ctx.beginPath()
  ctx.moveTo(toX, toY)
  ctx.lineTo(toX - headLength * Math.cos(angle - Math.PI / 6), toY - headLength * Math.sin(angle - Math.PI / 6))
  ctx.lineTo(toX - headLength * Math.cos(angle + Math.PI / 6), toY - headLength * Math.sin(angle + Math.PI / 6))
  ctx.lineTo(toX, toY)
  ctx.fillStyle = color
  ctx.fill()
}

// Source Image Loading
function handleFileUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = async (event) => {
    const dataUrl = event.target?.result as string
    sourceImageUrl.value = dataUrl
    const img = new Image()
    img.onload = async () => {
      sourceImageElement.value = img
      initCanvases(img.width, img.height)
      try {
        // Upload image to library to obtain mediaId
        const uploaded = await mediaApi.uploadMedia(file, props.projectId)
        sourceMediaId.value = uploaded.id
        addToast('Image chargée et enregistrée', 'success', 2500)
      } catch (err: any) {
        addToast('Image chargée localement', 'info', 2000)
      }
    }
    img.src = dataUrl
  }
  reader.readAsDataURL(file)
}

function setSourceFromMedia(mediaItem: any) {
  sourceMediaId.value = mediaItem.id
  sourceImageUrl.value = mediaApi.getMediaFileUrl(mediaItem.id)
  const img = new Image()
  img.onload = () => {
    sourceImageElement.value = img
    initCanvases(img.width, img.height)
  }
  img.src = sourceImageUrl.value
  addToast(`Image source : ${mediaItem.filename || mediaItem.id}`, 'info', 2000)
}

// Asset Picker
async function openAssetPicker(zone: ZoneData | null = null) {
  assetPickerTargetZone.value = zone
  showAssetPicker.value = true
  loadingAssets.value = true
  try {
    if (props.projectId) {
      const response = await assetApi.getProjectAssets(props.projectId)
      projectAssetsList.value = response.items || []
    } else {
      const response = await mediaApi.listMedia({ limit: 40 })
      projectAssetsList.value = response.items || []
    }
  } catch (err) {
    projectAssetsList.value = []
  } finally {
    loadingAssets.value = false
  }
}

function pickAsset(item: any) {
  const mId = item.primary_media_id || item.id
  if (assetPickerTargetZone.value) {
    assetPickerTargetZone.value.referenceMediaId = mId
    if (!assetPickerTargetZone.value.instruction.includes('@image')) {
      assetPickerTargetZone.value.instruction = `use reference @image${zones.indexOf(assetPickerTargetZone.value) + 2}`
    }
  } else {
    setSourceFromMedia({ id: mId, filename: item.title || item.filename })
  }
  showAssetPicker.value = false
}

// Inpainting Generation via AGY CLI
async function submitInpaint() {
  if (!sourceMediaId.value) {
    addToast('Sélectionnez ou importez une image source propre.', 'error', 3500)
    return
  }
  if (!maskCanvasRef.value) return

  const maskBase64 = maskCanvasRef.value.toDataURL('image/png')
  isGenerating.value = true
  errorMessage.value = null
  resultMediaId.value = null
  resultImageUrl.value = null

  try {
    const payloadZones: InpaintZoneInput[] = zones.map(z => ({
      color_name: z.colorName,
      color_hex: z.colorHex,
      target: z.target,
      operation: z.operation,
      instruction: z.instruction,
      reference_media_ids: z.referenceMediaId ? [z.referenceMediaId] : [],
    }))

    const result = await referencesApi.inpaintImage({
      source_media_id: sourceMediaId.value,
      mask_image_base64: maskBase64,
      zones: payloadZones,
      prompt_override: manualPromptOverride.value ? customPromptText.value : null,
      dimensions: imageDimensions.value ? [imageDimensions.value.width, imageDimensions.value.height] : undefined,
    }, props.projectId)

    if (result?.result_media_id) {
      resultMediaId.value = result.result_media_id
      resultImageUrl.value = mediaApi.getMediaFileUrl(result.result_media_id)
      addToast('Inpainting généré avec succès par AGY CLI !', 'success', 4000)
    }
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || err.message || 'Erreur lors de la génération inpainting.'
    addToast(errorMessage.value!, 'error', 6000)
  } finally {
    isGenerating.value = false
  }
}

async function approveResult() {
  if (!resultMediaId.value) return
  try {
    const asset = await assetApi.createAssetFromMedia({
      media_id: resultMediaId.value,
      title: `Inpainting Multi-Zone · ${new Date().toLocaleTimeString()}`,
      origin_type: 'inpaint_studio',
      project_id: props.projectId,
    })
    addToast('Résultat approuvé et ajouté aux Assets !', 'success', 3000)
    if (asset?.id) emit('asset-created', asset.id)
  } catch (err: any) {
    addToast(err.message || "Erreur d'approbation", 'error', 4000)
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header banner -->
    <div class="rounded-lg border border-edge bg-surface p-5">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="flex items-center gap-2 text-xs font-semibold text-accent">
            <SparklesIcon class="h-4 w-4" /> Multi-Zone Inpainting · Antigravity CLI
          </div>
          <h2 class="mt-1 text-base font-semibold text-content">Studio d'Édition et d'Inpainting Localisé</h2>
          <p class="mt-0.5 max-w-2xl text-xs text-content-secondary">
            Importe une photo, peins des zones avec des stylos de couleur sémantique (Jaune, Rouge, etc.), et génère un inpainting verrouillé sur la source via AGY CLI.
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <label class="cursor-pointer">
            <input type="file" accept="image/*" class="hidden" @change="handleFileUpload" />
            <Button size="sm" variant="secondary">
              <PhotoIcon class="h-4 w-4" /> Importer Photo
            </Button>
          </label>
          <Button size="sm" variant="ghost" @click="openAssetPicker(null)">
            <Square2StackIcon class="h-4 w-4" /> Choisir depuis Assets
          </Button>
        </div>
      </div>
    </div>

    <!-- Main Studio Grid -->
    <div class="grid gap-6 lg:grid-cols-[1fr_420px]">
      <!-- Left: Interactive Drawing Board -->
      <div class="space-y-3 rounded-lg border border-edge bg-surface p-4">
        <!-- Toolbar -->
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-edge-subtle pb-3">
          <!-- Tools Group -->
          <div class="flex items-center gap-1 rounded-md bg-overlay-faint p-1">
            <Tooltip text="Stylo / Pinceau (Dessin libre)">
              <button
                type="button"
                class="rounded p-1.5 transition-colors"
                :class="activeTool === 'pen' ? 'bg-accent/20 text-accent font-semibold' : 'text-content-muted hover:text-content'"
                @click="activeTool = 'pen'"
              >
                <PaintBrushIcon class="h-4 w-4" />
              </button>
            </Tooltip>
            <Tooltip text="Gomme (Effacer le masque)">
              <button
                type="button"
                class="rounded p-1.5 transition-colors"
                :class="activeTool === 'eraser' ? 'bg-accent/20 text-accent font-semibold' : 'text-content-muted hover:text-content'"
                @click="activeTool = 'eraser'"
              >
                <TrashIcon class="h-4 w-4" />
              </button>
            </Tooltip>
            <Tooltip text="Lasso (Sélection polygone)">
              <button
                type="button"
                class="rounded px-2 py-1 text-xs transition-colors"
                :class="activeTool === 'lasso' ? 'bg-accent/20 text-accent font-semibold' : 'text-content-muted hover:text-content'"
                @click="activeTool = 'lasso'"
              >
                🪢 Lasso
              </button>
            </Tooltip>
            <Tooltip text="Rectangle / Carré">
              <button
                type="button"
                class="rounded px-2 py-1 text-xs transition-colors"
                :class="activeTool === 'square' ? 'bg-accent/20 text-accent font-semibold' : 'text-content-muted hover:text-content'"
                @click="activeTool = 'square'"
              >
                ⬛ Rectangle
              </button>
            </Tooltip>
            <Tooltip text="Cercle / Ellipse">
              <button
                type="button"
                class="rounded px-2 py-1 text-xs transition-colors"
                :class="activeTool === 'circle' ? 'bg-accent/20 text-accent font-semibold' : 'text-content-muted hover:text-content'"
                @click="activeTool = 'circle'"
              >
                ⭕ Cercle
              </button>
            </Tooltip>
            <Tooltip text="Flèche indicatrice">
              <button
                type="button"
                class="rounded px-2 py-1 text-xs transition-colors"
                :class="activeTool === 'arrow' ? 'bg-accent/20 text-accent font-semibold' : 'text-content-muted hover:text-content'"
                @click="activeTool = 'arrow'"
              >
                ↗️ Flèche
              </button>
            </Tooltip>
          </div>

          <!-- Color Palette Picker -->
          <div class="flex items-center gap-1.5">
            <span class="text-[10px] uppercase font-semibold text-content-muted">Couleur:</span>
            <div class="flex items-center gap-1">
              <button
                v-for="color in PRESET_COLORS"
                :key="color.name"
                type="button"
                class="h-5 w-5 rounded-full border border-black/40 transition-transform"
                :style="{ backgroundColor: color.hex }"
                :class="activeColor.hex.toUpperCase() === color.hex.toUpperCase() ? 'scale-125 ring-2 ring-accent' : 'hover:scale-110'"
                :title="color.name"
                @click="selectColor(color)"
              />
              <input
                v-model="customColorHex"
                type="color"
                class="h-5 w-5 cursor-pointer rounded-full border-0 bg-transparent p-0"
                title="Couleur personnalisée"
                @input="onCustomColorChange"
              />
            </div>
          </div>

          <!-- Brush Size & Actions -->
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-2">
              <span class="text-[10px] text-content-muted">Taille: {{ brushSize }}px</span>
              <input
                v-model.number="brushSize"
                type="range"
                min="2"
                max="80"
                step="2"
                class="h-1.5 w-20 cursor-pointer accent-accent"
              />
            </div>
            <label class="flex items-center gap-1 text-[11px] text-content-muted cursor-pointer">
              <input v-model="fillShape" type="checkbox" class="accent-accent" /> Remplir
            </label>
            <div class="flex items-center gap-1 border-l border-edge-subtle pl-2">
              <Tooltip text="Annuler (Undo)">
                <IconButton :disabled="historyStep <= 0" aria-label="Annuler" @click="undo">
                  <ArrowUturnLeftIcon class="h-3.5 w-3.5" />
                </IconButton>
              </Tooltip>
              <Tooltip text="Rétablir (Redo)">
                <IconButton :disabled="historyStep >= historyStack.length - 1" aria-label="Rétablir" @click="redo">
                  <ArrowUturnRightIcon class="h-3.5 w-3.5" />
                </IconButton>
              </Tooltip>
              <Tooltip text="Masquer / Afficher le masque">
                <IconButton aria-label="Toggle Masque" @click="isMaskVisible = !isMaskVisible">
                  <EyeIcon v-if="isMaskVisible" class="h-3.5 w-3.5 text-accent" />
                  <EyeSlashIcon v-else class="h-3.5 w-3.5 text-content-muted" />
                </IconButton>
              </Tooltip>
              <Tooltip text="Effacer tout le masque">
                <IconButton variant="danger" aria-label="Effacer masque" @click="clearMask">
                  <TrashIcon class="h-3.5 w-3.5" />
                </IconButton>
              </Tooltip>
            </div>
          </div>
        </div>

        <!-- Canvas Stage -->
        <div
          ref="canvasContainerRef"
          class="relative flex min-h-[460px] max-h-[640px] items-center justify-center overflow-hidden rounded-md bg-matte p-2 select-none"
        >
          <!-- When no source image loaded -->
          <div v-if="!sourceImageUrl" class="p-12 text-center">
            <PhotoIcon class="mx-auto h-12 w-12 text-content-muted" />
            <p class="mt-2 text-xs font-semibold text-content">Aucune photo chargée</p>
            <p class="mt-1 text-[11px] text-content-muted">Importez une photo ou sélectionnez un asset du projet pour commencer l'inpainting.</p>
            <div class="mt-4 flex justify-center gap-2">
              <label class="cursor-pointer">
                <input type="file" accept="image/*" class="hidden" @change="handleFileUpload" />
                <Button size="sm">Importer une photo</Button>
              </label>
              <Button size="sm" variant="secondary" @click="openAssetPicker(null)">Choisir un asset</Button>
            </div>
          </div>

          <!-- Drawing stage when image is loaded -->
          <div v-else class="relative flex items-center justify-center max-h-full max-w-full">
            <img
              :src="sourceImageUrl"
              class="max-h-[580px] max-w-full object-contain pointer-events-none"
              alt="Source Canvas"
            />
            <!-- Drawn Mask Canvas -->
            <canvas
              ref="maskCanvasRef"
              class="absolute inset-0 h-full w-full object-contain cursor-crosshair"
              :class="{ 'opacity-0': !isMaskVisible }"
              @mousedown="onMouseDown"
              @mousemove="onMouseMove"
              @mouseup="onMouseUp"
              @mouseleave="onMouseUp"
            />
            <!-- Interaction Preview Canvas -->
            <canvas
              ref="previewCanvasRef"
              class="absolute inset-0 h-full w-full object-contain pointer-events-none"
            />
          </div>
        </div>

        <div v-if="sourceImageUrl" class="flex items-center justify-between text-[11px] text-content-muted">
          <span>Source : #{{ sourceMediaId || 'Local' }} ({{ imageDimensions?.width }}x{{ imageDimensions?.height }}px)</span>
          <span class="text-accent">Calque de masque actif · Dessinez pour ajouter des zones</span>
        </div>
      </div>

      <!-- Right: Zones & Auto Prompt Inspector -->
      <div class="space-y-5 rounded-lg border border-edge bg-surface p-4 flex flex-col justify-between">
        <div class="space-y-4 overflow-y-auto max-h-[600px] pr-1 custom-scrollbar">
          <!-- Zone Mapping Header -->
          <div class="flex items-center justify-between border-b border-edge-subtle pb-2">
            <div>
              <h3 class="text-xs font-semibold text-content">Zones de Modification (Color-to-Zone)</h3>
              <p class="text-[10px] text-content-muted">Chaque couleur correspond à une instruction stricte.</p>
            </div>
            <Button size="sm" variant="ghost" type="button" @click="addZone">
              <PlusIcon class="h-3.5 w-3.5" /> Zone
            </Button>
          </div>

          <!-- Zone Cards -->
          <div class="space-y-3">
            <div
              v-for="(zone, idx) in zones"
              :key="zone.id"
              class="rounded-md border border-edge bg-overlay-faint p-3 space-y-2.5"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span
                    class="h-3 w-3 rounded-full border border-black/50"
                    :style="{ backgroundColor: zone.colorHex }"
                  />
                  <span class="text-xs font-bold font-mono text-content">ZONE {{ idx + 1 }} — {{ zone.colorName.toUpperCase() }}</span>
                </div>
                <button
                  type="button"
                  class="p-1 text-content-muted hover:text-red-400"
                  title="Supprimer la zone"
                  @click="removeZone(idx)"
                >
                  <XMarkIcon class="h-3.5 w-3.5" />
                </button>
              </div>

              <div class="grid grid-cols-2 gap-2">
                <label class="space-y-1 text-[10px] text-content-muted">
                  Cible (Target):
                  <input
                    v-model="zone.target"
                    class="w-full rounded border border-edge bg-base px-2 py-1 text-xs text-content outline-none focus:border-accent"
                    placeholder="apartment door @image1"
                  />
                </label>
                <label class="space-y-1 text-[10px] text-content-muted">
                  Opération:
                  <select
                    v-model="zone.operation"
                    class="w-full rounded border border-edge bg-base px-2 py-1 text-xs text-content outline-none focus:border-accent"
                  >
                    <option value="replace">replace (Remplacer)</option>
                    <option value="remove">remove (Supprimer/Infill)</option>
                    <option value="add">add (Ajouter)</option>
                    <option value="modify">modify (Recolorer/Modifier)</option>
                    <option value="relight">relight (Rééclairer)</option>
                    <option value="restyle">restyle (Restyler)</option>
                  </select>
                </label>
              </div>

              <label class="block space-y-1 text-[10px] text-content-muted">
                Instruction spécifique à la zone:
                <input
                  v-model="zone.instruction"
                  class="w-full rounded border border-edge bg-base px-2 py-1 text-xs text-content outline-none focus:border-accent"
                  placeholder="use the exact design from reference @image2"
                />
              </label>

              <!-- Reference Attachment for Zone -->
              <div class="flex items-center justify-between pt-1 border-t border-edge-subtle text-[10px]">
                <div class="flex items-center gap-1 text-content-muted">
                  <span>Asset lié:</span>
                  <span v-if="zone.referenceMediaId" class="font-mono text-accent font-semibold">@image{{ idx + 2 }} (Media #{{ zone.referenceMediaId }})</span>
                  <span v-else class="italic">Aucun</span>
                </div>
                <button
                  type="button"
                  class="text-accent hover:underline font-medium"
                  @click="openAssetPicker(zone)"
                >
                  {{ zone.referenceMediaId ? 'Changer' : '+ Lier un asset' }}
                </button>
              </div>
            </div>
          </div>

          <!-- Prompt Compilation Box -->
          <div class="space-y-2 pt-2 border-t border-edge-subtle">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-semibold text-content">Prompt Auto-Généré (EDIT MAP)</span>
              <button
                type="button"
                class="text-[10px] text-accent hover:underline"
                @click="manualPromptOverride = !manualPromptOverride"
              >
                {{ manualPromptOverride ? 'Revenir à la génération auto' : 'Éditer manuellement' }}
              </button>
            </div>

            <textarea
              v-if="manualPromptOverride"
              v-model="customPromptText"
              rows="6"
              class="w-full font-mono text-[11px] rounded-md border border-edge bg-base p-2 text-content outline-none focus:border-accent"
            />
            <pre
              v-else
              class="max-h-36 overflow-y-auto whitespace-pre-wrap font-mono text-[10px] text-content-secondary rounded-md bg-base p-2 border border-edge custom-scrollbar select-text"
            >{{ autoCompiledPrompt }}</pre>
          </div>
        </div>

        <!-- Action Button -->
        <div class="pt-3 border-t border-edge space-y-2">
          <Button
            class="w-full"
            :disabled="!sourceMediaId || isGenerating"
            :loading="isGenerating"
            @click="submitInpaint"
          >
            <SparklesIcon class="h-4 w-4" /> Générer Inpainting avec AGY CLI
          </Button>
        </div>
      </div>
    </div>

    <!-- Results Stage / Comparison -->
    <div v-if="resultImageUrl && sourceImageUrl" class="rounded-lg border border-edge bg-surface p-5 space-y-4">
      <div class="flex items-center justify-between border-b border-edge-subtle pb-3">
        <div>
          <h3 class="text-sm font-semibold text-content">Résultat de l'Inpainting AGY</h3>
          <p class="text-xs text-content-muted">Glissez le curseur pour comparer avant / après.</p>
        </div>
        <div class="flex items-center gap-2">
          <Button size="sm" variant="secondary" @click="approveResult">
            <CheckIcon class="h-4 w-4" /> Approuver comme Asset
          </Button>
          <a
            :href="resultImageUrl"
            download="inpaint_result.png"
            target="_blank"
            class="rounded-md border border-edge bg-overlay-subtle px-3 py-1.5 text-xs font-medium text-content hover:bg-overlay-light"
          >
            Télécharger
          </a>
        </div>
      </div>

      <div class="relative h-[480px] w-full overflow-hidden rounded-md bg-matte">
        <ImageCompareSlider
          :left-src="resultImageUrl"
          :right-src="sourceImageUrl"
          left-label="Après Inpainting (AGY)"
          right-label="Avant (Source)"
        />
      </div>
    </div>

    <!-- Asset Picker Modal -->
    <div
      v-if="showAssetPicker"
      class="fixed inset-0 z-modal flex items-center justify-center bg-black/60 p-4"
      @click.self="showAssetPicker = false"
    >
      <div class="w-full max-w-2xl rounded-lg border border-edge bg-surface p-5 space-y-4 shadow-2xl">
        <div class="flex items-center justify-between border-b border-edge-subtle pb-3">
          <h3 class="text-sm font-semibold text-content">
            {{ assetPickerTargetZone ? `Choisir un asset de référence pour ${assetPickerTargetZone.colorName}` : 'Choisir une image source' }}
          </h3>
          <button type="button" class="text-content-muted hover:text-content" @click="showAssetPicker = false">
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>

        <div class="max-h-96 overflow-y-auto custom-scrollbar">
          <div v-if="loadingAssets" class="py-12 text-center text-xs text-content-muted">Chargement des assets...</div>
          <div v-else-if="!projectAssetsList.length" class="py-12 text-center text-xs text-content-muted">Aucun asset trouvé dans ce projet.</div>
          <div v-else class="grid grid-cols-3 sm:grid-cols-4 gap-3">
            <div
              v-for="item in projectAssetsList"
              :key="item.id"
              class="group relative aspect-square cursor-pointer overflow-hidden rounded-md border border-edge bg-matte hover:border-accent"
              @click="pickAsset(item)"
            >
              <MediaImage
                :media-id="item.primary_media_id || item.id"
                :thumbnail="true"
                :contain="true"
                container-class="h-full w-full"
                img-class="h-full w-full object-cover transition-transform group-hover:scale-105"
              />
              <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1 text-[10px] text-white truncate">
                {{ item.title || item.filename || item.name || `#${item.id}` }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
