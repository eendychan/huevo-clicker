import tkinter as tk
import keyboard
import threading
import time
import random
import json
import os
import re
import sys
import ctypes
from ctypes import wintypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

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
BG         = "#121214"  # Глубокий матовый фон
SURFACE    = "#1a1b1e"  # Карточки и элементы
SURFACE_HOV= "#222327"  # Эффект при наведении
BORDER     = "#2c2d32"  # Строгие тонкие границы
TEXT       = "#f4f4f5"  # Основной белый текст
TEXT_MUTED = "#71717a"  # Второстепенный серый текст
ACCENT     = "#6366f1"  # Строгий чистый акцент (Indigo)
ACCENT_HOV = "#4f46e5"  # Ховер акцента
GREEN      = "#10b981"  # Статус активности
RED        = "#ef4444"  # Статус выключения / ошибки

FONT_TITLE = ("Segoe UI", 10, "bold")
FONT_BODY  = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 9)
FONT_TINY  = ("Segoe UI", 8)


# ==========================================================
#  Приложение
# ==========================================================
class HuEvoClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("huEVO clicker")
        self.root.geometry("250x430")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.points = []
        self.is_running = False
        self.thread = None
        self.timer_mode = "fixed"
        self.last_update_time = 0

        self._build_ui()

        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

        # Запускаем локальный HTTP-сервер для синхронизации баланса
        threading.Thread(target=self._start_local_server, daemon=True).start()
        threading.Thread(target=self._connection_checker, daemon=True).start()

    # ------------------------------------------------------
    def _build_ui(self):
        root = self.root

        # Шапка
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="◆", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(header, text="huEVO clicker", bg=BG, fg=TEXT,
                 font=FONT_TITLE).pack(side="left")

        # ---- Интерактивная плашка баланса (Кликабельная карточка) ----
        self.balance_card = tk.Frame(
            root, bg=SURFACE, 
            highlightbackground=BORDER, highlightthickness=1,
            cursor="hand2"
        )
        self.balance_card.pack(fill="x", padx=12, pady=(4, 6))

        self.balance_label = tk.Label(
            self.balance_card, text="💰 Ожидание вкладки...", bg=SURFACE, fg=TEXT_MUTED,
            font=("Consolas", 9, "bold"), pady=8
        )
        self.balance_label.pack()

        # События клика и наведения для карточки баланса
        for widget in (self.balance_card, self.balance_label):
            widget.bind("<Button-1>", lambda e: self.open_sync_modal())
            widget.bind("<Enter>", lambda e: self.balance_card.config(bg=SURFACE_HOV))
            widget.bind("<Leave>", lambda e: self.balance_card.config(bg=SURFACE))
            widget.config(cursor="hand2")

        # ---- Точки ----
        tk.Button(
            root, text="+  Добавить точку (F2)", command=self.add_point,
            bg=SURFACE, fg=TEXT, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_BODY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", padx=12, pady=(2, 4), ipady=4)

        list_wrap = tk.Frame(root, bg=SURFACE,
                             highlightbackground=BORDER, highlightthickness=1)
        list_wrap.pack(fill="x", padx=12)

        self.listbox = tk.Listbox(
            list_wrap, height=4, bg=SURFACE, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#fff",
            bd=0, highlightthickness=0, font=FONT_MONO, activestyle="none",
        )
        self.listbox.pack(fill="x", padx=4, pady=4)

        tk.Button(
            root, text="✕  Очистить точки", command=self.clear_points,
            bg=SURFACE, fg=TEXT_MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_TINY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", padx=12, pady=(4, 0), ipady=2)

        # ---- Интервал + переключатель ----
        tf = tk.Frame(root, bg=BG)
        tf.pack(fill="x", padx=12, pady=(6, 2))

        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="0")
        self.ms_var  = tk.StringVar(value="50")

        def entry(parent, var, width=3):
            e = tk.Entry(parent, textvariable=var, width=width, justify="center",
                         bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=2, padx=(0, 2))
            return e

        entry(tf, self.min_var)
        tk.Label(tf, text="м", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 4))
        entry(tf, self.sec_var)
        tk.Label(tf, text="с", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 4))
        entry(tf, self.ms_var)
        tk.Label(tf, text="мс", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 6))

        self.mode_switch = self._make_switch(tf)
        self.mode_switch.pack(side="left")

        # ---- Рандом ----
        self.rand_frame = tk.Frame(root, bg=BG)
        self.rand_min_var = tk.StringVar(value="30")
        self.rand_max_var = tk.StringVar(value="120")

        def rentry(parent, var):
            e = tk.Entry(parent, textvariable=var, width=5, justify="center",
                         bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=2, padx=(0, 2))
            return e

        tk.Label(self.rand_frame, text="от", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 2))
        rentry(self.rand_frame, self.rand_min_var)
        tk.Label(self.rand_frame, text="до", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(4, 2))
        rentry(self.rand_frame, self.rand_max_var)
        tk.Label(self.rand_frame, text="мс", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(2, 0))

        # ---- Статус ----
        self.pill = tk.Label(
            root, text="●  Выкл", bg=RED, fg="#fff",
            font=("Segoe UI", 8, "bold"), padx=8, pady=2,
        )
        self.pill.pack(pady=(6, 4))

        # ---- Старт ----
        self.start_btn = tk.Button(
            root, text="▶  Старт (F6)", command=self.toggle_clicking,
            bg=ACCENT, fg="#fff",
            activebackground=ACCENT_HOV, activeforeground="#fff",
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        self.start_btn.pack(fill="x", padx=12, pady=(0, 6), ipady=6)

        tk.Label(root, text="F2 — точка · F6 — старт/стоп",
                 bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(pady=(0, 6))

    # ------------------------------------------------------
    #  Модальное окно с инструкцией и скриптом Tampermonkey
    # ------------------------------------------------------
    def open_sync_modal(self):
        modal = tk.Toplevel(self.root)
        modal.title("Синхронизация баланса")
        modal.geometry("380x440")
        modal.configure(bg=BG)
        modal.attributes("-topmost", True)
        modal.resizable(False, False)

        tk.Label(
            modal, text="Инструкция по синхронизации",
            bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=16, pady=(16, 4))

        info_text = (
            "1. Установите расширение Tampermonkey в браузер.\n"
            "2. Создайте новый скрипт и вставьте код ниже.\n"
            "3. Откройте вкладку huevo.su/clicker — баланс\n"
            "   будет автоматически передаваться в кликер."
        )
        tk.Label(
            modal, text=info_text, bg=BG, fg=TEXT_MUTED,
            font=FONT_TINY, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # Поле со скриптом
        script_code = (
            "// ==UserScript==\n"
            "// @name         HuEvo Clicker Balance Sync\n"
            "// @namespace    http://tampermonkey.net/\n"
            "// @version      1.0\n"
            "// @match        https://huevo.su/clicker*\n"
            "// @grant        none\n"
            "// ==/UserScript==\n\n"
            "(function() {\n"
            "    'use strict';\n"
            "    setInterval(() => {\n"
            "        const el = document.getElementById('ck-balance');\n"
            "        if (el) {\n"
            "            fetch(`http://127.0.0.1:58321/update?balance=${encodeURIComponent(el.innerText)}`)\n"
            "                .catch(() => {});\n"
            "        }\n"
            "    }, 1500);\n"
            "})();"
        )

        text_frame = tk.Frame(modal, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        text_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        script_box = tk.Text(
            text_frame, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, font=("Consolas", 8), wrap="none"
        )
        script_box.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        script_box.insert("1.0", script_code)
        script_box.config(state="disabled") # Только для чтения

        # Кнопка копирования
        copy_btn = tk.Button(
            modal, text="Скопировать скрипт", 
            command=lambda: self._copy_to_clipboard(script_code, copy_btn),
            bg=ACCENT, fg="#fff", activebackground=ACCENT_HOV, activeforeground="#fff",
            relief="flat", bd=0, font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        copy_btn.pack(fill="x", padx=16, pady=(0, 16), ipady=6)

    def _copy_to_clipboard(self, text, btn):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        btn.config(text="✓ Скопировано в буфер обмена", bg=GREEN)
        self.root.after(2000, lambda: btn.config(text="Скопировать скрипт", bg=ACCENT))

    # ------------------------------------------------------
    #  Локальный сервер для приема данных от браузера
    # ------------------------------------------------------
    def _start_local_server(self):
        outer = self
        class LocalHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/update":
                    query = urllib.parse.parse_qs(parsed.query)
                    if "balance" in query:
                        bal_str = query["balance"][0]
                        outer._update_balance_from_web(bal_str)
                
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

    def _update_balance_from_web(self, bal_str):
        self.last_update_time = time.time()
        try:
            bal = int(re.sub(r"\D", "", bal_str))
            def _do():
                self.balance_label.config(
                    text=f"💰 {bal:,}".replace(",", " "), fg=TEXT,
                )
                self.balance_card.config(bg=SURFACE)
            self.root.after(0, _do)
        except Exception:
            pass

    def _connection_checker(self):
        while True:
            time.sleep(1)
            if self.last_update_time > 0 and (time.time() - self.last_update_time > 6):
                def _do():
                    self.balance_label.config(text="💰 Вкладка не найдена", fg=TEXT_MUTED)
                try:
                    self.root.after(0, _do)
                except tk.TclError:
                    break

    # ------------------------------------------------------
    #  Переключатель Фикс / Рандом
    # ------------------------------------------------------
    def _make_switch(self, parent):
        wrap = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)

        self.sw_fixed  = tk.Label(wrap, text="Ф", bg=ACCENT, fg="#fff", font=("Segoe UI", 8, "bold"), width=2, cursor="hand2")
        self.sw_random = tk.Label(wrap, text="Р", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 8, "bold"), width=2, cursor="hand2")
        self.sw_fixed.pack(side="left")
        self.sw_random.pack(side="left")

        self.sw_fixed.bind("<Button-1>",  lambda e: self._set_timer_mode("fixed"))
        self.sw_random.bind("<Button-1>", lambda e: self._set_timer_mode("random"))
        return wrap

    def _set_timer_mode(self, mode):
        self.timer_mode = mode
        if mode == "fixed":
            self.sw_fixed.config(bg=ACCENT, fg="#fff")
            self.sw_random.config(bg=SURFACE, fg=TEXT_MUTED)
            self.rand_frame.pack_forget()
        else:
            self.sw_fixed.config(bg=SURFACE, fg=TEXT_MUTED)
            self.sw_random.config(bg=ACCENT, fg="#fff")
            self.rand_frame.pack(fill="x", padx=12, pady=(2, 0), before=self.pill)

    # ------------------------------------------------------
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

    # ------------------------------------------------------
    def toggle_clicking(self):
        if self.is_running:
            self.is_running = False
            self.root.after(0, lambda: self.pill.config(text="●  Выкл", bg=RED))
            self.root.after(0, lambda: self.start_btn.config(
                text="▶  Старт (F6)", bg=ACCENT, activebackground=ACCENT_HOV))
        else:
            if not self.points:
                self.root.after(0, lambda: self.pill.config(text="⚠  нет точек", bg=YELLOW if 'YELLOW' in globals() else "#f59e0b"))
                return
            self.is_running = True
            self.root.after(0, lambda: self.pill.config(text="●  Работа", bg=GREEN))
            self.root.after(0, lambda: self.start_btn.config(
                text="■  Стоп (F6)", bg=RED, activebackground="#dc2626"))
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    # ------------------------------------------------------
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
