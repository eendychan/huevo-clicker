import tkinter as tk
from tkinter import ttk
import keyboard
import threading
import time
import ctypes
from ctypes import wintypes

# ==========================================================
#  WinAPI
# ==========================================================
user32 = ctypes.WinDLL("user32", use_last_error=True)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203

# Для EnumWindows
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def click_at(x, y):
    """Обычный режим: глобальный клик с перемещением курсора."""
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def get_window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def is_window_visible(hwnd):
    return bool(user32.IsWindowVisible(hwnd))


def find_windows_by_title(part):
    """Возвращает список hwnd окон, чей заголовок содержит part."""
    result = []

    @WNDENUMPROC
    def enum_proc(hwnd, lparam):
        if is_window_visible(hwnd):
            title = get_window_title(hwnd)
            if part.lower() in title.lower():
                result.append(hwnd)
        return True

    user32.EnumWindows(enum_proc, 0)
    return result


def make_lparam(x, y):
    return (int(y) << 16) | (int(x) & 0xFFFF)


def post_click_to_window(hwnd, x, y):
    """
    Экспериментальный режим: шлём клики напрямую в окно.
    Курсор не трогаем.
    """
    lp = make_lparam(x, y)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)   # MK_LBUTTON = 1
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


# ==========================================================
#  Приложение
# ==========================================================
BG          = "#1e1f22"   # фон окна
SURFACE     = "#2b2d31"   # карточки
SURFACE_2   = "#313338"   # поля ввода
TEXT        = "#e6e6e6"
TEXT_MUTED  = "#9aa0a6"
ACCENT      = "#5865f2"   # Material-indigo
ACCENT_HOV  = "#4752c4"
GREEN       = "#3ba55d"
RED         = "#ed4245"
RADIUS      = 10


class MiniClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("Farm Clicker")
        self.root.geometry("360x560")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.points = []
        self.is_running = False
        self.thread = None
        self.mode = tk.StringVar(value="normal")  # normal | experiment

        self._build_style()
        self._build_ui()

        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

    # ---------- Стили ----------
    def _build_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("BG.TFrame", background=BG)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=BG, foreground=TEXT_MUTED,
                        font=("Segoe UI", 9, "bold"))

        style.configure("TButton",
                        background=SURFACE_2, foreground=TEXT,
                        borderwidth=0, focusthickness=0, focuscolor=SURFACE_2,
                        font=("Segoe UI", 10), padding=(10, 6))
        style.map("TButton",
                  background=[("active", ACCENT_HOV), ("pressed", ACCENT)],
                  foreground=[("active", "#ffffff")])

        style.configure("Accent.TButton",
                        background=ACCENT, foreground="#ffffff",
                        font=("Segoe UI", 10, "bold"), padding=(10, 6))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_HOV), ("pressed", ACCENT)])

        style.configure("TEntry",
                        fieldbackground=SURFACE_2, foreground=TEXT,
                        bordercolor=SURFACE_2, insertcolor=TEXT,
                        padding=4)

        style.configure("TListbox",
                        background=SURFACE_2, foreground=TEXT,
                        borderwidth=0, highlightthickness=0,
                        font=("Consolas", 9))

    # ---------- UI ----------
    def _build_ui(self):
        root = self.root

        # Заголовок
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(header, text="🎯 Farm Clicker", bg=BG, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(header, text="F2 — добавить точку · F6 — старт/стоп",
                 bg=BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        # ---- Раздел "Режимы" ----
        self._section_label("РЕЖИМ")
        mode_frame = tk.Frame(root, bg=SURFACE, highlightthickness=0)
        mode_frame.pack(fill="x", padx=16, pady=(0, 10))
        mode_frame.configure(padx=6, pady=6)

        self.btn_normal = self._chip(mode_frame, "Обычный", "normal")
        self.btn_exp    = self._chip(mode_frame, "Эксперимент", "experiment")
        self.btn_normal.pack(side="left", padx=(0, 6))
        self.btn_exp.pack(side="left")

        # Поле для заголовка окна (только для эксперимента)
        self.window_title_var = tk.StringVar(value="")
        self.exp_frame = tk.Frame(root, bg=BG)
        tk.Label(self.exp_frame, text="Заголовок окна (содержит)",
                 bg=BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        tk.Entry(self.exp_frame, textvariable=self.window_title_var,
                 bg=SURFACE_2, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Consolas", 10)
                 ).pack(fill="x", padx=16, pady=(2, 0), ipady=4)

        # ---- Раздел "Точки" ----
        self._section_label("ТОЧКИ")
        tk.Button(root, text="➕  Добавить точку (F2)", command=self.add_point,
                  bg=SURFACE_2, fg=TEXT, activebackground=ACCENT_HOV,
                  activeforeground="#fff", relief="flat", bd=0,
                  font=("Segoe UI", 10), cursor="hand2"
                  ).pack(fill="x", padx=16, pady=(0, 6), ipady=6)

        list_wrap = tk.Frame(root, bg=SURFACE_2, highlightthickness=0)
        list_wrap.pack(fill="x", padx=16)
        self.listbox = tk.Listbox(list_wrap, height=5,
                                  bg=SURFACE_2, fg=TEXT,
                                  selectbackground=ACCENT, selectforeground="#fff",
                                  bd=0, highlightthickness=0,
                                  font=("Consolas", 10), activestyle="none")
        self.listbox.pack(fill="x", padx=6, pady=6)

        tk.Button(root, text="🗑  Очистить точки", command=self.clear_points,
                  bg=SURFACE_2, fg=TEXT_MUTED, activebackground="#3a3d43",
                  activeforeground=TEXT, relief="flat", bd=0,
                  font=("Segoe UI", 9), cursor="hand2"
                  ).pack(fill="x", padx=16, pady=(6, 0), ipady=4)

        # ---- Раздел "Интервал" ----
        self._section_label("ИНТЕРВАЛ")
        time_frame = tk.Frame(root, bg=SURFACE)
        time_frame.pack(fill="x", padx=16)
        time_frame.configure(padx=8, pady=8)

        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="0")
        self.ms_var  = tk.StringVar(value="100")

        def entry(parent, var):
            e = tk.Entry(parent, textvariable=var, width=4, justify="center",
                         bg=SURFACE_2, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=("Consolas", 11), bd=0)
            e.pack(side="left", ipady=4, padx=(0, 2))
            return e

        entry(time_frame, self.min_var)
        tk.Label(time_frame, text="мин", bg=SURFACE, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        entry(time_frame, self.sec_var)
        tk.Label(time_frame, text="сек", bg=SURFACE, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        entry(time_frame, self.ms_var)
        tk.Label(time_frame, text="мс", bg=SURFACE, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        # ---- Статус ----
        self.status_frame = tk.Frame(root, bg=BG)
        self.status_frame.pack(fill="x", padx=16, pady=(14, 6))

        self.status_pill = tk.Label(
            self.status_frame, text="  ●  Выключено  ",
            bg=RED, fg="#ffffff", font=("Segoe UI", 10, "bold"),
            padx=10, pady=4,
        )
        self.status_pill.pack()

        # ---- Кнопка старт/стоп ----
        self.start_btn = tk.Button(
            root, text="▶   Старт  (F6)", command=self.toggle_clicking,
            bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOV,
            activeforeground="#ffffff", relief="flat", bd=0,
            font=("Segoe UI", 11, "bold"), cursor="hand2",
        )
        self.start_btn.pack(fill="x", padx=16, pady=(0, 16), ipady=10)

    def _section_label(self, text):
        tk.Label(self.root, text=text, bg=BG, fg=TEXT_MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(8, 4))

    def _chip(self, parent, text, value):
        chip = tk.Label(
            parent, text=text, bg=SURFACE_2, fg=TEXT,
            font=("Segoe UI", 10), padx=14, pady=6, cursor="hand2",
        )
        chip.bind("<Button-1>", lambda e, v=value: self.set_mode(v))
        return chip

    def set_mode(self, mode):
        self.mode.set(mode)

        for chip, val in ((self.btn_normal, "normal"), (self.btn_exp, "experiment")):
            if val == mode:
                chip.config(bg=ACCENT, fg="#ffffff")
            else:
                chip.config(bg=SURFACE_2, fg=TEXT)

        if mode == "experiment":
            self.exp_frame.pack(fill="x", padx=0, pady=(0, 10),
                                before=self.listbox.master)
        else:
            self.exp_frame.pack_forget()

    # ---------- Точки ----------
    def add_point(self):
        x, y = get_cursor_pos()
        self.points.append((x, y))
        self.listbox.insert(tk.END, f"  {x:>5}, {y:>5}")

    def clear_points(self):
        self.points.clear()
        self.listbox.delete(0, tk.END)

    # ---------- Интервал ----------
    def get_interval_seconds(self):
        try:
            m  = int(self.min_var.get() or 0)
            s  = int(self.sec_var.get() or 0)
            ms = int(self.ms_var.get() or 0)
            total = m * 60 + s + ms / 1000.0
            return total if total > 0 else 0.0
        except ValueError:
            return 0.0

    # ---------- Старт/стоп ----------
    def toggle_clicking(self):
        if self.is_running:
            self.is_running = False
            self.status_pill.config(text="  ●  Выключено  ", bg=RED)
            self.start_btn.config(text="▶   Старт  (F6)", bg=ACCENT)
        else:
            if not self.points:
                return
            if self.mode.get() == "experiment" and not self.window_title_var.get().strip():
                self.status_pill.config(text="  ⚠  Укажи заголовок окна  ", bg="#faa61a")
                return

            self.is_running = True
            self.status_pill.config(text="  ●  Работает  ", bg=GREEN)
            self.start_btn.config(text="■   Стоп  (F6)", bg=RED)

            target = self.click_loop_normal if self.mode.get() == "normal" else self.click_loop_experiment
            self.thread = threading.Thread(target=target, daemon=True)
            self.thread.start()

    # ---------- Циклы ----------
    def click_loop_normal(self):
        while self.is_running:
            interval = self.get_interval_seconds()
            t0 = time.perf_counter()
            for (x, y) in self.points:
                if not self.is_running:
                    break
                click_at(x, y)
            self._sleep_remainder(interval, t0)

    def click_loop_experiment(self):
        title_part = self.window_title_var.get().strip()

        while self.is_running:
            hwnds = find_windows_by_title(title_part)
            if not hwnds:
                self._set_status_async("  ⚠  Окно не найдено  ", "#faa61a")
                time.sleep(0.5)
                continue

            interval = self.get_interval_seconds()
            t0 = time.perf_counter()

            for hwnd in hwnds:
                for (x, y) in self.points:
                    if not self.is_running:
                        break
                    # Координаты шлём как есть — их можно задать и отрицательными,
                    # если окно где-то далеко.
                    post_click_to_window(hwnd, x, y)

            self._sleep_remainder(interval, t0)

    def _sleep_remainder(self, interval, t0):
        elapsed = time.perf_counter() - t0
        remaining = interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        else:
            time.sleep(0)

    def _set_status_async(self, text, color):
        # Из потока небезопасно трогать tk напрямую
        self.root.after(0, lambda: self.status_pill.config(text=text, bg=color))


if __name__ == "__main__":
    root = tk.Tk()
    app = MiniClicker(root)
    app.set_mode("normal")  # начальное состояние чипа
    root.mainloop()
