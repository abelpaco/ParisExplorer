FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY automation.py .
COPY youtube_uploader.py .
COPY content_manager.py .
COPY scheduler.py .
COPY config.yaml .

# Create necessary directories
RUN mkdir -p content/videos content/images content/metadata logs temp uploaded

# Set timezone
ENV TZ=Europe/Paris
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Run the automation
CMD ["python", "automation.py", "--mode", "scheduler"]
