//! Graphics-tablet (stylus) input for the webview, macOS only.
//!
//! WKWebView reports tablet input as plain mouse pointer events: pointerType
//! stays "mouse" and pressure/tilt/eraser are not populated (WebKit has no
//! macOS pen pointer-event support). Same class of gap as `shift_key_down` in
//! lib.rs. A local NSEvent monitor sees the tablet data riding on our own
//! app's mouse events and forwards it as `tablet-input` events; the frontend
//! merges the stream with DOM pointer events by recency.
//!
//! Apart from explicit middle-button pan gestures, the monitor only emits for
//! events carrying tablet data, so ordinary mouse movement produces no traffic.

use std::ptr::NonNull;

use block2::RcBlock;
use objc2_app_kit::{NSEvent, NSEventMask, NSEventSubtype, NSEventType, NSPointingDeviceType};
use tauri::Emitter;

#[derive(Clone, serde::Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
enum TabletEvent {
    /// Pressure/tilt sample from the pen. `phase` marks stroke boundaries so
    /// the frontend can hold the last pressure while the pen rests in place
    /// (no new samples arrive) without leaking it into mouse use; "hover"
    /// samples keep the stream fresh before the pen touches down, covering
    /// the race between this emit and the DOM pointerdown it precedes.
    #[serde(rename_all = "camelCase")]
    Point {
        phase: &'static str, // "down" | "move" | "up" | "hover"
        pressure: f32,
        tilt_x: f64,
        tilt_y: f64,
        x: f64,
        y: f64,
        absolute_x: isize,
        absolute_y: isize,
        delta_x: f64,
        delta_y: f64,
        buttons: usize,
    },
    /// Pen entered or left tablet range; identifies the eraser end.
    #[serde(rename_all = "camelCase")]
    Proximity { entering: bool, eraser: bool },
    /// A PLAIN mouse button went down or up. A parked pen keeps the tablet in
    /// proximity indefinitely, so the frontend needs a positive signal that
    /// the drag in progress is not a pen stroke and must ignore pen state.
    #[serde(rename_all = "camelCase")]
    MouseStroke { down: bool },
    /// Native middle-button drag samples. AppKit does not provide default
    /// handling for third-button drags, and WKWebView consequently delivers a
    /// sparse/unreliable DOM stream for a stylus barrel button mapped to
    /// middle-click. Window coordinates are logical points; the frontend uses
    /// their differences, so title-bar offsets and the flipped DOM Y axis do
    /// not affect the gesture.
    #[serde(rename_all = "camelCase")]
    Pan {
        phase: &'static str, // "down" | "move" | "up"
        x: f64,
        y: f64,
    },
}

fn point_event(event: &NSEvent, phase: &'static str) -> TabletEvent {
    let tilt = event.tilt();
    let point = event.locationInWindow();
    TabletEvent::Point {
        phase,
        pressure: event.pressure(),
        tilt_x: tilt.x,
        tilt_y: tilt.y,
        x: point.x,
        y: point.y,
        absolute_x: event.absoluteX(),
        absolute_y: event.absoluteY(),
        delta_x: event.deltaX(),
        delta_y: event.deltaY(),
        buttons: event.buttonMask().0,
    }
}

fn proximity_event(event: &NSEvent) -> TabletEvent {
    TabletEvent::Proximity {
        entering: event.isEnteringProximity(),
        eraser: event.pointingDeviceType() == NSPointingDeviceType::Eraser,
    }
}

fn pan_event(event: &NSEvent, phase: &'static str) -> TabletEvent {
    let point = event.locationInWindow();
    TabletEvent::Pan {
        phase,
        x: point.x,
        y: point.y,
    }
}

/// Install the monitor. Must be called on the main thread (Tauri's `setup`).
pub fn install(app: &tauri::AppHandle) {
    let app = app.clone();
    let handler = RcBlock::new(move |event: NonNull<NSEvent>| -> *mut NSEvent {
        let event_ref = unsafe { event.as_ref() };
        let payload = match event_ref.r#type() {
            // A barrel button configured as middle-click is button 2 in
            // AppKit. Capture its complete native drag stream instead of
            // relying on WKWebView to synthesize pointer movement for an
            // event AppKit otherwise leaves unhandled.
            kind @ (NSEventType::OtherMouseDown
            | NSEventType::OtherMouseDragged
            | NSEventType::OtherMouseUp)
                if event_ref.buttonNumber() == 2 =>
            {
                Some(pan_event(
                    event_ref,
                    match kind {
                        NSEventType::OtherMouseDown => "down",
                        NSEventType::OtherMouseUp => "up",
                        _ => "move",
                    },
                ))
            }
            NSEventType::TabletPoint => Some(point_event(event_ref, "move")),
            NSEventType::TabletProximity => Some(proximity_event(event_ref)),
            // Hover: the pen moving above the tablet rides on plain mouse
            // moves. Plain (non-tablet) moves emit nothing.
            NSEventType::MouseMoved => match event_ref.subtype() {
                NSEventSubtype::TabletPoint => Some(point_event(event_ref, "hover")),
                _ => None,
            },
            kind @ (NSEventType::LeftMouseDown
            | NSEventType::LeftMouseDragged
            | NSEventType::LeftMouseUp) => match event_ref.subtype() {
                NSEventSubtype::TabletPoint => Some(point_event(
                    event_ref,
                    match kind {
                        NSEventType::LeftMouseDown => "down",
                        NSEventType::LeftMouseUp => "up",
                        _ => "move",
                    },
                )),
                NSEventSubtype::TabletProximity => Some(proximity_event(event_ref)),
                _ => match kind {
                    NSEventType::LeftMouseDown => Some(TabletEvent::MouseStroke { down: true }),
                    NSEventType::LeftMouseUp => Some(TabletEvent::MouseStroke { down: false }),
                    _ => None,
                },
            },
            _ => None,
        };
        if let Some(payload) = payload {
            let _ = app.emit("tablet-input", payload);
        }
        event.as_ptr()
    });

    let mask = NSEventMask::LeftMouseDown
        | NSEventMask::LeftMouseDragged
        | NSEventMask::LeftMouseUp
        | NSEventMask::OtherMouseDown
        | NSEventMask::OtherMouseDragged
        | NSEventMask::OtherMouseUp
        | NSEventMask::MouseMoved
        | NSEventMask::TabletPoint
        | NSEventMask::TabletProximity;

    // The token is intentionally leaked: the monitor lives for the app's
    // lifetime, and releasing our reference would not deregister it anyway
    // (that requires removeMonitor:).
    let monitor = unsafe { NSEvent::addLocalMonitorForEventsMatchingMask_handler(mask, &handler) };
    if let Some(monitor) = monitor {
        std::mem::forget(monitor);
    } else {
        log::warn!("[tablet] failed to install NSEvent monitor; stylus pressure unavailable");
    }
}
