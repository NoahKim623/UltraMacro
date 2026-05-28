"""
Input Macro Recorder
====================
Records keyboard + mouse input (including movement) with a global toggle
hotkey, displays a timeline of every event, and lets you edit the millisecond
delays between events before playback.

Requires:
    pip install pynput

Notes:
    - Default toggle key is F5 (configurable at the top of this file).
    - macOS users: grant the Python binary / your terminal "Accessibility"
      and "Input Monitoring" permission in System Settings, or input capture
      will silently do nothing.
    - Linux/Wayland: pynput needs an X session; Wayland support is limited.
"""

import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController, Key, KeyCode
from pynput.mouse import Controller as MouseController, Button


# ---------- Config ----------
TOGGLE_KEY = Key.f5            # Press this anywhere to start/stop recording
DEFAULT_MOUSE_THROTTLE_MS = 10 # Lower = smoother + heavier; 0 = capture all
PLAYBACK_COUNTDOWN_MS = 1500   # Delay before playback so you can refocus
# ----------------------------


# =====================================================================
# Recorder
# =====================================================================
class InputRecorder:
    """Captures keyboard + mouse events into a flat list with absolute ms timestamps."""

    def __init__(self):
        self.events = []
        self.recording = False
        self.start_time = None
        self.last_mouse_move_time = -10_000
        self.mouse_move_throttle_ms = DEFAULT_MOUSE_THROTTLE_MS
        self._kb_listener = None
        self._mouse_listener = None

    def start(self):
        if self.recording:
            return
        self.events = []
        self.recording = True
        self.start_time = time.perf_counter()
        self.last_mouse_move_time = -10_000

        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._kb_listener.start()
        self._mouse_listener.start()

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        if self._kb_listener:
            self._kb_listener.stop()
            self._kb_listener = None
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

    def _elapsed_ms(self):
        return int((time.perf_counter() - self.start_time) * 1000)

    # ---- Keyboard ----
    def _on_key_press(self, key):
        if not self.recording or key == TOGGLE_KEY:
            return
        self.events.append({
            "time": self._elapsed_ms(),
            "type": "key_press",
            "key": key_to_str(key),
        })

    def _on_key_release(self, key):
        if not self.recording or key == TOGGLE_KEY:
            return
        self.events.append({
            "time": self._elapsed_ms(),
            "type": "key_release",
            "key": key_to_str(key),
        })

    # ---- Mouse ----
    def _on_mouse_move(self, x, y):
        if not self.recording:
            return
        now = self._elapsed_ms()
        if now - self.last_mouse_move_time < self.mouse_move_throttle_ms:
            return
        self.last_mouse_move_time = now
        self.events.append({"time": now, "type": "mouse_move", "x": x, "y": y})

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.recording:
            return
        self.events.append({
            "time": self._elapsed_ms(),
            "type": "mouse_press" if pressed else "mouse_release",
            "x": x,
            "y": y,
            "button": button.name,
        })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.recording:
            return
        self.events.append({
            "time": self._elapsed_ms(),
            "type": "mouse_scroll",
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy,
        })


# =====================================================================
# Key serialization helpers
# =====================================================================
def key_to_str(key):
    if isinstance(key, KeyCode):
        if key.char is not None:
            return key.char
        # Virtual key code fallback
        return f"vk:{key.vk}"
    # Special key (Key.shift, Key.enter, ...)
    return str(key).replace("Key.", "")


def str_to_key(s):
    if s.startswith("vk:"):
        return KeyCode(vk=int(s[3:]))
    if len(s) == 1:
        return s  # plain character
    try:
        return getattr(Key, s)
    except AttributeError:
        return s


