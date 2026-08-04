FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# ffmpeg is required by moviepy for the video creation pipeline
RUN apt-get update && apt-get install -y \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
# Copy every Python module: automation.py imports video_creator (which in turn
# needs utils.py), so listing files one by one silently breaks the image.
COPY *.py ./
COPY config.yaml .

# Create necessary directories
RUN mkdir -p content/videos content/images content/metadata logs temp uploaded

# Set timezone
ENV TZ=Europe/Paris
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Run the automation
CMD ["python", "automation.py", "--mode", "scheduler"]
