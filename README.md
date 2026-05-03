
---

# 🎀 GIF Widget

A lightweight floating GIF overlay for Niri. Made with AI.

---

## ✨ Features

* 🎯 Global edit mode – move all widgets at once
* 🖱️ Drag, resize, and position freely
* 🔒 Click-through when locked (perfect for gaming)
* 💾 Persistent positions across sessions
* ⚡ Simple CLI (`gif`) + Niri keybind integration

---

## 🔓 Global Edit Mode

A single keybind controls everything:

* First press → all GIFs become interactive
* Adjust them with your mouse
* Press again → everything locks back in place

### Workflow

```
1. GIFs are running (locked, click-through)
2. Press keybind → edit mode
3. Move/resize with mouse
4. Press keybind again → locked
```

No window switching. No naming. Just adjust and continue.

---

## 📦 Installation

### 1. Install dependencies

Arch/CachyOS
```bash
sudo pacman -S python python-pillow python-gobject gtk3 gtk-layer-shell gobject-introspection
```

---

### 2. Prepare directories

```bash
mkdir -p ~/Scripts ~/.config/fish/functions
```

Place your files:

* `gif-script.py` → `~/Scripts/`
* `gif.fish` → `~/.config/fish/functions/`
* GIF files → `~/Scripts/*.gif`

Make the script executable:

```bash
chmod +x ~/Scripts/gif-script.py
```

---

### 3. Reload Fish shell

```fish
source ~/.config/fish/functions/gif.fish
```

(or open a new terminal)

---

### 4. Configure Niri keybinds

Edit:

```
~/.config/niri/config.kdl
```

Add inside the `binds {}` block:

```kdl
binds {
    // Toggle global edit mode
    Mod+Shift+G { spawn "fish" "-c" "gif edit"; }

    // Kill all widgets
    Mod+Shift+K { spawn "fish" "-c" "gif kill-all"; }
}
```

---

## 🎮 Usage

### Global commands

| Command        | Description                     |
| -------------- | ------------------------------- |
| `gif edit`     | Toggle edit mode (smart toggle) |
| `gif lock`     | Lock all widgets                |
| `gif unlock`   | Unlock all widgets              |
| `gif toggle`   | Same as `gif edit`              |
| `gif list`     | Show running widgets            |
| `gif kill-all` | Stop all widgets                |

---

### Per-widget commands

| Command                  | Description                  |
| ------------------------ | ---------------------------- |
| `gif <name>`             | Start widget                 |
| `gif <name> -always`     | Run in background            |
| `gif lock <name>`        | Lock widget                  |
| `gif unlock <name>`      | Unlock widget                |
| `gif toggle <name>`      | Toggle state                 |
| `gif move <name> X Y`    | Set absolute position        |
| `gif nudge <name> DX DY` | Move relative                |
| `gif scale <name> F`     | Resize (1.0 = original size) |
| `gif corner <name> POS`  | Snap to screen position      |
| `gif pause <name>`       | Pause animation              |
| `gif play <name>`        | Resume animation             |
| `gif status <name>`      | Show current state           |
| `gif kill <name>`        | Stop widget                  |

---

## 🖱️ Mouse Controls (Edit Mode)

| Action            | Effect           |
| ----------------- | ---------------- |
| Left click + drag | Move widget      |
| Scroll            | Scale widget     |
| Right click       | Lock that widget |

---

## 🚀 Autostart

```kdl
spawn-at-startup "fish" "-c" "gif chika -always"
spawn-at-startup "fish" "-c" "gif miku -always"
```

---

## 🛠️ Examples

### First-time setup

```fish
gif chika -always
gif edit
# adjust position and size with mouse
gif edit
```

---

### Multiple widgets

```fish
gif chika -always
gif miku -always
gif anya -always

gif edit
# move all at once
gif edit
```

---

### Check status

```fish
gif list
gif status chika
```

---

## 🐛 Troubleshooting

### Script does not start

```bash
python3 ~/Scripts/gif-script.py run ~/Scripts/chika.gif
```

---

### Nothing happens on `gif edit`

```fish
gif list
```

Make sure widgets are running.

---

### Reset everything

```bash
gif kill-all
rm -rf /tmp/gif-widget-$USER
rm ~/.config/gif-widget/state.json
```

---


Enjoy ✨
