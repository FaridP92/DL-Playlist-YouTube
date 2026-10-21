# -*- coding: utf-8 -*-
"""
Téléchargeur de playlists YouTube (interface graphique)
- URL de la playlist, format de sortie, dossier de destination
- Utilise yt-dlp.exe et ffmpeg présents à côté du script (ou dans le PATH)
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / ".downloader_settings.json"

# label affiché -> (type, option)
FORMATS = {
    "MP3 (audio)": ("audio", "mp3"),
    "M4A / AAC (audio)": ("audio", "m4a"),
    "OPUS (audio)": ("audio", "opus"),
    "FLAC (audio sans perte)": ("audio", "flac"),
    "WAV (audio non compressé)": ("audio", "wav"),
    "MP4 - meilleure qualité (vidéo)": ("video", "bv*+ba/b"),
    "MP4 - 1080p max (vidéo)": ("video", "bv*[height<=1080]+ba/b[height<=1080]"),
    "MP4 - 720p max (vidéo)": ("video", "bv*[height<=720]+ba/b[height<=720]"),
    "MP4 - 480p max (vidéo)": ("video", "bv*[height<=480]+ba/b[height<=480]"),
}

AUDIO_QUALITIES = {
    "Haute (~245 kbps)": "0",
    "Standard (~190 kbps)": "2",
    "Légère (~150 kbps)": "5",
    "Très légère (~100 kbps)": "7",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_yt_dlp():
    for c in (APP_DIR / "yt-dlp.exe", shutil.which("yt-dlp.exe"), shutil.which("yt-dlp")):
        if c and Path(c).exists():
            return [str(c)]
    return None


def find_ffmpeg():
    local = APP_DIR / "ffmpeg"
    for c in (local / "bin" / "ffmpeg.exe", local / "ffmpeg.exe", shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return str(c)
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Téléchargeur de playlists YouTube")
        self.minsize(720, 560)
        self.proc = None
        self.worker = None
        self.cancelled = False
        self.log_q = queue.Queue()

        s = self.load_settings()
        self.url_var = tk.StringVar(value=s.get("url", ""))
        self.format_var = tk.StringVar(value=s.get("format", "MP3 (audio)"))
        self.quality_var = tk.StringVar(value=s.get("quality", "Standard (~190 kbps)"))
        self.dest_var = tk.StringVar(
            value=s.get("dest", str(Path.home() / "Downloads" / "YouTubePlaylists"))
        )
        self.cookies_var = tk.StringVar(value=s.get("cookies", ""))
        self.subfolder_var = tk.BooleanVar(value=s.get("subfolder", True))
        self.numbering_var = tk.BooleanVar(value=s.get("numbering", False))
        self.archive_var = tk.BooleanVar(value=s.get("archive", True))

        self.build_ui()
        self.format_var.trace_add("write", lambda *_: self.refresh_quality_state())
        self.refresh_quality_state()
        self.after(100, self.drain_log)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI ----------
    def build_ui(self):
        pad = {"padx": 10, "pady": 5}
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(8, weight=1)

        ttk.Label(root, text="URL de la playlist").grid(row=0, column=0, sticky="w", **pad)
        url_entry = ttk.Entry(root, textvariable=self.url_var)
        url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        url_entry.focus_set()

        ttk.Label(root, text="Format").grid(row=1, column=0, sticky="w", **pad)
        ttk.Combobox(
            root, textvariable=self.format_var, values=list(FORMATS), state="readonly"
        ).grid(row=1, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(root, text="Qualité audio").grid(row=2, column=0, sticky="w", **pad)
        self.quality_box = ttk.Combobox(
            root, textvariable=self.quality_var, values=list(AUDIO_QUALITIES), state="readonly"
        )
        self.quality_box.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(root, text="Dossier de destination").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(root, textvariable=self.dest_var).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(root, text="Parcourir…", command=self.pick_dest).grid(row=3, column=2, **pad)

        ttk.Label(root, text="cookies.txt (optionnel)").grid(row=4, column=0, sticky="w", **pad)
        ttk.Entry(root, textvariable=self.cookies_var).grid(row=4, column=1, sticky="ew", **pad)
        ttk.Button(root, text="Choisir…", command=self.pick_cookies).grid(row=4, column=2, **pad)

        opts = ttk.Frame(root)
        opts.grid(row=5, column=0, columnspan=3, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Créer un sous-dossier au nom de la playlist",
                        variable=self.subfolder_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="Numéroter les fichiers (01 - titre…)",
                        variable=self.numbering_var).pack(anchor="w")
        ttk.Checkbutton(opts, text="Ne pas retélécharger ce qui l'a déjà été (archive)",
                        variable=self.archive_var).pack(anchor="w")

        btns = ttk.Frame(root)
        btns.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)
        self.start_btn = ttk.Button(btns, text="Télécharger", command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Annuler", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        ttk.Button(btns, text="Ouvrir le dossier", command=self.open_dest).pack(side="left")
        ttk.Button(btns, text="Mettre à jour yt-dlp", command=self.update_ytdlp).pack(side="right")

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", **pad)

        self.log = tk.Text(root, height=12, state="disabled", wrap="word",
                           background="#1e1e1e", foreground="#d4d4d4", font=("Consolas", 9))
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew", **pad)
        sb = ttk.Scrollbar(root, command=self.log.yview)
        sb.grid(row=8, column=3, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)

        self.status = tk.StringVar(value="Prêt.")
        ttk.Label(root, textvariable=self.status).grid(row=9, column=0, columnspan=3, sticky="w", **pad)

    def refresh_quality_state(self):
        kind = FORMATS[self.format_var.get()][0]
        lossy = FORMATS[self.format_var.get()][1] in ("mp3", "m4a", "opus")
        self.quality_box.configure(state="readonly" if kind == "audio" and lossy else "disabled")

    # ---------- Settings ----------
    def load_settings(self):
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        data = {
            "url": self.url_var.get(), "format": self.format_var.get(),
            "quality": self.quality_var.get(), "dest": self.dest_var.get(),
            "cookies": self.cookies_var.get(), "subfolder": self.subfolder_var.get(),
            "numbering": self.numbering_var.get(), "archive": self.archive_var.get(),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ---------- Actions ----------
    def pick_dest(self):
        d = filedialog.askdirectory(initialdir=self.dest_var.get() or str(Path.home()))
        if d:
            self.dest_var.set(os.path.normpath(d))

    def pick_cookies(self):
        f = filedialog.askopenfilename(filetypes=[("cookies.txt", "*.txt"), ("Tous", "*.*")])
        if f:
            self.cookies_var.set(os.path.normpath(f))

    def open_dest(self):
        d = Path(self.dest_var.get())
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(d)

    def write(self, text):
        self.log_q.put(text)

    def drain_log(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                if isinstance(line, tuple):  # ("progress", pct)
                    self.progress["value"] = line[1]
                    continue
                self.log.configure(state="normal")
                self.log.insert("end", line if line.endswith("\n") else line + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.drain_log)

    def build_command(self, yt, ffmpeg, url):
        kind, opt = FORMATS[self.format_var.get()]
        dest = Path(self.dest_var.get())
        folder = "%(playlist_title|Videos)s/" if self.subfolder_var.get() else ""
        num = "%(playlist_index)02d - " if self.numbering_var.get() else ""
        tpl = str(dest / f"{folder}{num}%(title)s.%(ext)s")

        cmd = yt + [
            "--yes-playlist", "--ignore-errors", "--no-abort-on-error",
            "--newline", "--no-colors", "--continue", "--no-overwrites",
            "--fragment-retries", "50", "--concurrent-fragments", "4",
            "--user-agent", USER_AGENT,
            "--ffmpeg-location", ffmpeg,
            "--embed-metadata", "--no-write-playlist-metafiles",
            "-o", tpl,
        ]
        if self.archive_var.get():
            cmd += ["--download-archive", str(dest / ".yt_archive.txt")]
        cookies = self.cookies_var.get().strip()
        if cookies:
            cmd += ["--cookies", cookies]

        if kind == "audio":
            cmd += ["-f", "bestaudio/best", "-x", "--audio-format", opt]
            if opt != "wav":  # WAV ne supporte pas les pochettes
                cmd += ["--embed-thumbnail"]
            if opt in ("mp3", "m4a", "opus"):
                cmd += ["--audio-quality", AUDIO_QUALITIES[self.quality_var.get()]]
        else:
            cmd += ["-f", opt, "--merge-output-format", "mp4"]
        return cmd + [url]

    def start(self):
        url = self.url_var.get().strip()
        dest = self.dest_var.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("URL manquante", "Colle l'URL de la playlist YouTube.")
            return
        if not dest:
            messagebox.showwarning("Destination manquante", "Choisis un dossier de destination.")
            return
        yt = find_yt_dlp()
        if not yt:
            messagebox.showerror("yt-dlp introuvable",
                                 "Place yt-dlp.exe à côté du script ou ajoute-le au PATH.")
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            messagebox.showerror("ffmpeg introuvable",
                                 "Place ffmpeg dans le dossier 'ffmpeg\\bin' ou ajoute-le au PATH.")
            return
        cookies = self.cookies_var.get().strip()
        if cookies and not Path(cookies).is_file():
            messagebox.showerror("cookies.txt introuvable", f"Fichier absent :\n{cookies}")
            return
        try:
            Path(dest).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Dossier invalide", str(e))
            return

        self.save_settings()
        cmd = self.build_command(yt, ffmpeg, url)
        self.cancelled = False
        self.progress["value"] = 0
        self.set_running(True)
        self.write(f"> {self.format_var.get()} -> {dest}\n")
        self.worker = threading.Thread(target=self.run, args=(cmd,), daemon=True)
        self.worker.start()

    def run(self, cmd):
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            for line in self.proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                self.parse_progress(line)
                self.write(line)
            code = self.proc.wait()
            if self.cancelled:
                msg = "Annulé."
            elif code == 0:
                msg = "Terminé ✅"
            else:
                msg = f"Terminé avec des erreurs (code {code}) — voir le journal."
        except Exception as e:
            msg = f"Erreur : {e}"
        self.write(msg)
        self.after(0, lambda: self.finish(msg))

    def parse_progress(self, line):
        # "[download]  42.3% of ..." et "Downloading item 3 of 20"
        if line.startswith("[download]") and "%" in line:
            try:
                pct = float(line.split("%")[0].split()[-1])
                self.log_q.put(("progress", pct))
            except ValueError:
                pass
        elif "Downloading item" in line:
            self.after(0, lambda l=line: self.status.set(l.replace("[download] ", "")))

    def finish(self, msg):
        self.status.set(msg)
        self.set_running(False)

    def set_running(self, running):
        self.start_btn.configure(state="disabled" if running else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")
        if running:
            self.status.set("Téléchargement en cours…")

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            if os.name == "nt":  # tue aussi les processus enfants (ffmpeg)
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                               creationflags=CREATE_NO_WINDOW, capture_output=True)
            else:
                self.proc.terminate()

    def update_ytdlp(self):
        yt = find_yt_dlp()
        if not yt:
            messagebox.showerror("yt-dlp introuvable", "Aucun yt-dlp détecté.")
            return
        self.start_btn.configure(state="disabled")
        self.write("> Mise à jour de yt-dlp…")

        def job():
            try:
                r = subprocess.run(yt + ["-U"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   creationflags=CREATE_NO_WINDOW)
                self.write((r.stdout + r.stderr).strip())
            except Exception as e:
                self.write(f"Erreur : {e}")
            self.after(0, lambda: self.start_btn.configure(state="normal"))

        threading.Thread(target=job, daemon=True).start()

    def on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Quitter", "Un téléchargement est en cours. Quitter quand même ?"):
                return
            self.cancel()
        self.save_settings()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
