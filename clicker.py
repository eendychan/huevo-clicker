import tkinter as tk
import keyboard
import threading
import time
import ctypes
from ctypes import wintypes

# --- WinAPI ---
user32 = ctypes.WinDLL("user32", use_last_error=True)

# Константы для mouse_event
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Для получения позиции курсора
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def get_cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def click_at(x, y):
    """Мгновенно перемещает курсор и кликает ЛКМ."""
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


class MiniClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("Clicker")
        self.root.geometry("230x300")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.points = []
        self.is_running = False
        self.thread = None

        # --- Интерфейс ---
        tk.Button(root, text="➕ Добавить точку (F2)",
                  command=self.add_point).pack(pady=2, fill='x', padx=6)

        self.listbox = tk.Listbox(root, height=5, font=("Consolas", 9))
        self.listbox.pack(pady=2, fill='x', padx=6)

        tk.Button(root, text="🗑 Очистить точки",
                  command=self.clear_points).pack(pady=2, fill='x', padx=6)

        frame_time = tk.Frame(root)
        frame_time.pack(pady=6)

        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="0")
        self.ms_var = tk.StringVar(value="100")

        tk.Label(frame_time, text="Интервал:").pack(side='left')
        tk.Entry(frame_time, textvariable=self.min_var, width=3).pack(side='left')
        tk.Label(frame_time, text="м").pack(side='left')
        tk.Entry(frame_time, textvariable=self.sec_var, width=3).pack(side='left')
        tk.Label(frame_time, text="с").pack(side='left')
        tk.Entry(frame_time, textvariable=self.ms_var, width=4).pack(side='left')
        tk.Label(frame_time, text="мс").pack(side='left')

        self.status_label = tk.Label(root, text="🔴 Выключено", fg="red")
        self.status_label.pack(pady=6)

        tk.Label(root, text="F2 — добавить точку\nF6 — вкл/выкл",
                 font=("Arial", 8), fg="gray", justify="center").pack(side='bottom', pady=6)

        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

    def add_point(self):
        x, y = get_cursor_pos()
        self.points.append((x, y))
        self.listbox.insert(tk.END, f"{x}, {y}")

    def clear_points(self):
        self.points.clear()
        self.listbox.delete(0, tk.END)

    def get_interval_seconds(self):
        try:
            m = int(self.min_var.get() or 0)
            s = int(self.sec_var.get() or 0)
            ms = int(self.ms_var.get() or 0)
            total = (m * 60) + s + (ms / 1000.0)
            return total if total > 0 else 0.0
        except ValueError:
            return 0.0

    def toggle_clicking(self):
        if self.is_running:
            self.is_running = False
            self.status_label.config(text="🔴 Выключено", fg="red")
        else:
            if not self.points:
                return
            self.is_running = True
            self.status_label.config(text="🟢 Работает...", fg="green")
            self.thread = threading.Thread(target=self.click_loop, daemon=True)
            self.thread.start()

    def click_loop(self):
        while self.is_running:
            interval = self.get_interval_seconds()
            start = time.perf_counter()

            for point in self.points:
                if not self.is_running:
                    break
                click_at(point[0], point[1])

            # Компенсация: спим ровно столько, сколько осталось до конца интервала
            elapsed = time.perf_counter() - start
            remaining = interval - elapsed
            if remaining > 0:
                # sleep(0) отдаёт квант потоку, чтобы не задушить UI
                time.sleep(remaining)
            else:
                time.sleep(0)  # без паузы, но и без зависания UI


if __name__ == "__main__":
    root = tk.Tk()
    app = MiniClicker(root)
    root.mainloop()
