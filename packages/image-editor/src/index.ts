// Main entry point for @stimma/image-editor

// Styles
import './styles/index.css';

// Components
export { StimmaEditor } from './components';
export type { StimmaPlugin, EditorContext } from './types/plugins';

// Types
export type {
  // Geometry
  Point,
  Size,
  Rect,
  Color,
  ImageSource,

  // Editor
  EditorState,
  CropRect,
  ViewTransform,
  CropGuide,
  AspectRatioOption,
  FilterOption,
  FrameStyle,
  ExportOptions,
  LoadResult,
  ProcessResult,
  HistoryEntry,

  // Retouch
  RetouchTool,
  SelectionMode,
  DodgeBurnRange,

  // Settings
  EditorSettings,
  PersistedSettings,

  // Shapes
  Shape,
  BaseShape,
  RectangleShape,
  EllipseShape,
  LineShape,
  PathShape,
  StickerShape,
  TextShape,
  AnnotateTool,
  LineEndStyle,
  TextEffect,
  GradientDirection,
  GradientPreset,
  ShadowDirection,
} from './types';

// Shape constants
export { GRADIENT_PRESETS } from './types/shapes';

// Plugins
export { cropPlugin, finetunePlugin, filterPlugin, effectsPlugin, annotatePlugin, retouchPlugin } from './plugins';

// Utilities (for advanced usage)
export { colorToCss } from './types/geometry';
export {
  identityMatrix,
  multiplyColorMatrices,
  brightnessMatrix,
  contrastMatrix,
  saturationMatrix,
  combineAdjustments,
  applyColorMatrix,
  applySplitToning,
  applyGradientMap,
  applyColorIsolation,
} from './utils/colorMatrix';

// Pixel executors, exported so another editor can consume them as a library
// rather than reimplement the math. Purely additive: this editor's own render
// path (useImageWriter) still imports them directly and is unchanged.
export { hasEffects, applyEffects } from './utils/effects';
export { renderShape, renderShapes } from './utils/shapes';
export { FILTER_MATRICES, DEFAULT_EDITOR_STATE, DEFAULT_VIEW_TRANSFORM } from './constants';

// The plugin control surfaces and the canvas, exported so another editor can
// mount the SAME polished controls rather than re-authoring them. The plugin
// contract is already narrow (an EditorContext in, updateState out), so this
// is the supported way to reuse them.
export { default as EditorCanvas } from './components/EditorCanvas.vue';
// The tool rail: it is what PICKS the annotate/retouch tool that the controls
// panel then configures, so the two only make sense mounted together.
export { default as ToolSidebar } from './components/ToolSidebar.vue';
export { default as CropControls } from './plugins/crop/CropControls.vue';
export { default as FinetuneControls } from './plugins/finetune/FinetuneControls.vue';
export { default as FilterControls } from './plugins/filter/FilterControls.vue';
export { default as EffectsControls } from './plugins/effects/EffectsControls.vue';
export { default as AnnotateControls } from './plugins/annotate/AnnotateControls.vue';
export { default as RetouchControls } from './plugins/retouch/RetouchControls.vue';
export { default as RetouchOverlay } from './plugins/retouch/RetouchOverlay.vue';
export { icons } from './components/icons';
export type { RetouchOperations } from './types/plugins';

// Composables (for building custom editors)
export { useEditor } from './composables/useEditor';
export { useHistory } from './composables/useHistory';
export { useImageLoader } from './composables/useImageLoader';
export { useImageWriter } from './composables/useImageWriter';
export { useSettingsPersistence } from './composables/useSettingsPersistence';
export type { SettingsPersistence } from './composables/useSettingsPersistence';

// Serialization utilities (for save/load functionality)
export {
  serializeProject,
  deserializeProject,
  serializeProjectToJson,
  deserializeProjectFromJson,
  imageToDataUrl,
  createThumbnail,
} from './utils/serialization';

export type {
  SerializedProject,
  SerializeOptions,
} from './utils/serialization';

export {
  isEditorDebugEnabled,
  nextEditorDebugSession,
  logEditorDebug,
  getRecentEditorDebugEvents,
  summarizeEditorDebugError,
  clearEditorDebugEvents,
} from './utils/editorDebug';

export {
  CHAIN_FILTER_DEFS,
  COLOR_FILTER_OPTIONS,
  getChainFilterDef,
  getChainFilterAccepts,
  getChainFilterDefaults,
  getFilterDisplayLabel,
} from './filterDefs';
export type { ChainFilterDef, ChainFilterParam } from './filterDefs';
