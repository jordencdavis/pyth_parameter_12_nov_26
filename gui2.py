#!/usr/bin/env python3
"""
DYNAMIC JSON GENERATOR ENGINE (GUI2) — v2.0
============================================
• 100% Data-Driven / Configuration-Driven Architecture
• Split Screen Layout:
  - Left Pane: Dynamic Tab JSON Selector Details (fields, checkboxes, spinboxes, dropdowns)
  - Right Pane: Scrollable Windows Canvas for each tab (window1, window2, window3, etc.)
• Real-time Live JSON Preview Pop-up Window
• Bidirectional WebSocket IPC with GUI1 (note_tool.py)
• Per-window targeted generation (e.g. window1, window2...) and Batch "All Windows" generation
• Clean White Theme (#ffffff, #f8fafc, #f1f5f9, #2563eb)
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import sys
import json
import glob
import time
import argparse
from datetime import datetime
from typing import Dict, Any, Optional

from ipc_comm import WebSocketClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
#  WHITE THEME PALETTE
# ─────────────────────────────────────────────────────────────────────────────
THEME = {
    "bg_main":         "#f8fafc",
    "bg_card":         "#ffffff",
    "bg_header":       "#ffffff",
    "bg_tabbar":       "#f1f5f9",
    "bg_tab_active":   "#ffffff",
    "bg_tab_inactive": "#e2e8f0",
    "bg_input":        "#ffffff",
    "bg_preview":      "#f8fafc",
    "bg_win_active":   "#eff6ff",
    "border":          "#cbd5e1",
    "border_light":    "#e2e8f0",
    "border_active":   "#2563eb",
    "text_primary":    "#0f172a",
    "text_secondary":  "#475569",
    "text_muted":      "#94a3b8",
    "accent":          "#2563eb",
    "accent_hover":    "#1d4ed8",
    "accent_light":    "#eff6ff",
    "success":         "#16a34a",
    "success_light":   "#f0fdf4",
    "danger":          "#dc2626",
    "danger_light":    "#fef2f2",
    "font_family":     "Segoe UI" if os.name == "nt" else "DejaVu Sans",
    "font_mono":       "Consolas" if os.name == "nt" else "Monospace"
}

TOTAL_WINDOWS_PER_TAB = 7

def slugify(text: str) -> str:
    return text.lower().strip().replace(" ", "_").replace("-", "_")

class JSONDataGeneratorGUI2(tk.Tk):
    def __init__(self, port: int = 8765, initial_tab: Optional[str] = None, initial_window: int = 2, project_id: str = "Default_Project"):
        super().__init__()
        self.title("GUI2 — Dynamic JSON Data Generator & Window Canvas")
        self.geometry("1340x860")
        self.minsize(980, 620)
        self.configure(bg=THEME["bg_main"])

        self.port = port
        self.project_id = project_id
        self.current_request_id: Optional[str] = None
        self.selected_window_id: int = initial_window  # e.g. 2 for window2
        self.selected_tab_name: str = initial_tab or "VP Addresses"
        self.active_tab_slug: str = slugify(self.selected_tab_name)
        self.incoming_window_content: str = ""
        self.incoming_all_tabs: Dict[str, list] = {}

        # State storage: { tab_slug: { field_id: tk.Variable } }
        self.field_variables: Dict[str, Dict[str, Any]] = {}
        # Checkbox lists: { tab_slug: { field_id: { option_name: tk.BooleanVar } } }
        self.checkbox_variables: Dict[str, Dict[str, Dict[str, tk.BooleanVar]]] = {}

        # Per-tab, per-window generated JSON data storage: { tab_slug: { window_id: json_str } }
        self.window_data_store: Dict[str, Dict[int, str]] = {}
        # References to right-side window widgets: { tab_slug: { window_id: ScrolledText } }
        self.window_text_widgets: Dict[str, Dict[int, scrolledtext.ScrolledText]] = {}
        self.window_card_frames: Dict[str, Dict[int, tk.Frame]] = {}
        self.window_badge_labels: Dict[str, Dict[int, tk.Label]] = {}
        self.right_canvas: Optional[tk.Canvas] = None

        self.configs: Dict[str, Dict[str, Any]] = {}
        self.load_all_configurations()

        # Preview Popup Reference
        self.preview_window: Optional[tk.Toplevel] = None
        self.preview_text: Optional[scrolledtext.ScrolledText] = None

        # Build UI layout
        self._build_top_banner()
        self._build_tab_bar()
        self._build_container()
        self._build_bottom_bar()

        # Connect WebSocket to GUI1
        self.ws_client = WebSocketClient(host="127.0.0.1", port=self.port, on_message=self._on_ws_message)
        self._connect_to_gui1()

        # Render initial tab
        self.switch_tab(self.active_tab_slug)

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────────────────
    #  CONFIGURATION DISCOVERY
    # ─────────────────────────────────────────────────────────────────────────
    def load_all_configurations(self):
        """Discovers and parses all JSON files in config/."""
        self.configs.clear()
        config_files = glob.glob(os.path.join(CONFIG_DIR, "*.json"))
        for path in config_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    tab_id = cfg.get("tab_id") or slugify(cfg.get("tab_title", os.path.splitext(os.path.basename(path))[0]))
                    self.configs[tab_id] = cfg
            except Exception as e:
                print(f"[GUI2] Error loading {path}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    #  WEBSOCKET IPC
    # ─────────────────────────────────────────────────────────────────────────
    def _connect_to_gui1(self):
        connected = self.ws_client.connect(timeout=1.5)
        if connected:
            self.lbl_ws_status.config(text="🟢 Connected to GUI1", fg=THEME["success"])
            self.ws_client.send({
                "type": "GUI2_READY",
                "timestamp": datetime.now().isoformat()
            })
        else:
            self.lbl_ws_status.config(text="⚪ Standalone Mode (GUI1 offline)", fg=THEME["text_muted"])

    def _on_ws_message(self, data: dict):
        """Invoked when GUI1 sends a message."""
        msg_type = data.get("type")
        if msg_type == "GENERATE_REQUEST":
            self.after(0, self._handle_generate_request, data)

    def _handle_generate_request(self, req: dict):
        self.current_request_id = req.get("request_id", f"req_{int(time.time())}")
        self.project_id = req.get("project_id", self.project_id)
        tab_name = req.get("tab_name", "")
        self.selected_window_id = int(req.get("window_id", 1))
        self.incoming_window_content = req.get("window_content", "")
        self.incoming_all_tabs = req.get("all_tabs_data", {})

        tab_slug = slugify(tab_name)
        self.selected_tab_name = tab_name
        self.active_tab_slug = tab_slug

        # Store incoming window content if present
        if tab_slug not in self.window_data_store:
            self.window_data_store[tab_slug] = {}
        if self.incoming_window_content.strip():
            self.window_data_store[tab_slug][self.selected_window_id] = self.incoming_window_content

        self._update_banner()
        self.switch_tab(tab_slug)

        # Highlight and scroll to the requested window
        self.set_active_target_window(self.selected_window_id, scroll_to=True)

        self.lbl_status.config(
            text=f"📥 Received from GUI1: Tab '{tab_name}' -> window{self.selected_window_id}",
            fg=THEME["accent"]
        )
        self.update_live_preview()

    # ─────────────────────────────────────────────────────────────────────────
    #  UI CONSTRUCTION (WHITE THEME)
    # ─────────────────────────────────────────────────────────────────────────
    def _build_top_banner(self):
        banner = tk.Frame(self, bg=THEME["bg_header"], height=68, bd=0, highlightthickness=1, highlightbackground=THEME["border_light"])
        banner.pack(fill="x", side="top")
        banner.pack_propagate(False)

        # Left Info
        left_box = tk.Frame(banner, bg=THEME["bg_header"])
        left_box.pack(side="left", padx=20, pady=8)

        self.lbl_title = tk.Label(
            left_box, text="⚡ GUI2 — Dynamic JSON Generator & Window Canvas",
            font=(THEME["font_family"], 13, "bold"),
            bg=THEME["bg_header"], fg=THEME["text_primary"]
        )
        self.lbl_title.pack(anchor="w")

        self.lbl_context = tk.Label(
            left_box, text=f"Project: {self.project_id}  |  Active Tab: {self.selected_tab_name}  |  Target: window{self.selected_window_id}",
            font=(THEME["font_family"], 10),
            bg=THEME["bg_header"], fg=THEME["text_secondary"]
        )
        self.lbl_context.pack(anchor="w")

        # Right Info
        right_box = tk.Frame(banner, bg=THEME["bg_header"])
        right_box.pack(side="right", padx=20, pady=10)

        self.lbl_ws_status = tk.Label(
            right_box, text="Checking connection...",
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["bg_header"], fg=THEME["text_muted"]
        )
        self.lbl_ws_status.pack(anchor="e")

        btn_refresh = tk.Button(
            right_box, text="🔄 Reload Configs",
            font=(THEME["font_family"], 9),
            bg=THEME["bg_tabbar"], fg=THEME["text_primary"],
            relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
            command=self.reload_and_rebuild
        )
        btn_refresh.pack(anchor="e", pady=2)

    def _update_banner(self):
        self.lbl_context.config(
            text=f"Project: {self.project_id}  |  Active Tab: {self.selected_tab_name}  |  Target: window{self.selected_window_id}"
        )

    def _build_tab_bar(self):
        self.tab_bar_frame = tk.Frame(self, bg=THEME["bg_tabbar"], height=42)
        self.tab_bar_frame.pack(fill="x", side="top")
        self.tab_buttons: Dict[str, tk.Button] = {}
        self._populate_tab_buttons()

    def _populate_tab_buttons(self):
        for btn in self.tab_buttons.values():
            btn.destroy()
        self.tab_buttons.clear()

        display_slugs = list(self.configs.keys())
        if self.active_tab_slug and self.active_tab_slug not in display_slugs:
            display_slugs.append(self.active_tab_slug)

        for slug in display_slugs:
            cfg = self.configs.get(slug, {})
            title = cfg.get("tab_title", slug.replace("_", " ").title())
            btn = tk.Button(
                self.tab_bar_frame,
                text=title,
                font=(THEME["font_family"], 10, "bold"),
                relief="flat",
                bd=0,
                padx=16,
                pady=8,
                cursor="hand2",
                command=lambda s=slug: self.switch_tab(s)
            )
            btn.pack(side="left", padx=1, pady=0)
            self.tab_buttons[slug] = btn

    def _build_container(self):
        self.container = tk.Frame(self, bg=THEME["bg_main"])
        self.container.pack(fill="both", expand=True, padx=14, pady=10)
        self.active_form_frame: Optional[tk.Frame] = None

    def _build_bottom_bar(self):
        bottom = tk.Frame(self, bg=THEME["bg_card"], height=60, highlightthickness=1, highlightbackground=THEME["border_light"])
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        self.lbl_status = tk.Label(
            bottom, text="Ready. Choose parameters on the left; view/populate windows on the right canvas.",
            font=(THEME["font_family"], 10),
            bg=THEME["bg_card"], fg=THEME["text_secondary"]
        )
        self.lbl_status.pack(side="left", padx=20)

        btn_box = tk.Frame(bottom, bg=THEME["bg_card"])
        btn_box.pack(side="right", padx=16, pady=10)

        # Live Preview Button
        btn_preview = tk.Button(
            btn_box,
            text="🔍 Live JSON Preview (Pop-up)",
            font=(THEME["font_family"], 10, "bold"),
            bg=THEME["accent_light"],
            fg=THEME["accent"],
            activebackground="#dbeafe",
            activeforeground=THEME["accent"],
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self.open_live_preview_popup
        )
        btn_preview.pack(side="left", padx=6)

        # Generate & Send to Target Window
        self.btn_send_target = tk.Button(
            btn_box,
            text=f"💾 Send to window{self.selected_window_id}",
            font=(THEME["font_family"], 10, "bold"),
            bg=THEME["success"],
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=lambda: self.generate_and_send_target_window(self.selected_window_id)
        )
        self.btn_send_target.pack(side="left", padx=4)

        # Generate & Send ALL Windows
        btn_send_all = tk.Button(
            btn_box,
            text="⚡ Send ALL Windows (1-7)",
            font=(THEME["font_family"], 10, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self.generate_and_send_all_windows
        )
        btn_send_all.pack(side="left", padx=4)

    # ─────────────────────────────────────────────────────────────────────────
    #  TAB SWITCHING & TWO-COLUMN SPLIT LAYOUT
    # ─────────────────────────────────────────────────────────────────────────
    def switch_tab(self, tab_slug: str):
        self.active_tab_slug = tab_slug
        cfg = self.configs.get(tab_slug, {})
        self.selected_tab_name = cfg.get("tab_title", tab_slug.replace("_", " ").title())
        self._update_banner()

        # Update tab button highlight
        for slug, btn in self.tab_buttons.items():
            if slug == tab_slug:
                btn.configure(bg=THEME["bg_tab_active"], fg=THEME["accent"])
            else:
                btn.configure(bg=THEME["bg_tab_inactive"], fg=THEME["text_secondary"])

        # Reset active frame
        if self.active_form_frame:
            self.active_form_frame.destroy()

        self.active_form_frame = tk.Frame(self.container, bg=THEME["bg_main"])
        self.active_form_frame.pack(fill="both", expand=True)

        if tab_slug not in self.configs:
            self._render_failed_state(tab_slug)
        else:
            self._render_split_interface(tab_slug)

        self.update_live_preview()

    def _render_split_interface(self, tab_slug: str):
        """Renders the split layout: Left side (Selector details) + Right side (Windows Canvas)."""
        paned = tk.PanedWindow(self.active_form_frame, orient="horizontal", bg=THEME["bg_main"], bd=0, sashwidth=6, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        # ── LEFT PANE: Tab JSON Selector Details ─────────────────────────────
        left_pane = tk.Frame(paned, bg=THEME["bg_main"])
        paned.add(left_pane, minsize=420, width=470)

        self._render_left_selectors(left_pane, tab_slug)

        # ── RIGHT PANE: Canvas for each tab (window1, window2...) ─────────────
        right_pane = tk.Frame(paned, bg=THEME["bg_main"])
        paned.add(right_pane, minsize=480)

        self._render_right_windows_canvas(right_pane, tab_slug)

    # ─────────────────────────────────────────────────────────────────────────
    #  LEFT PANE: DYNAMIC JSON SELECTOR DETAILS
    # ─────────────────────────────────────────────────────────────────────────
    def _render_left_selectors(self, parent: tk.Frame, tab_slug: str):
        cfg = self.configs[tab_slug]
        fields = cfg.get("fields", [])

        # Header card on left
        hdr_card = tk.Frame(parent, bg=THEME["bg_card"], bd=0, highlightthickness=1, highlightbackground=THEME["border_light"])
        hdr_card.pack(fill="x", padx=(0, 6), pady=(0, 8))

        tk.Label(
            hdr_card, text=f"⚙️ {cfg.get('tab_title', tab_slug.title())} Configuration",
            font=(THEME["font_family"], 12, "bold"),
            bg=THEME["bg_card"], fg=THEME["text_primary"]
        ).pack(anchor="w", padx=14, pady=(10, 2))

        tk.Label(
            hdr_card, text=cfg.get("description", "Dynamic generation schema."),
            font=(THEME["font_family"], 9),
            bg=THEME["bg_card"], fg=THEME["text_secondary"]
        ).pack(anchor="w", padx=14, pady=(0, 10))

        # Scrollable form canvas for dynamic fields
        canvas = tk.Canvas(parent, bg=THEME["bg_main"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=THEME["bg_main"])

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        fields_card = tk.Frame(scrollable_frame, bg=THEME["bg_card"], bd=0, highlightthickness=1, highlightbackground=THEME["border_light"])
        fields_card.pack(fill="x", padx=(0, 6), pady=4)

        if tab_slug not in self.field_variables:
            self.field_variables[tab_slug] = {}
        if tab_slug not in self.checkbox_variables:
            self.checkbox_variables[tab_slug] = {}

        for idx, field in enumerate(fields):
            self._render_field(fields_card, tab_slug, field, row_idx=idx)

    def _render_field(self, parent: tk.Frame, tab_slug: str, field: dict, row_idx: int):
        field_id = field.get("id")
        field_type = field.get("type", "text")
        label_text = field.get("label", field_id.title())
        help_text = field.get("help", "")

        row = tk.Frame(parent, bg=THEME["bg_card"])
        row.pack(fill="x", padx=14, pady=8)

        lbl_frame = tk.Frame(row, bg=THEME["bg_card"])
        lbl_frame.pack(anchor="w", fill="x")

        tk.Label(
            lbl_frame, text=label_text,
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["bg_card"], fg=THEME["text_primary"]
        ).pack(side="left")

        if help_text:
            tk.Label(
                lbl_frame, text=f" ({help_text})",
                font=(THEME["font_family"], 8, "italic"),
                bg=THEME["bg_card"], fg=THEME["text_muted"]
            ).pack(side="left", padx=4)

        if field_type == "checkbox_group":
            opts = field.get("options", [])
            default_opts = field.get("default", [])

            # ── "View Config JSON" button beside the label ─────────────────
            btn_view_cfg = tk.Button(
                lbl_frame,
                text="📄 View Config JSON",
                font=(THEME["font_family"], 8, "bold"),
                bg="#eff6ff",
                fg=THEME["accent"],
                relief="flat", bd=0,
                padx=8, pady=2, cursor="hand2",
                command=lambda ts=tab_slug: self._show_config_json_popup(ts)
            )
            btn_view_cfg.pack(side="right", padx=4)

            cb_frame = tk.Frame(row, bg=THEME["bg_card"])
            cb_frame.pack(fill="x", pady=4)

            if field_id not in self.checkbox_variables[tab_slug]:
                self.checkbox_variables[tab_slug][field_id] = {}

            col = 0
            sub_row = 0
            for opt in opts:
                if opt not in self.checkbox_variables[tab_slug][field_id]:
                    var = tk.BooleanVar(value=(opt in default_opts))
                    var.trace_add("write", lambda *args: self._on_field_change())
                    self.checkbox_variables[tab_slug][field_id][opt] = var
                else:
                    var = self.checkbox_variables[tab_slug][field_id][opt]

                chk = tk.Checkbutton(
                    cb_frame, text=opt, variable=var,
                    font=(THEME["font_family"], 9),
                    bg=THEME["bg_card"], fg=THEME["text_primary"],
                    activebackground=THEME["bg_card"],
                    selectcolor=THEME["bg_card"],
                    cursor="hand2"
                )
                chk.grid(row=sub_row, column=col, sticky="w", padx=6, pady=2)
                col += 1
                if col > 1: # 2 columns on left side
                    col = 0
                    sub_row += 1

        elif field_type == "number":
            min_val = field.get("min", 1)
            max_val = field.get("max", 1000)
            default_val = field.get("default", min_val)

            if field_id not in self.field_variables[tab_slug]:
                var = tk.IntVar(value=default_val)
                var.trace_add("write", lambda *args: self._on_field_change())
                self.field_variables[tab_slug][field_id] = var
            else:
                var = self.field_variables[tab_slug][field_id]

            sp = tk.Spinbox(
                row, from_=min_val, to=max_val, textvariable=var,
                font=(THEME["font_family"], 9),
                width=14, relief="solid", bd=1
            )
            sp.pack(anchor="w", pady=3)

        elif field_type == "select":
            opts = field.get("options", [])
            default_val = field.get("default", opts[0] if opts else "")

            if field_id not in self.field_variables[tab_slug]:
                var = tk.StringVar(value=default_val)
                var.trace_add("write", lambda *args: self._on_field_change())
                self.field_variables[tab_slug][field_id] = var
            else:
                var = self.field_variables[tab_slug][field_id]

            cb = ttk.Combobox(row, textvariable=var, values=opts, state="readonly", width=28)
            cb.pack(anchor="w", pady=3)

        else: # text
            default_val = field.get("default", "")
            if field_id not in self.field_variables[tab_slug]:
                var = tk.StringVar(value=default_val)
                var.trace_add("write", lambda *args: self._on_field_change())
                self.field_variables[tab_slug][field_id] = var
            else:
                var = self.field_variables[tab_slug][field_id]

            entry = tk.Entry(
                row, textvariable=var,
                font=(THEME["font_family"], 9),
                width=36, relief="solid", bd=1
            )
            entry.pack(anchor="w", pady=3)

    def _on_field_change(self):
        """Called whenever user modifies any parameter on the left."""
        self.update_live_preview()

    # ─────────────────────────────────────────────────────────────────────────
    #  RIGHT PANE: CANVAS FOR EACH TAB (window1, window2, window3...)
    # ─────────────────────────────────────────────────────────────────────────
    def _render_right_windows_canvas(self, parent: tk.Frame, tab_slug: str):
        # Header for the right canvas
        right_hdr = tk.Frame(parent, bg=THEME["bg_card"], bd=0, highlightthickness=1, highlightbackground=THEME["border_light"])
        right_hdr.pack(fill="x", padx=(6, 0), pady=(0, 8))

        top_info = tk.Frame(right_hdr, bg=THEME["bg_card"])
        top_info.pack(side="left", padx=14, pady=8)

        tk.Label(
            top_info, text="🗂 Windows Canvas",
            font=(THEME["font_family"], 12, "bold"),
            bg=THEME["bg_card"], fg=THEME["text_primary"]
        ).pack(anchor="w")

        self.lbl_target_win_indicator = tk.Label(
            top_info, text=f"Active Target: window{self.selected_window_id}  (Click any window card to select)",
            font=(THEME["font_family"], 9),
            bg=THEME["bg_card"], fg=THEME["accent"]
        )
        self.lbl_target_win_indicator.pack(anchor="w")

        # Canvas actions
        act_box = tk.Frame(right_hdr, bg=THEME["bg_card"])
        act_box.pack(side="right", padx=12, pady=8)

        tk.Button(
            act_box, text=f"⚡ Gen window{self.selected_window_id}",
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["accent_light"], fg=THEME["accent"],
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=lambda: self.populate_window_card(self.selected_window_id)
        ).pack(side="left", padx=3)

        tk.Button(
            act_box, text="⚡ Gen ALL Windows (1-7)",
            font=(THEME["font_family"], 9, "bold"),
            bg="#f1f5f9", fg=THEME["text_primary"],
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self.populate_all_window_cards
        ).pack(side="left", padx=3)

        # Scrollable Canvas
        canvas_frame = tk.Frame(parent, bg=THEME["bg_main"])
        canvas_frame.pack(fill="both", expand=True, padx=(6, 0))

        self.right_canvas = tk.Canvas(canvas_frame, bg=THEME["bg_main"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.right_canvas.yview)
        win_cards_container = tk.Frame(self.right_canvas, bg=THEME["bg_main"])

        win_cards_container.bind("<Configure>", lambda e: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")))
        canvas_win = self.right_canvas.create_window((0, 0), window=win_cards_container, anchor="nw")

        def _on_right_canvas_configure(event):
            self.right_canvas.itemconfig(canvas_win, width=event.width)
        self.right_canvas.bind("<Configure>", _on_right_canvas_configure)
        self.right_canvas.configure(yscrollcommand=scrollbar.set)

        self.right_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Initialize widget registries
        if tab_slug not in self.window_text_widgets:
            self.window_text_widgets[tab_slug] = {}
        if tab_slug not in self.window_card_frames:
            self.window_card_frames[tab_slug] = {}
        if tab_slug not in self.window_badge_labels:
            self.window_badge_labels[tab_slug] = {}
        if tab_slug not in self.window_data_store:
            self.window_data_store[tab_slug] = {}

        # Render 7 window cards: window1, window2, ... window7
        for w_id in range(1, TOTAL_WINDOWS_PER_TAB + 1):
            self._render_window_card(win_cards_container, tab_slug, w_id)

    def _render_window_card(self, parent: tk.Frame, tab_slug: str, w_id: int):
        is_target = (w_id == self.selected_window_id)
        border_col = THEME["border_active"] if is_target else THEME["border_light"]
        bg_col = THEME["bg_win_active"] if is_target else THEME["bg_card"]

        card = tk.Frame(
            parent,
            bg=bg_col,
            bd=0,
            highlightthickness=2 if is_target else 1,
            highlightbackground=border_col
        )
        card.pack(fill="x", padx=4, pady=6)
        self.window_card_frames[tab_slug][w_id] = card

        # Window Header
        hdr = tk.Frame(card, bg=bg_col)
        hdr.pack(fill="x", padx=12, pady=(8, 4))

        # Title: Window X (windowX)
        title_lbl = tk.Label(
            hdr,
            text=f"✦ Window {w_id}  (window{w_id})",
            font=(THEME["font_family"], 10, "bold"),
            bg=bg_col,
            fg=THEME["accent"] if is_target else THEME["text_primary"],
            cursor="hand2"
        )
        title_lbl.pack(side="left")
        title_lbl.bind("<Button-1>", lambda e, wid=w_id: self.set_active_target_window(wid))

        # Badge
        badge = tk.Label(
            hdr,
            text="[ 🎯 ACTIVE TARGET ]" if is_target else "",
            font=(THEME["font_family"], 9, "bold"),
            bg=bg_col,
            fg=THEME["accent"]
        )
        badge.pack(side="left", padx=8)
        self.window_badge_labels[tab_slug][w_id] = badge

        # Action Buttons for this Window
        btn_target = tk.Button(
            hdr,
            text="🎯 Set Target",
            font=(THEME["font_family"], 8, "bold"),
            bg=THEME["bg_tabbar"],
            fg=THEME["text_primary"],
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda wid=w_id: self.set_active_target_window(wid)
        )
        btn_target.pack(side="right", padx=2)

        btn_gen = tk.Button(
            hdr,
            text="⚡ Gen JSON",
            font=(THEME["font_family"], 8, "bold"),
            bg=THEME["accent_light"],
            fg=THEME["accent"],
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda wid=w_id: self.populate_window_card(wid)
        )
        btn_gen.pack(side="right", padx=2)

        btn_copy = tk.Button(
            hdr,
            text="📋 Copy",
            font=(THEME["font_family"], 8),
            bg=THEME["bg_tabbar"],
            fg=THEME["text_secondary"],
            relief="flat",
            bd=0,
            padx=6,
            pady=2,
            cursor="hand2",
            command=lambda wid=w_id: self._copy_window_json(wid)
        )
        btn_copy.pack(side="right", padx=2)

        btn_original = tk.Button(
            hdr,
            text="📊 Original Form",
            font=(THEME["font_family"], 8),
            bg="#fef9c3",
            fg="#854d0e",
            relief="flat",
            bd=0,
            padx=6,
            pady=2,
            cursor="hand2",
            command=lambda wid=w_id: self._show_original_form(wid)
        )
        btn_original.pack(side="right", padx=2)

        # Scrolled Text Box for JSON
        txt = scrolledtext.ScrolledText(
            card,
            font=(THEME["font_mono"], 9),
            bg=THEME["bg_preview"],
            fg=THEME["text_primary"],
            height=7,
            bd=1,
            relief="solid",
            wrap="none"
        )
        txt.pack(fill="x", padx=12, pady=(2, 10))
        self.window_text_widgets[tab_slug][w_id] = txt

        # Populate with existing or placeholder content
        existing_val = self.window_data_store.get(tab_slug, {}).get(w_id, "")
        if existing_val:
            txt.delete("1.0", "end")
            txt.insert("1.0", existing_val)
        else:
            txt.delete("1.0", "end")
            txt.insert("1.0", f"// window{w_id} JSON data — Click '⚡ Gen JSON' or 'Set Target' to generate.")

    def set_active_target_window(self, w_id: int, scroll_to: bool = False):
        """Sets window w_id as the active target for generation & updates visual badges."""
        self.selected_window_id = w_id
        tab_slug = self.active_tab_slug
        self._update_banner()

        if hasattr(self, "lbl_target_win_indicator") and self.lbl_target_win_indicator:
            self.lbl_target_win_indicator.config(text=f"Active Target: window{w_id}  (Click any window card to select)")

        if hasattr(self, "btn_send_target") and self.btn_send_target:
            self.btn_send_target.config(text=f"💾 Send to window{w_id}")

        # Update card highlights
        frames = self.window_card_frames.get(tab_slug, {})
        badges = self.window_badge_labels.get(tab_slug, {})

        for wid, frame in frames.items():
            is_active = (wid == w_id)
            frame.configure(
                bg=THEME["bg_win_active"] if is_active else THEME["bg_card"],
                highlightbackground=THEME["border_active"] if is_active else THEME["border_light"],
                highlightthickness=2 if is_active else 1
            )
            # update header child widgets bg
            for child in frame.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=THEME["bg_win_active"] if is_active else THEME["bg_card"])
                    for subchild in child.winfo_children():
                        if isinstance(subchild, tk.Label):
                            subchild.configure(bg=THEME["bg_win_active"] if is_active else THEME["bg_card"])

            if wid in badges:
                badges[wid].configure(
                    text="[ 🎯 ACTIVE TARGET ]" if is_active else "",
                    bg=THEME["bg_win_active"] if is_active else THEME["bg_card"]
                )

        if scroll_to and self.right_canvas and w_id in frames:
            self.after(50, lambda: self._scroll_canvas_to_window(w_id))

    def _scroll_canvas_to_window(self, w_id: int):
        try:
            fraction = (w_id - 1) / max(1, TOTAL_WINDOWS_PER_TAB)
            self.right_canvas.yview_moveto(max(0.0, min(1.0, fraction)))
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    #  PER-WINDOW DATA POPULATION
    # ─────────────────────────────────────────────────────────────────────────
    def populate_window_card(self, w_id: int):
        """Generates JSON specifically configured for window w_id and inserts into its card."""
        tab_slug = self.active_tab_slug
        json_obj = self.generate_current_json(window_id=w_id)
        json_str = json.dumps(json_obj, indent=2)

        # Store in state
        if tab_slug not in self.window_data_store:
            self.window_data_store[tab_slug] = {}
        self.window_data_store[tab_slug][w_id] = json_str

        # Update text widget
        txt = self.window_text_widgets.get(tab_slug, {}).get(w_id)
        if txt:
            txt.delete("1.0", "end")
            txt.insert("1.0", json_str)

        self.lbl_status.config(
            text=f"⚡ Generated JSON for window{w_id} ({len(json_obj.get('data', []))} records).",
            fg=THEME["accent"]
        )
        self.update_live_preview()

    def populate_all_window_cards(self):
        """Generates JSON across all windows (1 to 7) for the active tab."""
        tab_slug = self.active_tab_slug
        for w_id in range(1, TOTAL_WINDOWS_PER_TAB + 1):
            self.populate_window_card(w_id)

        self.lbl_status.config(
            text=f"⚡ Populated all windows (window1 - window{TOTAL_WINDOWS_PER_TAB}) for {tab_slug.title()}.",
            fg=THEME["success"]
        )

    def _copy_window_json(self, w_id: int):
        tab_slug = self.active_tab_slug
        txt = self.window_text_widgets.get(tab_slug, {}).get(w_id)
        if txt:
            content = txt.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(content)
            messagebox.showinfo("Copied", f"JSON for window{w_id} copied to clipboard!")

    def _show_original_form(self, w_id: int):
        """
        Converts the JSON stored in window w_id back to a human-readable tabular
        'original form' (column-aligned table) and displays it in a popup window.
        Falls back gracefully if the content is plain text or malformed JSON.
        """
        tab_slug = self.active_tab_slug
        txt_widget = self.window_text_widgets.get(tab_slug, {}).get(w_id)
        if not txt_widget:
            return

        raw_content = txt_widget.get("1.0", "end-1c").strip()

        # ── Parse JSON ────────────────────────────────────────────────────────
        try:
            data = json.loads(raw_content)
        except (json.JSONDecodeError, ValueError):
            # Not JSON — show as plain text in a popup
            self._open_text_popup(
                title=f"Original Form — window{w_id}",
                content=raw_content,
                label=f"⚠️  window{w_id} content is not valid JSON — showing raw text:"
            )
            return

        # ── Build human-readable table from JSON ──────────────────────────────
        original_text = self._json_to_original_form(data, w_id)

        # ── Open popup ────────────────────────────────────────────────────────
        self._open_text_popup(
            title=f"📊 Original Form — {self.selected_tab_name} / window{w_id}",
            content=original_text,
            label=f"Tabular view of window{w_id} data ({self.selected_tab_name})"
        )

    @staticmethod
    def _json_to_original_form(data: dict, w_id: int) -> str:
        """
        Converts a GUI2 generated-JSON payload to a readable column-aligned table.
        Handles both the standard {metadata, data:[]} contract and plain record lists.
        """
        lines = []
        meta = {}
        records = []

        if isinstance(data, dict):
            meta = data.get("metadata", {})
            records = data.get("data", [])
            if not records and isinstance(data, dict):
                # Maybe it's a flat dict of k→v pairs
                records = [data]
        elif isinstance(data, list):
            records = data

        tab_name  = meta.get("tab_name",  "Data")
        win_key   = meta.get("target_window_key", f"window{w_id}")
        gen_at    = meta.get("generated_at", "")
        rec_count = meta.get("record_count", len(records))
        proj_id   = meta.get("project_id", "")

        sep = "═" * 74
        lines.append(sep)
        lines.append(f"  TAB : {tab_name.upper()}")
        if proj_id:
            lines.append(f"  PROJECT : {proj_id}")
        lines.append(f"  {win_key.upper()}  •  {rec_count} record(s)" + (f"  •  Generated: {gen_at[:19]}" if gen_at else ""))
        lines.append(sep)

        if not records:
            lines.append("  (no records)")
            lines.append(sep)
            return "\n".join(lines)

        # Determine columns from first record
        cols = list(records[0].keys()) if isinstance(records[0], dict) else ["value"]

        # Calculate column display widths
        col_w = {}
        for c in cols:
            max_val_w = max((len(str(r.get(c, ""))) for r in records if isinstance(r, dict)), default=0)
            col_w[c] = max(len(c), max_val_w)

        # Header row
        header = "  ".join(c.upper().ljust(col_w[c]) for c in cols)
        divider = "  ".join("─" * col_w[c] for c in cols)
        lines.append(header)
        lines.append(divider)

        # Data rows
        for r in records:
            if isinstance(r, dict):
                row_str = "  ".join(str(r.get(c, "")).ljust(col_w[c]) for c in cols)
            else:
                row_str = str(r)
            lines.append(row_str)

        lines.append(sep)

        # Append parameters_applied summary if present
        params = data.get("parameters_applied") if isinstance(data, dict) else None
        if params:
            lines.append("")
            lines.append("  Generation Parameters Applied:")
            lines.append("  " + "─" * 40)
            for k, v in params.items():
                val_str = ", ".join(v) if isinstance(v, list) else str(v)
                lines.append(f"  {k:<30} {val_str}")

        return "\n".join(lines)

    def _open_text_popup(self, title: str, content: str, label: str = ""):
        """Opens a generic text popup window (monospace, copy-able, scrollable)."""
        popup = tk.Toplevel(self)
        popup.title(title)
        popup.geometry("780x580")
        popup.minsize(520, 380)
        popup.configure(bg=THEME["bg_card"])

        # Header
        hdr = tk.Frame(popup, bg=THEME["bg_card"])
        hdr.pack(fill="x", padx=16, pady=(12, 6))

        tk.Label(
            hdr, text=label or title,
            font=(THEME["font_family"], 11, "bold"),
            bg=THEME["bg_card"], fg=THEME["text_primary"],
            wraplength=600, justify="left"
        ).pack(side="left", anchor="w")

        def _copy_all():
            popup.clipboard_clear()
            popup.clipboard_append(text_area.get("1.0", "end-1c"))
            messagebox.showinfo("Copied", "Content copied to clipboard!", parent=popup)

        tk.Button(
            hdr, text="📋 Copy All",
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["bg_tabbar"], fg=THEME["text_primary"],
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=_copy_all
        ).pack(side="right")

        # Text area
        text_area = scrolledtext.ScrolledText(
            popup,
            font=(THEME["font_mono"], 10),
            bg=THEME["bg_preview"],
            fg=THEME["text_primary"],
            bd=1, relief="solid",
            wrap="none"
        )
        text_area.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        text_area.insert("1.0", content)
        text_area.configure(state="normal")  # leave editable for user to annotate

    def _show_config_json_popup(self, tab_slug: str):
        """
        Opens a popup showing the raw config JSON file for the given tab.
        The file lives in CONFIG_DIR (config/<tab_slug>.json).
        Allows live editing and saving back to disk — columns/options update on reload.
        """
        config_path = os.path.join(CONFIG_DIR, f"{tab_slug}.json")

        if not os.path.isfile(config_path):
            messagebox.showerror(
                "Config File Missing",
                f"No config file found at:\n{config_path}\n\n"
                f"Click 'Create Starter Config Template' on the form to generate one."
            )
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_json = f.read()
        except Exception as e:
            messagebox.showerror("Read Error", f"Failed to read config file:\n{e}")
            return

        # ── Build popup ───────────────────────────────────────────────────────
        popup = tk.Toplevel(self)
        popup.title(f"📄 Config JSON — {tab_slug}.json")
        popup.geometry("780x620")
        popup.minsize(540, 420)
        popup.configure(bg=THEME["bg_card"])

        # Header
        hdr = tk.Frame(popup, bg=THEME["bg_card"])
        hdr.pack(fill="x", padx=16, pady=(12, 4))

        tk.Label(
            hdr, text=f"📄  config/{tab_slug}.json",
            font=(THEME["font_family"], 11, "bold"),
            bg=THEME["bg_card"], fg=THEME["text_primary"]
        ).pack(side="left", anchor="w")

        # Action buttons
        def _save_and_reload():
            new_content = text_area.get("1.0", "end-1c")
            try:
                parsed = json.loads(new_content)   # validate before saving
            except json.JSONDecodeError as e:
                messagebox.showerror("Invalid JSON", f"Cannot save — JSON syntax error:\n{e}", parent=popup)
                return
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2)
            popup.destroy()
            self.reload_and_rebuild()
            self.lbl_status.config(
                text=f"✅ Saved & reloaded config/{tab_slug}.json — columns updated!",
                fg=THEME["success"]
            )

        def _copy_config():
            popup.clipboard_clear()
            popup.clipboard_append(text_area.get("1.0", "end-1c"))
            messagebox.showinfo("Copied", "Config JSON copied to clipboard!", parent=popup)

        btn_box = tk.Frame(hdr, bg=THEME["bg_card"])
        btn_box.pack(side="right")

        tk.Button(
            btn_box, text="📋 Copy",
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["bg_tabbar"], fg=THEME["text_primary"],
            relief="flat", bd=0, padx=8, pady=4, cursor="hand2",
            command=_copy_config
        ).pack(side="left", padx=4)

        tk.Button(
            btn_box, text="💾 Save & Reload Columns",
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["success"], fg="#ffffff",
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=_save_and_reload
        ).pack(side="left", padx=4)

        # Info bar — file path
        info_bar = tk.Frame(popup, bg=THEME["bg_tabbar"])
        info_bar.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(
            info_bar,
            text=f"  📂 {config_path}",
            font=(THEME["font_mono"], 8),
            bg=THEME["bg_tabbar"], fg=THEME["text_muted"]
        ).pack(side="left", pady=4)

        # Hint label
        tk.Label(
            popup,
            text="💡 Edit the 'options' array under source_columns to add/remove columns. Click 'Save & Reload' to apply.",
            font=(THEME["font_family"], 9, "italic"),
            bg=THEME["bg_card"], fg=THEME["accent"],
            wraplength=740, justify="left"
        ).pack(padx=16, pady=(0, 6), anchor="w")

        # Editable JSON text area
        text_area = scrolledtext.ScrolledText(
            popup,
            font=(THEME["font_mono"], 10),
            bg=THEME["bg_preview"],
            fg=THEME["text_primary"],
            bd=1, relief="solid",
            wrap="none"
        )
        text_area.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        text_area.insert("1.0", raw_json)
        text_area.focus_set()
    def generate_current_json(self, window_id: Optional[int] = None) -> dict:
        tab_slug = self.active_tab_slug
        cfg = self.configs.get(tab_slug, {})
        gen_type = cfg.get("generator_type", tab_slug)

        win_num = window_id if window_id is not None else self.selected_window_id
        win_key = f"window{win_num}"

        # Collect user-specified values
        field_vals = {}
        for fid, var in self.field_variables.get(tab_slug, {}).items():
            field_vals[fid] = var.get()

        for fid, opt_dict in self.checkbox_variables.get(tab_slug, {}).items():
            field_vals[fid] = [opt for opt, var in opt_dict.items() if var.get()]

        records = []
        num_records = int(field_vals.get("num_records", 5))

        if gen_type == "vp_addresses":
            start_str = str(field_vals.get("starting_vp_address", "0x1000"))
            try:
                base_addr = int(start_str, 16) if start_str.startswith("0x") else int(start_str)
            except Exception:
                base_addr = 0x1000

            increment = int(field_vals.get("address_increment", 2))
            dtype = field_vals.get("data_type", "UINT16")
            access = field_vals.get("access_mode", "Read / Write")
            prefix = field_vals.get("variable_prefix", "VP_ADDR_")
            selected_cols = field_vals.get("source_columns", ["address_hex", "address_dec", "variable_name", "data_type", "access_mode"])

            # Offset address space per window so window1, window2, etc. have distinct address ranges
            win_offset = (win_num - 1) * num_records * increment
            window_base_addr = base_addr + win_offset

            for i in range(num_records):
                curr_addr = window_base_addr + (i * increment)
                row_data = {
                    "address_hex": f"0x{curr_addr:04X}",
                    "address_dec": curr_addr,
                    "variable_name": f"{prefix}W{win_num}_{i+1:02d}",
                    "data_type": dtype,
                    "access_mode": access,
                    "default_value": 0,
                    "description": f"VP Register for {win_key} slot {i+1:02d}"
                }
                filtered = {k: v for k, v in row_data.items() if k in selected_cols}
                records.append(filtered)

        elif gen_type == "sensors":
            selected_cols = field_vals.get("source_columns", ["sensor_id", "sensor_name", "sensor_type", "unit", "sampling_rate_ms", "status"])
            cat = field_vals.get("sensor_category", "Environmental")
            rate = field_vals.get("sampling_rate_ms", 1000)
            zone = field_vals.get("location_zone", f"Zone-{win_num}")

            sensor_profiles = [
                ("Temperature", "°C", 0.0, 100.0),
                ("Humidity", "%RH", 10.0, 90.0),
                ("Pressure", "hPa", 950.0, 1050.0),
                ("Vibration", "mm/s", 0.0, 15.0),
                ("Current", "Amps", 0.0, 30.0),
                ("Voltage", "Volts", 200.0, 240.0)
            ]

            for i in range(num_records):
                prof = sensor_profiles[i % len(sensor_profiles)]
                row_data = {
                    "sensor_id": f"SNS_W{win_num}_{i+1:03d}",
                    "sensor_name": f"{prof[0]} Sensor W{win_num}_{i+1}",
                    "sensor_type": cat,
                    "pin_channel": f"CH_W{win_num}_{i}",
                    "unit": prof[1],
                    "sampling_rate_ms": rate,
                    "min_threshold": prof[2],
                    "max_threshold": prof[3],
                    "status": "ONLINE",
                    "location": zone
                }
                filtered = {k: v for k, v in row_data.items() if k in selected_cols}
                records.append(filtered)

        elif gen_type == "parameters":
            selected_cols = field_vals.get("source_columns", ["param_id", "name", "group", "data_type", "default_value", "min_limit", "max_limit", "unit"])
            grp = field_vals.get("parameter_group", "General")
            unit = field_vals.get("unit_family", "%")
            prefix = field_vals.get("prefix", "PARAM_")

            base_param_id = (win_num * 100) + 1
            for i in range(num_records):
                row_data = {
                    "param_id": base_param_id + i,
                    "name": f"{prefix}W{win_num}_{i+1:02d}",
                    "group": f"{grp} (W{win_num})",
                    "data_type": "FLOAT32",
                    "default_value": round(10.0 * (i + 1), 2),
                    "min_limit": 0.0,
                    "max_limit": 100.0,
                    "unit": unit,
                    "read_only": False
                }
                filtered = {k: v for k, v in row_data.items() if k in selected_cols}
                records.append(filtered)

        elif gen_type == "topics":
            selected_cols = field_vals.get("source_columns", ["topic_name", "direction", "qos", "retained", "payload_type", "description"])
            protocol = field_vals.get("broker_protocol", "MQTT")
            ns = field_vals.get("root_namespace", f"devices/station_{win_num:02d}")
            qos_str = field_vals.get("qos_level", "1")
            qos = int(qos_str[0]) if qos_str else 1
            payload_fmt = field_vals.get("payload_format", "JSON")

            subtopics = ["telemetry", "alerts", "state", "commands", "heartbeat"]
            for i in range(num_records):
                sub = subtopics[i % len(subtopics)]
                row_data = {
                    "topic_name": f"{ns}/w{win_num}/{sub}_{i+1}",
                    "direction": "PUBLISH" if sub in ["telemetry", "alerts", "heartbeat"] else "SUBSCRIBE",
                    "qos": qos,
                    "retained": sub in ["state", "alerts"],
                    "payload_type": payload_fmt,
                    "description": f"Channel for {sub} messages ({protocol}) on {win_key}",
                    "rate_hz": 1.0
                }
                filtered = {k: v for k, v in row_data.items() if k in selected_cols}
                records.append(filtered)

        elif gen_type == "communication":
            selected_cols = field_vals.get("source_columns", ["interface_id", "protocol", "endpoint", "port_baud", "timeout_ms", "retry_limit"])
            proto = field_vals.get("protocol_type", "Modbus TCP/IP")
            host = field_vals.get("target_host", f"192.168.1.{100 + win_num}")
            port = field_vals.get("target_port", "502")
            timeout = int(field_vals.get("timeout_ms", 1500))
            retry = int(field_vals.get("retry_limit", 3))

            for i in range(num_records):
                row_data = {
                    "interface_id": f"COMM_W{win_num}_IF_{i+1:02d}",
                    "protocol": proto,
                    "endpoint": f"{host}:{port}" if "TCP" in proto or "EtherNet" in proto else f"/dev/ttyUSB{win_num}_{i}",
                    "port_baud": port,
                    "timeout_ms": timeout,
                    "retry_limit": retry,
                    "status": "CONFIGURED",
                    "keepalive_sec": 30
                }
                filtered = {k: v for k, v in row_data.items() if k in selected_cols}
                records.append(filtered)

        else: # Generic fallback
            selected_cols = field_vals.get("source_columns", ["id", "name", "value"])
            for i in range(num_records):
                row_data = {
                    "id": (win_num * 10) + i + 1,
                    "name": f"{tab_slug}_w{win_num}_item_{i+1}",
                    "value": round((i + 1) * 3.1415, 2),
                    "status": "ACTIVE",
                    "timestamp": datetime.now().isoformat()
                }
                filtered = {k: v for k, v in row_data.items() if k in selected_cols}
                records.append(filtered)

        # Full Document Output Contract
        payload = {
            "metadata": {
                "contract_version": "2.0",
                "request_id": self.current_request_id,
                "project_id": self.project_id,
                "tab_id": tab_slug,
                "tab_name": cfg.get("tab_title", tab_slug.title()),
                "target_window_id": win_num,
                "target_window_key": win_key,
                "generated_at": datetime.now().isoformat(),
                "record_count": len(records)
            },
            "parameters_applied": field_vals,
            "data": records
        }
        return payload

    # ─────────────────────────────────────────────────────────────────────────
    #  LIVE JSON PREVIEW (POP-UP WINDOW)
    # ─────────────────────────────────────────────────────────────────────────
    def open_live_preview_popup(self):
        """Creates or brings to front the Live JSON Preview pop-up window."""
        if self.preview_window is not None and tk.Toplevel.winfo_exists(self.preview_window):
            self.preview_window.lift()
            self.preview_window.focus_force()
            self.update_live_preview()
            return

        self.preview_window = tk.Toplevel(self)
        self.preview_window.title(f"🔍 Live JSON Preview — [{self.active_tab_slug.upper()}] (Target: window{self.selected_window_id})")
        self.preview_window.geometry("680x600")
        self.preview_window.minsize(480, 420)
        self.preview_window.configure(bg=THEME["bg_card"])

        hdr = tk.Frame(self.preview_window, bg=THEME["bg_card"])
        hdr.pack(fill="x", padx=16, pady=10)

        self.lbl_preview_target = tk.Label(
            hdr, text=f"Live JSON Output for window{self.selected_window_id}",
            font=(THEME["font_family"], 12, "bold"),
            bg=THEME["bg_card"], fg=THEME["text_primary"]
        )
        self.lbl_preview_target.pack(side="left")

        btn_copy = tk.Button(
            hdr, text="📋 Copy JSON",
            font=(THEME["font_family"], 9, "bold"),
            bg=THEME["bg_tabbar"], fg=THEME["text_primary"],
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=self._copy_preview_to_clipboard
        )
        btn_copy.pack(side="right")

        self.preview_text = scrolledtext.ScrolledText(
            self.preview_window,
            font=(THEME["font_mono"], 9),
            bg=THEME["bg_preview"],
            fg=THEME["text_primary"],
            bd=1, relief="solid",
            wrap="none"
        )
        self.preview_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.update_live_preview()

    def update_live_preview(self):
        if not self.preview_text or not self.preview_window or not tk.Toplevel.winfo_exists(self.preview_window):
            return
        try:
            data = self.generate_current_json(window_id=self.selected_window_id)
            formatted = json.dumps(data, indent=2)
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", formatted)
            if hasattr(self, "lbl_preview_target") and self.lbl_preview_target:
                self.lbl_preview_target.config(text=f"Live JSON Output for window{self.selected_window_id} ({len(data['data'])} records)")
        except Exception as e:
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", f"// Error updating preview:\n// {e}")

    def _copy_preview_to_clipboard(self):
        if self.preview_text:
            text = self.preview_text.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "JSON preview copied to clipboard!", parent=self.preview_window)

    # ─────────────────────────────────────────────────────────────────────────
    #  GENERATE & SEND ACTIONS (SINGLE WINDOW & BATCH ALL WINDOWS)
    # ─────────────────────────────────────────────────────────────────────────
    def generate_and_send_target_window(self, target_win_id: int):
        """Generates JSON for target_win_id, updates right canvas, saves to file, sends to GUI1."""
        try:
            self.populate_window_card(target_win_id)
            json_str = self.window_data_store[self.active_tab_slug][target_win_id]
            data = json.loads(json_str)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.project_id}_{self.active_tab_slug}_w{target_win_id}_{timestamp}.json"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_str)

            # Log history
            history_path = os.path.join(OUTPUT_DIR, "generation_history.jsonl")
            with open(history_path, "a", encoding="utf-8") as hf:
                history_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "file": filename,
                    "request_id": self.current_request_id,
                    "tab": self.active_tab_slug,
                    "window": target_win_id,
                    "records": len(data.get("data", []))
                }
                hf.write(json.dumps(history_entry) + "\n")

            # Send to GUI1
            resp_payload = {
                "type": "GENERATE_RESPONSE",
                "request_id": self.current_request_id,
                "project_id": self.project_id,
                "tab_id": self.active_tab_slug,
                "tab_name": self.selected_tab_name,
                "window_id": target_win_id,
                "window_key": f"window{target_win_id}",
                "file_path": filepath,
                "file_name": filename,
                "json_str": json_str
            }

            sent = self.ws_client.send(resp_payload)
            if sent:
                self.lbl_status.config(
                    text=f"✅ Dispatched to GUI1 -> Tab '{self.selected_tab_name}', window{target_win_id}",
                    fg=THEME["success"]
                )
                messagebox.showinfo("Sent to GUI1", f"Generated JSON sent to GUI1!\n\n• Target: {self.selected_tab_name}\n• Window: window{target_win_id}\n• Saved: output/{filename}")
            else:
                self.lbl_status.config(
                    text=f"⚠️ Saved locally to output/{filename} (GUI1 offline)",
                    fg=THEME["danger"]
                )
                messagebox.showwarning("Saved Locally", f"File saved to output/{filename}, but GUI1 connection is offline.")

        except Exception as e:
            messagebox.showerror("Generation Error", f"Failed to generate JSON:\n{e}")

    def generate_and_send_all_windows(self):
        """Generates JSON across all windows (1-7), updates canvas, and sends batch to GUI1."""
        try:
            self.populate_all_window_cards()
            tab_slug = self.active_tab_slug
            all_windows_dict = {}

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            batch_filename = f"{self.project_id}_{tab_slug}_all_windows_{timestamp}.json"
            batch_filepath = os.path.join(OUTPUT_DIR, batch_filename)

            combined_data = {
                "project_id": self.project_id,
                "tab_id": tab_slug,
                "tab_name": self.selected_tab_name,
                "timestamp": datetime.now().isoformat(),
                "windows": {}
            }

            for wid in range(1, TOTAL_WINDOWS_PER_TAB + 1):
                w_str = self.window_data_store[tab_slug][wid]
                all_windows_dict[wid] = w_str
                combined_data["windows"][f"window{wid}"] = json.loads(w_str)

            with open(batch_filepath, "w", encoding="utf-8") as f:
                json.dump(combined_data, f, indent=2)

            resp_payload = {
                "type": "GENERATE_RESPONSE",
                "request_id": self.current_request_id,
                "project_id": self.project_id,
                "tab_id": tab_slug,
                "tab_name": self.selected_tab_name,
                "window_id": self.selected_window_id,
                "window_key": f"window{self.selected_window_id}",
                "file_path": batch_filepath,
                "file_name": batch_filename,
                "json_str": self.window_data_store[tab_slug][self.selected_window_id],
                "all_windows": all_windows_dict
            }

            sent = self.ws_client.send(resp_payload)
            if sent:
                self.lbl_status.config(
                    text=f"✅ Dispatched ALL 7 windows to GUI1 for Tab '{self.selected_tab_name}'!",
                    fg=THEME["success"]
                )
                messagebox.showinfo("All Windows Dispatched", f"Successfully populated and sent ALL 7 windows to GUI1!\n\n• Tab: {self.selected_tab_name}\n• Windows: window1 - window7\n• Saved: output/{batch_filename}")
            else:
                self.lbl_status.config(
                    text=f"⚠️ Saved batch file output/{batch_filename} (GUI1 offline)",
                    fg=THEME["danger"]
                )

        except Exception as e:
            messagebox.showerror("Batch Generation Error", f"Failed to generate all windows:\n{e}")

    def _render_failed_state(self, tab_slug: str):
        card = tk.Frame(self.active_form_frame, bg=THEME["bg_card"], bd=1, relief="solid", highlightthickness=0)
        card.pack(fill="both", expand=True, padx=40, pady=30)

        tk.Label(
            card, text="⚠️ Configuration Missing",
            font=(THEME["font_family"], 16, "bold"),
            bg=THEME["bg_card"], fg=THEME["danger"]
        ).pack(pady=(40, 10))

        msg = (
            f"No JSON configuration definition was found for tab '{tab_slug}'.\n\n"
            f"Expected file: config/{tab_slug}.json\n"
            f"Please create the configuration JSON file to define this tab's generation rules."
        )
        tk.Label(
            card, text=msg,
            font=(THEME["font_family"], 11),
            bg=THEME["bg_card"], fg=THEME["text_secondary"], justify="center"
        ).pack(pady=10)

        tk.Button(
            card, text="➕ Create Starter Config Template",
            font=(THEME["font_family"], 10, "bold"),
            bg=THEME["accent"], fg="#ffffff",
            relief="flat", bd=0, padx=16, pady=8, cursor="hand2",
            command=lambda: self._create_starter_template(tab_slug)
        ).pack(pady=20)

    def _create_starter_template(self, tab_slug: str):
        template_path = os.path.join(CONFIG_DIR, f"{tab_slug}.json")
        template_data = {
            "tab_id": tab_slug,
            "tab_title": tab_slug.replace("_", " ").title(),
            "description": f"Dynamic data generator schema for {tab_slug}",
            "version": "1.0",
            "fields": [
                {
                    "id": "source_columns",
                    "label": "Source Columns",
                    "type": "checkbox_group",
                    "options": ["id", "name", "value", "status", "timestamp"],
                    "default": ["id", "name", "value"]
                },
                {
                    "id": "num_records",
                    "label": "Number of Records",
                    "type": "number",
                    "min": 1,
                    "max": 100,
                    "default": 5
                }
            ],
            "generator_type": "generic"
        }
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(template_data, f, indent=2)
        messagebox.showinfo("Created", f"Created starter configuration at {template_path}")
        self.reload_and_rebuild()

    def reload_and_rebuild(self):
        self.load_all_configurations()
        self._populate_tab_buttons()
        self.switch_tab(self.active_tab_slug)
        self.lbl_status.config(text=f"🔄 Reloaded {len(self.configs)} configuration definitions.", fg=THEME["accent"])

    def _on_close(self):
        self.ws_client.close()
        self.destroy()

# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GUI2 Dynamic JSON Data Generator Engine")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket IPC port")
    parser.add_argument("--tab", type=str, default="VP Addresses", help="Initial target tab name")
    parser.add_argument("--window", type=int, default=2, help="Initial target window ID")
    parser.add_argument("--project", type=str, default="Sample_Project", help="Project identifier")
    args = parser.parse_args()

    app = JSONDataGeneratorGUI2(
        port=args.port,
        initial_tab=args.tab,
        initial_window=args.window,
        project_id=args.project
    )
    app.mainloop()
