import tkinter as tk
import keyboard
import threading
import time
import random
import json
import os
import re
import sys
import webbrowser
import urllib.request
import io
import ctypes
from ctypes import wintypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

try:
    from PIL import Image, ImageTk, ImageEnhance, ImageOps, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ==========================================================
#  WinAPI
# ==========================================================
user32 = ctypes.WinDLL("user32", use_last_error=True)
winmm  = ctypes.WinDLL("winmm",  use_last_error=True)

try:
    winmm.timeBeginPeriod(1)
except Exception:
    pass

INPUT_MOUSE          = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004
MOUSEEVENTF_MOVE     = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          wintypes.LONG),
        ("dy",          wintypes.LONG),
        ("mouseData",   wintypes.DWORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _build_click_inputs(x, y, screen_w, screen_h):
    ax = int(x * 65535 / max(1, screen_w - 1))
    ay = int(y * 65535 / max(1, screen_h - 1))

    move = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(
            dx=ax, dy=ay, mouseData=0,
            dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
            time=0, dwExtraInfo=None,
        ),
    )
    down = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None),
    )
    return (INPUT * 3)(move, down, up)


_SCREEN_W = user32.GetSystemMetrics(0)
_SCREEN_H = user32.GetSystemMetrics(1)


# ==========================================================
#  Современная палитра (Минимализм / Без неона)
# ==========================================================
BG         = "#121214"
SURFACE    = "#1a1b1e"
SURFACE_HOV= "#222327"
BORDER     = "#2c2d32"
TEXT       = "#f4f4f5"
TEXT_MUTED = "#71717a"
ACCENT     = "#6366f1"
ACCENT_HOV = "#4f46e5"
GREEN_COL  = "#3c763d"
RED_COL    = "#E0262B"
YELLOW     = "#f59e0b"

