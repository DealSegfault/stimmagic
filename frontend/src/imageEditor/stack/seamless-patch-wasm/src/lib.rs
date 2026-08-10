//! Gradient-domain seamless cloning for the Patch tool.
//!
//! This is the production WASM implementation. The TypeScript sibling is a
//! readable reference implementation and a fallback for non-browser tests.

use wasm_bindgen::prelude::*;

const DOMAIN_THRESHOLD: u8 = 8;
const PYRAMID_MIN_SIZE: usize = 48;
const FINE_ITERATIONS: usize = 14;
const COARSE_ITERATIONS: usize = 100;
const TOLERANCE: f32 = 0.05;
const RELAXATION: f32 = 1.72;

struct Level {
    source: Vec<u8>,
    destination: Vec<u8>,
    mask: Vec<u8>,
    width: usize,
    height: usize,
}

struct Solution {
    red: Vec<f32>,
    green: Vec<f32>,
    blue: Vec<f32>,
    domain: Vec<u8>,
}

#[inline]
fn clamp_byte(value: f32) -> f32 {
    value.clamp(0.0, 255.0)
}

fn make_domain(level: &Level) -> Vec<u8> {
    let mut domain = vec![0; level.mask.len()];
    if level.width < 3 || level.height < 3 {
        return domain;
    }
    for y in 1..level.height - 1 {
        for x in 1..level.width - 1 {
            let pixel = y * level.width + x;
            domain[pixel] = u8::from(level.mask[pixel] >= DOMAIN_THRESHOLD);
        }
    }
    domain
}

fn downsample(level: &Level) -> Level {
    let width = level.width.div_ceil(2);
    let height = level.height.div_ceil(2);
    let mut source = vec![0; width * height * 4];
    let mut destination = vec![0; width * height * 4];
    let mut mask = vec![0; width * height];

    for y in 0..height {
        for x in 0..width {
            let target = y * width + x;
            let mut samples = 0_u32;
            let mut mask_sum = 0_u32;
            let mut source_sum = [0_u32; 4];
            let mut destination_sum = [0_u32; 4];
            for dy in 0..2 {
                let sy = y * 2 + dy;
                if sy >= level.height {
                    continue;
                }
                for dx in 0..2 {
                    let sx = x * 2 + dx;
                    if sx >= level.width {
                        continue;
                    }
                    let pixel = sy * level.width + sx;
                    let rgba = pixel * 4;
                    for channel in 0..4 {
                        source_sum[channel] += level.source[rgba + channel] as u32;
                        destination_sum[channel] += level.destination[rgba + channel] as u32;
                    }
                    mask_sum += level.mask[pixel] as u32;
                    samples += 1;
                }
            }
            let rgba = target * 4;
            for channel in 0..4 {
                source[rgba + channel] = ((source_sum[channel] + samples / 2) / samples) as u8;
                destination[rgba + channel] =
                    ((destination_sum[channel] + samples / 2) / samples) as u8;
            }
            mask[target] = ((mask_sum + samples / 2) / samples) as u8;
        }
    }
    Level {
        source,
        destination,
        mask,
        width,
        height,
    }
}

#[inline]
fn bilinear_channel(data: &[f32], width: usize, height: usize, x: f32, y: f32) -> f32 {
    let floor_x = x.floor();
    let floor_y = y.floor();
    let x0 = (floor_x as isize).clamp(0, width as isize - 1) as usize;
    let y0 = (floor_y as isize).clamp(0, height as isize - 1) as usize;
    let x1 = (x0 + 1).min(width - 1);
    let y1 = (y0 + 1).min(height - 1);
    let tx = x - floor_x;
    let ty = y - floor_y;
    let top = data[y0 * width + x0] * (1.0 - tx) + data[y0 * width + x1] * tx;
    let bottom = data[y1 * width + x0] * (1.0 - tx) + data[y1 * width + x1] * tx;
    top * (1.0 - ty) + bottom * ty
}

#[inline]
fn bilinear_rgba(data: &[u8], width: usize, height: usize, x: f32, y: f32, channel: usize) -> f32 {
    let floor_x = x.floor();
    let floor_y = y.floor();
    let x0 = (floor_x as isize).clamp(0, width as isize - 1) as usize;
    let y0 = (floor_y as isize).clamp(0, height as isize - 1) as usize;
    let x1 = (x0 + 1).min(width - 1);
    let y1 = (y0 + 1).min(height - 1);
    let tx = x - floor_x;
    let ty = y - floor_y;
    let at = |px: usize, py: usize| data[(py * width + px) * 4 + channel] as f32;
    let top = at(x0, y0) * (1.0 - tx) + at(x1, y0) * tx;
    let bottom = at(x0, y1) * (1.0 - tx) + at(x1, y1) * tx;
    top * (1.0 - ty) + bottom * ty
}

