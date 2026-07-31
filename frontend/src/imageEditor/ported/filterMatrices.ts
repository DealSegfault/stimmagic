/**
 * Filter preset matrices ported from the retired editor.
 *
 * The color matrices behind the filter presets. Copied rather than imported
 * so every filter surface goes through the same numbers.
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
