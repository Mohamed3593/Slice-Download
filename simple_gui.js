const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn, exec } = require('child_process');

const PORT = 3000;
const PUBLIC_DIR = path.join(__dirname, 'public');
const YT_DLP_CMD = 'yt-dlp'; // Assumed to be in PATH or same dir. Adjust if needed.

const server = http.createServer((req, res) => {
    // CORS headers for local development convenience
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    if (req.method === 'GET') {
        let filePath = path.join(PUBLIC_DIR, req.url === '/' ? 'index.html' : req.url);
        const extname = path.extname(filePath);
        let contentType = 'text/html';

        switch (extname) {
            case '.js': contentType = 'text/javascript'; break;
            case '.css': contentType = 'text/css'; break;
            case '.json': contentType = 'application/json'; break;
        }

        fs.readFile(filePath, (err, content) => {
            if (err) {
                if (err.code === 'ENOENT') {
                    res.writeHead(404);
                    res.end('404 Not Found');
                } else {
                    res.writeHead(500);
                    res.end(`Server Error: ${err.code}`);
                }
            } else {
                res.writeHead(200, { 'Content-Type': contentType });
                res.end(content, 'utf-8');
            }
        });
    } else if (req.method === 'POST' && req.url === '/api/formats') {
        collectRequestData(req, (data) => {
            const { url } = data;
            if (!url) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'URL is required' }));
                return;
            }

            console.log(`Fetching formats for: ${url}`);
            // Use -J (dump-json) to get structured data
            const ytdlp = spawn(YT_DLP_CMD, ['-J', url], { cwd: '..' }); 

            let stdoutData = '';
            let stderrData = '';

            ytdlp.stdout.on('data', (chunk) => stdoutData += chunk);
            ytdlp.stderr.on('data', (chunk) => stderrData += chunk);

            ytdlp.on('close', (code) => {
                if (code !== 0) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Failed to fetch formats', details: stderrData }));
                } else {
                    try {
                        const json = JSON.parse(stdoutData);
                        // Filter and map formats to a simpler structure
                        // yt-dlp 'formats' array contains all variants
                        const formats = (json.formats || []).map(f => ({
                            format_id: f.format_id,
                            ext: f.ext,
                            resolution: f.resolution || (f.width && f.height ? `${f.width}x${f.height}` : 'audio only'),
                            note: f.format_note || '',
                            filesize: f.filesize ? (f.filesize / 1024 / 1024).toFixed(2) + ' MB' : 'N/A',
                            vcodec: f.vcodec,
                            acodec: f.acodec
                        })).filter(f => f.resolution !== 'audio only'); // specific user request seemed to focus on video quality

                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ title: json.title, formats: formats }));
                    } catch (e) {
                        res.writeHead(500, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ error: 'Failed to parse JSON output', details: e.message }));
                    }
                }
            });
        });

    } else if (req.method === 'POST' && req.url === '/api/download') {
        collectRequestData(req, (data) => {
            const { url, format_id, start_time, end_time } = data;

            if (!url || !start_time || !end_time) {
                 res.writeHead(400, { 'Content-Type': 'application/json' });
                 res.end(JSON.stringify({ error: 'Missing parameters' }));
                 return;
            }
            
            // Construct the exact command requested:
            // yt-dlp -F "720p_HD" "link" -o "..." --download-sections "*34:31-36:00"
            // Note: -f (lowercase) is for selecting format, -F is for listing.
            // User said "check box executes -F", which means listing. 
            // Then "drop list... executes -f".
            
            const args = [
                '-f', format_id || 'best', // Default to best if no specific format selected
                url,
                '-o', '%(title)s_%(section_start)s-%(section_end)s_%(epoch)s.%(ext)s',
                '--download-sections', `*${start_time}-${end_time}`,
                '--force-keyframes-at-cuts' // Good practice for section downloads
            ];

            console.log(`Starting download: ${YT_DLP_CMD} ${args.join(' ')}`);

            // We can spawn and detach, or wait. Let's wait and stream logs back? 
            // For a simple GUI, just starting it and returning "Started" is often enough, 
            // but streaming logs is better. For simplicity, we'll wait for completion here 
            // or provide a simple log mechanism.
            // Let's use spawn and forward status immediately, maybe just text stream?
            
            res.writeHead(200, { 'Content-Type': 'text/plain' });
            
            const child = spawn(YT_DLP_CMD, args, { cwd: '..' }); // execution in parent dir (c:\ffmpeg)

            child.stdout.on('data', (chunk) => {
                res.write(chunk);
            });
            child.stderr.on('data', (chunk) => {
                res.write(chunk);
            });

            child.on('close', (code) => {
                res.write(`\nProcess exited with code ${code}`);
                res.end();
            });
        });
    } else {
        res.writeHead(404);
        res.end('Not Found');
    }
});

function collectRequestData(request, callback) {
    const FORM_URLENCODED = 'application/x-www-form-urlencoded';
    if(request.headers['content-type'] === FORM_URLENCODED) {
        let body = '';
        request.on('data', chunk => {
            body += chunk.toString();
        });
        request.on('end', () => {
            callback(parseQueryString(body));
        });
    }
    else {
        let body = '';
        request.on('data', chunk => {
            body += chunk.toString();
        });
        request.on('end', () => {
            try {
                callback(JSON.parse(body));
            } catch (e) {
                callback({});
            }
        });
    }
}

server.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}/`);
    console.log(`Serving files from ${PUBLIC_DIR}`);
});
