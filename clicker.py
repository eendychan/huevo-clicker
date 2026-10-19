import tkinter as tk
import pyautogui
import keyboard
import threading
import time
import sys
import os

# Отключаем "fail-safe" (иначе при быстрых кликах у края экрана pyautogui кинет исключение)
pyautogui.FAILSAFE = False


class MiniClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("Clicker")
        self.root.geometry("230x300")
        self.root.attributes("-topmost", True)  # окно поверх всех
        self.root.resizable(False, False)

        # Переменные
        self.points = []          # список координат [(x, y), ...]
        self.is_running = False
        self.thread = None

        # --- Интерфейс ---
        tk.Button(root, text="➕ Добавить точку (F2)",
                  command=self.add_point).pack(pady=2, fill='x', padx=6)

        self.listbox = tk.Listbox(root, height=5, font=("Consolas", 9))
        self.listbox.pack(pady=2, fill='x', padx=6)

        tk.Button(root, text="🗑 Очистить точки",
                  command=self.clear_points).pack(pady=2, fill='x', padx=6)

        # Интервал
        frame_time = tk.Frame(root)
        frame_time.pack(pady=6)

        self.min_var = tk.StringVar(value="0")
        self.sec_var = tk.StringVar(value="1")
        self.ms_var = tk.StringVar(value="0")

        tk.Label(frame_time, text="Интервал:").pack(side='left')
        tk.Entry(frame_time, textvariable=self.min_var, width=3).pack(side='left')
        tk.Label(frame_time, text="м").pack(side='left')
        tk.Entry(frame_time, textvariable=self.sec_var, width=3).pack(side='left')
        tk.Label(frame_time, text="с").pack(side='left')
        tk.Entry(frame_time, textvariable=self.ms_var, width=3).pack(side='left')
        tk.Label(frame_time, text="мс").pack(side='left')

        # Статус
        self.status_label = tk.Label(root, text="🔴 Выключено", fg="red")
        self.status_label.pack(pady=6)

        tk.Label(root, text="F2 — добавить точку\nF6 — вкл/выкл",
                 font=("Arial", 8), fg="gray", justify="center").pack(side='bottom', pady=6)

        # Горячие клавиши
        keyboard.add_hotkey('F2', self.add_point)
        keyboard.add_hotkey('F6', self.toggle_clicking)

    def add_point(self):
        x, y = pyautogui.position()
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
            return total if total > 0 else 0.01
        except ValueError:
            return 0.01

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
            for point in self.points:
                if not self.is_running:
                    break
                pyautogui.click(point[0], point[1])
            time.sleep(interval)


if __name__ == "__main__":
    # Запускаем от имени администратора? Не обязательно, но лучше для некоторых игр.
    root = tk.Tk()
    app = MiniClicker(root)
    root.mainloop()