fn color_offset_at_boundary(level: &Level, domain: &[u8]) -> [f32; 3] {
    let mut offset = [0.0; 3];
    let mut samples = 0_u32;
    for y in 1..level.height.saturating_sub(1) {
        for x in 1..level.width.saturating_sub(1) {
            let pixel = y * level.width + x;
            if domain[pixel] == 0 {
                continue;
            }
            if domain[pixel - 1] != 0
                && domain[pixel + 1] != 0
                && domain[pixel - level.width] != 0
                && domain[pixel + level.width] != 0
            {
                continue;
            }
            let rgba = pixel * 4;
            for channel in 0..3 {
                offset[channel] +=
                    level.destination[rgba + channel] as f32 - level.source[rgba + channel] as f32;
            }
            samples += 1;
        }
    }
    if samples > 0 {
        for value in &mut offset {
            *value /= samples as f32;
        }
    }
    offset
}

#[inline]
fn add_rhs_neighbor(
    level: &Level,
    domain: &[u8],
    pixel: usize,
    neighbor: usize,
    rhs: &mut [f32; 3],
) {
    let rgba = pixel * 4;
    let neighbor_rgba = neighbor * 4;
    for channel in 0..3 {
        rhs[channel] +=
            level.source[rgba + channel] as f32 - level.source[neighbor_rgba + channel] as f32;
        if domain[neighbor] == 0 {
            rhs[channel] += level.destination[neighbor_rgba + channel] as f32;
        }
    }
}

fn solve_level(level: &Level) -> Solution {
    let pixels = level.width * level.height;
    let domain = make_domain(level);
    let offset = color_offset_at_boundary(level, &domain);
    let mut red = vec![0.0; pixels];
    let mut green = vec![0.0; pixels];
    let mut blue = vec![0.0; pixels];

    let coarse_level = (level.width.max(level.height) > PYRAMID_MIN_SIZE
        && level.width.min(level.height) > 2)
        .then(|| downsample(level));
    let coarse = coarse_level.as_ref().map(solve_level);

    for y in 0..level.height {
        for x in 0..level.width {
            let pixel = y * level.width + x;
            let rgba = pixel * 4;
            if domain[pixel] == 0 {
                red[pixel] = level.destination[rgba] as f32;
                green[pixel] = level.destination[rgba + 1] as f32;
                blue[pixel] = level.destination[rgba + 2] as f32;
                continue;
            }
            let (Some(coarse_level), Some(coarse)) = (&coarse_level, &coarse) else {
                red[pixel] = clamp_byte(level.source[rgba] as f32 + offset[0]);
                green[pixel] = clamp_byte(level.source[rgba + 1] as f32 + offset[1]);
                blue[pixel] = clamp_byte(level.source[rgba + 2] as f32 + offset[2]);
                continue;
            };
            let coarse_x = (x as f32 + 0.5) * coarse_level.width as f32 / level.width as f32 - 0.5;
            let coarse_y =
                (y as f32 + 0.5) * coarse_level.height as f32 / level.height as f32 - 0.5;
            red[pixel] = clamp_byte(
                bilinear_channel(
                    &coarse.red,
                    coarse_level.width,
                    coarse_level.height,
                    coarse_x,
                    coarse_y,
                ) + level.source[rgba] as f32
                    - bilinear_rgba(
                        &coarse_level.source,
                        coarse_level.width,
                        coarse_level.height,
                        coarse_x,
                        coarse_y,
                        0,
                    ),
            );
            green[pixel] = clamp_byte(
                bilinear_channel(
                    &coarse.green,
                    coarse_level.width,
                    coarse_level.height,
                    coarse_x,
                    coarse_y,
                ) + level.source[rgba + 1] as f32
                    - bilinear_rgba(
                        &coarse_level.source,
                        coarse_level.width,
                        coarse_level.height,
                        coarse_x,
                        coarse_y,
                        1,
                    ),
            );
            blue[pixel] = clamp_byte(
                bilinear_channel(
                    &coarse.blue,
                    coarse_level.width,
                    coarse_level.height,
                    coarse_x,
                    coarse_y,
                ) + level.source[rgba + 2] as f32
                    - bilinear_rgba(
                        &coarse_level.source,
                        coarse_level.width,
                        coarse_level.height,
                        coarse_x,
                        coarse_y,
                        2,
                    ),
            );
        }
    }

    let mut rhs_red = vec![0.0; pixels];
    let mut rhs_green = vec![0.0; pixels];
    let mut rhs_blue = vec![0.0; pixels];
    for y in 1..level.height.saturating_sub(1) {
        for x in 1..level.width.saturating_sub(1) {
            let pixel = y * level.width + x;
            if domain[pixel] == 0 {
                continue;
            }
            let mut rhs = [0.0; 3];
            add_rhs_neighbor(level, &domain, pixel, pixel - 1, &mut rhs);
            add_rhs_neighbor(level, &domain, pixel, pixel + 1, &mut rhs);
            add_rhs_neighbor(level, &domain, pixel, pixel - level.width, &mut rhs);
            add_rhs_neighbor(level, &domain, pixel, pixel + level.width, &mut rhs);
            rhs_red[pixel] = rhs[0];
            rhs_green[pixel] = rhs[1];
            rhs_blue[pixel] = rhs[2];
        }
    }

    let iterations = if coarse.is_some() {
        FINE_ITERATIONS
    } else {
        COARSE_ITERATIONS
    };
    for _ in 0..iterations {
        let mut max_delta = 0.0_f32;
        for parity in 0..2 {
            for y in 1..level.height.saturating_sub(1) {
                let mut x = 1 + ((y + parity + 1) & 1);
                while x + 1 < level.width {
                    let pixel = y * level.width + x;
                    if domain[pixel] != 0 {
                        let left = pixel - 1;
                        let right = pixel + 1;
                        let top = pixel - level.width;
                        let bottom = pixel + level.width;
                        let sum_red = rhs_red[pixel]
                            + if domain[left] != 0 { red[left] } else { 0.0 }
                            + if domain[right] != 0 { red[right] } else { 0.0 }
                            + if domain[top] != 0 { red[top] } else { 0.0 }
                            + if domain[bottom] != 0 {
                                red[bottom]
                            } else {
                                0.0
                            };
                        let sum_green = rhs_green[pixel]
                            + if domain[left] != 0 { green[left] } else { 0.0 }
                            + if domain[right] != 0 {
                                green[right]
                            } else {
                                0.0
                            }
                            + if domain[top] != 0 { green[top] } else { 0.0 }
                            + if domain[bottom] != 0 {
                                green[bottom]
                            } else {
                                0.0
                            };
                        let sum_blue = rhs_blue[pixel]
                            + if domain[left] != 0 { blue[left] } else { 0.0 }
                            + if domain[right] != 0 { blue[right] } else { 0.0 }
                            + if domain[top] != 0 { blue[top] } else { 0.0 }
                            + if domain[bottom] != 0 {
                                blue[bottom]
                            } else {
                                0.0
                            };
                        let old_red = red[pixel];
                        let old_green = green[pixel];
                        let old_blue = blue[pixel];
                        red[pixel] = old_red + RELAXATION * (sum_red * 0.25 - old_red);
                        green[pixel] = old_green + RELAXATION * (sum_green * 0.25 - old_green);
                        blue[pixel] = old_blue + RELAXATION * (sum_blue * 0.25 - old_blue);
                        max_delta = max_delta
                            .max((red[pixel] - old_red).abs())
                            .max((green[pixel] - old_green).abs())
                            .max((blue[pixel] - old_blue).abs());
                    }
                    x += 2;
                }
            }
        }
        if max_delta <= TOLERANCE {
            break;
        }
    }

    Solution {
        red,
        green,
        blue,
        domain,
    }
}

