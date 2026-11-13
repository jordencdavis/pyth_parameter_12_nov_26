#!/usr/bin/env python3
"""
NOTE MAKING TOOL  v3.0
======================
• White theme
• 5 default tabs (Parameter | Features | Physical Pins | Communication | Firebase Path)
• Add tab (＋), Close tab (✕), Rename tab (double-click)
• Horizontal / Vertical alignment toggle per tab
• 7 windows per tab, Add Window, resizable, navigable
• Font size ±, bold, italic, colour picker
• Ctrl+↑/↓ window navigation  |  Bottom nav bar  |  Jump buttons
• Save Project / Load Project / Default Dir / Auto-save on close
• 5 .txt files (one per tab) + .notetool session JSON
"""

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog
import os, json, datetime, re, subprocess, sys, time
from ipc_comm import WebSocketServer

# ─────────────────────────────────────────────────────────────────────────────
#  THEME
# ─────────────────────────────────────────────────────────────────────────────
T = {
    "bg_root":         "#f5f5f5",
    "bg_menubar":      "#ffffff",
    "bg_tabbar":       "#e4e8f0",
    "bg_tab_active":   "#ffffff",
    "bg_tab_inactive": "#d8dce8",
    "bg_tab_hover":    "#eceef8",
    "bg_page":         "#f0f2f8",
    "bg_win_hdr":      "#dde8ff",
    "bg_win_body":     "#ffffff",
    "bg_text":         "#ffffff",
    "bg_toolbar":      "#f7f8fc",
    "bg_nav":          "#eaedf5",
    "bg_resize":       "#bcc8e0",
    "fg_title":        "#1a4fb5",
    "fg_label":        "#333344",
    "fg_muted":        "#8899aa",
    "fg_accent":       "#1a4fb5",
    "fg_text":         "#1a1a2e",
    "fg_win_num":      "#1a4fb5",
    "btn_add":         "#2563eb",
    "btn_add_fg":      "#ffffff",
    "btn_save":        "#15803d",
    "btn_save_fg":     "#ffffff",
    "btn_load":        "#0369a1",
    "btn_load_fg":     "#ffffff",
    "btn_dir":         "#7c3aed",
    "btn_dir_fg":      "#ffffff",
    "btn_clear":       "#dc2626",
    "btn_clear_fg":    "#ffffff",
    "btn_nav":         "#dde3f0",
    "btn_nav_fg":      "#1e3a5f",
    "btn_nav_act":     "#1a4fb5",
    "btn_nav_act_fg":  "#ffffff",
    "btn_ctrl":        "#e4ebf8",
    "btn_ctrl_fg":     "#1a4fb5",
    "btn_toggle_v":    "#1a4fb5",
    "btn_toggle_v_fg": "#ffffff",
    "btn_toggle_h":    "#7c3aed",
    "btn_toggle_h_fg": "#ffffff",
    "btn_tab_add":     "#22c55e",
    "btn_tab_add_fg":  "#ffffff",
    "btn_tab_close":   "#ef4444",
    "btn_tab_close_fg":"#ffffff",
    "border":          "#bec8de",
    "border_active":   "#1a4fb5",
    "bg_status":       "#e8eaf0",
    "fg_status":       "#556677",
}

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_TAB_NAMES  = ["Parameter", "Features", "Physical Pins",
                      "Communication", "Firebase Path"]
DEFAULT_WINDOWS    = 7
MIN_WIN_HEIGHT     = 110
DEFAULT_WIN_HEIGHT = 210
DEFAULT_WIN_WIDTH  = 340
FONT_FAMILY        = "Courier"
DEFAULT_FONT_SIZE  = 11
TOOL_DIR           = os.path.dirname(os.path.abspath(__file__))


def slug(name: str) -> str:
    """Turn a tab name into a safe filename slug."""
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "tab"


def flat_btn(parent, text, cmd, bg, fg,
             font_size=9, padx=10, pady=4, width=None, bold=False):
    kw = dict(text=text, command=cmd, bg=bg, fg=fg,
              font=(FONT_FAMILY, font_size, "bold" if bold else ""),
              relief="flat", bd=0, padx=padx, pady=pady,
              activebackground=T["border_active"],
              activeforeground="#ffffff", cursor="hand2")
    if width:
        kw["width"] = width
    return tk.Button(parent, **kw)


