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

from tkinterweb import HtmlFrame
from bs4 import BeautifulSoup

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
#  Конфиг
# ==========================================================
def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_app_dir(), "huEvoClicker.config.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ==========================================================
#  Палитра
# ==========================================================
BG         = "#1e1f22"
SURFACE_2  = "#2f3136"
BORDER     = "#3a3d42"
TEXT       = "#f2f3f5"
TEXT_MUTED = "#8b8f96"
ACCENT     = "#5865f2"
ACCENT_HOV = "#4752c4"
GREEN      = "#3ba55d"
RED        = "#ed4245"
YELLOW     = "#faa61a"

FONT_TITLE = ("Unbounded", 10, "bold")
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
        self.root.geometry("600x520")  # Увеличено окно для размещения браузера
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)

        self.points = []
        self.is_running = False
        self.thread = None
        self.timer_mode = "fixed"

        self._build_ui()

        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

        # Запускаем браузер на странице кликера
        self.html_frame.load_website("https://huevo.su/clicker")

        # Автоматическое считывание баланса и перезагрузка каждые 15 секунд
        self.root.after(5000, self._auto_refresh_web_balance)

    # ------------------------------------------------------
    def _build_ui(self):
        root = self.root

        # Левая панель (управление кликером)
        left_panel = tk.Frame(root, bg=BG, width=240)
        left_panel.pack(side="left", fill="y", padx=10, pady=8)
        left_panel.pack_propagate(False)

        # Правая панель (Встроенный браузер)
        right_panel = tk.Frame(root, bg=SURFACE_2, highlightbackground=BORDER, highlightthickness=1)
        right_panel.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=8)

        # ---- Браузер ----
        web_header = tk.Frame(right_panel, bg=SURFACE_2)
        web_header.pack(fill="x", padx=4, pady=2)
        
        tk.Label(web_header, text="Встроенный сайт (huevo.su)", bg=SURFACE_2, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left")
        
        tk.Button(
            web_header, text="↻ Обновить", command=self._refresh_browser,
            bg=ACCENT, fg="#fff", activebackground=ACCENT_HOV, activeforeground="#fff",
            relief="flat", bd=0, font=("Segoe UI", 8, "bold"), cursor="hand2", padx=6
        ).pack(side="right")

        self.html_frame = HtmlFrame(right_panel, messages_enabled=False)
        self.html_frame.pack(fill="both", expand=True)

        # ---- Левая панель: Заголовок ----
        header = tk.Frame(left_panel, bg=BG)
        header.pack(fill="x", pady=(0, 4))
        tk.Label(header, text="✦", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 4))
        tk.Label(header, text="huEVO clicker", bg=BG, fg=TEXT,
                 font=FONT_TITLE).pack(side="left")

        # ---- Баланс ----
        self.balance_label = tk.Label(
            left_panel, text="💰 ---", bg=BG, fg=ACCENT,
            font=("Consolas", 12, "bold"),
        )
        self.balance_label.pack(pady=(4, 6))

        # ---- Точки ----
        tk.Button(
            left_panel, text="+ Добавить точку (F2)", command=self.add_point,
            bg=SURFACE_2, fg=TEXT, activebackground=ACCENT_HOV,
            activeforeground="#fff", relief="flat", bd=0,
            font=FONT_BODY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", pady=(2, 4), ipady=4)

        list_wrap = tk.Frame(left_panel, bg=SURFACE_2,
                             highlightbackground=BORDER, highlightthickness=1)
        list_wrap.pack(fill="x")

        self.listbox = tk.Listbox(
            list_wrap, height=4, bg=SURFACE_2, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#fff",
            bd=0, highlightthickness=0, font=FONT_MONO, activestyle="none",
        )
        self.listbox.pack(fill="x", padx=4, pady=4)

        tk.Button(
            left_panel, text="✕ Очистить", command=self.clear_points,
            bg=SURFACE_2, fg=TEXT_MUTED, activebackground="#3a3d43",
            activeforeground=TEXT, relief="flat", bd=0,
            font=FONT_TINY, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", pady=(4, 0), ipady=2)

        # ---- Интервал ----
        tf = tk.Frame(left_panel, bg=BG)
        tf.pack(fill="x", pady=(6, 2))

        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="0")
        self.ms_var  = tk.StringVar(value="50")

        def entry(parent, var, width=3):
            e = tk.Entry(parent, textvariable=var, width=width, justify="center",
                         bg=SURFACE_2, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=2, padx=(0, 1))
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
        self.rand_frame = tk.Frame(left_panel, bg=BG)
        self.rand_min_var = tk.StringVar(value="30")
        self.rand_max_var = tk.StringVar(value="120")

        def rentry(parent, var):
            e = tk.Entry(parent, textvariable=var, width=5, justify="center",
                         bg=SURFACE_2, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=2, padx=(0, 1))
            return e

        tk.Label(self.rand_frame, text="от", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(0, 2))
        rentry(self.rand_frame, self.rand_min_var)
        tk.Label(self.rand_frame, text="до", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(4, 2))
        rentry(self.rand_frame, self.rand_max_var)
        tk.Label(self.rand_frame, text="мс", bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(side="left", padx=(2, 0))

        # ---- Статус ----
        self.pill = tk.Label(
            left_panel, text="● Выкл", bg=RED, fg="#fff",
            font=("Segoe UI", 8, "bold"), padx=8, pady=2,
        )
        self.pill.pack(pady=(6, 4))

        # ---- Старт ----
        self.start_btn = tk.Button(
            left_panel, text="▶ Старт (F6)", command=self.toggle_clicking,
            bg=ACCENT, fg="#fff",
            activebackground=ACCENT_HOV, activeforeground="#fff",
            relief="flat", bd=0, cursor="hand2",
            font=("Unbounded", 8, "bold"),
        )
        self.start_btn.pack(fill="x", pady=(0, 6), ipady=6)

        tk.Label(left_panel, text="F2 — точка · F6 — старт/стоп",
                 bg=BG, fg=TEXT_MUTED, font=FONT_TINY).pack(pady=(0, 6))

    # ------------------------------------------------------
    #  Логика взаимодействия с встроенным браузером
    # ------------------------------------------------------
    def _refresh_browser(self):
        """Ручная или автоматическая перезагрузка браузера"""
        self.html_frame.load_website("https://huevo.su/clicker")

    def _auto_refresh_web_balance(self):
        """Парсинг HTML внутри встроенного браузера и автообновление"""
        try:
            # Считываем текущий исходный код загруженной в браузер страницы
            html_source = self.html_frame.get_content()
            if html_source:
                soup = BeautifulSoup(html_source, "html.parser")
                el = soup.find("b", id="ck-balance")
                if el:
                    m = re.search(r"\d+", el.text.replace(" ", ""))
                    if m:
                        bal = int(m.group())
                        self.balance_label.config(text=f"💰 {bal:,}".replace(",", " "), fg=ACCENT)
                else:
                    self.balance_label.config(text="💰 Нужен вход", fg=YELLOW)
        except Exception:
            pass

        # Перезагружаем страницу в браузере каждые 15 секунд
        self._refresh_browser()
        self.root.after(15000, self._auto_refresh_web_balance)

    # ------------------------------------------------------
    #  Переключатель Фикс / Рандом
    # ------------------------------------------------------
    def _make_switch(self, parent):
        wrap = tk.Frame(parent, bg=SURFACE_2, highlightbackground=BORDER, highlightthickness=1)

        self.sw_fixed  = tk.Label(wrap, text="Ф", bg=ACCENT, fg="#fff", font=("Segoe UI", 8, "bold"), width=2, cursor="hand2")
        self.sw_random = tk.Label(wrap, text="Р", bg=SURFACE_2, fg=TEXT_MUTED, font=("Segoe UI", 8, "bold"), width=2, cursor="hand2")
        self.sw_fixed.pack(side="left")
        self.sw_random.pack(side="left")

        self.sw_fixed.bind("<Button-1>",  lambda e: self._set_timer_mode("fixed"))
        self.sw_random.bind("<Button-1>", lambda e: self._set_timer_mode("random"))
        return wrap

    def _set_timer_mode(self, mode):
        self.timer_mode = mode
        if mode == "fixed":
            self.sw_fixed.config(bg=ACCENT, fg="#fff")
            self.sw_random.config(bg=SURFACE_2, fg=TEXT_MUTED)
            self.rand_frame.pack_forget()
        else:
            self.sw_fixed.config(bg=SURFACE_2, fg=TEXT_MUTED)
            self.sw_random.config(bg=ACCENT, fg="#fff")
            self.rand_frame.pack(fill="x", pady=(2, 0), before=self.pill)

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
            self.root.after(0, lambda: self.pill.config(text="● Выкл", bg=RED))
            self.root.after(0, lambda: self.start_btn.config(
                text="▶ Старт (F6)", bg=ACCENT, activebackground=ACCENT_HOV))
        else:
            if not self.points:
                self.root.after(0, lambda: self.pill.config(text="⚠ нет точек", bg=YELLOW))
                return
            self.is_running = True
            self.root.after(0, lambda: self.pill.config(text="● Работа", bg=GREEN))
            self.root.after(0, lambda: self.start_btn.config(
                text="■ Стоп (F6)", bg=RED, activebackground="#c03535"))
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
