/**
 * Filter preset matrices ported from the retired editor.
 *
 * Two consumers, and they are NOT the same feature:
 *
 * 1. The post-processing chain's `filter` step, whose enum is these ids and
 *    whose pixel math is mirrored server-side in `backend/filters/defs.py`.
 *    That contract is persisted in saved chains, so these ids are frozen.
 * 2. Read compatibility for editor documents that still carry a `filter`
 *    param. The editor's Looks strip no longer writes one — a look is a bundle
 *    of ordinary adjustment params now (see `adjustSections.ts`), which is what
 *    lets it scope to a selection and stay editable. The names are shared
 *    because they name the same intent, not the same arithmetic.
 */
export const FILTER_MATRICES: Record<string, number[]> = {
  none: [
    1, 0, 0, 0, 0,
    0, 1, 0, 0, 0,
    0, 0, 1, 0, 0,
    0, 0, 0, 1, 0,
  ],
  chrome: [
    1.2, 0.1, 0.1, 0, -20,
    0.1, 1.1, 0.1, 0, -10,
    0.1, 0.1, 1.3, 0, -20,
    0, 0, 0, 1, 0,
  ],
  fade: [
    1, 0, 0, 0, 30,
    0, 1, 0, 0, 30,
    0, 0, 1, 0, 30,
    0, 0, 0, 0.9, 0,
  ],
  cold: [
    0.9, 0, 0.1, 0, 0,
    0, 0.95, 0.1, 0, 0,
    0.1, 0.1, 1.2, 0, 10,
    0, 0, 0, 1, 0,
  ],
  warm: [
    1.2, 0.1, 0, 0, 10,
    0.1, 1.05, 0, 0, 5,
    0, 0, 0.9, 0, -10,
    0, 0, 0, 1, 0,
  ],
  pastel: [
    1.1, 0.1, 0.1, 0, 20,
    0.1, 1.1, 0.1, 0, 20,
    0.1, 0.1, 1.1, 0, 20,
    0, 0, 0, 1, 0,
  ],
  mono: [
    0.33, 0.33, 0.33, 0, 0,
    0.33, 0.33, 0.33, 0, 0,
    0.33, 0.33, 0.33, 0, 0,
    0, 0, 0, 1, 0,
  ],
  noir: [
    0.4, 0.4, 0.2, 0, -20,
    0.3, 0.4, 0.2, 0, -10,
    0.2, 0.3, 0.4, 0, 0,
    0, 0, 0, 1, 0,
  ],
  stark: [
    0.5, 0.5, 0.5, 0, -50,
    0.5, 0.5, 0.5, 0, -50,
    0.5, 0.5, 0.5, 0, -50,
    0, 0, 0, 1, 0,
  ],
  sepia: [
    0.393, 0.769, 0.189, 0, 0,
    0.349, 0.686, 0.168, 0, 0,
    0.272, 0.534, 0.131, 0, 0,
    0, 0, 0, 1, 0,
  ],
  vintage: [
    0.9, 0.2, 0.1, 0, 20,
    0.1, 0.8, 0.2, 0, 15,
    0.1, 0.1, 0.7, 0, 30,
    0, 0, 0, 1, 0,
  ],
  vivid: [
    1.3, -0.1, -0.1, 0, 0,
    -0.1, 1.3, -0.1, 0, 0,
    -0.1, -0.1, 1.3, 0, 0,
    0, 0, 0, 1, 0,
  ],
  dramatic: [
    1.3, -0.1, -0.1, 0, -20,
    -0.1, 1.3, -0.1, 0, -20,
    -0.1, -0.1, 1.3, 0, -20,
    0, 0, 0, 1, 0,
  ],

  // Film Emulation Filters

  // Portra 400: Warm, creamy skin tones, lifted shadows, muted greens
  'portra-400': [
    1.05, 0.08, 0.02, 0, 8,
    0.02, 1.0, 0.05, 0, 6,
    -0.02, 0.05, 0.92, 0, 15,
    0, 0, 0, 1, 0,
  ],

  // Velvia: High saturation, punchy blues/greens, deep shadows
  velvia: [
    1.2, -0.05, -0.05, 0, -15,
    -0.05, 1.15, -0.05, 0, -10,
    -0.05, 0.05, 1.3, 0, -20,
    0, 0, 0, 1, 0,
  ],

  // Kodachrome: Rich reds, unique cyan-blue shadows, golden tones
  kodachrome: [
    1.15, 0.1, -0.05, 0, 5,
    0.05, 1.05, 0.0, 0, 0,
    -0.05, 0.1, 1.1, 0, 10,
    0, 0, 0, 1, 0,
  ],

  // Cinestill 800T: Tungsten-balanced, teal highlights, warm shadows
  'cinestill-800t': [
    0.95, 0.05, 0.1, 0, 10,
    0.0, 1.0, 0.1, 0, 5,
    0.1, 0.1, 1.15, 0, 0,
    0, 0, 0, 1, 0,
  ],

  // Polaroid 600: Faded, lifted blacks, subtle yellow/teal split
  'polaroid-600': [
    1.0, 0.05, 0.0, 0, 25,
    0.02, 0.98, 0.05, 0, 20,
    0.0, 0.08, 0.9, 0, 30,
    0, 0, 0, 0.95, 0,
  ],

  // Tri-X 400: Classic B&W with rich midtones and distinctive grain curve
  'tri-x-400': [
    0.35, 0.45, 0.2, 0, 0,
    0.35, 0.45, 0.2, 0, 0,
    0.35, 0.45, 0.2, 0, 0,
    0, 0, 0, 1, 0,
  ],
};

/**
 * Display names for the presets above, in the order they are offered.
 *
 * `none` is excluded: it is the identity entry the matrix table needs, not a
 * preset anyone picks.
 */
export const FILTER_PRESET_LABELS: Array<{ id: string; label: string }> = [
  { id: 'chrome', label: 'Chrome' },
  { id: 'vivid', label: 'Vivid' },
  { id: 'dramatic', label: 'Dramatic' },
  { id: 'cold', label: 'Cold' },
  { id: 'warm', label: 'Warm' },
  { id: 'pastel', label: 'Pastel' },
  { id: 'fade', label: 'Fade' },
  { id: 'vintage', label: 'Vintage' },
  { id: 'mono', label: 'Mono' },
  { id: 'noir', label: 'Noir' },
  { id: 'stark', label: 'Stark' },
  { id: 'tri-x-400', label: 'Tri-X 400' },
  { id: 'sepia', label: 'Sepia' },
  { id: 'portra-400', label: 'Portra 400' },
  { id: 'velvia', label: 'Velvia' },
  { id: 'kodachrome', label: 'Kodachrome' },
  { id: 'cinestill-800t', label: 'Cinestill' },
  { id: 'polaroid-600', label: 'Polaroid' },
];
