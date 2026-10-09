import os
import re
import queue
import shutil
import tempfile
import threading
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import imageio_ffmpeg
from pytubefix import YouTube

QUALITIES = {
    "Highest (320 kbps)": "320",
    "High (256 kbps)": "256",
    "Medium (192 kbps)": "192",
    "Low (128 kbps)": "128",
    "Very Low (96 kbps)": "96",
}
DEFAULT_QUALITY = "Highest (320 kbps)"


def default_download_dir():
    downloads = Path.home() / "Downloads"
    return str(downloads) if downloads.is_dir() else str(Path.home())


def sanitize_filename(name):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    return cleaned or "audio"


class ConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube to MP3 Converter")
        self.root.minsize(560, 260)

        self.events = queue.Queue()
        self.worker = None

        pad = {"padx": 10, "pady": 6}

        tk.Label(root, text="YouTube URL:").grid(row=0, column=0, sticky="w", **pad)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(root, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)

        tk.Label(root, text="Quality:").grid(row=1, column=0, sticky="w", **pad)
        self.quality_var = tk.StringVar(value=DEFAULT_QUALITY)
        self.quality_combo = ttk.Combobox(
            root,
            textvariable=self.quality_var,
            values=list(QUALITIES.keys()),
            state="readonly",
        )
        self.quality_combo.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)

        tk.Label(root, text="Save to:").grid(row=2, column=0, sticky="w", **pad)
        self.folder_var = tk.StringVar(value=default_download_dir())
        self.folder_entry = ttk.Entry(root, textvariable=self.folder_var)
        self.folder_entry.grid(row=2, column=1, sticky="ew", **pad)
        self.browse_btn = ttk.Button(root, text="Browse...", command=self.browse)
        self.browse_btn.grid(row=2, column=2, sticky="ew", **pad)

        self.convert_btn = ttk.Button(root, text="Convert", command=self.start)
        self.convert_btn.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(root, textvariable=self.status_var, anchor="w").grid(
            row=5, column=0, columnspan=3, sticky="ew", **pad
        )

        root.columnconfigure(1, weight=1)
        self.root.after(100, self.poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def browse(self):
        chosen = filedialog.askdirectory(
            title="Choose destination folder",
            initialdir=self.folder_var.get() or default_download_dir(),
        )
        if chosen:
            self.folder_var.set(chosen)

    def start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a YouTube URL.")
            return
        folder = self.folder_var.get().strip() or default_download_dir()
        if not os.path.isdir(folder):
            messagebox.showerror("Invalid folder", "The selected folder does not exist.")
            return
        bitrate = QUALITIES[self.quality_var.get()]

        self.convert_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("Starting...")

        self.worker = threading.Thread(
            target=self.convert, args=(url, folder, bitrate), daemon=True
        )
        self.worker.start()

    def convert(self, url, folder, bitrate):
        temp_dir = tempfile.mkdtemp(prefix="ytmp3_")
        try:
            self.events.put(("status", "Fetching video info..."))
            yt = YouTube(url, on_progress_callback=self.on_download_progress)
            title = sanitize_filename(yt.title)

            stream = yt.streams.get_audio_only()
            if stream is None:
                raise RuntimeError("No audio stream available for this video.")

            self.events.put(("status", "Downloading audio..."))
            downloaded = stream.download(output_path=temp_dir)

            self.events.put(("status", "Converting to MP3..."))
            self.events.put(("progress", 100))
            output = os.path.join(folder, f"{title}.mp3")
            output = self.unique_path(output)
            self.to_mp3(downloaded, output, bitrate)

            self.events.put(("done", output))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def to_mp3(self, source, destination, bitrate):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                source,
                "-vn",
                "-b:a",
                f"{bitrate}k",
                destination,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "ffmpeg conversion failed:\n"
                + result.stderr.decode(errors="replace").strip()[-500:]
            )

    @staticmethod
    def unique_path(path):
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        return f"{base} ({i}){ext}"

    def on_download_progress(self, stream, chunk, bytes_remaining):
        total = stream.filesize or 0
        if total:
            done = total - bytes_remaining
            self.events.put(("progress", done * 100 / total))

    def poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.status_var.set(value)
                elif kind == "progress":
                    self.progress["value"] = value
                elif kind == "done":
                    self.progress["value"] = 100
                    self.status_var.set(f"Saved: {value}")
                    self.reset_buttons()
                    messagebox.showinfo("Success", f"Saved to:\n{value}")
                elif kind == "error":
                    self.status_var.set("Error")
                    self.reset_buttons()
                    messagebox.showerror("Conversion failed", value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def reset_buttons(self):
        self.convert_btn.config(state="normal")
        self.browse_btn.config(state="normal")

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Quit", "A conversion is in progress. Quit anyway?"):
                return
        self.root.destroy()


def main():
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
