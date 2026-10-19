import tkinter as tk
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
MOUSEEVENTF_LEFTUP   = 0x0004


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))


def mouse_down():
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)


def mouse_up():
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def click_at(x, y):
    set_cursor_pos(x, y)
    mouse_down()
    mouse_up()


# ==========================================================
#  Палитра / размеры
# ==========================================================
BG         = "#1e1f22"
SURFACE    = "#26282c"
SURFACE_2  = "#2f3136"
SURFACE_3  = "#35373c"
BORDER     = "#3a3d42"
TEXT       = "#f2f3f5"
TEXT_MUTED = "#8b8f96"
ACCENT     = "#5865f2"
ACCENT_HOV = "#4752c4"
GREEN      = "#3ba55d"
RED        = "#ed4245"
YELLOW     = "#faa61a"

FONT_TITLE   = ("Unbounded", 15, "bold")
FONT_SUB     = ("Unbounded", 8)
FONT_BODY    = ("Segoe UI", 10)
FONT_BODY_B  = ("Segoe UI", 10, "bold")
FONT_MONO    = ("Consolas", 10)
FONT_TINY    = ("Segoe UI", 8)


# ==========================================================
#  Иконки (SVG-пути → маленькие canvas-рисунки через текст)
#  Простая эмуляция: рисуем через юникод-глифы, но в цвете.
#  Полноценный SVG в tkinter без доп. библиотек не вставить,
#  поэтому берём лаконичные символы + цвет.
# ==========================================================
ICON_TARGET   = "◎"
ICON_PLUS     = "+"
ICON_TRASH    = "✕"
ICON_PLAY     = "▶"
ICON_STOP     = "■"
ICON_CURSOR   = "➤"
ICON_MOUSE    = "🖱"
ICON_WAND     = "✦"


