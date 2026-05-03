#!/usr/bin/env python3
"""
gif-script.py - Floating GIF Widget Daemon mit IPC-Steuerung

Standardmäßig "locked" = Klicks gehen durch zum Spiel.
Steuerung über Unix-Socket via 'gif <subcommand>' Fish-Funktion.

Modi:
    gif-script.py <gif-pfad>                         Daemon starten (ID = Dateiname)
    gif-script.py run <gif-pfad> [--id NAME]         Daemon mit eigener ID
    gif-script.py ipc <id> <action> [args...]        IPC-Befehl senden
    gif-script.py list                               Laufende Widgets auflisten
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GLib, GtkLayerShell, GdkPixbuf
import cairo
import sys
import signal
import os
import socket
import json
import threading
import argparse
import getpass
from pathlib import Path
from PIL import Image, ImageSequence


# ===========================================================================
# Pfade & Hilfsfunktionen
# ===========================================================================

USER = getpass.getuser()
RUNTIME_DIR = Path(f"/tmp/gif-widget-{USER}")
CONFIG_DIR = Path.home() / ".config" / "gif-widget"
STATE_FILE = CONFIG_DIR / "state.json"


def ensure_dirs():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def socket_path(wid):
    return RUNTIME_DIR / f"{wid}.sock"


def pid_file(wid):
    return RUNTIME_DIR / f"{wid}.pid"


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state_for(wid, data):
    state = load_state()
    state[wid] = data
    try:
        ensure_dirs()
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        print(f"[gif-widget] State save failed: {e}", file=sys.stderr)


def is_pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_widget_alive(wid):
    pf = pid_file(wid)
    if not pf.exists():
        return False
    try:
        return is_pid_alive(int(pf.read_text().strip()))
    except Exception:
        return False


def cleanup_stale(wid):
    for f in (pid_file(wid), socket_path(wid)):
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass


def list_running():
    if not RUNTIME_DIR.exists():
        return []
    result = []
    for pf in sorted(RUNTIME_DIR.glob("*.pid")):
        wid = pf.stem
        if is_widget_alive(wid):
            result.append(wid)
        else:
            cleanup_stale(wid)
    return result


def send_ipc(wid, command, timeout=2.0):
    sp = socket_path(wid)
    if not sp.exists():
        return {"error": f"No widget '{wid}' running"}
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(sp))
        s.sendall((json.dumps(command) + "\n").encode())
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\n"):
                break
        s.close()
        return json.loads(data.decode().strip()) if data else {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ===========================================================================
# Das Widget
# ===========================================================================

class FloatingWidget(Gtk.Window):
    def __init__(self, gif_path, widget_id):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.widget_id = widget_id
        self.gif_path = gif_path

        # Fenster-Setup
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_accept_focus(False)

        screen = self.get_screen()
        rgba = screen.get_rgba_visual()
        if rgba:
            self.set_visual(rgba)

        # Layer Shell (Wayland Overlay)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_namespace(self, f"gif-widget-{widget_id}")
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)

        # Bildschirmgröße
        display = Gdk.Display.get_default()
        self.screen_width = 0
        self.screen_height = 0
        for i in range(display.get_n_monitors()):
            geom = display.get_monitor(i).get_geometry()
            self.screen_width = max(self.screen_width, geom.x + geom.width)
            self.screen_height = max(self.screen_height, geom.y + geom.height)
        if self.screen_width == 0:
            self.screen_width = 1920
        if self.screen_height == 0:
            self.screen_height = 1080

        self._load_gif()

        # State (mit Persistenz)
        prev = load_state().get(widget_id, {})
        self.window_x = float(prev.get("x", 100))
        self.window_y = float(prev.get("y", 100))
        self.scale = float(prev.get("scale", 0.7))
        self.locked = bool(prev.get("locked", True))  # Default: locked = sicher!
        self.paused = False
        self._state_dirty = False

        self._setup_css()

        # UI
        self.image = Gtk.Image()
        self.event_box = Gtk.EventBox()
        self.event_box.set_visible_window(False)
        self.event_box.add(self.image)

        self.frame_box = Gtk.Box()
        self.frame_box.get_style_context().add_class("gif-frame")
        self.frame_box.pack_start(self.event_box, True, True, 0)
        self.add(self.frame_box)

        self.event_box.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.event_box.connect("button-press-event", self.on_press)
        self.event_box.connect("motion-notify-event", self.on_motion)
        self.event_box.connect("button-release-event", self.on_release)
        self.event_box.connect("scroll-event", self.on_scroll)

        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0

        self.connect("realize", lambda w: self._apply_lock_state())
        self.connect("size-allocate", lambda w, a: self._apply_lock_state())

        self.update_position()
        self.update_frame()

        GLib.timeout_add(self.frame_durations[0], self.next_frame)
        GLib.timeout_add_seconds(3, self._auto_save)

        self.show_all()

    # -------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------

    def _setup_css(self):
        css = b"""
        .gif-frame { background: transparent; }
        .gif-frame.unlocked {
            border: 2px dashed rgba(255, 100, 200, 0.75);
            border-radius: 6px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _load_gif(self):
        try:
            self.gif = Image.open(self.gif_path)
            self.frames = []
            self.frame_durations = []
            for frame in ImageSequence.Iterator(self.gif):
                rgba = frame.convert("RGBA")
                w, h = rgba.size
                pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                    GLib.Bytes.new(rgba.tobytes()),
                    GdkPixbuf.Colorspace.RGB,
                    True, 8, w, h, w * 4,
                )
                self.frames.append(pixbuf)
                duration = frame.info.get("duration", 80)
                self.frame_durations.append(80 if duration < 20 else duration)
        except Exception as e:
            print(f"[gif-widget] Failed to load GIF: {e}", file=sys.stderr)
            sys.exit(1)

        if not self.frames:
            print("[gif-widget] No frames in GIF", file=sys.stderr)
            sys.exit(1)

        self.frame_index = 0
        self.base_width = self.frames[0].get_width()
        self.base_height = self.frames[0].get_height()

    # -------------------------------------------------------------------
    # Lock-State (Click-Through)
    # -------------------------------------------------------------------

    def _apply_lock_state(self):
        """Setzt Input-Region und Visual abhängig von self.locked."""
        win = self.get_window()
        ctx = self.frame_box.get_style_context()
        if self.locked:
            ctx.remove_class("unlocked")
            if win is not None:
                # Leere Region = keine Maus-Events (Click-Through)
                win.input_shape_combine_region(cairo.Region())
        else:
            ctx.add_class("unlocked")
            if win is not None:
                # None = Default = volles Fenster
                win.input_shape_combine_region(None)

    # -------------------------------------------------------------------
    # Position/Frame
    # -------------------------------------------------------------------

    def update_position(self):
        max_x = max(0, self.screen_width - int(self.base_width * self.scale))
        max_y = max(0, self.screen_height - int(self.base_height * self.scale))
        self.window_x = max(0, min(self.window_x, max_x))
        self.window_y = max(0, min(self.window_y, max_y))
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, int(self.window_x))
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, int(self.window_y))
        self._state_dirty = True

    def update_frame(self):
        pixbuf = self.frames[self.frame_index]
        w = int(self.base_width * self.scale)
        h = int(self.base_height * self.scale)
        scaled = pixbuf.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        self.image.set_from_pixbuf(scaled)
        self.set_size_request(w, h)

    def next_frame(self):
        if not self.paused:
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            self.update_frame()
        delay = 200 if self.paused else self.frame_durations[self.frame_index]
        GLib.timeout_add(delay, self.next_frame)
        return False

    # -------------------------------------------------------------------
    # Maus-Events (nur wenn unlocked)
    # -------------------------------------------------------------------

    def on_press(self, widget, event):
        if self.locked:
            return False  # sollte eh nicht ankommen wegen empty input region
        if event.button == 1:
            self.dragging = True
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            return True
        elif event.button == 3:
            # Rechtsklick auf unlocked GIF → sofort lock (game-ready)
            self.set_locked(True)
            return True
        return False

    def on_motion(self, widget, event):
        if self.dragging:
            dx = event.x_root - self.drag_start_x
            dy = event.y_root - self.drag_start_y
            self.window_x += dx
            self.window_y += dy
            self.update_position()
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            return True
        return False

    def on_release(self, widget, event):
        if event.button == 1:
            self.dragging = False
            return True
        return False

    def on_scroll(self, widget, event):
        if self.locked:
            return False
        if event.direction == Gdk.ScrollDirection.UP:
            self.scale *= 1.05
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.scale *= 0.95
        self.scale = max(0.2, min(self.scale, 3.0))
        self.update_frame()
        self._state_dirty = True
        return True

    # -------------------------------------------------------------------
    # State Persistence
    # -------------------------------------------------------------------

    def _auto_save(self):
        if self._state_dirty:
            self._save_now()
            self._state_dirty = False
        return True

    def _save_now(self):
        save_state_for(self.widget_id, {
            "x": self.window_x,
            "y": self.window_y,
            "scale": self.scale,
            "locked": self.locked,
        })

    # -------------------------------------------------------------------
    # IPC-Aktionen (alle thread-safe via GLib.idle_add im Server)
    # -------------------------------------------------------------------

    def set_locked(self, locked):
        self.locked = bool(locked)
        self._apply_lock_state()
        self._state_dirty = True
        return self.status()

    def toggle_locked(self):
        return self.set_locked(not self.locked)

    def set_position(self, x, y):
        self.window_x = float(x)
        self.window_y = float(y)
        self.update_position()
        return self.status()

    def move_by(self, dx, dy):
        self.window_x += float(dx)
        self.window_y += float(dy)
        self.update_position()
        return self.status()

    def set_scale(self, s):
        self.scale = max(0.1, min(float(s), 5.0))
        self.update_frame()
        self._state_dirty = True
        return self.status()

    def go_corner(self, pos):
        margin = 20
        w = int(self.base_width * self.scale)
        h = int(self.base_height * self.scale)
        positions = {
            "tl": (margin, margin),
            "tr": (self.screen_width - w - margin, margin),
            "bl": (margin, self.screen_height - h - margin),
            "br": (self.screen_width - w - margin, self.screen_height - h - margin),
            "center": ((self.screen_width - w) // 2, (self.screen_height - h) // 2),
        }
        if pos not in positions:
            return {"error": f"Unknown corner: {pos} (use tl/tr/bl/br/center)"}
        x, y = positions[pos]
        return self.set_position(x, y)

    def set_paused(self, paused):
        self.paused = bool(paused)
        return self.status()

    def status(self):
        return {
            "ok": True,
            "id": self.widget_id,
            "x": int(self.window_x),
            "y": int(self.window_y),
            "scale": round(self.scale, 3),
            "locked": self.locked,
            "paused": self.paused,
            "size": [int(self.base_width * self.scale), int(self.base_height * self.scale)],
            "screen": [self.screen_width, self.screen_height],
        }

    def shutdown(self):
        self._save_now()
        GLib.timeout_add(50, Gtk.main_quit)
        return {"ok": True, "shutdown": True}


# ===========================================================================
# IPC-Server (Unix-Socket)
# ===========================================================================

class IPCServer(threading.Thread):
    def __init__(self, widget, sock_path):
        super().__init__(daemon=True)
        self.widget = widget
        self.sock_path = sock_path
        self.running = True
        self.sock = None

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(str(self.sock_path))
            os.chmod(str(self.sock_path), 0o600)
            self.sock.listen(5)
            self.sock.settimeout(0.5)
            while self.running:
                try:
                    conn, _ = self.sock.accept()
                    self._handle(conn)
                except socket.timeout:
                    continue
                except Exception:
                    if not self.running:
                        break
        finally:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass

    def stop(self):
        self.running = False

    def _handle(self, conn):
        try:
            conn.settimeout(2.0)
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if not data:
                return
            cmd = json.loads(data.decode().strip())

            holder = {}
            done = threading.Event()

            def execute():
                try:
                    holder["result"] = self._dispatch(cmd)
                except Exception as e:
                    holder["result"] = {"error": str(e)}
                finally:
                    done.set()
                return False

            GLib.idle_add(execute)
            done.wait(timeout=3.0)

            response = holder.get("result", {"error": "timeout"})
            conn.sendall((json.dumps(response) + "\n").encode())
        except Exception as e:
            try:
                conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _dispatch(self, cmd):
        action = cmd.get("action", "")
        w = self.widget
        handlers = {
            "status": lambda: w.status(),
            "quit": lambda: w.shutdown(),
            "lock": lambda: w.set_locked(True),
            "unlock": lambda: w.set_locked(False),
            "toggle": lambda: w.toggle_locked(),
            "pause": lambda: w.set_paused(True),
            "play": lambda: w.set_paused(False),
            "move": lambda: w.set_position(cmd["x"], cmd["y"]),
            "move-by": lambda: w.move_by(cmd["dx"], cmd["dy"]),
            "scale": lambda: w.set_scale(cmd["scale"]),
            "corner": lambda: w.go_corner(cmd["position"]),
        }
        if action not in handlers:
            return {"error": f"Unknown action: {action}"}
        return handlers[action]()


# ===========================================================================
# Daemon-Modus
# ===========================================================================

def run_daemon(gif_path, widget_id):
    ensure_dirs()

    if is_widget_alive(widget_id):
        print(f"[gif-widget] '{widget_id}' läuft bereits. "
              f"Erst 'gif kill {widget_id}' nutzen.", file=sys.stderr)
        sys.exit(1)

    cleanup_stale(widget_id)
    pid_file(widget_id).write_text(str(os.getpid()))

    widget = FloatingWidget(gif_path, widget_id)
    sp = socket_path(widget_id)
    ipc = IPCServer(widget, sp)
    ipc.start()

    def cleanup():
        try:
            widget._save_now()
        except Exception:
            pass
        ipc.stop()
        cleanup_stale(widget_id)

    def sig_handler(sig, frame):
        Gtk.main_quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


# ===========================================================================
# CLI
# ===========================================================================

def cli_ipc(widget_id, action_args):
    if not action_args:
        return {"error": "No action specified"}
    action = action_args[0]
    args = action_args[1:]
    cmd = {"action": action}
    try:
        if action == "move":
            cmd["x"], cmd["y"] = float(args[0]), float(args[1])
        elif action == "move-by":
            cmd["dx"], cmd["dy"] = float(args[0]), float(args[1])
        elif action == "scale":
            cmd["scale"] = float(args[0])
        elif action == "corner":
            cmd["position"] = args[0]
    except (IndexError, ValueError) as e:
        return {"error": f"Bad args for {action}: {e}"}
    return send_ipc(widget_id, cmd)


def main():
    # Legacy: erstes arg ist ein existierender Pfad → daemon starten
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]) and sys.argv[1] not in ("list",):
        gif_path = sys.argv[1]
        widget_id = os.path.splitext(os.path.basename(gif_path))[0]
        if len(sys.argv) >= 3 and sys.argv[2] == "--id" and len(sys.argv) >= 4:
            widget_id = sys.argv[3]
        run_daemon(gif_path, widget_id)
        return

    parser = argparse.ArgumentParser(description="Floating GIF Widget")
    sub = parser.add_subparsers(dest="mode")

    p_run = sub.add_parser("run", help="Daemon starten")
    p_run.add_argument("gif_path")
    p_run.add_argument("--id", default=None)

    p_ipc = sub.add_parser("ipc", help="IPC-Befehl senden")
    p_ipc.add_argument("widget_id")
    p_ipc.add_argument("action_args", nargs="+")

    sub.add_parser("list", help="Laufende Widgets auflisten")

    args = parser.parse_args()

    if args.mode == "run":
        if not os.path.exists(args.gif_path):
            print(f"Error: GIF not found: {args.gif_path}", file=sys.stderr)
            sys.exit(1)
        wid = args.id or os.path.splitext(os.path.basename(args.gif_path))[0]
        run_daemon(args.gif_path, wid)
    elif args.mode == "ipc":
        result = cli_ipc(args.widget_id, args.action_args)
        print(json.dumps(result))
        if result and "error" in result:
            sys.exit(1)
    elif args.mode == "list":
        for wid in list_running():
            print(wid)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