# =====================================================================
# Player
# =====================================================================
class MacroPlayer:
    def __init__(self):
        self.kb = KeyboardController()
        self.mouse = MouseController()
        self.playing = False
        self._thread = None

    def play(self, events, on_complete=None):
        if self.playing or not events:
            return
        self.playing = True
        self._thread = threading.Thread(
            target=self._run, args=(list(events), on_complete), daemon=True
        )
        self._thread.start()

    def stop(self):
        self.playing = False

    def _run(self, events, on_complete):
        try:
            start = time.perf_counter()
            for ev in events:
                if not self.playing:
                    break
                target = ev["time"] / 1000.0
                wait = target - (time.perf_counter() - start)
                if wait > 0:
                    # Sleep in small chunks so .stop() is responsive
                    end = time.perf_counter() + wait
                    while self.playing and time.perf_counter() < end:
                        time.sleep(min(0.01, end - time.perf_counter()))
                if not self.playing:
                    break
                self._execute(ev)
        finally:
            self.playing = False
            if on_complete:
                on_complete()

    def _execute(self, ev):
        t = ev["type"]
        try:
            if t == "key_press":
                self.kb.press(str_to_key(ev["key"]))
            elif t == "key_release":
                self.kb.release(str_to_key(ev["key"]))
            elif t == "mouse_move":
                self.mouse.position = (ev["x"], ev["y"])
            elif t == "mouse_press":
                self.mouse.position = (ev["x"], ev["y"])
                self.mouse.press(Button[ev["button"]])
            elif t == "mouse_release":
                self.mouse.position = (ev["x"], ev["y"])
                self.mouse.release(Button[ev["button"]])
            elif t == "mouse_scroll":
                self.mouse.scroll(ev["dx"], ev["dy"])
        except Exception as e:
            print(f"[playback] {t} failed: {e}")


