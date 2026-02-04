FROM python:3.9-slim

# 1. Install system dependencies (FFmpeg is crucial here)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. Set up working directory
WORKDIR /app

# 3. Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of the application code
COPY . .

# 5. Create downloads directory
RUN mkdir -p downloads

# 6. Expose the port (Hugging Face uses 7860)
ENV PORT=7860
EXPOSE 7860

# 7. Start the application using Gunicorn (Production Server)
CMD gunicorn -w 2 -b 0.0.0.0:$PORT app:app
