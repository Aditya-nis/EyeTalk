import cv2
import time
import pyttsx3
import threading
import tkinter as tk
from tkinter import (
    Label, Button, Frame, Text, Scrollbar, END, filedialog,
    simpledialog, messagebox, Toplevel, Canvas
)
from queue import Queue, Empty
from PIL import Image, ImageTk

# ----------------- CONFIGURATION -----------------
BLINK_MIN_DURATION = 0.1   # Short blink (dot)
LONG_BLINK_DURATION = 0.25 # Long blink (dash)
PAUSE_DURATION = 1.5       # Gap between letters
WORD_PAUSE_DURATION = 3.0  # Gap between words

MORSE_PAIRS = [
    # Emojis
    ("😊", "...--."), ("😢", "..--.."), ("❤️", ".-.-."),
    ("👍", ".--.-"), ("🙏", "--..-."), ("😂", ".-..-."),
    ("🎉", "-.-.-."), ("🔥", "--..--"),
    # Common Words
    ("YES", "-.-- . ..."), ("NO", "-. ---"), ("HELP", ".... . .-.. .--."),
    ("OK", "--- -.-"), ("STOP", "... - --- .--."), ("PLEASE", ".--. .-.. . .- ... ."),
    ("THANKS", "- .... .- -. -.- ..."), ("SORRY", "... --- .-. .-. -.--"),
    ("HI", ".... .."), ("BYE", "-... -.-- ."),
    # Numbers
    ("0", "-----"), ("1", ".----"), ("2", "..---"), ("3", "...--"),
    ("4", "....-"), ("5", "....."), ("6", "-...."), ("7", "--..."),
    ("8", "---.."), ("9", "----.")
]
# Morse code for words is space-separated by letter, e.g., "YES" = "-.-- . ..."

MORSE_CODE_DICT = {morse.replace(" ", ""): char for char, morse in MORSE_PAIRS}
LETTER_TO_MORSE = {char: morse for char, morse in MORSE_PAIRS}

# Improved blink sign: allow for more precise detection and feedback
# (You may want to tweak these values for your camera/environment)
BLINK_MIN_DURATION = 0.08   # Short blink (dot)
LONG_BLINK_DURATION = 0.22  # Long blink (dash)
PAUSE_DURATION = 1.2        # Gap between letters
WORD_PAUSE_DURATION = 2.5   # Gap between words

engine = pyttsx3.init()
eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

def decode_morse(sequence):
    return MORSE_CODE_DICT.get(sequence, '?')

def speak_text(text):
    threading.Thread(
        target=lambda: engine.say(text) or engine.runAndWait(),
        daemon=True
    ).start()

class EyeBlinkApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Eye Blink Sign by aditya Nisargandh")
        self.root.geometry("900x650")
        self.bg_light = "#f0f0f0"
        self.bg_dark = "#222"
        self.fg_light = "#222"
        self.fg_dark = "#f0f0f0"
        self.dark_mode = False

        self.decoded_text = ""
        self.morse_sequence = ""
        self.blink_start = None
        self.last_blink_time = None
        self.running = False
        self.paused = False
        self.history = []
        self.queue = Queue()
        self.eye_preview = None
        self.eye_canvas = None
        self.eye_imgtk = None
        self.eye_preview_open = False

        self._init_gui()
        self.root.after(20, self._process_queue)  # Faster UI update

    def _init_gui(self):
        self.root.configure(bg=self.bg_light)
        Label(self.root, text="👁 Eye Blink Sign Language (Morse Code)",
              font=("Arial", 18, "bold"), bg=self.bg_light, fg="blue").pack(pady=10)

        text_frame = Frame(self.root, bg="#ffffff", relief="solid", bd=1)
        text_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.label_morse = Label(text_frame, text="Morse: ",
                                 font=("Courier", 14), bg="white", anchor="w")
        self.label_morse.pack(fill="x", padx=5, pady=5)

        self.text_output = Text(text_frame, height=8, font=("Courier", 14), wrap="word")
        self.text_output.pack(fill="both", padx=5, pady=5, expand=True)
        self.text_output.insert(END, "Decoded: \n")

        history_frame = Frame(self.root, bg=self.bg_light)
        history_frame.pack(pady=5, padx=10, fill="x")
        Label(history_frame, text="History:", font=("Arial", 12, "bold"), bg=self.bg_light).pack(side="left")
        self.history_text = Text(history_frame, height=2, font=("Courier", 12), wrap="word", state="disabled", bg="#eaeaea")
        self.history_text.pack(side="left", fill="x", expand=True, padx=5)

        btn_frame = Frame(self.root, bg=self.bg_light)
        btn_frame.pack(pady=10)

        buttons = [
            ("▶ Start Camera", self.toggle_camera, "green"),
            ("⏸ Pause", self.toggle_pause, None),
            ("🧹 Clear", self.clear_text, None),
            ("💾 Save", self.save_text, None),
            ("📋 Copy", self.copy_text, None),
            ("🔊 Speak", self.speak_sentence, None),
            ("⚙️ Settings", self.open_settings, None),
            ("🌙 Dark Mode", self.toggle_dark_mode, None),
        ]
        self.button_refs = []
        for idx, (text, cmd, color) in enumerate(buttons):
            btn = Button(btn_frame, text=text, command=cmd,
                         font=("Arial", 14), width=12)
            if color:
                btn.config(bg=color, fg="white")
            btn.grid(row=0, column=idx, padx=5)
            self.button_refs.append(btn)
        self.start_button, self.pause_button, self.clear_button, self.save_button, \
            self.copy_button, self.speak_button, self.settings_button, self.darkmode_button = self.button_refs

        self.pause_button.config(state="disabled")

        self.status_label = Label(self.root, text="Camera: OFF", font=("Arial", 12), bg=self.bg_light, fg="red")
        self.status_label.pack(pady=5)

        Label(self.root, text="📌 Short blink = Dot (.), Long blink = Dash (-)\n"
                              "Pause = Letter, Long pause = Word\n"
                              "Try emojis: 😊 😢 ❤️ 👍 🙏 😂 🎉 🔥",
              font=("Arial", 12), bg=self.bg_light).pack(pady=5)

    def open_eye_preview(self):
        if self.eye_preview_open:
            return
        self.eye_preview = Toplevel(self.root)
        self.eye_preview.title("Eye Preview")
        self.eye_preview.geometry("320x240")
        self.eye_preview.resizable(False, False)
        self.eye_canvas = Canvas(self.eye_preview, width=320, height=240, bg="black")
        self.eye_canvas.pack()
        self.eye_preview.protocol("WM_DELETE_WINDOW", self.close_eye_preview)
        self.eye_preview_open = True

    def close_eye_preview(self):
        if self.eye_preview:
            self.eye_preview.destroy()
        self.eye_preview = None
        self.eye_canvas = None
        self.eye_preview_open = False

    def update_eye_preview(self, frame, blink_flash):
        if not self.eye_preview_open or self.eye_canvas is None:
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, (320, 240))
        img = Image.fromarray(frame)
        self.eye_imgtk = ImageTk.PhotoImage(image=img)
        self.eye_canvas.create_image(0, 0, anchor="nw", image=self.eye_imgtk)
        if blink_flash:
            self.eye_canvas.create_oval(120, 80, 200, 160, outline="lime", width=8)

    def toggle_camera(self):
        if self.running:
            self.running = False
            self.start_button.config(text="▶ Start Camera", bg="green")
            self.status_label.config(text="Camera: OFF", fg="red")
            self.pause_button.config(state="disabled")
            self.close_eye_preview()
        else:
            self.running = True
            self.paused = False
            self.start_button.config(text="⏹ Stop Camera", bg="red")
            self.status_label.config(text="Camera: ON", fg="green")
            self.pause_button.config(state="normal", text="⏸ Pause")
            self.open_eye_preview()
            threading.Thread(target=self.camera_loop, daemon=True).start()

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_button.config(text="▶ Resume")
            self.status_label.config(text="Camera: Paused", fg="orange")
        else:
            self.pause_button.config(text="⏸ Pause")
            self.status_label.config(text="Camera: ON", fg="green")

    def clear_text(self):
        if self.decoded_text.strip():
            self.history.append(self.decoded_text.strip())
            self.update_history()
        self.decoded_text = ""
        self.morse_sequence = ""
        self.text_output.delete(1.0, END)
        self.text_output.insert(END, "Decoded: \n")
        self.label_morse.config(text="Morse: ")

    def update_history(self):
        self.history_text.config(state="normal")
        self.history_text.delete(1.0, END)
        for line in self.history[-5:]:
            self.history_text.insert(END, line + "\n")
        self.history_text.config(state="disabled")

    def save_text(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("Text Files", "*.txt")])
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.decoded_text)
                messagebox.showinfo("Saved", "Text saved successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file:\n{e}")

    def copy_text(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.decoded_text.strip())
        messagebox.showinfo("Copied", "Decoded text copied to clipboard.")

    def speak_sentence(self):
        if self.decoded_text.strip():
            speak_text(self.decoded_text.strip())

    def open_settings(self):
        global BLINK_MIN_DURATION, LONG_BLINK_DURATION, PAUSE_DURATION, WORD_PAUSE_DURATION
        blink = simpledialog.askfloat("Settings", "Short blink duration (sec):", initialvalue=BLINK_MIN_DURATION, minvalue=0.05, maxvalue=1)
        long_blink = simpledialog.askfloat("Settings", "Long blink duration (sec):", initialvalue=LONG_BLINK_DURATION, minvalue=0.1, maxvalue=2)
        pause = simpledialog.askfloat("Settings", "Letter pause (sec):", initialvalue=PAUSE_DURATION, minvalue=0.5, maxvalue=5)
        word_pause = simpledialog.askfloat("Settings", "Word pause (sec):", initialvalue=WORD_PAUSE_DURATION, minvalue=1, maxvalue=10)
        if all([blink, long_blink, pause, word_pause]):
            BLINK_MIN_DURATION = blink
            LONG_BLINK_DURATION = long_blink
            PAUSE_DURATION = pause
            WORD_PAUSE_DURATION = word_pause

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        bg = self.bg_dark if self.dark_mode else self.bg_light
        fg = self.fg_dark if self.dark_mode else self.fg_light
        self.root.configure(bg=bg)
        for widget in self.root.winfo_children():
            try:
                widget.configure(bg=bg, fg=fg)
            except Exception:
                pass
        self.label_morse.configure(bg="#333" if self.dark_mode else "white", fg=fg)
        self.text_output.configure(bg="#222" if self.dark_mode else "white", fg=fg)
        self.history_text.configure(bg="#333" if self.dark_mode else "#eaeaea", fg=fg)
        self.status_label.configure(bg=bg, fg="green" if self.running else "red")
        self.darkmode_button.config(text="☀️ Light Mode" if self.dark_mode else "🌙 Dark Mode")

    def process_eye_blink(self, eyes_detected):
        blink_now = False
        now = time.time()
        if eyes_detected == 0:
            if self.blink_start is None:
                self.blink_start = now
        else:
            if self.blink_start:
                blink_duration = now - self.blink_start
                if BLINK_MIN_DURATION < blink_duration < LONG_BLINK_DURATION:
                    self.morse_sequence += "."
                    blink_now = True
                elif blink_duration >= LONG_BLINK_DURATION:
                    self.morse_sequence += "-"
                    blink_now = True
                self.blink_start = None
                self.last_blink_time = now

        # Decode letter
        if self.last_blink_time and (now - self.last_blink_time > PAUSE_DURATION) and self.morse_sequence:
            char = decode_morse(self.morse_sequence)
            self.decoded_text += char
            self.queue.put(('char', char))
            self.morse_sequence = ""
            speak_text(char)

        # Add space (word separator)
        if self.last_blink_time and (now - self.last_blink_time > WORD_PAUSE_DURATION):
            if not self.decoded_text.endswith(" "):
                self.decoded_text += " "
                self.queue.put(('char', " "))

        return blink_now

    def camera_loop(self):
        cap = cv2.VideoCapture(0)
        blink_flash_counter = 0
        try:
            while self.running:
                if self.paused:
                    time.sleep(0.05)
                    continue
                ret, frame = cap.read()
                if not ret:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                eyes = eye_cascade.detectMultiScale(gray, 1.3, 5)
                eyes_detected = len(eyes)
                blink_now = self.process_eye_blink(eyes_detected)
                for (ex, ey, ew, eh) in eyes:
                    cv2.rectangle(frame, (ex, ey), (ex + ew, ey + eh), (0, 255, 0), 2)
                if blink_now:
                    blink_flash_counter = 6
                # Only send latest state to UI
                self.queue.put(('morse', self.morse_sequence))
                self.queue.put(('eye_preview', frame.copy(), blink_flash_counter > 0))
                if blink_flash_counter > 0:
                    blink_flash_counter -= 1
        finally:
            cap.release()
            cv2.destroyAllWindows()

    def _process_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == 'char':
                    self.text_output.insert(END, item[1])
                elif item[0] == 'morse':
                    self.label_morse.config(text=f"Morse: {item[1]}")
                elif item[0] == 'eye_preview':
                    frame, blink_flash = item[1], item[2]
                    self.update_eye_preview(frame, blink_flash)
        except Empty:
            pass
        self.root.after(20, self._process_queue)  # Faster UI update

if __name__ == "__main__":
    root = tk.Tk()
    app = EyeBlinkApp(root)
    root.mainloop()
