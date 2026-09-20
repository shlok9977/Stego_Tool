#!/usr/bin/env python3
"""
gui.py — StegoSuite desktop GUI.

A CustomTkinter front-end over the `stego` engine (stego/api.py,
stego/analyze.py). Pure presentation layer: every actual hide / extract /
capacity / analyze operation is delegated to the already-tested engine, and
every blocking operation runs on a worker thread so the UI never freezes.

Run with:  python3 gui.py
"""
import os
import sys
import threading
import traceback
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stego import api, analyze  # noqa: E402
from stego.image_stego import get_capacity_bytes as img_capacity  # noqa: E402
from stego.audio_stego import get_capacity_bytes as audio_capacity  # noqa: E402

APP_NAME = "StegoSuite"
APP_VERSION = "1.0.0"

IMAGE_EXTS = (".png", ".bmp")
AUDIO_EXTS = (".wav",)
CARRIER_EXTS = IMAGE_EXTS + AUDIO_EXTS

ACCENT = "#2FA572"
DANGER = "#D64545"
MUTED = "#8A8D91"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


def human_size(n: int) -> str:
    n = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def carrier_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    return "unknown"


class LogPanel(ctk.CTkTextbox):
    """Read-only, timestamp-free scrolling log used at the bottom of every tab."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("height", 120)
        kwargs.setdefault("font", ("Consolas", 12))
        super().__init__(master, **kwargs)
        self.configure(state="disabled")
        self.tag_config = {}

    def log(self, message: str, kind: str = "info"):
        prefix = {"info": "•", "success": "✅", "error": "❌", "warn": "⚠"}.get(kind, "•")
        self.configure(state="normal")
        self.insert("end", f"{prefix} {message}\n")
        self.configure(state="disabled")
        self.see("end")

    def clear(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")


class FilePicker(ctk.CTkFrame):
    """A labeled row: [entry showing path] [Browse button]."""

    def __init__(self, master, label: str, mode="open", filetypes=None,
                 defaultextension=None, on_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.mode = mode
        self.filetypes = filetypes or [("All files", "*.*")]
        self.defaultextension = defaultextension
        self.on_change = on_change

        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=label, width=110, anchor="w",
                     font=("", 13, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.var = ctk.StringVar()
        self.entry = ctk.CTkEntry(self, textvariable=self.var, placeholder_text="No file selected")
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.var.trace_add("write", lambda *_: self.on_change and self.on_change(self.var.get()))
        ctk.CTkButton(self, text="Browse", width=90, command=self._browse).grid(row=0, column=2)

    def _browse(self):
        if self.mode == "open":
            path = filedialog.askopenfilename(filetypes=self.filetypes)
        elif self.mode == "save":
            path = filedialog.asksaveasfilename(filetypes=self.filetypes,
                                                 defaultextension=self.defaultextension)
        else:
            path = filedialog.askdirectory()
        if path:
            self.var.set(path)

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, path: str):
        self.var.set(path)


class PasswordRow(ctk.CTkFrame):
    """Password entry with a show/hide toggle."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="Password", width=110, anchor="w",
                     font=("", 13, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.var = ctk.StringVar()
        self.entry = ctk.CTkEntry(self, textvariable=self.var, show="•",
                                   placeholder_text="Optional — leave blank for no encryption")
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._shown = False
        self.toggle = ctk.CTkButton(self, text="Show", width=60, command=self._toggle)
        self.toggle.grid(row=0, column=2)

    def _toggle(self):
        self._shown = not self._shown
        self.entry.configure(show="" if self._shown else "•")
        self.toggle.configure(text="Hide" if self._shown else "Show")

    def get(self):
        return self.var.get()


class CarrierPreview(ctk.CTkFrame):
    """Small thumbnail + metadata box for the selected carrier."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(1, weight=1)
        self.image_label = ctk.CTkLabel(self, text="", width=110, height=110,
                                         fg_color=("gray85", "gray20"), corner_radius=8)
        self.image_label.grid(row=0, column=0, rowspan=3, padx=10, pady=10)
        self.title_lbl = ctk.CTkLabel(self, text="No carrier selected", font=("", 14, "bold"), anchor="w")
        self.title_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 0))
        self.meta_lbl = ctk.CTkLabel(self, text="", font=("", 12), text_color=MUTED, anchor="w", justify="left")
        self.meta_lbl.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        self._photo = None

    def update_for(self, path: str):
        if not path or not os.path.isfile(path):
            self.title_lbl.configure(text="No carrier selected")
            self.meta_lbl.configure(text="")
            self.image_label.configure(image=None, text="")
            return

        kind = carrier_kind(path)
        name = os.path.basename(path)
        size = human_size(os.path.getsize(path))

        if kind == "image":
            try:
                img = Image.open(path).convert("RGB")
                w, h = img.size
                thumb = img.copy()
                thumb.thumbnail((100, 100))
                self._photo = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
                self.image_label.configure(image=self._photo, text="")
                self.title_lbl.configure(text=name)
                self.meta_lbl.configure(text=f"Image · {w}×{h}px · {size}")
            except Exception:
                self.image_label.configure(image=None, text="🖼")
                self.title_lbl.configure(text=name)
                self.meta_lbl.configure(text=f"Image · {size} · (preview failed)")
        elif kind == "audio":
            self.image_label.configure(image=None, text="🔊")
            self.title_lbl.configure(text=name)
            self.meta_lbl.configure(text=f"Audio (WAV) · {size}")
        else:
            self.image_label.configure(image=None, text="?")
            self.title_lbl.configure(text=name)
            self.meta_lbl.configure(text=f"Unsupported carrier type · {size}", text_color=DANGER)


def run_in_thread(fn, on_done=None, on_error=None):
    """Runs fn() on a worker thread; on_done/on_error are invoked back on the
    Tk main thread via .after(0, ...) so widgets can be touched safely."""

    def worker():
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001
            err = e  # capture before Python clears `e` at except-block exit
            if on_error:
                app_root.after(0, lambda: on_error(err))
            else:
                traceback.print_exc()
            return
        if on_done:
            app_root.after(0, lambda: on_done(result))

    threading.Thread(target=worker, daemon=True).start()


# ----------------------------------------------------------------------- #
#  Tabs
# ----------------------------------------------------------------------- #

class HideTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        self.carrier_picker = FilePicker(
            self, "Carrier", mode="open",
            filetypes=[("Supported carriers", "*.png *.bmp *.wav"), ("All files", "*.*")],
            on_change=self._on_carrier_change,
        )
        self.carrier_picker.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        self.preview = CarrierPreview(self, fg_color=("gray92", "gray14"), corner_radius=10)
        self.preview.grid(row=1, column=0, sticky="ew", padx=16, pady=6)

        # payload type selector
        payload_frame = ctk.CTkFrame(self, fg_color="transparent")
        payload_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        payload_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(payload_frame, text="Payload", width=110, anchor="w",
                     font=("", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.payload_mode = ctk.StringVar(value="text")
        seg = ctk.CTkSegmentedButton(payload_frame, values=["Text message", "File"],
                                      command=self._on_payload_mode_change)
        seg.set("Text message")
        seg.grid(row=0, column=1, sticky="w")
        self._seg = seg

        # text payload widget
        self.text_box = ctk.CTkTextbox(self, height=90)
        self.text_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 0))
        self.text_box.insert("1.0", "Type the secret message to hide here...")

        # file payload widget (hidden by default)
        self.file_picker = FilePicker(self, "File to hide", mode="open")

        # bit depth
        bits_frame = ctk.CTkFrame(self, fg_color="transparent")
        bits_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(14, 0))
        bits_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bits_frame, text="Bit depth", width=110, anchor="w",
                     font=("", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.bits_var = ctk.IntVar(value=1)
        self.bits_slider = ctk.CTkSlider(bits_frame, from_=1, to=4, number_of_steps=3,
                                          command=self._on_bits_change)
        self.bits_slider.set(1)
        self.bits_slider.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.bits_readout = ctk.CTkLabel(bits_frame, text="1 bit/ch — least detectable", text_color=MUTED)
        self.bits_readout.grid(row=0, column=2, sticky="w")

        # password
        self.password_row = PasswordRow(self)
        self.password_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(14, 0))

        # output
        self.output_picker = FilePicker(
            self, "Save as", mode="save",
            filetypes=[("PNG image", "*.png"), ("BMP image", "*.bmp"), ("WAV audio", "*.wav")],
        )
        self.output_picker.grid(row=6, column=0, sticky="ew", padx=16, pady=(10, 0))

        # capacity readout + action button
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.grid(row=7, column=0, sticky="ew", padx=16, pady=(16, 6))
        action_row.grid_columnconfigure(0, weight=1)
        self.capacity_lbl = ctk.CTkLabel(action_row, text="", text_color=MUTED, anchor="w")
        self.capacity_lbl.grid(row=0, column=0, sticky="w")
        self.hide_btn = ctk.CTkButton(action_row, text="🔒 Hide Data", height=38,
                                       fg_color=ACCENT, command=self._on_hide_clicked)
        self.hide_btn.grid(row=0, column=1, sticky="e")
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")

        self.log = LogPanel(self)
        self.log.grid(row=9, column=0, sticky="nsew", padx=16, pady=(6, 16))
        self.grid_rowconfigure(9, weight=1)

    def _on_payload_mode_change(self, value):
        self.payload_mode.set("text" if value == "Text message" else "file")
        if self.payload_mode.get() == "text":
            self.file_picker.grid_forget()
            self.text_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 0))
        else:
            self.text_box.grid_forget()
            self.file_picker.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._refresh_capacity()

    def _on_bits_change(self, value):
        b = int(round(value))
        self.bits_var.set(b)
        note = {1: "least detectable", 2: "balanced", 3: "higher capacity", 4: "max capacity, most detectable"}[b]
        self.bits_readout.configure(text=f"{b} bit/ch — {note}")
        self._refresh_capacity()

    def _on_carrier_change(self, path):
        self.preview.update_for(path)
        # auto-suggest an output filename next to the carrier
        if path and os.path.isfile(path):
            base, ext = os.path.splitext(path)
            self.output_picker.set(f"{base}_stego{ext}")
        self._refresh_capacity()

    def _refresh_capacity(self):
        path = self.carrier_picker.get()
        if not path or not os.path.isfile(path):
            self.capacity_lbl.configure(text="")
            return
        kind = carrier_kind(path)
        if kind not in ("image", "audio"):
            self.capacity_lbl.configure(text="Unsupported carrier type", text_color=DANGER)
            return
        try:
            fn = img_capacity if kind == "image" else audio_capacity
            cap = fn(path, self.bits_var.get())
            self.capacity_lbl.configure(text=f"Capacity at this bit depth: {human_size(cap)}", text_color=MUTED)
        except Exception:
            self.capacity_lbl.configure(text="")

    def _on_hide_clicked(self):
        carrier = self.carrier_picker.get()
        output = self.output_picker.get()
        bits = self.bits_var.get()
        password = self.password_row.get() or None

        if not carrier or not os.path.isfile(carrier):
            messagebox.showerror(APP_NAME, "Please choose a valid carrier file.")
            return
        if carrier_kind(carrier) not in ("image", "audio"):
            messagebox.showerror(APP_NAME, "Carrier must be a PNG, BMP, or WAV file.")
            return
        if not output:
            messagebox.showerror(APP_NAME, "Please choose where to save the output.")
            return

        is_file_mode = self.payload_mode.get() == "file"
        if is_file_mode:
            src = self.file_picker.get()
            if not src or not os.path.isfile(src):
                messagebox.showerror(APP_NAME, "Please choose a file to hide.")
                return
            with open(src, "rb") as f:
                data = f.read()
            filename = os.path.basename(src)
        else:
            text = self.text_box.get("1.0", "end").strip()
            if not text:
                messagebox.showerror(APP_NAME, "Please enter a message to hide.")
                return
            data = text.encode("utf-8")
            filename = ""

        self.log.clear()
        self.log.log("Starting embed operation...")
        self._set_busy(True)

        def work():
            return api.hide(carrier, output, data, filename=filename,
                             is_file=is_file_mode, password=password, bits=bits)

        def done(report):
            self._set_busy(False)
            self.log.log(f"Payload size: {human_size(len(data))} raw "
                          f"→ {human_size(report['packet_bytes'])} packed", "info")
            self.log.log(f"Encryption: {'AES-256-GCM enabled' if report['encrypted'] else 'none'}", "info")
            self.log.log(f"Bit depth used: {report['bits_used']} bit(s)/channel", "info")
            self.log.log(f"Saved to {report['output']}", "success")
            messagebox.showinfo(APP_NAME, f"Hidden successfully!\nSaved to:\n{report['output']}")

        def error(e):
            self._set_busy(False)
            self.log.log(str(e), "error")
            messagebox.showerror(APP_NAME, str(e))

        run_in_thread(work, on_done=done, on_error=error)

    def _set_busy(self, busy: bool):
        self.hide_btn.configure(state="disabled" if busy else "normal",
                                 text="Working..." if busy else "🔒 Hide Data")
        if busy:
            self.progress.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 6))
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_forget()


class ExtractTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        self.stego_picker = FilePicker(
            self, "Stego file", mode="open",
            filetypes=[("Supported carriers", "*.png *.bmp *.wav"), ("All files", "*.*")],
            on_change=self._on_change,
        )
        self.stego_picker.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        self.preview = CarrierPreview(self, fg_color=("gray92", "gray14"), corner_radius=10)
        self.preview.grid(row=1, column=0, sticky="ew", padx=16, pady=6)

        self.password_row = PasswordRow(self)
        self.password_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(14, 0))

        self.save_dir_picker = FilePicker(self, "Save folder", mode="dir")
        self.save_dir_picker.set(os.path.expanduser("~"))
        self.save_dir_picker.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 0))

        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(16, 6))
        action_row.grid_columnconfigure(0, weight=1)
        self.status_lbl = ctk.CTkLabel(action_row, text="", text_color=MUTED, anchor="w")
        self.status_lbl.grid(row=0, column=0, sticky="w")
        self.extract_btn = ctk.CTkButton(action_row, text="🔓 Extract Data", height=38,
                                          fg_color=ACCENT, command=self._on_extract_clicked)
        self.extract_btn.grid(row=0, column=1, sticky="e")
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")

        ctk.CTkLabel(self, text="Extracted text preview", font=("", 13, "bold"),
                     anchor="w").grid(row=6, column=0, sticky="ew", padx=16, pady=(10, 0))
        self.result_box = ctk.CTkTextbox(self, height=100)
        self.result_box.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 6))
        self.result_box.configure(state="disabled")

        self.log = LogPanel(self, height=80)
        self.log.grid(row=8, column=0, sticky="nsew", padx=16, pady=(6, 16))
        self.grid_rowconfigure(8, weight=1)

    def _on_change(self, path):
        self.preview.update_for(path)

    def _on_extract_clicked(self):
        path = self.stego_picker.get()
        password = self.password_row.get() or None
        save_dir = self.save_dir_picker.get() or os.getcwd()

        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "Please choose a valid stego file.")
            return
        if carrier_kind(path) not in ("image", "audio"):
            messagebox.showerror(APP_NAME, "File must be a PNG, BMP, or WAV.")
            return

        self.log.clear()
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.configure(state="disabled")
        self.log.log("Reading embedded payload...")
        self._set_busy(True)

        def work():
            return api.reveal(path, password=password)

        def done(result):
            self._set_busy(False)
            self.log.log(f"Encrypted: {result['encrypted']}", "info")
            if result["is_file"]:
                out_name = result["filename"] or "extracted_output"
                out_path = os.path.join(save_dir, out_name)
                with open(out_path, "wb") as f:
                    f.write(result["data"])
                self.log.log(f"Extracted file ({human_size(len(result['data']))}) -> {out_path}", "success")
                messagebox.showinfo(APP_NAME, f"File extracted:\n{out_path}")
            else:
                text = result["data"].decode("utf-8", errors="replace")
                self.result_box.configure(state="normal")
                self.result_box.insert("1.0", text)
                self.result_box.configure(state="disabled")
                self.log.log("Extracted text message shown below.", "success")

        def error(e):
            self._set_busy(False)
            self.log.log(str(e), "error")
            messagebox.showerror(APP_NAME, str(e))

        run_in_thread(work, on_done=done, on_error=error)

    def _set_busy(self, busy: bool):
        self.extract_btn.configure(state="disabled" if busy else "normal",
                                    text="Working..." if busy else "🔓 Extract Data")
        if busy:
            self.progress.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 6))
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_forget()


class CapacityTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        self.carrier_picker = FilePicker(
            self, "Carrier", mode="open",
            filetypes=[("Supported carriers", "*.png *.bmp *.wav"), ("All files", "*.*")],
        )
        self.carrier_picker.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        self.preview = CarrierPreview(self, fg_color=("gray92", "gray14"), corner_radius=10)
        self.preview.grid(row=1, column=0, sticky="ew", padx=16, pady=6)

        ctk.CTkButton(self, text="Calculate Capacity", command=self._calculate,
                       fg_color=ACCENT).grid(row=2, column=0, sticky="e", padx=16, pady=(14, 6))

        self.table = ctk.CTkFrame(self, fg_color=("gray92", "gray14"), corner_radius=10)
        self.table.grid(row=3, column=0, sticky="ew", padx=16, pady=6)
        self.table.grid_columnconfigure((0, 1, 2), weight=1)
        self.bars = {}
        self.row_labels = {}
        for i, bits in enumerate(range(1, 5)):
            ctk.CTkLabel(self.table, text=f"{bits} bit/ch", width=70,
                         anchor="w").grid(row=i, column=0, padx=10, pady=8, sticky="w")
            bar = ctk.CTkProgressBar(self.table)
            bar.set(0)
            bar.grid(row=i, column=1, sticky="ew", padx=10, pady=8)
            lbl = ctk.CTkLabel(self.table, text="—", width=90, anchor="e")
            lbl.grid(row=i, column=2, padx=10, pady=8, sticky="e")
            self.bars[bits] = bar
            self.row_labels[bits] = lbl

        self.log = LogPanel(self, height=90)
        self.log.grid(row=4, column=0, sticky="nsew", padx=16, pady=(16, 16))
        self.grid_rowconfigure(4, weight=1)

    def _calculate(self):
        path = self.carrier_picker.get()
        self.preview.update_for(path)
        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "Please choose a valid carrier file.")
            return
        kind = carrier_kind(path)
        if kind not in ("image", "audio"):
            messagebox.showerror(APP_NAME, "File must be a PNG, BMP, or WAV.")
            return

        self.log.clear()
        try:
            fn = img_capacity if kind == "image" else audio_capacity
            caps = {b: fn(path, b) for b in range(1, 5)}
        except Exception as e:
            self.log.log(str(e), "error")
            return

        max_cap = max(caps.values()) or 1
        for b, cap in caps.items():
            self.bars[b].set(cap / max_cap)
            self.row_labels[b].configure(text=human_size(cap))
        self.log.log(f"Capacity calculated for '{os.path.basename(path)}'.", "success")


class AnalyzeTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Basic LSB steganalysis heuristic — checks whether an image "
                                 "*might* already contain hidden LSB data.",
                     text_color=MUTED, wraplength=560, justify="left",
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 6))

        self.image_picker = FilePicker(
            self, "Image", mode="open",
            filetypes=[("Images", "*.png *.bmp"), ("All files", "*.*")],
            on_change=lambda p: self.preview.update_for(p),
        )
        self.image_picker.grid(row=1, column=0, sticky="ew", padx=16, pady=6)

        self.preview = CarrierPreview(self, fg_color=("gray92", "gray14"), corner_radius=10)
        self.preview.grid(row=2, column=0, sticky="ew", padx=16, pady=6)

        ctk.CTkButton(self, text="Run Analysis", command=self._analyze,
                       fg_color=ACCENT).grid(row=3, column=0, sticky="e", padx=16, pady=(10, 6))

        self.result_frame = ctk.CTkFrame(self, fg_color=("gray92", "gray14"), corner_radius=10)
        self.result_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=6)
        self.result_frame.grid_columnconfigure(1, weight=1)
        self.chi_lbl = ctk.CTkLabel(self.result_frame, text="Chi-square: —")
        self.chi_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.risk_lbl = ctk.CTkLabel(self.result_frame, text="Risk: —", font=("", 14, "bold"))
        self.risk_lbl.grid(row=0, column=1, sticky="e", padx=12, pady=(10, 4))
        self.verdict_lbl = ctk.CTkLabel(self.result_frame, text="", wraplength=560,
                                         justify="left", anchor="w", text_color=MUTED)
        self.verdict_lbl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        self.log = LogPanel(self, height=90)
        self.log.grid(row=5, column=0, sticky="nsew", padx=16, pady=(16, 16))
        self.grid_rowconfigure(5, weight=1)

    def _analyze(self):
        path = self.image_picker.get()
        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "Please choose a valid image.")
            return
        self.log.clear()
        try:
            result = analyze.chi_square_lsb_score(path)
        except Exception as e:
            self.log.log(str(e), "error")
            return

        color = {"high": DANGER, "medium": "#D6A445", "low": ACCENT}[result["risk"]]
        self.chi_lbl.configure(text=f"Chi-square: {result['chi_square']}")
        self.risk_lbl.configure(text=f"Risk: {result['risk'].upper()}", text_color=color)
        self.verdict_lbl.configure(text=f"{result['verdict']}\n\n{result['note']}")
        self.log.log("Analysis complete.", "success")


class AboutTab(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=f"{APP_NAME} v{APP_VERSION}",
                     font=("", 20, "bold")).grid(row=0, column=0, pady=(24, 4))
        ctk.CTkLabel(self, text="A feature-rich LSB steganography toolkit",
                     text_color=MUTED).grid(row=1, column=0, pady=(0, 20))

        features = [
            "Hide text or any file inside PNG, BMP, or WAV carriers",
            "AES-256-GCM password protection (PBKDF2, 200k iterations)",
            "Adjustable bit depth (1-4 bits/channel) — capacity vs. stealth trade-off",
            "Integrity checking via CRC32, byte-exact recovery",
            "Capacity calculator per carrier and bit depth",
            "Basic chi-square LSB steganalysis heuristic",
            "Command-line interface (cli.py) for scripting/automation",
        ]
        box = ctk.CTkFrame(self, fg_color=("gray92", "gray14"), corner_radius=10)
        box.grid(row=2, column=0, sticky="ew", padx=40)
        for i, feat in enumerate(features):
            ctk.CTkLabel(box, text=f"•  {feat}", anchor="w",
                         justify="left").grid(row=i, column=0, sticky="w", padx=16, pady=6)

        ctk.CTkLabel(self, text="Built for educational / authorized security research use only.",
                     text_color=MUTED, font=("", 11, "italic")).grid(row=3, column=0, pady=(20, 10))


class StegoSuiteApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — Steganography Toolkit")
        self.geometry("680x760")
        self.minsize(600, 640)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(header, text="🕵 StegoSuite", font=("", 22, "bold")).pack(side="left")
        ctk.CTkLabel(header, text=f"v{APP_VERSION}", text_color=MUTED).pack(side="left", padx=(8, 0))

        appearance = ctk.CTkOptionMenu(header, values=["Dark", "Light", "System"],
                                        width=100, command=self._change_appearance)
        appearance.set("Dark")
        appearance.pack(side="right")

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=16)
        for name in ["Hide", "Extract", "Capacity", "Analyze", "About"]:
            self.tabs.add(name)

        HideTab(self.tabs.tab("Hide")).pack(fill="both", expand=True)
        ExtractTab(self.tabs.tab("Extract")).pack(fill="both", expand=True)
        CapacityTab(self.tabs.tab("Capacity")).pack(fill="both", expand=True)
        AnalyzeTab(self.tabs.tab("Analyze")).pack(fill="both", expand=True)
        AboutTab(self.tabs.tab("About")).pack(fill="both", expand=True)

    @staticmethod
    def _change_appearance(choice):
        ctk.set_appearance_mode(choice.lower())


app_root = None  # set in main(), used by run_in_thread for .after() scheduling


def main():
    global app_root
    app_root = StegoSuiteApp()
    app_root.mainloop()


if __name__ == "__main__":
    main()