# =====================================================================
# GUI
# =====================================================================
class MacroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Input Macro Recorder")
        self.root.geometry("1000x650")

        self.recorder = InputRecorder()
        self.player = MacroPlayer()

        self._build_ui()
        self._install_global_hotkey()

    # ---- UI construction ----
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Top control bar
        top = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        top.pack(fill="x")

        self.status_label = ttk.Label(
            top, text="● Idle", foreground="gray", font=("Segoe UI", 12, "bold")
        )
        self.status_label.pack(side="left", padx=(0, 16))

        ttk.Button(top, text=f"Toggle Record  ({key_to_str(TOGGLE_KEY).upper()})",
                   command=self.toggle_recording).pack(side="left", padx=4)
        ttk.Button(top, text="▶  Play",        command=self.play_macro).pack(side="left", padx=4)
        ttk.Button(top, text="■  Stop",        command=self.stop_playback).pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top, text="Save…",          command=self.save_macro).pack(side="left", padx=4)
        ttk.Button(top, text="Load…",          command=self.load_macro).pack(side="left", padx=4)
        ttk.Button(top, text="Clear",          command=self.clear_events).pack(side="left", padx=4)

        # Settings row
        settings = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        settings.pack(fill="x")
        ttk.Label(settings, text="Mouse-move sample interval (ms):").pack(side="left")
        self.throttle_var = tk.IntVar(value=DEFAULT_MOUSE_THROTTLE_MS)
        ttk.Spinbox(
            settings, from_=0, to=500, textvariable=self.throttle_var, width=6,
            command=self._update_throttle,
        ).pack(side="left", padx=6)
        ttk.Label(
            settings,
            text="(0 = record every move; higher = lighter timeline)",
            foreground="#666",
        ).pack(side="left", padx=8)

        # Timeline
        tl_frame = ttk.LabelFrame(self.root, text="Timeline", padding=8)
        tl_frame.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        cols = ("idx", "delay", "abs", "type", "details")
        self.tree = ttk.Treeview(tl_frame, columns=cols, show="headings", height=18,
                                 selectmode="extended")
        headings = {
            "idx":     ("#",             50,  "center"),
            "delay":   ("Δ Delay (ms)",  110, "e"),
            "abs":     ("Absolute (ms)", 110, "e"),
            "type":    ("Type",          130, "w"),
            "details": ("Details",       500, "w"),
        }
        for c, (label, w, anchor) in headings.items():
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, anchor=anchor)

        vsb = ttk.Scrollbar(tl_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

        # Edit row
        edit = ttk.Frame(self.root, padding=10)
        edit.pack(fill="x")
        ttk.Label(edit, text="Delay before selected event (ms):").pack(side="left")
        self.delay_var = tk.StringVar()
        self.delay_entry = ttk.Entry(edit, textvariable=self.delay_var, width=10)
        self.delay_entry.pack(side="left", padx=6)
        self.delay_entry.bind("<Return>", lambda e: self.apply_delay())
        ttk.Button(edit, text="Apply Delay",    command=self.apply_delay).pack(side="left", padx=4)
        ttk.Button(edit, text="Insert Pause…",  command=self.insert_pause).pack(side="left", padx=4)
        ttk.Button(edit, text="Delete Selected",command=self.delete_selected).pack(side="left", padx=4)

        # Hint footer
        hint = ttk.Label(
            self.root,
            text=("Tip: double-click a row's delay to edit it inline. "
                  "Press F5 anywhere on your system to start/stop recording."),
            foreground="#666",
            padding=(10, 0, 10, 8),
        )
        hint.pack(fill="x")

    def _install_global_hotkey(self):
        """Listen for the toggle key system-wide so the app needn't be focused."""
        def on_press(key):
            if key == TOGGLE_KEY:
                # Must marshal back to Tk's main thread
                self.root.after(0, self.toggle_recording)
        self._hotkey_listener = keyboard.Listener(on_press=on_press)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    # ---- Actions ----
    def _update_throttle(self):
        try:
            self.recorder.mouse_move_throttle_ms = int(self.throttle_var.get())
        except (ValueError, tk.TclError):
            pass

    def toggle_recording(self):
        if self.player.playing:
            return  # ignore while playing back
        if self.recorder.recording:
            self.recorder.stop()
            self.status_label.config(text="● Idle", foreground="gray")
            self.refresh_timeline()
        else:
            self._update_throttle()
            self.recorder.start()
            self.status_label.config(text="● RECORDING", foreground="#c0392b")

    def play_macro(self):
        if not self.recorder.events:
            messagebox.showinfo("Empty", "Nothing to play — record or load a macro first.")
            return
        if self.recorder.recording:
            messagebox.showinfo("Busy", "Stop recording before playback.")
            return
        if self.player.playing:
            return
        self.status_label.config(text=f"▶ Playing in {PLAYBACK_COUNTDOWN_MS} ms…",
                                 foreground="#2c81e0")
        # Brief delay so the user can refocus their target window
        self.root.after(
            PLAYBACK_COUNTDOWN_MS,
            lambda: (
                self.status_label.config(text="▶ Playing…", foreground="#2c81e0"),
                self.player.play(
                    self.recorder.events,
                    on_complete=lambda: self.root.after(0, self._on_playback_done),
                ),
            ),
        )

    def _on_playback_done(self):
        self.status_label.config(text="● Idle", foreground="gray")

    def stop_playback(self):
        self.player.stop()

    def save_macro(self):
        if not self.recorder.events:
            messagebox.showinfo("Empty", "No events to save.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Macro JSON", "*.json")],
            title="Save macro",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.recorder.events, f, indent=2)

    def load_macro(self):
        path = filedialog.askopenfilename(
            filetypes=[("Macro JSON", "*.json"), ("All files", "*.*")],
            title="Load macro",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("File does not contain a macro list.")
            self.recorder.events = data
            self.refresh_timeline()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def clear_events(self):
        if not self.recorder.events:
            return
        if messagebox.askyesno("Confirm", "Clear all recorded events?"):
            self.recorder.events = []
            self.refresh_timeline()

    # ---- Timeline rendering ----
    def refresh_timeline(self):
        self.tree.delete(*self.tree.get_children())
        prev_t = 0
        for i, ev in enumerate(self.recorder.events):
            delay = ev["time"] - prev_t
            prev_t = ev["time"]
            self.tree.insert(
                "", "end", iid=str(i),
                values=(i + 1, delay, ev["time"], ev["type"], self._format_details(ev)),
            )

    def _format_details(self, ev):
        t = ev["type"]
        if t in ("key_press", "key_release"):
            return f"key = {ev['key']}"
        if t == "mouse_move":
            return f"({ev['x']}, {ev['y']})"
        if t in ("mouse_press", "mouse_release"):
            return f"{ev['button']} at ({ev['x']}, {ev['y']})"
        if t == "mouse_scroll":
            return f"scroll dx={ev['dx']} dy={ev['dy']} at ({ev['x']}, {ev['y']})"
        return ""

    # ---- Selection + editing ----
    def _on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        prev_t = self.recorder.events[idx - 1]["time"] if idx > 0 else 0
        delay = self.recorder.events[idx]["time"] - prev_t
        self.delay_var.set(str(delay))

    def _on_double_click(self, event):
        # If user double-clicks the delay column, pop an inline editor
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#2":  # the "delay" column
            self.delay_entry.focus()
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        self._popup_delay_editor(row_id, event)

    def _popup_delay_editor(self, row_id, event):
        idx = int(row_id)
        prev_t = self.recorder.events[idx - 1]["time"] if idx > 0 else 0
        current = self.recorder.events[idx]["time"] - prev_t

        bbox = self.tree.bbox(row_id, column="#2")
        if not bbox:
            return
        x, y, w, h = bbox
        editor = ttk.Entry(self.tree)
        editor.insert(0, str(current))
        editor.select_range(0, "end")
        editor.focus()
        editor.place(x=x, y=y, width=w, height=h)

        def commit(_e=None):
            try:
                new_delay = int(editor.get())
            except ValueError:
                editor.destroy()
                return
            editor.destroy()
            self._set_delay(idx, new_delay)

        def cancel(_e=None):
            editor.destroy()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)
        editor.bind("<Escape>", cancel)

    def apply_delay(self):
        sel = self.tree.selection()
        if not sel:
            return
        try:
            new_delay = int(self.delay_var.get())
            if new_delay < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "Delay must be a non-negative integer (ms).")
            return
        idx = int(sel[0])
        self._set_delay(idx, new_delay)

    def _set_delay(self, idx, new_delay):
        prev_t = self.recorder.events[idx - 1]["time"] if idx > 0 else 0
        old_time = self.recorder.events[idx]["time"]
        new_time = prev_t + new_delay
        diff = new_time - old_time
        # Shift this event and everything after it
        for i in range(idx, len(self.recorder.events)):
            self.recorder.events[i]["time"] += diff
        self.refresh_timeline()
        self.tree.selection_set(str(idx))
        self.tree.see(str(idx))

    def insert_pause(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a row", "Select an event to insert a pause before it.")
            return
        idx = int(sel[0])
        pause_str = SimplePromptDialog(self.root, "Insert pause", "Pause length (ms):").result
        if pause_str is None:
            return
        try:
            pause = int(pause_str)
            if pause <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "Pause must be a positive integer (ms).")
            return
        for i in range(idx, len(self.recorder.events)):
            self.recorder.events[i]["time"] += pause
        self.refresh_timeline()
        self.tree.selection_set(str(idx))
        self.tree.see(str(idx))

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        indices = sorted((int(s) for s in sel), reverse=True)
        for idx in indices:
            del self.recorder.events[idx]
        self.refresh_timeline()


# =====================================================================
# Tiny prompt dialog (avoids tkinter.simpledialog quirks on some themes)
# =====================================================================
class SimplePromptDialog(tk.Toplevel):
    def __init__(self, parent, title, prompt):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None

        ttk.Label(self, text=prompt).pack(padx=16, pady=(14, 4))
        self.entry = ttk.Entry(self, width=20)
        self.entry.pack(padx=16, pady=4)
        self.entry.focus()
        self.entry.bind("<Return>", lambda _e: self._ok())
        self.entry.bind("<Escape>", lambda _e: self._cancel())

        btns = ttk.Frame(self)
        btns.pack(pady=(4, 12))
        ttk.Button(btns, text="OK",     command=self._ok).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="left", padx=6)

        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = self.entry.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# =====================================================================
def main():
    root = tk.Tk()
    MacroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
