import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import json
import os
import sys

# Configure yt-dlp command - assumes it's in the same directory or PATH
YT_DLP_CMD = 'yt-dlp'

class YtDlpGui:
    def __init__(self, root):
        self.root = root
        self.root.title("DL-Master (yt-dlp GUI)")
        self.root.geometry("600x500")
        self.root.configure(bg="#f0f0f0")

        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.create_widgets()

    def create_widgets(self):
        # Main Container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # URL Section
        url_frame = ttk.LabelFrame(main_frame, text="Video URL", padding="10")
        url_frame.pack(fill=tk.X, pady=5)
        
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(fill=tk.X, pady=5)

        # Formats Section
        fmt_frame = ttk.Frame(main_frame)
        fmt_frame.pack(fill=tk.X, pady=5)

        self.check_formats_btn = ttk.Button(fmt_frame, text="Check Formats", command=self.check_formats)
        self.check_formats_btn.pack(side=tk.LEFT, padx=5)

        self.formats_loading = ttk.Label(fmt_frame, text="")
        self.formats_loading.pack(side=tk.LEFT, padx=5)

        # Quality Selection (Hidden initially, but we'll just disable it)
        self.quality_var = tk.StringVar()
        self.quality_combo = ttk.Combobox(main_frame, textvariable=self.quality_var, state="readonly")
        self.quality_combo.set("Best Available (Default)")
        self.quality_combo.pack(fill=tk.X, pady=5)
        self.quality_map = {} # To store format_id mapping

        # Time Section
        time_frame = ttk.LabelFrame(main_frame, text="Time Range (mm:ss)", padding="10")
        time_frame.pack(fill=tk.X, pady=5)

        tk.Label(time_frame, text="Start:").grid(row=0, column=0, padx=5)
        self.start_var = tk.StringVar()
        self.start_entry = ttk.Entry(time_frame, textvariable=self.start_var, width=15)
        self.start_entry.grid(row=0, column=1, padx=5)

        tk.Label(time_frame, text="End:").grid(row=0, column=2, padx=5)
        self.end_var = tk.StringVar()
        self.end_entry = ttk.Entry(time_frame, textvariable=self.end_var, width=15)
        self.end_entry.grid(row=0, column=3, padx=5)
        
        # Bind Enter key on End Entry to Download
        self.end_entry.bind('<Return>', lambda e: self.start_download())

        # Download Button
        self.download_btn = ttk.Button(main_frame, text="Download Clip", command=self.start_download)
        self.download_btn.pack(fill=tk.X, pady=15)

        # Log Area
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_area = scrolledtext.ScrolledText(log_frame, height=8, state='disabled', font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # Configure tags for coloring
        self.log_area.tag_config('error', foreground='red')
        self.log_area.tag_config('success', foreground='green')
        self.log_area.tag_config('info', foreground='blue')

    def log(self, message, tag=None):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def check_formats(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL")
            return

        self.check_formats_btn.config(state=tk.DISABLED)
        self.formats_loading.config(text="Fetching formats...", foreground="blue")
        self.log(f"Fetching formats for: {url}", "info")

        threading.Thread(target=self._run_formats, args=(url,), daemon=True).start()

    def _run_formats(self, url):
        try:
            # Run yt-dlp -J to get JSON info
            # Using creationflags=subprocess.CREATE_NO_WINDOW to hide console on Windows if packaged
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                [YT_DLP_CMD, '-J', url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8', 
                startupinfo=startupinfo
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                self.root.after(0, self._formats_error, stderr)
            else:
                self.root.after(0, self._formats_success, stdout)

        except Exception as e:
            self.root.after(0, self._formats_error, str(e))

    def _formats_error(self, error_msg):
        self.check_formats_btn.config(state=tk.NORMAL)
        self.formats_loading.config(text="Error fetching formats", foreground="red")
        self.log(f"Error fetching formats: {error_msg}", "error")

    def _formats_success(self, json_data):
        self.check_formats_btn.config(state=tk.NORMAL)
        self.formats_loading.config(text="Formats loaded!", foreground="green")
        
        try:
            data = json.loads(json_data)
            self.log(f"Successfully fetched details for: {data.get('title', 'Unknown Title')}", "success")
            
            formats = data.get('formats', [])
            # Filter and process formats
            video_formats = []
            
            # Simple list for parsing
            self.quality_map = {} 
            display_values = ["Best Available (Default)"]
            self.quality_map["Best Available (Default)"] = "best"

            # Reverse to get best quality typically at bottom/top depending on list
            # yt-dlp usually sorts worst to best.
            for f in reversed(formats):
                # We want video resolutions, skip audio only usually (vcodec='none')
                if f.get('vcodec') != 'none' and f.get('resolution') != 'audio only':
                     fid = f.get('format_id')
                     res = f.get('resolution') or f"{f.get('width')}x{f.get('height')}"
                     ext = f.get('ext')
                     note = f.get('format_note', '')
                     filesize = f.get('filesize')
                     fs_str = f"{filesize / 1024 / 1024:.2f} MB" if filesize else "N/A"
                     
                     display_str = f"{res} ({ext}) - {note} [{fs_str}]"
                     display_values.append(display_str)
                     self.quality_map[display_str] = fid

            self.quality_combo['values'] = display_values
            self.quality_combo.current(0)

        except json.JSONDecodeError:
            self.log("Failed to parse JSON output from yt-dlp", "error")

    def start_download(self):
        url = self.url_var.get().strip()
        start = self.start_var.get().strip()
        end = self.end_var.get().strip()
        
        if not url or not start or not end:
            messagebox.showwarning("Missing Info", "Please fill in URL, Start Time, and End Time.")
            return

        display_quality = self.quality_combo.get()
        format_id = self.quality_map.get(display_quality, 'best')

        self.download_btn.config(state=tk.DISABLED, text="Downloading...")
        self.log(f"Starting download: {url} [{start} - {end}] (Format: {format_id})", "info")

        threading.Thread(target=self._run_download, args=(url, start, end, format_id), daemon=True).start()

    def _run_download(self, url, start, end, format_id):
        try:
            # Construct command
            # yt-dlp -f format_id url -o ... --download-sections ...
            cmd = [
                YT_DLP_CMD,
                '-f', format_id,
                url,
                '-o', '%(title)s_%(section_start)s-%(section_end)s_%(epoch)s.%(ext)s',
                '--restrict-filenames', # Prevent issues with special characters/length on Windows
                '--download-sections', f'*{start}-{end}',
                '--force-keyframes-at-cuts'
            ]

            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                startupinfo=startupinfo,
                bufsize=1 # Line buffered
            )

            # Read stdout line by line
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    self.root.after(0, self.log, line.strip())

            # Read stderr for errors
            stderr_out = process.stderr.read()
            if stderr_out:
                self.root.after(0, self.log, stderr_out.strip(), "error")

            rc = process.poll()
            
            if rc == 0:
                self.root.after(0, self._download_success)
            else:
                self.root.after(0, self._download_error)

        except Exception as e:
             self.root.after(0, self._download_error_msg, str(e))

    def _download_success(self):
        self.download_btn.config(state=tk.NORMAL, text="Download Clip")
        self.log("Download Completed Successfully!", "success")
        
        # User Requirement: Clear start/end and focus start ONLY on success
        self.start_var.set("")
        self.end_var.set("")
        self.start_entry.focus_set()

    def _download_error(self):
        self.download_btn.config(state=tk.NORMAL, text="Download Clip")
        self.log("Download Finished with Errors (Check log above).", "error")
        # User Requirement: Do NOT clear fields on error

    def _download_error_msg(self, msg):
        self.download_btn.config(state=tk.NORMAL, text="Download Clip")
        self.log(f"Execution Error: {msg}", "error")


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = YtDlpGui(root)
        root.mainloop()
    except Exception as e:
        # Fallback logging if GUI fails to start
        with open("error_log.txt", "w") as f:
            f.write(str(e))
