# UltraMacro
Records every single keyboard input with millisecond precision

# Input Macro Recorder

A G Hub–style macro recorder, with mouse movement, written in Python.

## Setup

```bash
pip install pynput
python macro_recorder.py
```

`tkinter` ships with the standard CPython installer on Windows/macOS. On
Debian/Ubuntu: `sudo apt install python3-tk`.

## Permissions

- **macOS** — grant your terminal (or the Python binary) both
  *Accessibility* and *Input Monitoring* in **System Settings → Privacy &
  Security**. Without these, the listeners attach but silently see nothing.
- **Windows** — works out of the box; run as admin only if you need to
  capture input inside elevated windows.
- **Linux** — works on X11. Wayland support in `pynput` is limited; if
  events don't appear, log into an X session.

## How to use

1. Launch the app.
2. Press **F5** anywhere on your system (or click *Toggle Record*).
   The status indicator turns red and recording begins.
3. Do whatever you want recorded — type, move the mouse, click, scroll.
4. Press **F5** again to stop. The timeline fills in.
5. Edit the timeline:
   - **Double-click** the *Δ Delay* cell of any row to change just that
     gap inline.
   - Or select a row, type into the *Delay before selected event* field,
     and click **Apply Delay**.
   - **Insert Pause…** adds an arbitrary wait before the selected event.
   - **Delete Selected** removes events (select multiple with Ctrl/Shift).
   - All subsequent absolute timestamps shift automatically — the rest of
     the macro's relative timing is preserved.
6. Click **▶ Play**. The app waits ~1.5 seconds so you can refocus the
   target window, then replays the macro at the (possibly edited) timings.
   Click **■ Stop** at any time.
7. **Save…** writes the macro to a JSON file; **Load…** reads it back.

## Settings

- **Mouse-move sample interval (ms)** — minimum gap between recorded mouse
  positions. `0` captures every move (heavy but butter-smooth). `10`
  (default) gives ~100 samples/sec, similar to G Hub. Higher values
  produce shorter timelines that are easier to edit.

## Macro file format

A macro is a JSON array of events with absolute millisecond timestamps:

```json
[
  { "time": 0,    "type": "mouse_move",    "x": 412, "y": 300 },
  { "time": 120,  "type": "mouse_press",   "x": 412, "y": 300, "button": "left" },
  { "time": 180,  "type": "mouse_release", "x": 412, "y": 300, "button": "left" },
  { "time": 500,  "type": "key_press",     "key": "a" },
  { "time": 560,  "type": "key_release",   "key": "a" }
]
```

Event types: `key_press`, `key_release`, `mouse_move`, `mouse_press`,
`mouse_release`, `mouse_scroll`. The file is plain JSON — you can edit it
by hand if you want.

## A few notes

- The F5 toggle itself is filtered out so it never appears in your macros.
  If you'd rather toggle with a different key, change `TOGGLE_KEY` at the
  top of `macro_recorder.py`.
- Playback uses absolute screen coordinates, so it expects the same
  resolution / monitor layout you recorded under.
- Long sessions with `sample interval = 0` can generate tens of thousands
  of mouse-move events. The Treeview handles this fine but editing is
  easier if you crank the interval up.