#[inline]
fn composite_channel(solved: f32, destination: u8, alpha: f32) -> u8 {
    (clamp_byte(solved) * alpha + destination as f32 * (1.0 - alpha))
        .round()
        .clamp(0.0, 255.0) as u8
}

/// Reconstruct source gradients inside `mask` against the destination boundary.
#[wasm_bindgen]
pub fn seamless_patch(
    source: &[u8],
    destination: &[u8],
    mask: &[u8],
    width: usize,
    height: usize,
) -> Result<Vec<u8>, JsValue> {
    let pixels = width
        .checked_mul(height)
        .ok_or_else(|| JsValue::from_str("patch dimensions overflow"))?;
    let rgba_values = pixels
        .checked_mul(4)
        .ok_or_else(|| JsValue::from_str("patch raster dimensions overflow"))?;
    if source.len() != rgba_values || destination.len() != rgba_values || mask.len() != pixels {
        return Err(JsValue::from_str("patch raster dimensions do not match"));
    }
    let level = Level {
        source: source.to_vec(),
        destination: destination.to_vec(),
        mask: mask.to_vec(),
        width,
        height,
    };
    let solved = solve_level(&level);
    let mut output = destination.to_vec();
    for pixel in 0..pixels {
        if mask[pixel] == 0 {
            continue;
        }
        let rgba = pixel * 4;
        let alpha = mask[pixel] as f32 / 255.0;
        // Pixels at the cropped raster edge are boundary conditions, not donor
        // pixels. Normally applyPatch supplies a one-pixel destination border.
        let solved_channels = if solved.domain[pixel] != 0 {
            [solved.red[pixel], solved.green[pixel], solved.blue[pixel]]
        } else {
            [
                destination[rgba] as f32,
                destination[rgba + 1] as f32,
                destination[rgba + 2] as f32,
            ]
        };
        for channel in 0..3 {
            output[rgba + channel] =
                composite_channel(solved_channels[channel], destination[rgba + channel], alpha);
        }
        output[rgba + 3] = ((source[rgba + 3] as f32 * alpha)
            + destination[rgba + 3] as f32 * (1.0 - alpha))
            .round()
            .clamp(0.0, 255.0) as u8;
    }
    Ok(output)
}
