# ParisExplorer YouTube Automation - Setup Guide

## Prerequisites

- Python 3.8 or higher
- A Google Cloud Project with YouTube Data API v3 enabled
- A YouTube channel

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the YouTube Data API v3:
   - Navigate to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click "Enable"

4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app" as application type
   - Download the credentials JSON file
   - Save it as `client_secrets.json` in the project root

## Step 3: Configure Environment

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and fill in your values (optional, mainly for external APIs):
```bash
YOUTUBE_CHANNEL_ID=your_channel_id
EXTERNAL_API_URL=your_api_endpoint
EXTERNAL_API_KEY=your_api_key
```

## Step 4: Configure Automation

Edit `config.yaml` to customize:

- **Schedule times**: Set when you want posts to go live
- **Content sources**: Enable/disable local files, external URLs, or APIs
- **YouTube settings**: Default privacy, category, tags, location
- **Queue settings**: Maximum size, retry logic, archiving

Example schedule configuration:
```yaml
schedule:
  post_times:
    - "09:00"  # Morning
    - "14:00"  # Afternoon
    - "19:00"  # Evening
  timezone: "Europe/Paris"
  enabled: true
```

## Step 5: First Run - Authentication

On first run, you'll need to authenticate:

```bash
python automation.py --mode channel-info
```

This will:
1. Open a browser for OAuth authentication
2. Ask you to sign in to your Google account
3. Request permission to manage your YouTube channel
4. Save the authentication token for future use

## Step 6: Prepare Content

1. Create content folders:
```bash
mkdir -p content/videos content/images content/metadata
```

2. Add your videos, images, or text files to the `content/` directory

3. Optionally create JSON metadata files with the same name as your content:
```
content/
├── paris_tour.mp4
├── paris_tour.json          # Metadata
└── paris_tour_thumb.jpg     # Thumbnail
```

Example metadata file (`paris_tour.json`):
```json
{
  "title": "Amazing Paris Tour",
  "description": "Explore the beautiful city of Paris",
  "tags": ["Paris", "Travel", "France"],
  "privacy": "public"
}
```

## Step 7: Test the System

1. **Check the queue**:
```bash
python automation.py --mode queue
```

2. **Refresh content** (scan for new files):
```bash
python automation.py --mode refresh
```

3. **Post immediately** (test upload):
```bash
python automation.py --mode post-now
```

4. **Run scheduler** (automated posting):
```bash
python automation.py --mode scheduler
```

## Usage Modes

### Scheduler Mode (Default)
Run continuous automation with scheduled posts:
```bash
python automation.py --mode scheduler
```

### Manual Post
Upload next item from queue immediately:
```bash
python automation.py --mode post-now
```

### Refresh Content
Scan content sources and update queue:
```bash
python automation.py --mode refresh
```

### View Queue
Display current content queue:
```bash
python automation.py --mode queue
```

### Channel Info
Display your YouTube channel information:
```bash
python automation.py --mode channel-info
```

## Content Sources

### Local Files
Place files in the `content/` directory. The system will automatically scan and queue them.

### External URLs
Add URLs to `config.yaml`:
```yaml
content_sources:
  external_urls:
    enabled: true
    urls:
      - "https://example.com/video.mp4"
      - "https://example.com/image.jpg"
```

### External API
Configure an API endpoint in `config.yaml`:
```yaml
content_sources:
  external_api:
    enabled: true
    endpoint: "https://api.example.com/content"
    auth_type: "bearer"
```

Set the API key in `.env`:
```
EXTERNAL_API_KEY=your_api_key
```

## Running as a Service

### Linux (systemd)

Create `/etc/systemd/system/paris-explorer.service`:

```ini
[Unit]
Description=ParisExplorer YouTube Automation
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/ParisExplorer
ExecStart=/usr/bin/python3 automation.py --mode scheduler
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable paris-explorer
sudo systemctl start paris-explorer
sudo systemctl status paris-explorer
```

### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., "At startup")
4. Action: Start a program
   - Program: `python`
   - Arguments: `automation.py --mode scheduler`
   - Start in: `C:\path\to\ParisExplorer`

### Docker

Create `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "automation.py", "--mode", "scheduler"]
```

Build and run:
```bash
docker build -t paris-explorer .
docker run -d --name paris-explorer -v $(pwd)/content:/app/content paris-explorer
```

## Troubleshooting

### Authentication Issues
- Ensure `client_secrets.json` is in the project root
- Delete `token.json` and re-authenticate
- Check that YouTube Data API v3 is enabled

### Upload Failures
- Check video file format (MP4 recommended)
- Verify file size (< 128 GB for YouTube)
- Check quota limits in Google Cloud Console
- Review logs in `logs/automation.log`

### No Content in Queue
- Run `python automation.py --mode refresh`
- Check content directory has files
- Verify file formats in `config.yaml`
- Check logs for scanning errors

## API Quotas

YouTube Data API has daily quota limits:
- Default: 10,000 units per day
- Video upload: 1,600 units
- Thumbnail upload: 50 units

Monitor usage in Google Cloud Console.

## Best Practices

1. **Test with private videos first**
2. **Use descriptive titles and tags**
3. **Provide custom thumbnails** (1280x720 recommended)
4. **Schedule posts during peak times** for your audience
5. **Monitor logs regularly**
6. **Keep content organized** in the content directory
7. **Backup uploaded content history**

## Support

For issues or questions:
- Check logs: `logs/automation.log`
- Review YouTube API documentation
- Check Google Cloud Console for quota/errors

## Security Notes

- Never commit `client_secrets.json` or `token.json` to version control
- Keep `.env` file private
- Use environment variables for sensitive data
- Regularly rotate API keys