# ─────────────────────────────────────────────────────────────────────────────
#  NOTE WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class NoteWindow(tk.Frame):
    """One resizable, editable note card inside a tab."""

    def __init__(self, parent, tab_ref, index,
                 height=DEFAULT_WIN_HEIGHT, win_width=DEFAULT_WIN_WIDTH, **kw):
        super().__init__(parent, bd=0, highlightthickness=1,
                         highlightbackground=T["border"],
                         bg=T["bg_win_body"], **kw)
        self.tab_ref    = tab_ref
        self.index      = index
        self._h         = height
        self._win_width = win_width
        self.font_size  = DEFAULT_FONT_SIZE
        self.font_color = T["fg_text"]
        self.bold       = False
        self.italic     = False

        self._build_header()
        self._build_text()
        self._build_resize_handle()
        self.pack_propagate(False)
        self.configure(height=self._h, width=self._win_width)

    # ── header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=T["bg_win_hdr"], height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self.lbl_num = tk.Label(
            hdr, text=f"  ✦ Window {self.index + 1}",
            bg=T["bg_win_hdr"], fg=T["fg_win_num"],
            font=(FONT_FAMILY, 9, "bold"))
        self.lbl_num.pack(side="left")

        ctrl = tk.Frame(hdr, bg=T["bg_win_hdr"])
        ctrl.pack(side="right", padx=3)

        def cb(txt, cmd, w=2):
            b = flat_btn(ctrl, txt, cmd, T["btn_ctrl"], T["btn_ctrl_fg"],
                         font_size=8, padx=4, pady=1, width=w)
            b.pack(side="left", padx=1, pady=2)
            return b

        cb("A+", self.font_increase)
        cb("A-", self.font_decrease)
        self._btn_bold   = cb("B",  self.toggle_bold,   w=1)
        self._btn_italic = cb("I",  self.toggle_italic, w=1)
        cb("🎨", self.choose_color, w=2)

    # ── text area ─────────────────────────────────────────────────────────────
    def _build_text(self):
        frm = tk.Frame(self, bg=T["bg_text"])
        frm.pack(fill="both", expand=True, padx=1)

        self.text = tk.Text(
            frm, wrap="word",
            bg=T["bg_text"], fg=self.font_color,
            insertbackground=T["fg_accent"],
            selectbackground=T["fg_accent"],
            selectforeground="#ffffff",
            relief="flat", bd=4,
            font=(FONT_FAMILY, DEFAULT_FONT_SIZE),
            undo=True)
        self.text.pack(side="left", fill="both", expand=True)

        sb = tk.Scrollbar(frm, command=self.text.yview,
                          bg=T["bg_win_hdr"], troughcolor=T["bg_page"],
                          highlightthickness=0)
        sb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=sb.set)

        # Ctrl+↑/↓ → navigate between windows
        self.text.bind("<Control-Up>",
                       lambda e: (self.tab_ref.navigate(-1), "break"))
        self.text.bind("<Control-Down>",
                       lambda e: (self.tab_ref.navigate(+1), "break"))
        self.text.bind("<FocusIn>", lambda e: self.tab_ref.set_focus(self))

        # right-click context menu
        self._ctx = tk.Menu(self.text, tearoff=0,
                            bg=T["bg_menubar"], fg=T["fg_label"],
                            activebackground=T["border_active"],
                            activeforeground="#ffffff",
                            font=(FONT_FAMILY, 9),
                            relief="flat", bd=1)
        self._build_context_menu()
        self.text.bind("<Button-3>", self._show_context_menu)

    # ── context menu ──────────────────────────────────────────────────────────
    def _build_context_menu(self):
        m = self._ctx

        def add(label, cmd, underline=0):
            m.add_command(label=label, command=cmd, underline=underline)

        def sep():
            m.add_separator()

        # ── Clipboard ─────────────────────────────────────────────────────────
        add("✂  Cut",             self._ctx_cut)
        add("⎘  Copy",            self._ctx_copy)
        add("⎗  Paste",           self._ctx_paste)
        add("⬚  Copy All Text",   self._ctx_copy_all)
        sep()

        # ── Edit ──────────────────────────────────────────────────────────────
        add("↩  Undo",            self._ctx_undo)
        add("↪  Redo",            self._ctx_redo)
        sep()
        add("▦  Select All",      self._ctx_select_all)
        add("⌦  Clear Window",    self._ctx_clear)
        sep()

        # ── Font ──────────────────────────────────────────────────────────────
        add("A↑  Font Size +",    self.font_increase)
        add("A↓  Font Size -",    self.font_decrease)
        add("B  Bold",            self.toggle_bold)
        add("I  Italic",          self.toggle_italic)
        add("🎨  Font Colour…",   self.choose_color)
        sep()

        # ── Insert ────────────────────────────────────────────────────────────
        add("📅  Insert Date",     self._ctx_insert_date)
        add("🕐  Insert Time",     self._ctx_insert_time)
        add("─  Insert Divider",  self._ctx_insert_divider)
        sep()

        # ── Window ops ────────────────────────────────────────────────────────
        add("⬆  Navigate Prev Window",   lambda: self.tab_ref.navigate(-1))
        add("⬇  Navigate Next Window",   lambda: self.tab_ref.navigate(+1))
        add("⧉  Duplicate This Window",  self._ctx_duplicate)
        sep()

        # ── Resize ────────────────────────────────────────────────────────────
        # sub-menu
        size_menu = tk.Menu(m, tearoff=0,
                            bg=T["bg_menubar"], fg=T["fg_label"],
                            activebackground=T["border_active"],
                            activeforeground="#ffffff",
                            font=(FONT_FAMILY, 9))
        for label, h in [("Small (120px)", 120),
                         ("Medium (210px)", 210),
                         ("Large (340px)", 340),
                         ("Extra Large (480px)", 480)]:
            size_menu.add_command(
                label=label,
                command=lambda hh=h: self._ctx_set_height(hh))
        m.add_cascade(label="↕  Window Height", menu=size_menu)

        width_menu = tk.Menu(m, tearoff=0,
                             bg=T["bg_menubar"], fg=T["fg_label"],
                             activebackground=T["border_active"],
                             activeforeground="#ffffff",
                             font=(FONT_FAMILY, 9))
        for label, w in [("Compact (260px)", 260),
                         ("Normal (340px)", 340),
                         ("Wide (460px)", 460),
                         ("Extra Wide (600px)", 600)]:
            width_menu.add_command(
                label=label,
                command=lambda ww=w: self._ctx_set_width(ww))
        m.add_cascade(label="↔  Window Width", menu=width_menu)
        sep()

        # ── Wrap ──────────────────────────────────────────────────────────────
        wrap_menu = tk.Menu(m, tearoff=0,
                            bg=T["bg_menubar"], fg=T["fg_label"],
                            activebackground=T["border_active"],
                            activeforeground="#ffffff",
                            font=(FONT_FAMILY, 9))
        for label, mode in [("Word wrap", "word"),
                             ("Char wrap", "char"),
                             ("No wrap",   "none")]:
            wrap_menu.add_command(
                label=label,
                command=lambda m=mode: self.text.configure(wrap=m))
        m.add_cascade(label="⇌  Text Wrap", menu=wrap_menu)
        sep()

        # ── Save ──────────────────────────────────────────────────────────────
        add("💾  Save All Tabs",   self._ctx_save_all)
        add("📋  Copy Tab as Text",self._ctx_copy_tab)

    def _show_context_menu(self, e):
        # Update dynamic items before showing
        try:
            self._ctx_update_state()
            self._ctx.tk_popup(e.x_root, e.y_root)
        finally:
            self._ctx.grab_release()

    def _ctx_update_state(self):
        """Enable/disable clipboard items based on selection / clipboard."""
        has_sel = bool(self.text.tag_ranges("sel"))
        try:
            has_clip = bool(self.text.clipboard_get())
        except tk.TclError:
            has_clip = False

        s_cut   = "normal" if has_sel  else "disabled"
        s_copy  = "normal" if has_sel  else "disabled"
        s_paste = "normal" if has_clip else "disabled"

        self._ctx.entryconfigure(0, state=s_cut)   # Cut
        self._ctx.entryconfigure(1, state=s_copy)  # Copy
        self._ctx.entryconfigure(2, state=s_paste) # Paste

    # ── clipboard actions ─────────────────────────────────────────────────────
    def _ctx_cut(self):
        try:
            self.text.event_generate("<<Cut>>")
        except tk.TclError:
            pass

    def _ctx_copy(self):
        try:
            self.text.event_generate("<<Copy>>")
        except tk.TclError:
            pass

    def _ctx_paste(self):
        try:
            self.text.event_generate("<<Paste>>")
        except tk.TclError:
            pass

    def _ctx_copy_all(self):
        content = self.get_content()
        self.clipboard_clear()
        self.clipboard_append(content)

    # ── edit actions ──────────────────────────────────────────────────────────
    def _ctx_undo(self):
        try: self.text.edit_undo()
        except tk.TclError: pass

    def _ctx_redo(self):
        try: self.text.edit_redo()
        except tk.TclError: pass

    def _ctx_select_all(self):
        self.text.tag_add("sel", "1.0", "end")
        self.text.mark_set("insert", "end")

    def _ctx_clear(self):
        from tkinter import messagebox as mb
        if mb.askyesno("Clear Window",
                       f"Clear all text in Window {self.index + 1}?",
                       parent=self):
            self.set_content("")

    # ── insert helpers ────────────────────────────────────────────────────────
    def _ctx_insert_date(self):
        self.text.insert("insert",
                         datetime.datetime.now().strftime("%Y-%m-%d"))

    def _ctx_insert_time(self):
        self.text.insert("insert",
                         datetime.datetime.now().strftime("%H:%M:%S"))

    def _ctx_insert_divider(self):
        self.text.insert("insert", "\n" + "─" * 50 + "\n")

    # ── window operations ─────────────────────────────────────────────────────
    def _ctx_duplicate(self):
        content = self.get_content()
        meta    = self.get_meta()
        self.tab_ref.add_window(content=content, meta=meta)

    def _ctx_set_height(self, h):
        self._h = h
        if self.tab_ref._orient == TabContent.ORIENT_V:
            self.configure(height=h)
            self.tab_ref._sync_scroll()

    def _ctx_set_width(self, w):
        self._win_width = w
        if self.tab_ref._orient == TabContent.ORIENT_H:
            self.configure(width=w)
            self.tab_ref._sync_scroll()

    # ── save / copy tab ──────────────────────────────────────────────────────
    def _ctx_save_all(self):
        # Walk up to NoteTool instance
        w = self.master
        while w and not isinstance(w, tk.Tk):
            w = w.master
        if w and hasattr(w, "_save_all"):
            w._save_all(notify=True)

    def _ctx_copy_tab(self):
        txt = self.tab_ref.to_text()
        self.clipboard_clear()
        self.clipboard_append(txt)

    # ── resize handle ─────────────────────────────────────────────────────────
    def _build_resize_handle(self):
        h = tk.Frame(self, bg=T["bg_resize"], height=6,
                     cursor="sb_v_double_arrow")
        h.pack(fill="x", side="bottom")
        h.bind("<ButtonPress-1>", self._resize_start)
        h.bind("<B1-Motion>",     self._resize_drag)

    def _resize_start(self, e):
        self._ry = e.y_root
        self._rh = self.winfo_height()

    def _resize_drag(self, e):
        if self.tab_ref._orient == TabContent.ORIENT_H:
            return
        new_h = max(MIN_WIN_HEIGHT, self._rh + (e.y_root - self._ry))
        self._h = new_h
        self.configure(height=new_h)
        self.tab_ref._sync_scroll()

    # ── font helpers ──────────────────────────────────────────────────────────
    def _apply_font(self):
        s = []
        if self.bold:   s.append("bold")
        if self.italic: s.append("italic")
        f = (FONT_FAMILY, self.font_size, " ".join(s)) if s \
            else (FONT_FAMILY, self.font_size)
        self.text.configure(font=f, fg=self.font_color)
        self._btn_bold.configure(
            bg=T["border_active"] if self.bold   else T["btn_ctrl"],
            fg="#fff"             if self.bold   else T["btn_ctrl_fg"])
        self._btn_italic.configure(
            bg=T["border_active"] if self.italic else T["btn_ctrl"],
            fg="#fff"             if self.italic else T["btn_ctrl_fg"])

    def font_increase(self):
        self.font_size = min(48, self.font_size + 1); self._apply_font()

    def font_decrease(self):
        self.font_size = max(6,  self.font_size - 1); self._apply_font()

    def toggle_bold(self):
        self.bold = not self.bold; self._apply_font()

    def toggle_italic(self):
        self.italic = not self.italic; self._apply_font()

    def choose_color(self):
        _, hx = colorchooser.askcolor(color=self.font_color,
                                      title="Font colour")
        if hx:
            self.font_color = hx
            self._apply_font()

    # ── data ──────────────────────────────────────────────────────────────────
    def get_content(self):
        return self.text.get("1.0", "end-1c")

    def set_content(self, txt):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", txt)

    def get_meta(self):
        return dict(font_size=self.font_size, font_color=self.font_color,
                    bold=self.bold, italic=self.italic,
                    height=self._h, win_width=self._win_width)

    def set_meta(self, m):
        if not m: return
        self.font_size   = m.get("font_size",  DEFAULT_FONT_SIZE)
        self.font_color  = m.get("font_color", T["fg_text"])
        self.bold        = m.get("bold",        False)
        self.italic      = m.get("italic",      False)
        self._h          = m.get("height",      DEFAULT_WIN_HEIGHT)
        self._win_width  = m.get("win_width",   DEFAULT_WIN_WIDTH)
        self.configure(height=self._h, width=self._win_width)
        self._apply_font()

    def focus_text(self):
        self.text.focus_set()
        self.configure(highlightbackground=T["border_active"],
                       highlightthickness=2)

    def unfocus(self):
        self.configure(highlightbackground=T["border"],
                       highlightthickness=1)


