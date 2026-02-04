import os
import subprocess
import json
import uuid
import threading
from flask import Flask, render_template, request, jsonify, send_file, after_this_request

app = Flask(__name__)
# Configure yt-dlp command - assumes it's in the PATH or same directory
YT_DLP_CMD = 'yt-dlp'
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'downloads')

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def cleanup_file(filepath):
    """Deletes the file after response is sent."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Error removing file {filepath}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/formats', methods=['POST'])
def get_formats():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        # Run yt-dlp -J to get JSON info
        cmd = [YT_DLP_CMD, '-J', url]
        
        # Windows-specific startup info to hide console window
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
            startupinfo=startupinfo
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            return jsonify({'error': stderr or 'Unknown error fetching formats'}), 500

        data = json.loads(stdout)
        formats = data.get('formats', [])
        
        filtered_formats = []
        
        # User Logic: Filter out "Video Only" and "Audio Only"
        # We want Combined (vcodec != 'none' and acodec != 'none')
        # OR if user explicitly wants to see everything, but the request says:
        # "Show me things that don't have this [video only/audio only], meaning video and audio together"
        
        for f in formats:
            # Use 'unknown' as default to avoid filtering out formats where codec info is missing (like generic 'sd'/'hd')
            vcodec = f.get('vcodec', 'unknown')
            acodec = f.get('acodec', 'unknown')
            
            # Skip only if explicitly marked as 'none' (meaning stream is missing that component)
            if vcodec == 'none' or acodec == 'none':
                continue
                
            fid = f.get('format_id')
            # Handle "unknown resolution" logic: if resolution is 'unknown' or not present, use width x height
            res = f.get('resolution')
            width = f.get('width')
            height = f.get('height')
            
            if not res or res == 'unknown':
                if width and height:
                     res = f"{width}x{height}"
                else:
                     res = f"{fid}"
            
            ext = f.get('ext', '')
            note = f.get('format_note', '')
            filesize = f.get('filesize')
            fs_str = f"{filesize / 1024 / 1024:.2f} MB" if filesize else "N/A"
            
            display_str = f"{res} ({ext}) - {note} [{fs_str}]"
            
            filtered_formats.append({
                'id': fid,
                'display': display_str,
                'res': res, # For sorting potentially
                'filesize': filesize or 0
            })
            
        # Sort by filesize usually indicates quality for combined streams
        filtered_formats.sort(key=lambda x: x['filesize'], reverse=True)
        
        # Add a "Best" option at the top
        filtered_formats.insert(0, {'id': 'best', 'display': 'Best Quality (Default)'})

        # Extract duration
        duration_sec = data.get('duration', 0)
        duration_str = data.get('duration_string')
        
        # If no duration is provided, treat it as less than an hour (3600 seconds)
        if not duration_sec:
            duration_sec = 3600
        
        # Fallback formatting if duration_string is missing
        if not duration_str:
             m, s = divmod(int(duration_sec), 60)
             h, m = divmod(m, 60)
             if h > 0:
                 duration_str = f"{h}:{m:02d}:{s:02d}"
             else:
                 duration_str = f"{m:02d}:{s:02d}"

        return jsonify({
            'title': data.get('title', 'Unknown'), 
            'formats': filtered_formats,
            'duration': duration_sec,
            'duration_string': duration_str
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id', 'best')
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    # Helper function to convert time string to seconds
    def time_to_seconds(time_str):
        if not time_str:
            return 0
        parts = time_str.strip().split(':')[::-1]
        seconds = 0
        if len(parts) > 0:
            seconds += int(parts[0])
        if len(parts) > 1:
            seconds += int(parts[1]) * 60
        if len(parts) > 2:
            seconds += int(parts[2]) * 3600
        return seconds

    # Validate time inputs
    if start_time and end_time:
        start_sec = time_to_seconds(start_time)
        end_sec = time_to_seconds(end_time)
        if end_sec <= start_sec:
            return jsonify({'error': 'End time must be greater than Start time.'}), 400

    try:
        # Get video duration first to validate times
        cmd_info = [YT_DLP_CMD, '-J', url]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.Popen(
            cmd_info,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            startupinfo=startupinfo
        )
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            video_info = json.loads(stdout)
            duration = video_info.get('duration', 0)
            
            # If no duration is provided, treat it as less than an hour (3599 seconds)
            if not duration:
                duration = 3599
            
            # Validate start_time and end_time against duration
            if start_time:
                start_sec = time_to_seconds(start_time)
                if start_sec > duration:
                    return jsonify({'error': f'Start time exceeds video duration ({duration} seconds).'}), 400
            
            if end_time:
                end_sec = time_to_seconds(end_time)
                if end_sec > (duration+1):
                    return jsonify({'error': f'End time exceeds video duration ({duration} seconds).'}), 400

        # Generate unique filename for temp storage
        file_id = str(uuid.uuid4())
        # Template for output filename: id.ext
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

        cmd = [
            YT_DLP_CMD,
            '-f', format_id,
            url,
            '-o', output_template,
            '--force-keyframes-at-cuts'
        ]

        if start_time and end_time:
             cmd.extend(['--download-sections', f'*{start_time}-{end_time}'])

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
            startupinfo=startupinfo
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
             return jsonify({'error': stderr}), 500

        # Find the downloaded file
        downloaded_file = None
        for file in os.listdir(DOWNLOAD_FOLDER):
            if file.startswith(file_id):
                downloaded_file = os.path.join(DOWNLOAD_FOLDER, file)
                break
        
        if not downloaded_file:
            return jsonify({'error': 'Download failed, file not found.'}), 500

        # Return the file name for the client to request download
        return jsonify({'download_url': f'/get-file/{os.path.basename(downloaded_file)}'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-file/<filename>')
def get_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return "File not found", 404

    @after_this_request
    def remove_file(response):
        try:
            # Clean up in a separate thread/timer to allow file handle release? 
            # Flask usually handles streaming fine, but on Windows file locks can be tricky.
            # We'll rely on OS simple remove, wrapped in try-except.
            # Actually, `send_file` keeps it open. We might need `send_from_directory`.
            # A robust way is a scheduled cleanup. But let's try immediate remove.
            # Wait, standard practice for temp downloads is hard in simple Flask.
            # We will use a timer based cleanup or just leave them for now?
            # User wants a robust solution. I'll add a timer thread to delete it after 60s.
            threading.Timer(60, lambda: cleanup_file(filepath)).start()
        except Exception as e:
            print(e)
        return response

    return send_file(filepath, as_attachment=True)

if __name__ == '__main__':
    # Determine port from env or default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