FONT_TITLE = ("Segoe UI", 9, "bold")
FONT_BODY  = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 9)
FONT_TINY  = ("Segoe UI", 8)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ==========================================================
#  Приложение
# ==========================================================
class HuEvoClicker:
    def __init__(self, root):
        self.root = root
        self.root.overrideredirect(True)
        self.root.geometry("250x350")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        ico_path = resource_path("icon.ico")
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        def fix_taskbar():
            try:
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
                if not hwnd:
                    hwnd = root.winfo_id()
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                ex_style = ex_style & ~0x00000080
                ex_style = ex_style | 0x00040000
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style)
                root.withdraw()
                root.deiconify()
            except Exception:
                pass
        root.after(50, fix_taskbar)

        self.toast_anim_id = None
        self.tab_active = False
        self.last_balance = None
        self.current_bal_text = "0"

        self.stat_day = "0"
        self.stat_clicks = "0"
        self.stat_total = "0"
        self.last_avatar_url = ""

        self.cat_frames = []
        self.cat_photo_dim = None
        self.cat_photo_normal = None
        self.avatar_photo = None

        cat_path = resource_path("cat.png")
        if os.path.exists(cat_path) and PIL_AVAILABLE:
            try:
                pil_img = Image.open(cat_path).convert("RGBA")
                w, h = pil_img.size
                new_h = 16
                new_w = max(1, int(w * (new_h / h)))
                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                self.cat_photo_normal = ImageTk.PhotoImage(pil_img)

                def make_frame(img_transformed):
                    f = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
                    fw, fh = img_transformed.size
                    px = (new_w - fw) // 2
                    py = (new_h - fh) // 2
                    f.paste(img_transformed, (px, py))
                    return ImageTk.PhotoImage(f)

                img_big = pil_img.resize((int(new_w * 1.15), int(new_h * 1.15)), Image.Resampling.LANCZOS)
                img_tilt = pil_img.rotate(12, resample=Image.Resampling.BICUBIC, expand=False)
                img_tilt2 = pil_img.rotate(-10, resample=Image.Resampling.BICUBIC, expand=False)

                self.cat_frames = [
                    self.cat_photo_normal,
                    make_frame(img_big),
                    make_frame(img_tilt),
                    make_frame(img_tilt2),
                    self.cat_photo_normal
                ]

                enhancer = ImageEnhance.Brightness(pil_img)
                dimmed = enhancer.enhance(0.5)
                self.cat_photo_dim = ImageTk.PhotoImage(dimmed)
            except Exception:
                pass

        self.points = []
        self.is_running = False
        self.thread = None
        self.timer_mode = "fixed"
        self.last_update_time = 0

        self._build_ui()
        self._start_rainbow_animation()

        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

        threading.Thread(target=self._start_local_server, daemon=True).start()
        threading.Thread(target=self._connection_checker, daemon=True).start()

    # ------------------------------------------------------
    def _build_ui(self):
        root = self.root

        self.title_bar = tk.Frame(root, bg=BG, height=28)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        tk.Label(self.title_bar, text="huEVO clicker", bg=BG, fg=TEXT_MUTED,
                 font=FONT_TITLE).pack(side="left", padx=10)

        close_btn = tk.Button(self.title_bar, text="✕", command=root.destroy,
                              bg=BG, fg=TEXT_MUTED, activebackground=RED_COL,
                              activeforeground="#fff", relief="flat", bd=0, font=FONT_TINY, width=3)
        close_btn.pack(side="right", fill="y")

        def start_move(event):
            root.x = event.x
            root.y = event.y
        def do_move(event):
            x = root.winfo_x() + (event.x - root.x)
            y = root.winfo_y() + (event.y - root.y)
            root.geometry(f"+{x}+{y}")
        self.title_bar.bind("<Button-1>", start_move)
        self.title_bar.bind("<B1-Motion>", do_move)

        main_frame = tk.Frame(root, bg=BG)
        main_frame.pack(fill="both", expand=True, padx=12, pady=(2, 2))

        self.balance_card = tk.Frame(
            main_frame, bg=SURFACE,
            highlightbackground=BORDER, highlightthickness=1,
            cursor="hand2", height=32
        )
        self.balance_card.pack(fill="x", pady=(2, 3))
        self.balance_card.pack_propagate(False)

        self.balance_left_frame = tk.Frame(self.balance_card, bg=SURFACE)
        self.balance_left_frame.pack(side="left", fill="y", padx=4)

        self.balance_label = tk.Label(
            self.balance_left_frame, text="  Ожидание вкладки...", bg=SURFACE, fg=TEXT_MUTED,
            font=("Consolas", 9, "bold")
        )
        if self.cat_photo_dim:
            self.balance_label.config(image=self.cat_photo_dim, compound="left")
        self.balance_label.pack(side="left", pady=5)

        self.balance_right_frame = tk.Frame(self.balance_card, bg=SURFACE)
        self.balance_right_frame.pack(side="right", fill="y", padx=6)

        self.avatar_label = tk.Label(self.balance_right_frame, bg=SURFACE)
        self.avatar_label.pack(side="right", pady=4)

        self.user_label = tk.Label(
            self.balance_right_frame, text="", bg=SURFACE, fg=TEXT_MUTED,
            font=("Consolas", 8)
        )
        self.user_label.pack(side="right", padx=(0, 4), pady=6)

        for widget in (self.balance_card, self.balance_left_frame, self.balance_right_frame, self.balance_label, self.user_label, self.avatar_label):
            widget.bind("<Enter>", self._on_card_enter)
            widget.bind("<Leave>", self._on_card_leave)
            widget.bind("<Button-1>", lambda e: self.open_sync_modal())

        self.expanded_card = tk.Frame(
            main_frame, bg=SURFACE,
            highlightbackground=BORDER, highlightthickness=1,
            cursor="hand2"
        )
        for w in (self.expanded_card,):
            w.bind("<Enter>", self._on_card_enter)
            w.bind("<Leave>", self._on_card_leave)
            w.bind("<Button-1>", lambda e: self.open_sync_modal())

        exp_inner = tk.Frame(self.expanded_card, bg=SURFACE)
        exp_inner.pack(fill="both", expand=True, padx=8, pady=4)

        def make_stat_row(parent, label_text):
            f = tk.Frame(parent, bg=SURFACE)
            f.pack(fill="x", pady=1)
            lbl = tk.Label(f, text=label_text, bg=SURFACE, fg=TEXT_MUTED, font=("Consolas", 8), anchor="w")
            lbl.pack(side="left")
            val = tk.Label(f, text="0", bg=SURFACE, fg=TEXT, font=("Consolas", 8, "bold"), anchor="e")
            val.pack(side="right")
            return val

        self.exp_day_val = make_stat_row(exp_inner, "Седня")
        self.exp_clicks_val = make_stat_row(exp_inner, "Кликов")
        self.exp_total_val = make_stat_row(exp_inner, "Нарулил")

        tk.Button(
            main_frame, text="+  Добавить точку (F2)", command=self.add_point,
            bg=SURFACE, fg=TEXT, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_BODY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", pady=(2, 2), ipady=2)

        list_wrap = tk.Frame(main_frame, bg=SURFACE,
                             highlightbackground=BORDER, highlightthickness=1)
        list_wrap.pack(fill="x")

        self.listbox = tk.Listbox(
            list_wrap, height=3, bg=SURFACE, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#fff",
            bd=0, highlightthickness=0, font=FONT_MONO, activestyle="none",
        )
        self.listbox.pack(fill="x", padx=4, pady=2)

        tk.Button(
            main_frame, text="✕  Очистить", command=self.clear_points,
            bg=SURFACE, fg=TEXT_MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_TINY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", pady=(2, 0), ipady=1)

        self.params_parent = tk.Frame(main_frame, bg=BG)
        self.params_parent.pack(fill="x", pady=(3, 1))

        self.fixed_container = tk.Frame(self.params_parent, bg=BG)
        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="0")
        self.ms_var  = tk.StringVar(value="50")

        fixed_inner = tk.Frame(self.fixed_container, bg=BG)
        fixed_inner.pack(anchor="center")

        def entry(parent, var, width=3):
            e = tk.Entry(parent, textvariable=var, width=width, justify="center",
                         bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=2, padx=(0, 2))
            return e

        entry(fixed_inner, self.min_var)
        tk.Label(fixed_inner, text="м", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 4))
        entry(fixed_inner, self.sec_var)
        tk.Label(fixed_inner, text="с", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 4))
        entry(fixed_inner, self.ms_var)
        tk.Label(fixed_inner, text="мс", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 0))

        self.rand_container = tk.Frame(self.params_parent, bg=BG)
        self.rand_min_var = tk.StringVar(value="30")
        self.rand_max_var = tk.StringVar(value="120")

        rand_inner = tk.Frame(self.rand_container, bg=BG)
        rand_inner.pack(anchor="center")

        def rentry(parent, var):
            e = tk.Entry(parent, textvariable=var, width=5, justify="center",
                         bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=2, padx=(0, 2))
            return e

        tk.Label(rand_inner, text="от", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 2))
        rentry(rand_inner, self.rand_min_var)
        tk.Label(rand_inner, text="до", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(4, 2))
        rentry(rand_inner, self.rand_max_var)
        tk.Label(rand_inner, text="мс", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(2, 0))

        self.fixed_container.pack(fill="x")

        self.mode_btn = tk.Button(
            main_frame, text="таймер-клик", command=self.toggle_timer_mode,
            bg=SURFACE, fg=TEXT_MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_TINY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.mode_btn.pack(fill="x", pady=(2, 2), ipady=1)

        self.pill = tk.Label(
            main_frame, text="Заглох", bg=BG, fg=RED_COL,
            font=("Segoe UI", 8, "bold"),
        )
        self.pill.pack(pady=(1, 1))

        self.start_btn = tk.Button(
            main_frame, text="▶  Старт (F6)", command=self.toggle_clicking,
            bg=GREEN_COL, fg="#fff",
            activebackground="#2b552c", activeforeground="#fff",
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        self.start_btn.pack(fill="x", pady=(0, 2), ipady=4)

        tk.Label(main_frame, text="F2 — точка · F6 — старт/стоп",
                 bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(pady=(0, 1))

        # ---- Нижняя панель: Проебать + бирка (market) + @ (usernames) ----
        bottom_row = tk.Frame(main_frame, bg=BG)
        bottom_row.pack(fill="x", pady=(1, 0))

        # «Проебать» — растягивается, своя радужная обводка
        self.proebat_outer = tk.Frame(bottom_row, bg="#ef4444", bd=0)
        self.proebat_outer.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.proebat_btn = tk.Button(
            self.proebat_outer, text="Проебать",
            command=lambda: webbrowser.open("https://huevo.su/apps/1"),
            bg=SURFACE, fg=TEXT_MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_TINY, cursor="hand2", highlightthickness=0,
        )
        self.proebat_btn.pack(fill="both", expand=True, padx=1, pady=1, ipady=1)

        # Квадратная кнопка-бирка → market (24×24)
        self.market_outer = tk.Frame(bottom_row, bg="#f97316", bd=0, width=24, height=24)
        self.market_outer.pack(side="left", padx=(0, 4))
        self.market_outer.pack_propagate(False)

        self.market_btn = tk.Button(
            self.market_outer, text="🏷",
            command=lambda: webbrowser.open("https://huevo.su/market"),
            bg=SURFACE, fg=TEXT_MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=("Segoe UI Emoji", 8), cursor="hand2", highlightthickness=0,
            padx=0, pady=0,
        )
        self.market_btn.pack(fill="both", expand=True, padx=1, pady=1)

        # Квадратная кнопка @ → settings/usernames (24×24)
        self.usernames_outer = tk.Frame(bottom_row, bg="#eab308", bd=0, width=24, height=24)
        self.usernames_outer.pack(side="left")
        self.usernames_outer.pack_propagate(False)

        self.usernames_btn = tk.Button(
            self.usernames_outer, text="@",
            command=lambda: webbrowser.open("https://huevo.su/settings/usernames"),
            bg=SURFACE, fg=TEXT_MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=("Consolas", 9, "bold"), cursor="hand2", highlightthickness=0,
            padx=0, pady=0,
        )
        self.usernames_btn.pack(fill="both", expand=True, padx=1, pady=1)

        self.toast_label = tk.Label(
            main_frame, text="", bg=BG, fg=BG,
            font=("Segoe UI", 8, "bold"), anchor="center", bd=0, pady=0
        )
        self.toast_label.pack(side="bottom", fill="x")

    # ------------------------------------------------------
    def _start_rainbow_animation(self):
        self.rainbow_colors = ["#ef4444", "#f97316", "#eab308", "#10b981", "#06b6d4", "#6366f1", "#a855f7"]
        n = len(self.rainbow_colors)
        # у каждой кнопки своя фаза, чтобы переливались не синхронно
        self.rainbow_idx_proebat = 0
        self.rainbow_idx_market = 2
        self.rainbow_idx_usernames = 4

        def update_border():
            try:
                self.rainbow_idx_proebat = (self.rainbow_idx_proebat + 1) % n
                self.rainbow_idx_market = (self.rainbow_idx_market + 1) % n
                self.rainbow_idx_usernames = (self.rainbow_idx_usernames + 1) % n

                self.proebat_outer.config(bg=self.rainbow_colors[self.rainbow_idx_proebat])
                self.market_outer.config(bg=self.rainbow_colors[self.rainbow_idx_market])
                self.usernames_outer.config(bg=self.rainbow_colors[self.rainbow_idx_usernames])

                self.root.after(200, update_border)
            except Exception:
                pass
        update_border()

    def _on_card_enter(self, event=None):
        if self.tab_active:
            self.exp_day_val.config(text=f"{self.stat_day}/90k")
            self.exp_clicks_val.config(text=self.stat_clicks)
            self.exp_total_val.config(text=self.stat_total)

            self.expanded_card.place(x=12, y=32, relwidth=1, width=-24, height=72)
            self.expanded_card.lift()

    def _on_card_leave(self, event=None):
        self.root.after(100, self._check_leave)

    def _check_leave(self):
        try:
            rx = self.root.winfo_pointerx()
            ry = self.root.winfo_pointery()
            bx = self.balance_card.winfo_rootx()
            by = self.balance_card.winfo_rooty()
            bw = self.balance_card.winfo_width()

            if not (bx <= rx <= bx + bw and by <= ry <= by + 104):
                self.expanded_card.place_forget()
        except Exception:
            pass

    def _trigger_cat_bounce(self):
        if not self.cat_frames:
            return
        def play_frame(idx):
            if idx < len(self.cat_frames):
                self.balance_label.config(image=self.cat_frames[idx])
                self.root.after(35, lambda: play_frame(idx + 1))
            else:
                if self.tab_active and self.cat_photo_normal:
                    self.balance_label.config(image=self.cat_photo_normal)
        play_frame(0)

    def toggle_timer_mode(self):
        if self.timer_mode == "fixed":
            self.timer_mode = "random"
            self.fixed_container.pack_forget()
            self.rand_container.pack(fill="x")
            self.mode_btn.config(text="инт. клика", fg=TEXT)
        else:
            self.timer_mode = "fixed"
            self.rand_container.pack_forget()
            self.fixed_container.pack(fill="x")
            self.mode_btn.config(text="таймер-клик", fg=TEXT_MUTED)

    def open_sync_modal(self):
        modal = tk.Toplevel(self.root)
        modal.overrideredirect(True)
        modal.geometry("380x470")
        modal.configure(bg=BG)
        modal.attributes("-topmost", True)
        modal.resizable(False, False)

        ico_path = resource_path("icon.ico")
        if os.path.exists(ico_path):
            try:
                modal.iconbitmap(ico_path)
            except Exception:
                pass

        modal_title = tk.Frame(modal, bg=BG, height=28)
        modal_title.pack(fill="x", side="top")
        modal_title.pack_propagate(False)

        tk.Label(modal_title, text="Синхронизация баланса", bg=BG, fg=TEXT_MUTED,
                 font=FONT_TITLE).pack(side="left", padx=10)

        close_modal_btn = tk.Button(modal_title, text="✕", command=modal.destroy,
                                    bg=BG, fg=TEXT_MUTED, activebackground=RED_COL,
                                    activeforeground="#fff", relief="flat", bd=0, font=FONT_TINY, width=3)
        close_modal_btn.pack(side="right", fill="y")

        def start_move_modal(event):
            modal.x = event.x
            modal.y = event.y
        def do_move_modal(event):
            x = modal.winfo_x() + (event.x - modal.x)
            y = modal.winfo_y() + (event.y - modal.y)
            modal.geometry(f"+{x}+{y}")
        modal_title.bind("<Button-1>", start_move_modal)
        modal_title.bind("<B1-Motion>", do_move_modal)

        modal_body = tk.Frame(modal, bg=BG)
        modal_body.pack(fill="both", expand=True, padx=16, pady=8)

        tk.Label(
            modal_body, text="Инструкция по синхронизации",
            bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 4))

        info_text = (
            "1. Установите расширение Браузера Tampermonkey.\n"
            "2. Создайте новый скрипт и вставьте код ниже.\n"
            "3. Откройте вкладку huevo.su/clicker — баланс, аватар,\n"
            "   никнейм и статистика будут передаваться в кликер.\n"
            "4. Данные шлёт ТОЛЬКО активная вкладка — баланс не будет\n"
            "   прыгать при открытии нескольких вкладок.\n"
            "5. Уведомления о монетках приходят мгновенно (MutationObserver)."
        )
        tk.Label(
            modal_body, text=info_text, bg=BG, fg=TEXT_MUTED,
            font=FONT_TINY, justify="left"
        ).pack(anchor="w", pady=(0, 8))

        code_header = tk.Frame(modal_body, bg=BG)
        code_header.pack(fill="x", pady=(0, 2))

        tk.Label(
            code_header, text="Код скрипта Tampermonkey:",
            bg=BG, fg=TEXT_MUTED, font=FONT_TINY
        ).pack(side="left")

        script_code = (
            "// ==UserScript==\n"
            "// @name         HuEvo Clicker Full Sync\n"
            "// @namespace    http://tampermonkey.net/\n"
            "// @version      1.6\n"
            "// @match        https://huevo.su/clicker*\n"
            "// @grant        none\n"
            "// ==/UserScript==\n\n"
            "(function() {\n"
            "    'use strict';\n\n"
            "    // ---------- 1. Мгновенная отправка тостов через MutationObserver ----------\n"
            "    function sendToast(toastText) {\n"
            "        if (!toastText) return;\n"
            "        const url = 'http://127.0.0.1:58321/update?toast=' + encodeURIComponent(toastText);\n"
            "        fetch(url).catch(() => {});\n"
            "    }\n\n"
            "    function attachToastObserver() {\n"
            "        const toastEl = document.getElementById('hue-toast');\n"
            "        if (!toastEl) {\n"
            "            setTimeout(attachToastObserver, 1000);\n"
            "            return;\n"
            "        }\n"
            "        let lastText = '';\n"
            "        const obs = new MutationObserver(() => {\n"
            "            const visible = toastEl.style.display !== 'none' && toastEl.innerText.trim();\n"
            "            if (visible && toastEl.innerText !== lastText) {\n"
            "                lastText = toastEl.innerText;\n"
            "                sendToast(toastEl.innerText);\n"
            "            }\n"
            "            if (!visible) {\n"
            "                lastText = '';\n"
            "            }\n"
            "        });\n"
            "        obs.observe(toastEl, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['style'] });\n"
            "    }\n"
            "    attachToastObserver();\n\n"
            "    // ---------- 2. Периодическая отправка баланса (только активная вкладка) ----------\n"
            "    setInterval(() => {\n"
            "        if (!document.hasFocus()) return;\n\n"
            "        const el = document.getElementById('ck-balance');\n"
            "        const dayEl = document.getElementById('ck-day');\n"
            "        const clicksEl = document.getElementById('ck-clicks');\n"
            "        const totalEl = document.getElementById('ck-total');\n"
            "        const userEl = document.querySelector('.mh-user-name');\n"
            "        const avEl = document.querySelector('.mh-user-av');\n\n"
            "        const balanceText = el ? el.innerText : '';\n"
            "        if (!balanceText) return;\n\n"
            "        const dayText = dayEl ? dayEl.innerText : '0';\n"
            "        const clicksText = clicksEl ? clicksEl.innerText : '0';\n"
            "        const totalText = totalEl ? totalEl.innerText : '0';\n"
            "        const userText = userEl ? userEl.innerText : '';\n"
            "        let avUrl = avEl ? avEl.src : '';\n"
            "        if (avUrl && avUrl.startsWith('/')) {\n"
            "            avUrl = window.location.origin + avUrl;\n"
            "        }\n\n"
            "        const url = 'http://127.0.0.1:58321/update?balance=' + encodeURIComponent(balanceText)\n"
            "            + '&day=' + encodeURIComponent(dayText)\n"
            "            + '&clicks=' + encodeURIComponent(clicksText)\n"
            "            + '&total=' + encodeURIComponent(totalText)\n"
            "            + '&user=' + encodeURIComponent(userText)\n"
            "            + '&av=' + encodeURIComponent(avUrl);\n\n"
            "        fetch(url).catch(() => {});\n"
            "    }, 1000);\n"
            "})();"
        )

        copy_icon_btn = tk.Button(
            code_header, text="📋",
            command=lambda: self._copy_to_clipboard(script_code, copy_icon_btn, is_icon=True),
            bg=SURFACE, fg=TEXT, activebackground=BORDER, activeforeground=TEXT,
            relief="flat", bd=0, font=("Segoe UI", 9), cursor="hand2",
            width=3, highlightthickness=1, highlightbackground=BORDER
        )
        copy_icon_btn.pack(side="right")

        text_frame = tk.Frame(modal_body, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        text_frame.pack(fill="both", expand=True, pady=(4, 8))

        script_box = tk.Text(
            text_frame, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, font=("Consolas", 8), wrap="none"
        )
        script_box.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        script_box.insert("1.0", script_code)
        script_box.config(state="disabled")

        copy_btn = tk.Button(
            modal_body, text="Скопировать скрипт полностью",
            command=lambda: self._copy_to_clipboard(script_code, copy_btn, is_icon=False),
            bg=ACCENT, fg="#fff", activebackground=ACCENT_HOV, activeforeground="#fff",
            relief="flat", bd=0, font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        copy_btn.pack(fill="x", pady=(0, 8), ipady=6)

    def _copy_to_clipboard(self, text, btn, is_icon=False):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        if is_icon:
            btn.config(text="✓", bg=GREEN_COL, fg="#fff")
            self.root.after(2000, lambda: btn.config(text="📋", bg=SURFACE, fg=TEXT))
        else:
            btn.config(text="✓ Скопировано в буфер обмена", bg=GREEN_COL)
            self.root.after(2000, lambda: btn.config(text="Скопировать скрипт полностью", bg=ACCENT))

    def _start_local_server(self):
        outer = self
        class LocalHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/update":
                    query = urllib.parse.parse_qs(parsed.query)
                    bal_str = query.get("balance", [""])[0]
                    toast_str = query.get("toast", [""])[0]

                    outer.stat_day = query.get("day", ["0"])[0]
                    outer.stat_clicks = query.get("clicks", ["0"])[0]
                    outer.stat_total = query.get("total", ["0"])[0]

                    user_str = query.get("user", [""])[0]
                    av_url = query.get("av", [""])[0]

                    if bal_str:
                        outer._update_balance_from_web(bal_str, user_str, av_url)
                    if toast_str:
                        outer._show_toast(toast_str)

                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, format, *args):
                pass

        try:
            server = HTTPServer(("127.0.0.1", 58321), LocalHandler)
            server.serve_forever()
        except Exception:
            pass

    def _update_balance_from_web(self, bal_str, user_str="", av_url=""):
        is_first_active = not self.tab_active
        self.tab_active = True
        self.last_update_time = time.time()

        try:
            bal = int(re.sub(r"\D", "", bal_str))
            self.current_bal_text = f"{bal:,}".replace(",", " ")

            short_user = ""
            if user_str:
                clean_u = user_str.strip()
                short_user = (clean_u[:3] + "...") if len(clean_u) > 3 else clean_u

            if av_url and av_url.startswith('/'):
                av_url = "https://huevo.su" + av_url

            if av_url and av_url != self.last_avatar_url and PIL_AVAILABLE:
                self.last_avatar_url = av_url
                try:
                    req = urllib.request.Request(av_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=3) as response:
                        img_data = response.read()
                        im = Image.open(io.BytesIO(img_data)).convert("RGBA")
                        im = im.resize((20, 20), Image.Resampling.LANCZOS)

                        mask = Image.new('L', (20, 20), 0)
                        draw = ImageDraw.Draw(mask)
                        draw.ellipse((0, 0, 20, 20), fill=255)
                        im.putalpha(mask)

                        self.avatar_photo = ImageTk.PhotoImage(im)
                except Exception:
                    self.avatar_photo = None

            def _do():
                if is_first_active and self.cat_photo_normal:
                    self.balance_label.config(image=self.cat_photo_normal)

                self.balance_label.config(
                    text=f" {self.current_bal_text}", fg=TEXT,
                )
                self.balance_card.config(bg=SURFACE)

                if short_user:
                    self.user_label.config(text=short_user)
                if self.avatar_photo:
                    self.avatar_label.config(image=self.avatar_photo)

                if self.last_balance is not None and bal != self.last_balance:
                    self._trigger_cat_bounce()
                self.last_balance = bal
            self.root.after(0, _do)
        except Exception:
            pass

    def _show_toast(self, toast_str):
        def _do():
            if self.toast_anim_id:
                self.root.after_cancel(self.toast_anim_id)

            self._trigger_cat_bounce()
            self.toast_label.config(text=toast_str, bg=GREEN_COL, fg="#ffffff")

            def step_in(p):
                if p <= 5:
                    self.toast_label.config(pady=p)
                    self.toast_anim_id = self.root.after(15, lambda: step_in(p + 1))
                else:
                    self.toast_anim_id = self.root.after(5000, lambda: step_out(5))

            def step_out(p):
                if p >= 0:
                    self.toast_label.config(pady=p)
                    self.toast_anim_id = self.root.after(15, lambda: step_out(p - 1))
                else:
                    self.toast_label.config(text="", bg=BG, fg=BG, pady=0)
                    self.toast_anim_id = None

            step_in(0)

        try:
            self.root.after(0, _do)
        except tk.TclError:
            pass

    def _connection_checker(self):
        while True:
            time.sleep(1)
            if self.last_update_time > 0 and (time.time() - self.last_update_time > 6):
                self.tab_active = False
                self.last_balance = None
                self.last_avatar_url = ""
                def _do():
                    if self.cat_photo_dim:
                        self.balance_label.config(image=self.cat_photo_dim)
                    self.balance_label.config(text=" Вкладка не найдена", fg=TEXT_MUTED)
                    self.user_label.config(text="")
                    self.avatar_label.config(image="")
                    self.expanded_card.place_forget()
                try:
                    self.root.after(0, _do)
                except tk.TclError:
                    break

    def add_point(self):
        x, y = get_cursor_pos()
        self.points.append((x, y))
        self.listbox.insert(tk.END, f"{x:>5},{y:>5}")

    def clear_points(self):
        self.points.clear()
        self.listbox.delete(0, tk.END)

    def get_interval_seconds(self):
        try:
            m  = int(self.min_var.get() or 0)
            s  = int(self.sec_var.get() or 0)
            ms = int(self.ms_var.get() or 0)
            total = m * 60 + s + ms / 1000.0
            return total if total > 0 else 0.0
        except ValueError:
            return 0.0

    def get_random_interval_seconds(self):
        try:
            lo = int(self.rand_min_var.get() or 0)
            hi = int(self.rand_max_var.get() or 0)
        except ValueError:
            return 0.0
        if lo < 0: lo = 0
        if hi < lo: lo, hi = hi, lo
        return random.randint(lo, hi) / 1000.0

    def toggle_clicking(self):
        if self.is_running:
            self.is_running = False
            self.root.after(0, lambda: self.pill.config(text="Заглох", fg=RED_COL))
            self.root.after(0, lambda: self.start_btn.config(
                text="▶  Старт (F6)", bg=GREEN_COL, activebackground="#2b552c"))
        else:
            if not self.points:
                self.root.after(0, lambda: self.pill.config(text="⚠ нет точек", fg=YELLOW))
                return
            self.is_running = True
            self.root.after(0, lambda: self.pill.config(text="Шуршит", fg=GREEN_COL))
            self.root.after(0, lambda: self.start_btn.config(
                text="■  Стоп (F6)", bg=RED_COL, activebackground="#b91c1c"))
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _loop(self):
        send_input = user32.SendInput
        send_input.argtypes = (wintypes.UINT,
                               ctypes.POINTER(INPUT),
                               ctypes.c_int)
        send_input.restype = wintypes.UINT

        points = self.points
        sw, sh = _SCREEN_W, _SCREEN_H

        cache = {p: _build_click_inputs(p[0], p[1], sw, sh) for p in points}
        n = len(points)
        i = 0
        tick = 0
        next_t = time.perf_counter()

        while self.is_running:
            p = points[i % n]
            send_input(3, cache[p], ctypes.sizeof(INPUT))
            i += 1

            if self.timer_mode == "random":
                delay = self.get_random_interval_seconds()
                if delay > 0:
                    time.sleep(delay)
                else:
                    tick += 1
                    if (tick & 31) == 0:
                        time.sleep(0)
            else:
                interval = self.get_interval_seconds()
                if interval > 0:
                    next_t += interval
                    now = time.perf_counter()
                    if next_t > now:
                        time.sleep(next_t - now)
                    else:
                        next_t = now
                else:
                    tick += 1
                    if (tick & 31) == 0:
                        time.sleep(0)


if __name__ == "__main__":
    root = tk.Tk()
    app = HuEvoClicker(root)
    root.mainloop()