# ─────────────────────────────────────────────────────────────────────────────
#  TAB CONTENT
# ─────────────────────────────────────────────────────────────────────────────
class TabContent(tk.Frame):
    ORIENT_V = "vertical"
    ORIENT_H = "horizontal"

    def __init__(self, parent, tab_name, **kw):
        super().__init__(parent, bg=T["bg_page"], **kw)
        self.tab_name        = tab_name
        self.windows: list[NoteWindow] = []
        self._focused_index  = 0
        self._orient         = self.ORIENT_V

        self._build_ui()
        for _ in range(DEFAULT_WINDOWS):
            self._add_window_internal()
        self._update_nav_buttons()

    # ── ui ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # top toolbar
        tb = tk.Frame(self, bg=T["bg_toolbar"], height=40)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        self._tab_name_lbl = tk.Label(
            tb, text=f"  {self.tab_name}",
            bg=T["bg_toolbar"], fg=T["fg_title"],
            font=(FONT_FAMILY, 11, "bold"))
        self._tab_name_lbl.pack(side="left", pady=5)

        # alignment toggle
        self._toggle_var = tk.StringVar(value="⬛ Vertical")
        self._btn_toggle = tk.Button(
            tb, textvariable=self._toggle_var,
            command=self.toggle_orientation,
            bg=T["btn_toggle_v"], fg=T["btn_toggle_v_fg"],
            font=(FONT_FAMILY, 9, "bold"),
            relief="flat", bd=0, padx=10, pady=4,
            activebackground=T["border_active"],
            activeforeground="#fff", cursor="hand2")
        self._btn_toggle.pack(side="right", padx=6, pady=5)

        flat_btn(tb, "＋ Add Window", self.add_window,
                 T["btn_add"], T["btn_add_fg"],
                 bold=True).pack(side="right", padx=4, pady=5)

        # scrollable canvas
        wrap = tk.Frame(self, bg=T["bg_page"])
        wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(wrap, bg=T["bg_page"],
                                highlightthickness=0, bd=0)
        self._vsb = tk.Scrollbar(wrap, orient="vertical",
                                 command=self.canvas.yview,
                                 bg=T["bg_tabbar"], troughcolor=T["bg_page"])
        self._hsb = tk.Scrollbar(wrap, orient="horizontal",
                                 command=self.canvas.xview,
                                 bg=T["bg_tabbar"], troughcolor=T["bg_page"])
        self._vsb.pack(side="right",  fill="y")
        self._hsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self._vsb.set,
                              xscrollcommand=self._hsb.set)

        self.inner = tk.Frame(self.canvas, bg=T["bg_page"])
        self._win_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._sync_scroll)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # mouse-wheel
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

        # bottom nav bar
        nav = tk.Frame(self, bg=T["bg_nav"], height=40)
        nav.pack(fill="x", side="bottom")
        nav.pack_propagate(False)

        tk.Label(nav, text=" Navigate:", bg=T["bg_nav"], fg=T["fg_label"],
                 font=(FONT_FAMILY, 9)).pack(side="left", padx=4)

        self.btn_prev = flat_btn(nav, "◀ Prev", lambda: self.navigate(-1),
                                 T["btn_nav"], T["btn_nav_fg"], padx=8)
        self.btn_prev.pack(side="left", padx=3, pady=5)

        self.btn_next = flat_btn(nav, "Next ▶", lambda: self.navigate(+1),
                                 T["btn_nav"], T["btn_nav_fg"], padx=8)
        self.btn_next.pack(side="left", padx=3, pady=5)

        self.nav_lbl = tk.Label(nav, text="Window 1/7",
                                bg=T["bg_nav"], fg=T["fg_accent"],
                                font=(FONT_FAMILY, 9, "bold"))
        self.nav_lbl.pack(side="left", padx=10)

        self.jump_frame = tk.Frame(nav, bg=T["bg_nav"])
        self.jump_frame.pack(side="left", padx=4)

    # ── mousewheel ────────────────────────────────────────────────────────────
    def _bind_wheel(self, _=None):
        self.canvas.bind_all("<MouseWheel>", self._mwheel)
        self.canvas.bind_all("<Button-4>",   self._mwheel)
        self.canvas.bind_all("<Button-5>",   self._mwheel)

    def _unbind_wheel(self, _=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _mwheel(self, e):
        if self._orient == self.ORIENT_H:
            if e.num == 4 or e.delta > 0:
                self.canvas.xview_scroll(-1, "units")
            else:
                self.canvas.xview_scroll( 1, "units")
        else:
            if e.num == 4 or e.delta > 0:
                self.canvas.yview_scroll(-1, "units")
            else:
                self.canvas.yview_scroll( 1, "units")

    # ── canvas helpers ────────────────────────────────────────────────────────
    def _sync_scroll(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, event=None):
        cw = event.width if event and hasattr(event, "width") else self.canvas.winfo_width()
        ch = event.height if event and hasattr(event, "height") else self.canvas.winfo_height()
        if self._orient == self.ORIENT_V:
            if cw > 1:
                self.canvas.itemconfig(self._win_id, width=cw, height=0)
        else:
            if ch > 1:
                self.canvas.itemconfig(self._win_id, width=0, height=ch)
        self._sync_scroll()

    # ── orientation toggle ────────────────────────────────────────────────────
    def toggle_orientation(self):
        if self._orient == self.ORIENT_V:
            self._orient = self.ORIENT_H
            self._toggle_var.set("⬜ Horizontal")
            self._btn_toggle.configure(bg=T["btn_toggle_h"],
                                       fg=T["btn_toggle_h_fg"])
        else:
            self._orient = self.ORIENT_V
            self._toggle_var.set("⬛ Vertical")
            self._btn_toggle.configure(bg=T["btn_toggle_v"],
                                       fg=T["btn_toggle_v_fg"])
        self._relayout()

    def _relayout(self):
        for w in self.windows:
            w.pack_forget()
        if self._orient == self.ORIENT_V:
            cw = self.canvas.winfo_width()
            self.canvas.itemconfig(self._win_id,
                                   width=cw if cw > 1 else 0,
                                   height=0)
            for w in self.windows:
                w.configure(height=w._h)
                w.pack(fill="x", padx=6, pady=(0, 5))
            self.canvas.xview_moveto(0.0)
        else:
            ch = self.canvas.winfo_height()
            self.canvas.itemconfig(self._win_id,
                                   width=0,
                                   height=ch if ch > 1 else 0)
            for w in self.windows:
                w.configure(width=w._win_width)
                w.pack(side="left", fill="y", padx=(5, 0), pady=5)
            self.canvas.yview_moveto(0.0)
        self._sync_scroll()

    # ── window management ─────────────────────────────────────────────────────
    def _add_window_internal(self, content="", meta=None):
        idx = len(self.windows)
        win = NoteWindow(self.inner, tab_ref=self, index=idx)
        if content: win.set_content(content)
        if meta:    win.set_meta(meta)
        self.windows.append(win)

        if self._orient == self.ORIENT_V:
            win.configure(height=win._h)
            win.pack(fill="x", padx=6, pady=(0, 5))
        else:
            win.configure(width=win._win_width)
            win.pack(side="left", fill="y", padx=(5, 0), pady=5)
        return win

    def add_window(self, content="", meta=None):
        win = self._add_window_internal(content, meta)
        self._rebuild_jump_buttons()
        self._update_nav_buttons()
        # scroll to new window after layout settles
        if self._orient == self.ORIENT_V:
            self.after(50, lambda: self.canvas.yview_moveto(1.0))
        else:
            self.after(50, lambda: self.canvas.xview_moveto(1.0))
        return win

    def _rebuild_jump_buttons(self):
        for c in self.jump_frame.winfo_children():
            c.destroy()
        for i in range(len(self.windows)):
            b = flat_btn(self.jump_frame, str(i + 1),
                         lambda x=i: self._jump_to(x),
                         T["btn_nav"], T["btn_nav_fg"],
                         font_size=8, padx=5, pady=2, width=2)
            b.pack(side="left", padx=1)

    # ── navigation ────────────────────────────────────────────────────────────
    def _jump_to(self, idx):
        self._focused_index = max(0, min(idx, len(self.windows) - 1))
        self._unfocus_all()
        self.windows[self._focused_index].focus_text()
        self._update_nav_buttons()
        self.after(30, self._scroll_to_focused)

    def navigate(self, d):
        ni = max(0, min(self._focused_index + d, len(self.windows) - 1))
        self._focused_index = ni
        self._unfocus_all()
        self.windows[ni].focus_text()
        self._update_nav_buttons()
        self.after(30, self._scroll_to_focused)

    def set_focus(self, win_obj):
        if win_obj in self.windows:
            self._unfocus_all()
            win_obj.configure(highlightbackground=T["border_active"],
                              highlightthickness=2)
            self._focused_index = self.windows.index(win_obj)
            self._update_nav_buttons()

    def _unfocus_all(self):
        for w in self.windows:
            w.unfocus()

    def _scroll_to_focused(self):
        """Scroll canvas so the focused window is visible."""
        if not self.windows:
            return
        win = self.windows[self._focused_index]
        # force geometry update
        self.inner.update_idletasks()
        self.canvas.update_idletasks()

        if self._orient == self.ORIENT_V:
            total_h = self.inner.winfo_height()
            view_h  = self.canvas.winfo_height()
            if total_h <= view_h:
                return
            win_top = win.winfo_y()
            win_bot = win_top + win.winfo_height()
            # get current viewport top pixel
            top_frac = self.canvas.yview()[0]
            top_px   = top_frac * total_h
            bot_px   = top_px + view_h
            # only scroll if window is outside viewport
            if win_top < top_px:
                # scroll up so window top has 10px margin
                target = max(0, win_top - 10)
            elif win_bot > bot_px:
                # scroll down so window bottom has 10px margin
                target = min(total_h - view_h, win_bot - view_h + 10)
            else:
                return
            self.canvas.yview_moveto(target / total_h)
        else:
            total_w = self.inner.winfo_width()
            view_w  = self.canvas.winfo_width()
            if total_w <= view_w:
                return
            win_left  = win.winfo_x()
            win_right = win_left + win.winfo_width()
            left_frac = self.canvas.xview()[0]
            left_px   = left_frac * total_w
            right_px  = left_px + view_w
            if win_left < left_px:
                target = max(0, win_left - 10)
            elif win_right > right_px:
                target = min(total_w - view_w, win_right - view_w + 10)
            else:
                return
            self.canvas.xview_moveto(target / total_w)

    def _update_nav_buttons(self):
        total = len(self.windows)
        cur   = self._focused_index
        self.nav_lbl.config(text=f"Window {cur + 1}/{total}")
        active = cur > 0
        self.btn_prev.config(
            state="normal" if active else "disabled",
            bg=T["btn_nav_act"] if active else T["btn_nav"],
            fg=T["btn_nav_act_fg"] if active else T["btn_nav_fg"])
        active = cur < total - 1
        self.btn_next.config(
            state="normal" if active else "disabled",
            bg=T["btn_nav_act"] if active else T["btn_nav"],
            fg=T["btn_nav_act_fg"] if active else T["btn_nav_fg"])

    # ── serialise ─────────────────────────────────────────────────────────────
    def get_all_data(self):
        return {
            "tab_name": self.tab_name,
            "orient":   self._orient,
            "windows":  [{"content": w.get_content(), "meta": w.get_meta()}
                         for w in self.windows]
        }

    def set_all_data(self, data):
        for w in self.windows: w.destroy()
        self.windows.clear()
        orient = data.get("orient", self.ORIENT_V)
        self._orient = orient
        if orient == self.ORIENT_H:
            self._toggle_var.set("⬜ Horizontal")
            self._btn_toggle.configure(bg=T["btn_toggle_h"],
                                       fg=T["btn_toggle_h_fg"])
        else:
            self._toggle_var.set("⬛ Vertical")
            self._btn_toggle.configure(bg=T["btn_toggle_v"],
                                       fg=T["btn_toggle_v_fg"])
        for entry in data.get("windows", []):
            self._add_window_internal(
                content=entry.get("content", ""),
                meta=entry.get("meta"))
        self._relayout()
        self._rebuild_jump_buttons()
        self._update_nav_buttons()

    def to_text(self):
        lines = [
            "=" * 70,
            f"  TAB : {self.tab_name}",
            f"  Saved: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
            "=" * 70, ""
        ]
        for i, w in enumerate(self.windows):
            body = w.get_content().strip()
            lines += ["─" * 70, f"  WINDOW {i + 1}", "─" * 70,
                      body if body else "(empty)", ""]
        return "\n".join(lines)

    def rename(self, new_name: str):
        self.tab_name = new_name
        self._tab_name_lbl.configure(text=f"  {new_name}")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────
class NoteTool(tk.Tk):

    CFG_FILE = os.path.join(TOOL_DIR, ".note_tool_cfg.json")

    def __init__(self):
        super().__init__()
        self.title("📝 Note Making Tool")
        self.geometry("1200x880")
        self.minsize(860, 600)
        self.configure(bg=T["bg_root"])

        self._cfg          = self._load_cfg()
        self._project_file = self._cfg.get("last_project")
        self.default_dir   = self._cfg.get("default_dir", TOOL_DIR)
        self.save_dir      = self._cfg.get("save_dir",    self.default_dir)

        # tab state: parallel lists  btn_frame / page
        self._tab_btn_frames: list[tk.Frame]    = []
        self._tab_pages:      list[TabContent]  = []
        self._active_tab: int = 0

        # WebSocket IPC Server for communicating with GUI2
        self.ws_port = 8765
        self.ws_server = WebSocketServer(port=self.ws_port, on_message=self._on_ws_message)
        try:
            self.ws_server.start()
        except Exception as e:
            print(f"[GUI1] WebSocket error: {e}")

        self._build_menubar()
        self._build_tabbar()       # builds self.tab_bar + "＋" button
        self._build_pages()
        self._build_statusbar()

        # create default tabs
        for name in DEFAULT_TAB_NAMES:
            self._create_tab(name)
        self._switch_tab(0)

        self._restore()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Control-s>", lambda e: self._save_all(notify=True))
        self.bind_all("<Control-o>", lambda e: self._load_project())
        self.bind_all("<Control-n>", lambda e: self._new_project())

    # ═════════════════════════════════════════════════════════════════════════
    #  UI BUILD
    # ═════════════════════════════════════════════════════════════════════════
    def _build_menubar(self):
        mb = tk.Frame(self, bg=T["bg_menubar"], height=48)
        mb.pack(fill="x")
        mb.pack_propagate(False)

        tk.Label(mb, text="  📝 NOTE TOOL",
                 bg=T["bg_menubar"], fg=T["fg_title"],
                 font=(FONT_FAMILY, 14, "bold")).pack(side="left", pady=8)

        self._proj_lbl = tk.Label(mb, text="  No project loaded",
                                  bg=T["bg_menubar"], fg=T["fg_muted"],
                                  font=(FONT_FAMILY, 9, "italic"))
        self._proj_lbl.pack(side="left", padx=8)

        def rb(text, cmd, bg, fg):
            b = flat_btn(mb, text, cmd, bg, fg,
                         font_size=9, bold=True, padx=10, pady=5)
            b.pack(side="right", padx=4, pady=7)
            return b

        rb("⚡ Generate Data", self._launch_data_generator,
           "#2563eb",       "#ffffff")
        rb("🗑 Clear Tab",    self._clear_tab,
           T["btn_clear"],  T["btn_clear_fg"])
        rb("💾 Save All",     lambda: self._save_all(notify=True),
           T["btn_save"],   T["btn_save_fg"])
        rb("💾 Save Project", self._save_project,
           "#0f766e",       "#ffffff")
        rb("📂 Load Project", self._load_project,
           T["btn_load"],   T["btn_load_fg"])
        rb("🆕 New Project",  self._new_project,
           "#6d28d9",       "#ffffff")
        rb("📁 Default Dir",  self._set_default_dir,
           T["btn_dir"],    T["btn_dir_fg"])

    def _build_tabbar(self):
        # outer frame holds the scrollable tab strip + "＋" button
        outer = tk.Frame(self, bg=T["bg_tabbar"])
        outer.pack(fill="x")

        # scrollable canvas for tab buttons
        self._tab_canvas = tk.Canvas(outer, bg=T["bg_tabbar"],
                                     height=42, highlightthickness=0, bd=0)
        self._tab_canvas.pack(side="left", fill="x", expand=True)

        add_btn = flat_btn(outer, " ＋ ", self._add_tab_dialog,
                           T["btn_tab_add"], T["btn_tab_add_fg"],
                           font_size=12, padx=6, pady=0, bold=True)
        add_btn.pack(side="right", padx=4, pady=4)

        # inner frame inside canvas holds the actual tab button frames
        self.tab_bar = tk.Frame(self._tab_canvas, bg=T["bg_tabbar"])
        self._tab_canvas.create_window((0, 0), window=self.tab_bar, anchor="nw")
        self.tab_bar.bind("<Configure>",
                          lambda e: self._tab_canvas.configure(
                              scrollregion=self._tab_canvas.bbox("all")))

        # separator
        tk.Frame(self, bg=T["border"], height=2).pack(fill="x")

    def _build_pages(self):
        self.page_host = tk.Frame(self, bg=T["bg_page"])
        self.page_host.pack(fill="both", expand=True)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=T["bg_status"], height=24)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status_lbl = tk.Label(
            bar,
            text="  Ready — Ctrl+S Save | Ctrl+O Load | Ctrl+N New | "
                 "Double-click tab to rename",
            bg=T["bg_status"], fg=T["fg_status"],
            font=(FONT_FAMILY, 8), anchor="w")
        self._status_lbl.pack(side="left", fill="x", expand=True)

        self._dir_lbl = tk.Label(
            bar, text=f"📁 {self.save_dir}  ",
            bg=T["bg_status"], fg=T["fg_muted"],
            font=(FONT_FAMILY, 8), anchor="e")
        self._dir_lbl.pack(side="right")

    # ═════════════════════════════════════════════════════════════════════════
    #  DYNAMIC TABS
    # ═════════════════════════════════════════════════════════════════════════
    def _create_tab(self, name: str, switch_to=False, data=None) -> int:
        """Create one tab (button + page). Returns the new tab index."""
        idx = len(self._tab_pages)

        # ── tab button frame  ─────────────────────────────────────────────────
        frm = tk.Frame(self.tab_bar, bg=T["bg_tab_inactive"],
                       highlightthickness=1,
                       highlightbackground=T["border"])
        frm.pack(side="left", padx=(0, 2), pady=4)

        lbl = tk.Label(frm, text=f"  {name}  ",
                       bg=T["bg_tab_inactive"], fg=T["fg_muted"],
                       font=(FONT_FAMILY, 10), padx=2, pady=5,
                       cursor="hand2")
        lbl.pack(side="left")

        close_btn = tk.Label(frm, text=" ✕ ",
                             bg=T["bg_tab_inactive"], fg=T["fg_muted"],
                             font=(FONT_FAMILY, 9, "bold"),
                             cursor="hand2", padx=2, pady=5)
        close_btn.pack(side="left")

        # bind events (use default-arg capture so lambdas freeze the right idx)
        lbl.bind("<Button-1>",       lambda e, i=idx: self._switch_tab(i))
        frm.bind("<Button-1>",       lambda e, i=idx: self._switch_tab(i))
        lbl.bind("<Double-Button-1>",lambda e, i=idx: self._rename_tab(i))
        close_btn.bind("<Button-1>", lambda e, i=idx: self._close_tab(i))

        self._tab_btn_frames.append(frm)

        # ── page ──────────────────────────────────────────────────────────────
        page = TabContent(self.page_host, tab_name=name)
        if data:
            page.set_all_data(data)
        self._tab_pages.append(page)

        if switch_to:
            self._switch_tab(idx)

        return idx

    def _add_tab_dialog(self):
        name = simpledialog.askstring(
            "New Tab", "Tab name:", initialvalue="New Tab", parent=self)
        if name and name.strip():
            self._create_tab(name.strip(), switch_to=True)
            self._status(f"✦ Tab '{name}' added")

    def _close_tab(self, idx):
        if len(self._tab_pages) <= 1:
            messagebox.showwarning("Cannot Close",
                                   "At least one tab must remain.")
            return
        name = self._tab_pages[idx].tab_name
        if not messagebox.askyesno("Close Tab",
                                   f"Close tab '{name}'? All content will be lost."):
            return

        # destroy widgets
        self._tab_pages[idx].pack_forget()
        self._tab_pages[idx].destroy()
        self._tab_btn_frames[idx].destroy()
        del self._tab_pages[idx]
        del self._tab_btn_frames[idx]

        # re-bind all remaining tab buttons with updated indices
        self._rebind_all_tabs()

        # decide which tab to show
        new_active = min(self._active_tab, len(self._tab_pages) - 1)
        self._active_tab = -1          # force redraw
        self._switch_tab(new_active)
        self._status(f"✕ Tab '{name}' closed")

    def _rename_tab(self, idx):
        old = self._tab_pages[idx].tab_name
        new = simpledialog.askstring(
            "Rename Tab", f"New name for '{old}':",
            initialvalue=old, parent=self)
        if new and new.strip() and new.strip() != old:
            new = new.strip()
            self._tab_pages[idx].rename(new)
            # update label in button frame
            lbl = self._tab_btn_frames[idx].winfo_children()[0]
            lbl.configure(text=f"  {new}  ")
            self._status(f"✎ Renamed '{old}' → '{new}'")

    def _rebind_all_tabs(self):
        """After add/remove, re-bind click handlers with fresh indices."""
        for i, frm in enumerate(self._tab_btn_frames):
            children = frm.winfo_children()
            lbl       = children[0]
            close_btn = children[1]
            lbl.bind("<Button-1>",        lambda e, x=i: self._switch_tab(x))
            frm.bind("<Button-1>",        lambda e, x=i: self._switch_tab(x))
            lbl.bind("<Double-Button-1>", lambda e, x=i: self._rename_tab(x))
            close_btn.bind("<Button-1>",  lambda e, x=i: self._close_tab(x))

    # ═════════════════════════════════════════════════════════════════════════
    #  TAB SWITCHING
    # ═════════════════════════════════════════════════════════════════════════
    def _switch_tab(self, idx):
        if idx < 0 or idx >= len(self._tab_pages):
            return
        for p in self._tab_pages:
            p.pack_forget()
        for i, frm in enumerate(self._tab_btn_frames):
            lbl = frm.winfo_children()[0]
            x_lbl = frm.winfo_children()[1]
            if i == idx:
                frm.configure(bg=T["bg_tab_active"],
                              highlightbackground=T["border_active"])
                lbl.configure(bg=T["bg_tab_active"], fg=T["fg_accent"],
                              font=(FONT_FAMILY, 10, "bold"))
                x_lbl.configure(bg=T["bg_tab_active"], fg=T["btn_clear"])
            else:
                frm.configure(bg=T["bg_tab_inactive"],
                              highlightbackground=T["border"])
                lbl.configure(bg=T["bg_tab_inactive"], fg=T["fg_muted"],
                              font=(FONT_FAMILY, 10))
                x_lbl.configure(bg=T["bg_tab_inactive"], fg=T["fg_muted"])

        self._active_tab = idx
        page = self._tab_pages[idx]
        page.pack(in_=self.page_host, fill="both", expand=True)
        page._on_canvas_resize()

    # ═════════════════════════════════════════════════════════════════════════
    #  PROJECT MANAGEMENT
    # ═════════════════════════════════════════════════════════════════════════
    def _new_project(self):
        name = simpledialog.askstring(
            "New Project", "Project name:",
            initialvalue="my_project", parent=self)
        if not name: return
        d = filedialog.askdirectory(title="Choose project folder",
                                    initialdir=self.default_dir)
        if not d: return
        self.save_dir      = d
        self._project_file = os.path.join(d, f"{name}.notetool")
        # reset all pages
        for page in self._tab_pages:
            for w in page.windows: w.destroy()
            page.windows.clear()
            for _ in range(DEFAULT_WINDOWS):
                page._add_window_internal()
            page._rebuild_jump_buttons()
            page._update_nav_buttons()
        self._update_proj_label()
        self._status(f"🆕 New project '{name}' — {d}")

    def _save_project(self):
        if not self._project_file:
            path = filedialog.asksaveasfilename(
                title="Save Project As",
                initialdir=self.default_dir,
                defaultextension=".notetool",
                filetypes=[("Note Tool Project", "*.notetool"),
                           ("All files", "*.*")])
            if not path: return
            self._project_file = path
            self.save_dir = os.path.dirname(path)
        self._do_save_project()

    def _do_save_project(self):
        data = {
            "version":  3,
            "saved":    datetime.datetime.now().isoformat(),
            "save_dir": self.save_dir,
            "tabs":     [p.get_all_data() for p in self._tab_pages]
        }
        os.makedirs(os.path.dirname(self._project_file) or ".", exist_ok=True)
        with open(self._project_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._save_txt_files()
        self._update_proj_label()
        self._status(f"✅ Saved → {self._project_file}")

    def _load_project(self):
        path = filedialog.askopenfilename(
            title="Load Project",
            initialdir=self.default_dir,
            filetypes=[("Note Tool Project", "*.notetool"),
                       ("All files", "*.*")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            messagebox.showerror("Load Error", str(ex)); return

        self._project_file = path
        self.save_dir = data.get("save_dir", os.path.dirname(path))
        self._load_tabs_from_data(data)
        self._update_proj_label()
        self._status(f"📂 Loaded → {path}")

    def _load_tabs_from_data(self, data):
        """Destroy all current tabs and recreate from saved data."""
        # destroy existing
        for p in self._tab_pages:  p.destroy()
        for f in self._tab_btn_frames: f.destroy()
        self._tab_pages.clear()
        self._tab_btn_frames.clear()
        self._active_tab = 0

        tabs_data = data.get("tabs", [])
        # support both v2 (dict keyed by index) and v3 (list)
        if isinstance(tabs_data, dict):
            tabs_data = [tabs_data[k] for k in sorted(tabs_data, key=int)]

        for td in tabs_data:
            name = td.get("tab_name", "Tab")
            self._create_tab(name, data=td)

        if not self._tab_pages:
            for n in DEFAULT_TAB_NAMES:
                self._create_tab(n)

        self._switch_tab(0)

    # ── txt export ────────────────────────────────────────────────────────────
    def _save_txt_files(self):
        os.makedirs(self.save_dir, exist_ok=True)
        for page in self._tab_pages:
            fname = slug(page.tab_name) + ".txt"
            fp = os.path.join(self.save_dir, fname)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(page.to_text())

    def _save_all(self, notify=False):
        self._save_txt_files()
        self._persist_cfg()
        self._dir_lbl.configure(text=f"📁 {self.save_dir}  ")
        self._status(f"💾 Saved → {self.save_dir}")
        if notify:
            messagebox.showinfo("Saved",
                                f"{len(self._tab_pages)} files saved to:\n"
                                f"{self.save_dir}")

    # ── default dir ───────────────────────────────────────────────────────────
    def _set_default_dir(self):
        d = filedialog.askdirectory(title="Set Default Project Directory",
                                    initialdir=self.default_dir)
        if d:
            self.default_dir = self.save_dir = d
            self._persist_cfg()
            self._dir_lbl.configure(text=f"📁 {d}  ")
            self._status(f"📁 Default dir → {d}")

    def _clear_tab(self):
        page = self._tab_pages[self._active_tab]
        if messagebox.askyesno("Clear Tab",
                               f"Clear all windows in '{page.tab_name}'?"):
            for w in page.windows: w.set_content("")
            self._status(f"🗑 Cleared: {page.tab_name}")

    # ═════════════════════════════════════════════════════════════════════════
    #  PERSISTENCE
    # ═════════════════════════════════════════════════════════════════════════
    def _persist_cfg(self):
        try:
            with open(self.CFG_FILE, "w", encoding="utf-8") as f:
                json.dump({"default_dir":  self.default_dir,
                           "save_dir":     self.save_dir,
                           "last_project": self._project_file}, f, indent=2)
        except Exception:
            pass

    def _load_cfg(self):
        try:
            with open(self.CFG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _restore(self):
        if self._project_file and os.path.exists(self._project_file):
            try:
                with open(self._project_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.save_dir = data.get("save_dir", self.save_dir)
                self._load_tabs_from_data(data)
                self._update_proj_label()
                self._status(f"🔄 Restored → {self._project_file}")
            except Exception:
                pass
        self._dir_lbl.configure(text=f"📁 {self.save_dir}  ")

    # ═════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ═════════════════════════════════════════════════════════════════════════
    def _update_proj_label(self):
        if self._project_file:
            name = os.path.basename(self._project_file)
            self._proj_lbl.configure(
                text=f"  📄 {name}  ({self.save_dir})",
                fg=T["fg_accent"])
        else:
            self._proj_lbl.configure(text="  No project loaded",
                                     fg=T["fg_muted"])

    def _status(self, msg, duration=5000):
        self._status_lbl.configure(text=f"  {msg}")
        self.after(duration,
                   lambda: self._status_lbl.configure(
                       text="  Ready — Ctrl+S Save | Ctrl+O Load | "
                            "Ctrl+N New | Double-click tab to rename"))

    # ═════════════════════════════════════════════════════════════════════════
    #  GUI2 IPC & DATA GENERATOR INTEGRATION
    # ═════════════════════════════════════════════════════════════════════════
    def _launch_data_generator(self):
        """Sends generation request to GUI2 or launches GUI2 if not running."""
        if not self._tab_pages:
            return

        page = self._tab_pages[self._active_tab]
        tab_name = page.tab_name
        tab_id = tab_name.lower().strip().replace(" ", "_").replace("-", "_")
        win_idx = page._focused_index
        win_num = win_idx + 1
        win_content = page.windows[win_idx].get_content() if win_idx < len(page.windows) else ""
        proj_name = os.path.splitext(os.path.basename(self._project_file))[0] if self._project_file else "NoteTool_Project"

        # Global project summary across tabs
        all_context = {}
        for p in self._tab_pages:
            all_context[p.tab_name] = [w.get_content() for w in p.windows]

        req_payload = {
            "type": "GENERATE_REQUEST",
            "request_id": f"req_{int(time.time() * 1000)}",
            "project_id": proj_name,
            "tab_id": tab_id,
            "tab_name": tab_name,
            "window_id": win_num,
            "window_content": win_content,
            "all_tabs_data": all_context,
            "timestamp": datetime.datetime.now().isoformat()
        }

        gui2_connected = self.ws_server.has_clients()
        if gui2_connected:
            self.ws_server.broadcast(req_payload)
            self._status(f"⚡ Context dispatched to active GUI2: '{tab_name}' (Window {win_num})")
        else:
            gui2_path = os.path.join(TOOL_DIR, "gui2.py")
            subprocess.Popen([
                sys.executable, gui2_path,
                "--port", str(self.ws_port),
                "--tab", tab_name,
                "--window", str(win_num),
                "--project", proj_name
            ])
            self._status(f"🚀 Launched GUI2 for '{tab_name}' (Window {win_num})")

    def _on_ws_message(self, data: dict):
        """Thread-safe WebSocket receiver callback."""
        msg_type = data.get("type")
        if msg_type == "GENERATE_RESPONSE":
            self.after(0, self._handle_generate_response, data)

    def _handle_generate_response(self, resp: dict):
        """Processes generated JSON received from GUI2 and writes it to target window."""
        tab_name = resp.get("tab_name", "")
        tab_id = resp.get("tab_id", "")
        target_win_id = resp.get("window_id", 1)
        json_str = resp.get("json_str", "")
        req_id = resp.get("request_id", "")

        # Find matching tab in GUI1
        target_page = None
        target_page_idx = -1
        for idx, page in enumerate(self._tab_pages):
            p_slug = page.tab_name.lower().strip().replace(" ", "_").replace("-", "_")
            if p_slug == tab_id.lower() or page.tab_name.lower() == tab_name.lower():
                target_page = page
                target_page_idx = idx
                break

        if target_page is None and self._tab_pages:
            target_page = self._tab_pages[self._active_tab]
            target_page_idx = self._active_tab

        if target_page:
            self._switch_tab(target_page_idx)
            all_wins = resp.get("all_windows")
            if all_wins and isinstance(all_wins, dict):
                for wid_str, w_json in all_wins.items():
                    try:
                        w_idx = int(wid_str) - 1
                        if 0 <= w_idx < len(target_page.windows):
                            target_page.windows[w_idx].set_content(w_json)
                    except Exception:
                        pass
                self._status(f"✅ Injected generated JSON across all windows in Tab '{target_page.tab_name}'")
                messagebox.showinfo(
                    "All Windows Updated",
                    f"Successfully updated ALL windows in Tab '{target_page.tab_name}'!\n\n"
                    f"• Request ID: {req_id}"
                )
            else:
                win_idx = max(0, min(target_win_id - 1, len(target_page.windows) - 1))
                win_obj = target_page.windows[win_idx]
                win_obj.set_content(json_str)
                target_page.set_focus(win_obj)
                target_page._scroll_to_focused()
                self._status(f"✅ Injected generated JSON into Tab '{target_page.tab_name}' (Window {target_win_id})")
                messagebox.showinfo(
                    "JSON Injected",
                    f"Successfully received data from GUI2!\n\n"
                    f"• Target Tab: {target_page.tab_name}\n"
                    f"• Target Window: {target_win_id}\n"
                    f"• Request ID: {req_id}"
                )

    def _on_close(self):
        try:
            self.ws_server.stop()
        except Exception:
            pass
        if self._project_file:
            self._do_save_project()
        else:
            self._save_txt_files()
        self._persist_cfg()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = NoteTool()
    app.mainloop()
