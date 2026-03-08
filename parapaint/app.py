from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional, Sequence, Set, Tuple

from .editor import BRUSH_SHAPES, DEFAULT_PALETTE, PixelDocument, ZOOM_LEVELS
from .oklab import oklch_to_rgb, rgb_to_hex, rgb_to_oklch
from .settings import load_settings

Color = Tuple[int, int, int, int]
Point = Tuple[int, int]
TOOLS = [
    ("brush", "1 Brush"),
    ("fill", "2 Fill"),
    ("replace", "3 Replace"),
    ("line", "4 Line"),
    ("magic", "5 Magic"),
    ("rect", "Rect"),
    ("ellipse", "Ellipse"),
    ("picker", "Picker"),
    ("select", "Select"),
    ("move", "Move"),
    ("zoom", "Zoom"),
]
THEMES = {
    "Classic Dark": {
        "bg": "#1b1f24",
        "panel": "#232933",
        "accent": "#f4a261",
        "text": "#edf2f4",
        "button_bg": "#34404f",
        "button_text": "#ffffff",
        "button_selected_bg": "#465466",
        "muted": "#5c6773",
        "canvas": "#0f1318",
    },
    "Paper Mint": {
        "bg": "#dfe7da",
        "panel": "#f8f5ef",
        "accent": "#2a9d8f",
        "text": "#1f2933",
        "button_bg": "#d6e2da",
        "button_text": "#102027",
        "button_selected_bg": "#bfd4cc",
        "muted": "#a9b4b0",
        "canvas": "#cbd5c0",
    },
    "Amber Grid": {
        "bg": "#221d18",
        "panel": "#33291f",
        "accent": "#ffb703",
        "text": "#fff4d6",
        "button_bg": "#4a3827",
        "button_text": "#fff8e7",
        "button_selected_bg": "#634b33",
        "muted": "#7d6652",
        "canvas": "#17120e",
    },
}


class ParaPaintApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings(Path(__file__).resolve().parent.parent)
        self.title("ParaPaint")
        self.geometry("1480x920")
        self.minsize(1120, 720)
        self.option_add("*Font", "TkDefaultFont 10")

        self.theme_name = tk.StringVar(value=self.settings.get("theme", "Classic Dark"))
        self.doc = PixelDocument(32, 32)
        self.primary_color: Color = (255, 255, 255, 255)
        self.secondary_color: Color = (0, 0, 0, 255)
        self.current_tool = tk.StringVar(value="brush")
        self.brush_shape = tk.StringVar(value="Point")
        self.zoom_percent = tk.IntVar(value=800)
        self.show_grid = tk.BooleanVar(value=True)
        self.show_ui = True
        self.offset_x = 120
        self.offset_y = 90
        self.pixel_scale = 8
        self.drag_start: Optional[Point] = None
        self.drag_last: Optional[Point] = None
        self.preview_points: List[Point] = []
        self.selection_anchor: Optional[Point] = None
        self.moving_selection = False
        self.pan_anchor: Optional[Tuple[int, int]] = None
        self.live_mode = tk.StringVar(value="oklab")
        self.oklab_values = [tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()]
        self.rgb_values = [tk.IntVar(), tk.IntVar(), tk.IntVar()]
        self._color_update_lock = False
        self._palette_signature: Tuple[Color, ...] = ()
        self._layer_signature: Tuple[Tuple[str, bool], ...] = ()
        self.status_text = tk.StringVar(value="Ready")

        self._apply_theme()
        self._build_ui()
        self._bind_shortcuts()
        self._set_primary_color((255, 255, 255))
        self._refresh_everything()
        self.after(15000, self._autosave_tick)

    def _apply_theme(self) -> None:
        self.theme = THEMES[self.theme_name.get()]
        self.configure(bg=self.theme["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.theme["panel"])
        style.configure("TLabelframe", background=self.theme["panel"], foreground=self.theme["text"])
        style.configure("TLabelframe.Label", background=self.theme["panel"], foreground=self.theme["text"])
        style.configure("TLabel", background=self.theme["panel"], foreground=self.theme["text"])
        style.configure("TButton", background=self.theme["button_bg"], foreground=self.theme["button_text"], borderwidth=0)
        style.map("TButton", background=[("active", self.theme["accent"])], foreground=[("active", "#000000")])
        style.configure("TCombobox", fieldbackground=self.theme["panel"], background=self.theme["panel"], foreground=self.theme["text"])
        style.configure("TScale", background=self.theme["panel"])

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.left_panel = tk.Frame(self, bg=self.theme["panel"], width=240)
        self.left_panel.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)
        self.left_panel.grid_propagate(False)

        self.center_panel = tk.Frame(self, bg=self.theme["bg"])
        self.center_panel.grid(row=0, column=1, sticky="nsew", pady=12)
        self.center_panel.rowconfigure(0, weight=1)
        self.center_panel.columnconfigure(0, weight=1)

        self.right_panel = tk.Frame(self, bg=self.theme["panel"], width=310)
        self.right_panel.grid(row=0, column=2, sticky="nse", padx=(6, 12), pady=12)
        self.right_panel.grid_propagate(False)

        self._build_left_panel()
        self._build_canvas()
        self._build_right_panel()
        self._build_statusbar()

    def _build_left_panel(self) -> None:
        header = tk.Label(self.left_panel, text="ParaPaint", bg=self.theme["panel"], fg=self.theme["accent"], font=("TkDefaultFont", 18, "bold"))
        header.pack(anchor="w", padx=12, pady=(12, 10))

        tool_frame = tk.LabelFrame(self.left_panel, text="Tools", bg=self.theme["panel"], fg=self.theme["text"])
        tool_frame.pack(fill="x", padx=10, pady=6)
        for index, (tool, label) in enumerate(TOOLS):
            button = tk.Radiobutton(
                tool_frame,
                text=label,
                indicatoron=False,
                value=tool,
                variable=self.current_tool,
                command=self._update_status,
                bg=self.theme["button_bg"],
                fg=self.theme["button_text"],
                activebackground=self.theme["button_selected_bg"],
                activeforeground=self.theme["button_text"],
                selectcolor=self.theme["button_selected_bg"],
                width=14,
                anchor="w",
                font=("TkDefaultFont", 10, "bold"),
                relief="raised",
                offrelief="flat",
                borderwidth=2,
            )
            button.grid(row=index // 2, column=index % 2, padx=4, pady=4, sticky="ew")

        brush_frame = tk.LabelFrame(self.left_panel, text="Brush", bg=self.theme["panel"], fg=self.theme["text"])
        brush_frame.pack(fill="x", padx=10, pady=6)
        tk.Label(brush_frame, text="Shape", bg=self.theme["panel"], fg=self.theme["text"]).pack(anchor="w", padx=8, pady=(8, 2))
        ttk.Combobox(brush_frame, values=list(BRUSH_SHAPES.keys()), state="readonly", textvariable=self.brush_shape).pack(fill="x", padx=8, pady=(0, 8))

        view_frame = tk.LabelFrame(self.left_panel, text="View", bg=self.theme["panel"], fg=self.theme["text"])
        view_frame.pack(fill="x", padx=10, pady=6)
        tk.Checkbutton(
            view_frame,
            text="Show Grid (G)",
            variable=self.show_grid,
            command=self._refresh_grid_visibility,
            bg=self.theme["panel"],
            fg=self.theme["text"],
            activebackground=self.theme["panel"],
            activeforeground=self.theme["text"],
            selectcolor=self.theme["button_bg"],
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=8)

        theme_frame = tk.LabelFrame(self.left_panel, text="Theme", bg=self.theme["panel"], fg=self.theme["text"])
        theme_frame.pack(fill="x", padx=10, pady=6)
        ttk.Combobox(theme_frame, values=list(THEMES.keys()), state="readonly", textvariable=self.theme_name).pack(fill="x", padx=8, pady=8)
        tk.Button(theme_frame, text="Apply Theme", command=self._rebuild_with_theme, bg=self.theme["accent"], fg="#000000", relief="flat", font=("TkDefaultFont", 10, "bold")).pack(fill="x", padx=8, pady=(0, 8))

        file_frame = tk.LabelFrame(self.left_panel, text="Document", bg=self.theme["panel"], fg=self.theme["text"])
        file_frame.pack(fill="x", padx=10, pady=6)
        buttons = [
            ("New", self._new_canvas),
            ("Open PNG", self._open_png),
            ("Save PNG", self._save_png),
            ("Resize", self._resize_canvas_dialog),
            ("Crop To Selection", self._crop_to_selection),
            ("Swap Colors", self._swap_colors),
        ]
        for text, command in buttons:
            tk.Button(file_frame, text=text, command=command, bg=self.theme["button_bg"], fg=self.theme["button_text"], activebackground=self.theme["accent"], activeforeground="#000000", relief="groove", font=("TkDefaultFont", 10, "bold")).pack(fill="x", padx=8, pady=3)

    def _build_canvas(self) -> None:
        self.canvas = tk.Canvas(self.center_panel, bg=self.theme["canvas"], highlightthickness=0, cursor="crosshair")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_left_down)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_up)
        self.canvas.bind("<Button-2>", self._start_pan)
        self.canvas.bind("<B2-Motion>", self._do_pan)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Configure>", lambda _event: self._redraw_canvas())

    def _build_right_panel(self) -> None:
        color_frame = tk.LabelFrame(self.right_panel, text="Colors", bg=self.theme["panel"], fg=self.theme["text"])
        color_frame.pack(fill="x", padx=10, pady=8)

        swatch_row = tk.Frame(color_frame, bg=self.theme["panel"])
        swatch_row.pack(fill="x", padx=8, pady=8)
        self.primary_swatch = tk.Canvas(swatch_row, width=56, height=56, bg="#ffffff", highlightthickness=2, highlightbackground=self.theme["accent"])
        self.primary_swatch.pack(side="left")
        self.secondary_swatch = tk.Canvas(swatch_row, width=40, height=40, bg="#000000", highlightthickness=1, highlightbackground=self.theme["muted"])
        self.secondary_swatch.pack(side="left", padx=10, pady=10)
        tk.Button(swatch_row, text="X", command=self._swap_colors, bg=self.theme["accent"], fg="#000000", relief="flat", width=3, font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=6)

        mode_row = tk.Frame(color_frame, bg=self.theme["panel"])
        mode_row.pack(fill="x", padx=8, pady=(0, 8))
        tk.Radiobutton(mode_row, text="OKLAB", variable=self.live_mode, value="oklab", command=self._toggle_color_mode, bg=self.theme["button_bg"], fg=self.theme["button_text"], activebackground=self.theme["button_selected_bg"], activeforeground=self.theme["button_text"], selectcolor=self.theme["button_selected_bg"], font=("TkDefaultFont", 10, "bold"), relief="raised", offrelief="flat", borderwidth=2).pack(side="left")
        tk.Radiobutton(mode_row, text="RGB", variable=self.live_mode, value="rgb", command=self._toggle_color_mode, bg=self.theme["button_bg"], fg=self.theme["button_text"], activebackground=self.theme["button_selected_bg"], activeforeground=self.theme["button_text"], selectcolor=self.theme["button_selected_bg"], font=("TkDefaultFont", 10, "bold"), relief="raised", offrelief="flat", borderwidth=2).pack(side="left", padx=8)

        self.slider_host = tk.Frame(color_frame, bg=self.theme["panel"])
        self.slider_host.pack(fill="x", padx=8, pady=(0, 8))
        self._build_color_sliders()

        palette_frame = tk.LabelFrame(self.right_panel, text="Palette", bg=self.theme["panel"], fg=self.theme["text"])
        palette_frame.pack(fill="x", padx=10, pady=8)
        self.palette_grid = tk.Frame(palette_frame, bg=self.theme["panel"])
        self.palette_grid.pack(fill="x", padx=8, pady=8)
        self._render_palette(DEFAULT_PALETTE)

        layer_frame = tk.LabelFrame(self.right_panel, text="Layers", bg=self.theme["panel"], fg=self.theme["text"])
        layer_frame.pack(fill="both", expand=True, padx=10, pady=8)
        list_row = tk.Frame(layer_frame, bg=self.theme["panel"])
        list_row.pack(fill="both", expand=True, padx=8, pady=8)
        self.layer_list = tk.Listbox(list_row, activestyle="none", bg=self.theme["bg"], fg=self.theme["text"], selectbackground=self.theme["accent"], selectforeground="#000000", height=10)
        self.layer_list.pack(fill="both", expand=True, side="left")
        self.layer_list.bind("<<ListboxSelect>>", self._on_select_layer)
        button_col = tk.Frame(list_row, bg=self.theme["panel"])
        button_col.pack(side="left", fill="y", padx=(8, 0))
        for text, command in [
            ("Add", self._add_layer),
            ("Hide/Show", self._toggle_layer),
            ("Up", lambda: self._move_layer(-1)),
            ("Down", lambda: self._move_layer(1)),
        ]:
            tk.Button(button_col, text=text, command=command, bg=self.theme["button_bg"], fg=self.theme["button_text"], activebackground=self.theme["accent"], activeforeground="#000000", relief="groove", font=("TkDefaultFont", 10, "bold")).pack(fill="x", pady=2)

        preview_frame = tk.LabelFrame(self.right_panel, text="Preview", bg=self.theme["panel"], fg=self.theme["text"])
        preview_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.preview_canvas = tk.Canvas(preview_frame, width=180, height=180, bg=self.theme["canvas"], highlightthickness=0)
        self.preview_canvas.pack(fill="x", padx=8, pady=8)

    def _build_color_sliders(self) -> None:
        for child in self.slider_host.winfo_children():
            child.destroy()
        if self.live_mode.get() == "oklab":
            labels = [("H", 0.0, 360.0, 1.0), ("S", 0.0, 0.4, 0.005), ("L", 0.0, 1.0, 0.01)]
            vars_ = self.oklab_values
            callback = self._apply_oklab_sliders
        else:
            labels = [("R", 0, 255, 1), ("G", 0, 255, 1), ("B", 0, 255, 1)]
            vars_ = self.rgb_values
            callback = self._apply_rgb_sliders
        for index, (label, low, high, resolution) in enumerate(labels):
            row = tk.Frame(self.slider_host, bg=self.theme["panel"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, width=3, bg=self.theme["panel"], fg=self.theme["text"]).pack(side="left")
            scale = tk.Scale(row, from_=low, to=high, orient="horizontal", resolution=resolution, command=lambda _value, cb=callback: cb(), bg=self.theme["panel"], fg=self.theme["text"], troughcolor=self.theme["muted"], highlightthickness=0)
            scale.configure(variable=vars_[index])
            scale.pack(side="left", fill="x", expand=True)

    def _bind_shortcuts(self) -> None:
        hotkeys = self.settings["hotkeys"]
        self.bind(f"<Key-{hotkeys['tool_brush']}>", lambda _e: self._set_tool("brush"))
        self.bind(f"<Key-{hotkeys['tool_fill']}>", lambda _e: self._set_tool("fill"))
        self.bind(f"<Key-{hotkeys['tool_replace']}>", lambda _e: self._set_tool("replace"))
        self.bind(f"<Key-{hotkeys['tool_line']}>", lambda _e: self._set_tool("line"))
        self.bind(f"<Key-{hotkeys['tool_magic']}>", lambda _e: self._set_tool("magic"))
        self.bind(f"<Key-{hotkeys['undo']}>", lambda _e: self._undo())
        self.bind(f"<Key-{hotkeys['redo']}>", lambda _e: self._redo())
        self.bind(f"<Key-{hotkeys['swap_colors']}>", lambda _e: self._swap_colors())
        self.bind(f"<Key-{hotkeys['zoom_in']}>", lambda _e: self._step_zoom(1))
        self.bind(f"<Key-{hotkeys['zoom_out']}>", lambda _e: self._step_zoom(-1))
        self.bind(f"<Key-{hotkeys['brush_prev']}>", lambda _e: self._cycle_brush(-1))
        self.bind(f"<Key-{hotkeys['brush_next']}>", lambda _e: self._cycle_brush(1))
        self.bind(f"<Key-{hotkeys['toggle_grid']}>", lambda _e: self._toggle_grid())
        self.bind("<Delete>", lambda _e: self._delete_selection())
        self.bind("<Control-c>", lambda _e: self._copy_selection())
        self.bind("<Control-v>", lambda _e: self._paste_selection())
        self.bind("<Control-a>", lambda _e: self._select_all())
        self.bind("<Control-d>", lambda _e: self._clear_selection())
        self.bind(f"<Key-{hotkeys['crop_selection']}>", lambda _e: self._crop_to_selection())
        self.bind("<Shift-K>", lambda _e: self._resize_canvas_dialog())
        self.bind("<Tab>", self._toggle_ui)
        self.bind_all("<ButtonRelease-1>", self._on_global_left_up, add="+")

    def _refresh_everything(self) -> None:
        self._refresh_layer_list()
        self._redraw_canvas()
        self._render_preview()
        self._render_palette(self._palette_from_doc())
        self._update_color_swatches()
        self._update_status()

    def _rebuild_with_theme(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self._apply_theme()
        self._build_ui()
        self._bind_shortcuts()
        self._refresh_everything()

    def _set_primary_color(self, rgb: Tuple[int, int, int]) -> None:
        self._color_update_lock = True
        self.primary_color = (rgb[0], rgb[1], rgb[2], 255)
        l, chroma, hue = rgb_to_oklch(rgb)
        self.oklab_values[0].set(round(hue, 1))
        self.oklab_values[1].set(round(chroma, 3))
        self.oklab_values[2].set(round(l, 3))
        self.rgb_values[0].set(rgb[0])
        self.rgb_values[1].set(rgb[1])
        self.rgb_values[2].set(rgb[2])
        self._color_update_lock = False
        self._update_color_swatches()

    def _update_color_swatches(self) -> None:
        self.primary_swatch.configure(bg=rgb_to_hex(self.primary_color[:3]))
        self.secondary_swatch.configure(bg=rgb_to_hex(self.secondary_color[:3]))

    def _toggle_color_mode(self) -> None:
        self._build_color_sliders()

    def _apply_oklab_sliders(self) -> None:
        if self._color_update_lock:
            return
        hue = self.oklab_values[0].get()
        chroma = self.oklab_values[1].get()
        lightness = self.oklab_values[2].get()
        rgb = oklch_to_rgb((lightness, chroma, hue))
        self._set_primary_color(rgb)

    def _apply_rgb_sliders(self) -> None:
        if self._color_update_lock:
            return
        rgb = (self.rgb_values[0].get(), self.rgb_values[1].get(), self.rgb_values[2].get())
        self._set_primary_color(rgb)

    def _render_palette(self, colors: Sequence[Color]) -> None:
        visible_colors = tuple(colors[:24])
        if visible_colors == self._palette_signature and self.palette_grid.winfo_children():
            return
        for child in self.palette_grid.winfo_children():
            child.destroy()
        for index, color in enumerate(visible_colors):
            swatch = tk.Canvas(self.palette_grid, width=26, height=26, bg=rgb_to_hex(color[:3]), highlightthickness=1, highlightbackground=self.theme["muted"])
            swatch.grid(row=index // 6, column=index % 6, padx=2, pady=2)
            swatch.bind("<Button-1>", lambda _e, rgb=color[:3]: self._set_primary_color(rgb))
            swatch.bind("<Button-3>", lambda _e, rgb=color[:3]: self._set_secondary_color(rgb))
        self._palette_signature = visible_colors

    def _set_secondary_color(self, rgb: Tuple[int, int, int]) -> None:
        self.secondary_color = (rgb[0], rgb[1], rgb[2], 255)
        self._update_color_swatches()

    def _palette_from_doc(self) -> Sequence[Color]:
        colors = list(DEFAULT_PALETTE)
        for color in self.doc.colors_on_canvas():
            if color not in colors:
                colors.append(color)
        return colors

    def _add_layer(self) -> None:
        self.doc.commit_history()
        self.doc.add_layer()
        self._refresh_everything()

    def _toggle_layer(self) -> None:
        selection = self.layer_list.curselection()
        if not selection:
            return
        self.doc.commit_history()
        self.doc.toggle_layer_visibility(selection[0])
        self._refresh_everything()

    def _move_layer(self, direction: int) -> None:
        selection = self.layer_list.curselection()
        if not selection:
            return
        old_index = selection[0]
        new_index = max(0, min(len(self.doc.layers) - 1, old_index + direction))
        if old_index == new_index:
            return
        self.doc.commit_history()
        self.doc.move_layer(old_index, new_index)
        self._refresh_everything()
        self.layer_list.selection_set(new_index)

    def _on_select_layer(self, _event=None) -> None:
        selection = self.layer_list.curselection()
        if selection:
            self.doc.set_active_layer(selection[0])
            self._redraw_canvas()

    def _refresh_layer_list(self) -> None:
        signature = tuple((layer.name, layer.visible) for layer in self.doc.layers)
        current_selection = self.layer_list.curselection()
        selected_index = current_selection[0] if current_selection else None
        if signature != self._layer_signature:
            self.layer_list.delete(0, tk.END)
            for layer in self.doc.layers:
                prefix = "[x]" if layer.visible else "[ ]"
                self.layer_list.insert(tk.END, f"{prefix} {layer.name}")
            self._layer_signature = signature
        if selected_index != self.doc.active_layer:
            self.layer_list.selection_clear(0, tk.END)
            self.layer_list.selection_set(self.doc.active_layer)

    def _canvas_point(self, event) -> Optional[Point]:
        x = int((self.canvas.canvasx(event.x) - self.offset_x) / self.pixel_scale)
        y = int((self.canvas.canvasy(event.y) - self.offset_y) / self.pixel_scale)
        if 0 <= x < self.doc.width and 0 <= y < self.doc.height:
            return x, y
        return None

    def _canvas_point_from_root(self, x_root: int, y_root: int) -> Optional[Point]:
        local_x = x_root - self.canvas.winfo_rootx()
        local_y = y_root - self.canvas.winfo_rooty()
        x = int((local_x - self.offset_x) / self.pixel_scale)
        y = int((local_y - self.offset_y) / self.pixel_scale)
        if 0 <= x < self.doc.width and 0 <= y < self.doc.height:
            return x, y
        return None

    def _tool_color(self, event=None) -> Color:
        if event is not None and (event.state & 0x0100):
            return self.secondary_color
        return self.primary_color

    def _on_left_down(self, event) -> None:
        point = self._canvas_point(event)
        if point is None:
            return
        self.focus_set()
        self.drag_start = point
        self.drag_last = point
        tool = self.current_tool.get()
        if tool == "brush":
            self.doc.commit_history()
            self._paint_brush(point, self._tool_color(event))
        elif tool in {"fill", "replace", "picker", "magic", "select"}:
            self._apply_click_tool(point, event)
        elif tool == "zoom":
            if event.state & 0x0004:
                self.zoom_percent.set(100)
            else:
                self._step_zoom(1)
        elif tool == "move":
            self.pan_anchor = (event.x, event.y)
        else:
            self.preview_points = []
            self._redraw_canvas()

    def _on_left_drag(self, event) -> None:
        point = self._canvas_point(event)
        if point is None or self.drag_start is None:
            return
        self.drag_last = point
        tool = self.current_tool.get()
        if tool == "brush":
            self._paint_along(self.drag_start, point, self._tool_color(event))
            self.drag_start = point
        elif tool in {"line", "rect", "ellipse", "select"}:
            self.preview_points = self._preview_shape(self.drag_start, point)
            self._redraw_canvas()
        elif tool == "move" and self.pan_anchor:
            dx = event.x - self.pan_anchor[0]
            dy = event.y - self.pan_anchor[1]
            self.offset_x += dx
            self.offset_y += dy
            self.pan_anchor = (event.x, event.y)
            self._redraw_canvas()

    def _on_left_up(self, event) -> None:
        point = self._canvas_point(event)
        self._finish_left_interaction(point, event)

    def _on_global_left_up(self, event) -> None:
        if self.drag_start is None and self.pan_anchor is None:
            return
        point = self._canvas_point_from_root(event.x_root, event.y_root)
        self._finish_left_interaction(point, event)

    def _finish_left_interaction(self, point: Optional[Point], event) -> None:
        if self.drag_start is None:
            self.pan_anchor = None
            return
        if point is None:
            point = self.drag_last
        if point is None:
            self.preview_points = []
            self.drag_start = None
            self.drag_last = None
            self.pan_anchor = None
            self._refresh_everything()
            return
        tool = self.current_tool.get()
        if tool in {"line", "rect", "ellipse"}:
            self.doc.commit_history()
            points = self._preview_shape(self.drag_start, point)
            self.doc.apply_points(self._apply_brush_shape(points), self._tool_color(event))
        elif tool == "select":
            mode = self._selection_mode(event)
            points = set(self.doc.select_rect(self.drag_start, point))
            self.doc.commit_history()
            self.doc.update_selection(points, mode=mode)
        self.preview_points = []
        self.drag_start = None
        self.drag_last = None
        self.pan_anchor = None
        self._refresh_everything()

    def _on_right_click(self, event) -> None:
        point = self._canvas_point(event)
        if point is None:
            self.doc.clear_selection()
            self._refresh_everything()
            return
        self._pick_color(point, secondary=True)

    def _on_mousewheel(self, event) -> None:
        if event.state & 0x0001:
            self.offset_x += 24 if event.delta > 0 else -24
        else:
            self.offset_y += 24 if event.delta > 0 else -24
        self._redraw_canvas()

    def _start_pan(self, event) -> None:
        self.pan_anchor = (event.x, event.y)

    def _do_pan(self, event) -> None:
        if not self.pan_anchor:
            return
        dx = event.x - self.pan_anchor[0]
        dy = event.y - self.pan_anchor[1]
        self.offset_x += dx
        self.offset_y += dy
        self.pan_anchor = (event.x, event.y)
        self._redraw_canvas()

    def _on_motion(self, event) -> None:
        point = self._canvas_point(event)
        if point is None:
            self.status_text.set(f"{self.current_tool.get()} | zoom {self.zoom_percent.get()}%")
        else:
            self.status_text.set(f"{self.current_tool.get()} | x={point[0]} y={point[1]} | zoom {self.zoom_percent.get()}%")

    def _selection_mode(self, event) -> str:
        shift = bool(event.state & 0x0001)
        alt = bool(event.state & 0x0008)
        if shift:
            return "add"
        if alt:
            return "subtract"
        return "replace"

    def _apply_click_tool(self, point: Point, event) -> None:
        tool = self.current_tool.get()
        if tool == "fill":
            self.doc.commit_history()
            self.doc.apply_points(self.doc.flood_fill(point, self._tool_color(event)), self._tool_color(event))
        elif tool == "replace":
            target = self.doc.get_pixel(*point)
            self.doc.commit_history()
            points = [(x, y) for y in range(self.doc.height) for x in range(self.doc.width) if self.doc.get_pixel(x, y) == target]
            self.doc.apply_points(points, self._tool_color(event))
        elif tool == "picker":
            self._pick_color(point)
        elif tool == "magic":
            mode = self._selection_mode(event)
            color = self.doc.merged_pixel(*point)
            self.doc.commit_history()
            self.doc.update_selection(self.doc.contiguous_same_color(point, color), mode=mode)
        elif tool == "select":
            self.doc.commit_history()
            self.doc.update_selection({point}, mode=self._selection_mode(event))
        self._refresh_everything()

    def _pick_color(self, point: Point, secondary: bool = False) -> None:
        color = self.doc.merged_pixel(*point)
        if color[3] == 0:
            color = (255, 255, 255, 255)
        if secondary:
            self._set_secondary_color(color[:3])
        else:
            self._set_primary_color(color[:3])
        self._refresh_everything()

    def _paint_brush(self, point: Point, color: Color) -> None:
        self.doc.apply_points(self._brush_points(point), color)
        self._refresh_everything()

    def _paint_along(self, start: Point, end: Point, color: Color) -> None:
        points = self.doc.draw_line(start, end)
        self.doc.apply_points(self._apply_brush_shape(points), color)
        self._refresh_everything()

    def _brush_points(self, point: Point) -> List[Point]:
        return self._apply_brush_shape([point])

    def _apply_brush_shape(self, points: Sequence[Point]) -> List[Point]:
        shaped: Set[Point] = set()
        offsets = BRUSH_SHAPES[self.brush_shape.get()]
        for x, y in points:
            for dx, dy in offsets:
                shaped.add((x + dx, y + dy))
        return list(shaped)

    def _preview_shape(self, start: Point, end: Point) -> List[Point]:
        tool = self.current_tool.get()
        if tool == "line":
            return self.doc.draw_line(start, end)
        if tool == "rect":
            return self.doc.draw_rect(start, end)
        if tool == "ellipse":
            return self.doc.draw_ellipse(start, end)
        if tool == "select":
            return list(self.doc.select_rect(start, end))
        return []

    def _redraw_canvas(self) -> None:
        self.pixel_scale = max(2, self.zoom_percent.get() // 100)
        self.canvas.delete("all")
        width_px = self.doc.width * self.pixel_scale
        height_px = self.doc.height * self.pixel_scale
        self.canvas.create_rectangle(self.offset_x - 1, self.offset_y - 1, self.offset_x + width_px + 1, self.offset_y + height_px + 1, outline=self.theme["muted"], fill="#ffffff")

        for y in range(self.doc.height):
            for x in range(self.doc.width):
                color = self.doc.merged_pixel(x, y)
                if color[3] == 0:
                    fill = "#ffffff" if (x + y) % 2 == 0 else "#ececec"
                else:
                    fill = rgb_to_hex(color[:3])
                x1 = self.offset_x + x * self.pixel_scale
                y1 = self.offset_y + y * self.pixel_scale
                self.canvas.create_rectangle(x1, y1, x1 + self.pixel_scale, y1 + self.pixel_scale, outline=fill, fill=fill)

        if self.show_grid.get() and self.pixel_scale >= 8:
            for x in range(self.doc.width + 1):
                xpos = self.offset_x + x * self.pixel_scale
                self.canvas.create_line(xpos, self.offset_y, xpos, self.offset_y + height_px, fill=self.theme["muted"])
            for y in range(self.doc.height + 1):
                ypos = self.offset_y + y * self.pixel_scale
                self.canvas.create_line(self.offset_x, ypos, self.offset_x + width_px, ypos, fill=self.theme["muted"])

        for x, y in self.doc.selection:
            x1 = self.offset_x + x * self.pixel_scale
            y1 = self.offset_y + y * self.pixel_scale
            self.canvas.create_rectangle(x1, y1, x1 + self.pixel_scale, y1 + self.pixel_scale, outline=self.theme["accent"], width=2)

        for x, y in self.preview_points:
            if 0 <= x < self.doc.width and 0 <= y < self.doc.height:
                x1 = self.offset_x + x * self.pixel_scale
                y1 = self.offset_y + y * self.pixel_scale
                self.canvas.create_rectangle(x1, y1, x1 + self.pixel_scale, y1 + self.pixel_scale, outline=self.theme["accent"], width=2)

    def _render_preview(self) -> None:
        self.preview_canvas.delete("all")
        if self.doc.width == 0 or self.doc.height == 0:
            return
        scale = min(160 / max(self.doc.width, 1), 160 / max(self.doc.height, 1))
        size = max(2, int(scale))
        origin_x = (180 - self.doc.width * size) / 2
        origin_y = (180 - self.doc.height * size) / 2
        for y in range(self.doc.height):
            for x in range(self.doc.width):
                color = self.doc.merged_pixel(x, y)
                fill = rgb_to_hex(color[:3]) if color[3] > 0 else self.theme["canvas"]
                x1 = origin_x + x * size
                y1 = origin_y + y * size
                self.preview_canvas.create_rectangle(x1, y1, x1 + size, y1 + size, outline=fill, fill=fill)

    def _update_status(self) -> None:
        grid_state = "grid on" if self.show_grid.get() else "grid off"
        self.status_text.set(f"{self.current_tool.get()} | zoom {self.zoom_percent.get()}% | {grid_state} | undo {len(self.doc.undo_stack)} | redo {len(self.doc.redo_stack)}")

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=self.theme["panel"], height=30)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        tk.Label(bar, textvariable=self.status_text, bg=self.theme["panel"], fg=self.theme["text"], anchor="w").pack(fill="x", padx=8, pady=4)

    def _step_zoom(self, direction: int) -> None:
        levels = ZOOM_LEVELS
        current = self.zoom_percent.get()
        try:
            index = levels.index(current)
        except ValueError:
            index = levels.index(100)
        index = max(0, min(len(levels) - 1, index + direction))
        self.zoom_percent.set(levels[index])
        self._redraw_canvas()
        self._update_status()

    def _refresh_grid_visibility(self) -> None:
        self._redraw_canvas()
        self._update_status()

    def _toggle_grid(self) -> None:
        self.show_grid.set(not self.show_grid.get())
        self._refresh_grid_visibility()

    def _cycle_brush(self, direction: int) -> None:
        shapes = list(BRUSH_SHAPES.keys())
        index = shapes.index(self.brush_shape.get())
        self.brush_shape.set(shapes[(index + direction) % len(shapes)])
        self._update_status()

    def _set_tool(self, tool: str) -> None:
        self.current_tool.set(tool)
        self._update_status()

    def _swap_colors(self) -> None:
        self.primary_color, self.secondary_color = self.secondary_color, self.primary_color
        self._set_primary_color(self.primary_color[:3])
        self._set_secondary_color(self.secondary_color[:3])

    def _delete_selection(self) -> None:
        if not self.doc.selection:
            return
        self.doc.commit_history()
        self.doc.delete_selection()
        self._refresh_everything()

    def _select_all(self) -> None:
        self.doc.commit_history()
        self.doc.update_selection({(x, y) for y in range(self.doc.height) for x in range(self.doc.width)})
        self._refresh_everything()

    def _clear_selection(self) -> None:
        self.doc.commit_history()
        self.doc.clear_selection()
        self._refresh_everything()

    def _copy_selection(self) -> None:
        points = self.doc.selection or {(x, y) for y in range(self.doc.height) for x in range(self.doc.width)}
        if not points:
            return
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        left, top = min(xs), min(ys)
        right, bottom = max(xs), max(ys)
        payload = []
        for y in range(top, bottom + 1):
            row = []
            for x in range(left, right + 1):
                row.append(self.doc.get_pixel(x, y))
            payload.append(row)
        self.clipboard_data = (left, top, payload)
        self.status_text.set("Copied selection")

    def _paste_selection(self) -> None:
        if not hasattr(self, "clipboard_data"):
            return
        _, _, payload = self.clipboard_data
        self.doc.commit_history()
        for y, row in enumerate(payload):
            for x, color in enumerate(row):
                if color[3] > 0:
                    self.doc.set_pixel(x, y, color)
        self._refresh_everything()

    def _crop_to_selection(self) -> None:
        if not self.doc.selection:
            return
        self.doc.commit_history()
        self.doc.crop_to_selection()
        self.offset_x = 120
        self.offset_y = 90
        self._refresh_everything()

    def _resize_canvas_dialog(self) -> None:
        width = simpledialog.askinteger("Resize canvas", "Width", initialvalue=self.doc.width, minvalue=1, parent=self)
        if width is None:
            return
        height = simpledialog.askinteger("Resize canvas", "Height", initialvalue=self.doc.height, minvalue=1, parent=self)
        if height is None:
            return
        self.doc.commit_history()
        self.doc.resize_canvas(width, height)
        self._refresh_everything()

    def _maybe_save_before_destructive(self) -> bool:
        if not self.doc.dirty:
            return True
        result = messagebox.askyesnocancel("Unsaved changes", "Save current canvas before continuing?")
        if result is None:
            return False
        if result:
            return self._save_png()
        return True

    def _new_canvas(self) -> None:
        if not self._maybe_save_before_destructive():
            return
        width = simpledialog.askinteger("New canvas", "Width", initialvalue=32, minvalue=1, parent=self)
        if width is None:
            return
        height = simpledialog.askinteger("New canvas", "Height", initialvalue=32, minvalue=1, parent=self)
        if height is None:
            return
        self.doc = PixelDocument(width, height)
        self.offset_x = 120
        self.offset_y = 90
        self._refresh_everything()

    def _save_png(self) -> bool:
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not path:
            return False
        image = tk.PhotoImage(width=self.doc.width, height=self.doc.height)
        self.doc.export_to_photoimage(image)
        image.write(path, format="png")
        self.doc.file_path = path
        self.doc.dirty = False
        self.status_text.set(f"Saved {path}")
        return True

    def _open_png(self) -> None:
        if not self._maybe_save_before_destructive():
            return
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.gif *.ppm *.pgm")])
        if not path:
            return
        image = tk.PhotoImage(file=path)
        self.doc = PixelDocument(image.width(), image.height())
        self.doc.import_from_photoimage(image)
        self.doc.file_path = path
        self.offset_x = 120
        self.offset_y = 90
        self._refresh_everything()

    def _undo(self) -> None:
        if self.doc.undo():
            self._refresh_everything()

    def _redo(self) -> None:
        if self.doc.redo():
            self._refresh_everything()

    def _toggle_ui(self, event=None) -> str:
        self.show_ui = not self.show_ui
        if self.show_ui:
            self.left_panel.grid()
            self.right_panel.grid()
        else:
            self.left_panel.grid_remove()
            self.right_panel.grid_remove()
        return "break"

    def _autosave_tick(self) -> None:
        if self.doc.dirty:
            path = self.doc.autosave()
            self.status_text.set(f"Autosaved to {path}")
        self.after(15000, self._autosave_tick)


def run() -> None:
    app = ParaPaintApp()
    app.mainloop()