# ==========================================================
#  Приложение
# ==========================================================
class HuEvoClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("huEVO clicker")
        self.root.geometry("320x545")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.points = []
        self.is_running = False
        self.thread = None
        self.mode = "normal"
        self._anim_job = None

        self._build_ui()

        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

    # ------------------------------------------------------
    #  UI
    # ------------------------------------------------------
    def _build_ui(self):
        root = self.root

        # ------- Header -------
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=14, pady=(12, 8))

        tk.Label(header, text=ICON_WAND, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 16)).pack(side="left", padx=(0, 6))

        title_wrap = tk.Frame(header, bg=BG)
        title_wrap.pack(side="left")

        tk.Label(title_wrap, text="huEVO clicker", bg=BG, fg=TEXT,
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(title_wrap, text="click · farm · chill", bg=BG, fg=TEXT_MUTED,
                 font=FONT_SUB).pack(anchor="w")

        # ------- Mode chips -------
        self._section("РЕЖИМ")

        chips = tk.Frame(root, bg=BG)
        chips.pack(fill="x", padx=14, pady=(0, 8))

        self.chip_normal = self._make_chip(chips, ICON_CURSOR + "  Обычный", "normal")
        self.chip_mouse  = self._make_chip(chips, ICON_MOUSE + "  Свободная мышь", "free")

        self.chip_normal.pack(side="left", padx=(0, 6))
        self.chip_mouse.pack(side="left")

        self._apply_chip_state()

        # Hint для режима
        self.mode_hint = tk.Label(
            root, text="", bg=BG, fg=TEXT_MUTED, font=FONT_TINY,
            wraplength=290, justify="left",
        )
        self.mode_hint.pack(fill="x", padx=14, pady=(0, 8))

        # ------- Points -------
        self._section("ТОЧКИ")

        add_btn = self._flat_button(root, ICON_PLUS + "  Добавить точку",
                                    self.add_point, fg=TEXT)
        add_btn.pack(fill="x", padx=14, pady=(0, 6), ipady=6)

        list_wrap = tk.Frame(root, bg=SURFACE_2, highlightbackground=BORDER,
                             highlightthickness=1)
        list_wrap.pack(fill="x", padx=14)

        self.listbox = tk.Listbox(
            list_wrap, height=4, bg=SURFACE_2, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#fff",
            bd=0, highlightthickness=0, font=FONT_MONO,
            activestyle="none",
        )
        self.listbox.pack(fill="x", padx=6, pady=6)

        clear_btn = self._flat_button(root, ICON_TRASH + "  Очистить",
                                      self.clear_points, fg=TEXT_MUTED,
                                      hover_bg=SURFACE_3)
        clear_btn.pack(fill="x", padx=14, pady=(6, 0), ipady=4)

        # ------- Interval -------
        self._section("ИНТЕРВАЛ")

        tf = tk.Frame(root, bg=SURFACE, highlightbackground=BORDER,
                      highlightthickness=1)
        tf.pack(fill="x", padx=14)
        tf.configure(padx=10, pady=8)

        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="0")
        self.ms_var  = tk.StringVar(value="250")

        def entry(parent, var):
            e = tk.Entry(parent, textvariable=var, width=4, justify="center",
                         bg=SURFACE_2, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_MONO, bd=0,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
            e.pack(side="left", ipady=4, padx=(0, 2))
            return e

        entry(tf, self.min_var)
        tk.Label(tf, text="мин", bg=SURFACE, fg=TEXT_MUTED,
                 font=FONT_TINY).pack(side="left", padx=(0, 10))
        entry(tf, self.sec_var)
        tk.Label(tf, text="сек", bg=SURFACE, fg=TEXT_MUTED,
                 font=FONT_TINY).pack(side="left", padx=(0, 10))
        entry(tf, self.ms_var)
        tk.Label(tf, text="мс", bg=SURFACE, fg=TEXT_MUTED,
                 font=FONT_TINY).pack(side="left")

        # ------- Status pill -------
        self.status_wrap = tk.Frame(root, bg=BG)
        self.status_wrap.pack(fill="x", padx=14, pady=(12, 6))

        self.pill = tk.Label(
            self.status_wrap, text="●  Выключено",
            bg=RED, fg="#ffffff", font=FONT_BODY_B,
            padx=12, pady=4,
        )
        self.pill.pack()

        # ------- Big button -------
        self.start_btn = tk.Button(
            root, text=f"{ICON_PLAY}   Старт",
            command=self.toggle_clicking,
            bg=ACCENT, fg="#ffffff",
            activebackground=ACCENT_HOV, activeforeground="#ffffff",
            relief="flat", bd=0, cursor="hand2",
            font=("Unbounded", 10, "bold"),
        )
        self.start_btn.pack(fill="x", padx=14, pady=(0, 6), ipady=10)

        # ------- Footer hint -------
        tk.Label(
            root,
            text="F2 — добавить точку   ·   F6 — старт/стоп",
            bg=BG, fg=TEXT_MUTED, font=FONT_TINY,
        ).pack(pady=(0, 10))

        # Начальное состояние
        self._update_hint()

    # ------------------------------------------------------
    #  Хелперы UI
    # ------------------------------------------------------
    def _section(self, text):
        tk.Label(self.root, text=text, bg=BG, fg=TEXT_MUTED,
                 font=("Unbounded", 7, "bold")).pack(anchor="w", padx=14, pady=(6, 4))

    def _make_chip(self, parent, text, value):
        chip = tk.Label(parent, text=text, bg=SURFACE_2, fg=TEXT,
                        font=FONT_BODY_B, padx=10, pady=6, cursor="hand2",
                        highlightthickness=1, highlightbackground=BORDER)
        chip.bind("<Button-1>", lambda e, v=value: self.set_mode(v))
        chip.bind("<Enter>",    lambda e, c=chip: self._chip_hover(c, True))
        chip.bind("<Leave>",    lambda e, c=chip: self._chip_hover(c, False))
        return chip

    def _chip_hover(self, chip, on):
        if chip in (self.chip_normal, self.chip_mouse) and self._chip_is_active(chip):
            return
        chip.config(bg=SURFACE_3 if on else SURFACE_2)

    def _chip_is_active(self, chip):
        return (self.mode == "normal" and chip is self.chip_normal) or \
               (self.mode == "free"   and chip is self.chip_mouse)

    def _apply_chip_state(self):
        for chip, val in ((self.chip_normal, "normal"), (self.chip_mouse, "free")):
            if val == self.mode:
                chip.config(bg=ACCENT, fg="#ffffff", highlightbackground=ACCENT)
            else:
                chip.config(bg=SURFACE_2, fg=TEXT, highlightbackground=BORDER)

    def _flat_button(self, parent, text, cmd, fg=TEXT, hover_bg=SURFACE_3):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=SURFACE_2, fg=fg,
                      activebackground=hover_bg, activeforeground=fg,
                      relief="flat", bd=0, cursor="hand2",
                      font=FONT_BODY, highlightthickness=1,
                      highlightbackground=BORDER)
        b.bind("<Enter>", lambda e: b.config(bg=hover_bg))
        b.bind("<Leave>", lambda e: b.config(bg=SURFACE_2))
        return b

    # ------------------------------------------------------
    #  Переключение режима
    # ------------------------------------------------------
    def set_mode(self, mode):
        self.mode = mode
        self._apply_chip_state()
        self._update_hint()

    def _update_hint(self):
        if self.mode == "normal":
            self.mode_hint.config(
                text="Курсор прыгает по точкам и кликает. Мышь занята во время кликов."
            )
        else:
            self.mode_hint.config(
                text="Курсор ненадолго телепортируется в точки, кликает и возвращается "
                     "туда, где ты держишь мышь. Между прыжками ты ей управляешь."
            )

    # ------------------------------------------------------
    #  Точки
    # ------------------------------------------------------
    def add_point(self):
        x, y = get_cursor_pos()
        self.points.append((x, y))
        self.listbox.insert(tk.END, f"  {x:>5}, {y:>5}")
        self._flash_row(len(self.points) - 1)

    def _flash_row(self, idx):
        # короткая подсветка новой строки
        try:
            self.listbox.itemconfig(idx, bg=SURFACE_3)
            self.root.after(220, lambda i=idx: self.listbox.itemconfig(i, bg=SURFACE_2))
        except tk.TclError:
            pass

    def clear_points(self):
        self.points.clear()
        self.listbox.delete(0, tk.END)

    # ------------------------------------------------------
    #  Интервал
    # ------------------------------------------------------
    def get_interval_seconds(self):
        try:
            m  = int(self.min_var.get() or 0)
            s  = int(self.sec_var.get() or 0)
            ms = int(self.ms_var.get() or 0)
            total = m * 60 + s + ms / 1000.0
            return total if total > 0 else 0.0
        except ValueError:
            return 0.0

    # ------------------------------------------------------
    #  Старт / стоп
    # ------------------------------------------------------
    def toggle_clicking(self):
        if self.is_running:
            self.is_running = False
            self._set_pill("●  Выключено", RED)
            self.start_btn.config(text=f"{ICON_PLAY}   Старт", bg=ACCENT,
                                  activebackground=ACCENT_HOV)
            self._stop_pulse()
        else:
            if not self.points:
                self._set_pill("⚠  Нет точек", YELLOW)
                return

            self.is_running = True
            self._set_pill("●  Работает", GREEN)
            self.start_btn.config(text=f"{ICON_STOP}   Стоп", bg=RED,
                                  activebackground="#c03535")
            self._start_pulse()

            target = (self._loop_normal if self.mode == "normal"
                      else self._loop_free_mouse)
            self.thread = threading.Thread(target=target, daemon=True)
            self.thread.start()

    def _set_pill(self, text, color):
        self.root.after(0, lambda: self.pill.config(text=text, bg=color))

    # лёгкая пульсация статуса, пока работает
    def _start_pulse(self):
        self._pulse_on = True
        self._pulse()

    def _stop_pulse(self):
        self._pulse_on = False
        if self._anim_job:
            try:
                self.root.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

    def _pulse(self):
        if not self._pulse_on:
            return
        cur = self.pill.cget("bg")
        nxt = GREEN if cur != GREEN else "#2f8e4c"
        try:
            self.pill.config(bg=nxt)
        except tk.TclError:
            return
        self._anim_job = self.root.after(420, self._pulse)

    # ------------------------------------------------------
    #  Циклы
    # ------------------------------------------------------
    def _loop_normal(self):
        while self.is_running:
            interval = self.get_interval_seconds()
            t0 = time.perf_counter()
            for (x, y) in self.points:
                if not self.is_running:
                    break
                click_at(x, y)
            self._sleep_remainder(interval, t0)

    def _loop_free_mouse(self):
        """
        Телепорт → клик → возврат туда, где была мышь.
        Между итерациями мышь полностью свободна.
        """
        while self.is_running:
            interval = self.get_interval_seconds()

            # Запоминаем, где сейчас «живёт» пользовательская мышь
            user_x, user_y = get_cursor_pos()

            # Делаем проход по всем точкам
            for (x, y) in self.points:
                if not self.is_running:
                    break
                # Перед кликом заново фиксируем реальную позицию —
                # пользователь мог двинуть мышь между точками
                user_x, user_y = get_cursor_pos()
                set_cursor_pos(x, y)
                mouse_down()
                mouse_up()
                set_cursor_pos(user_x, user_y)

            # И после прохода возвращаем курсор туда, где он был в начале
            set_cursor_pos(user_x, user_y)

            self._sleep_remainder(interval, t0=None, start=time.perf_counter(),
                                  whole=interval)

    def _sleep_remainder(self, interval, t0=None, start=None, whole=None):
        if start is None:
            start = t0
        elapsed = time.perf_counter() - start
        target = interval if whole is None else whole
        remaining = target - elapsed
        if remaining > 0:
            time.sleep(remaining)
        else:
            time.sleep(0)


if __name__ == "__main__":
    root = tk.Tk()
    app = HuEvoClicker(root)
    root.mainloop()
