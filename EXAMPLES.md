# ParisExplorer Automation - Usage Examples

This document provides practical examples for using the ParisExplorer YouTube automation system.

## Table of Contents

1. [Basic Setup](#basic-setup)
2. [Content Preparation](#content-preparation)
3. [Metadata Examples](#metadata-examples)
4. [Running Automation](#running-automation)
5. [Advanced Configuration](#advanced-configuration)
6. [Troubleshooting Examples](#troubleshooting-examples)

## Basic Setup

### First-Time Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run quick start guide
python quickstart.py

# 3. Authenticate with YouTube
python automation.py --mode channel-info
```

### Check System Status

```bash
# View system report
python utils.py

# Test configuration
python test_system.py

# View current queue
python automation.py --mode queue
```

## Content Preparation

### Example 1: Simple Video Upload

**File Structure:**
```
content/videos/
├── paris_eiffel_tour.mp4
└── paris_eiffel_tour.json
```

**paris_eiffel_tour.json:**
```json
{
  "title": "Eiffel Tower Tour - Paris 2024",
  "description": "Experience the magnificent Eiffel Tower in Paris, France. Watch as we explore this iconic landmark from base to summit.\n\n📍 Location: Champ de Mars, Paris\n🎫 Visit: www.toureiffel.paris\n\n#Paris #EiffelTower #France",
  "tags": ["Paris", "Eiffel Tower", "France", "Travel", "Tourism", "Europe"],
  "privacy": "public"
}
```

### Example 2: Video with Custom Thumbnail

**File Structure:**
```
content/videos/
├── louvre_museum.mp4
├── louvre_museum.json
└── louvre_museum_thumb.jpg
```

**louvre_museum.json:**
```json
{
  "title": "Inside the Louvre Museum - Art and History",
  "description": "Join us on a journey through the world's most visited museum. Discover masterpieces including the Mona Lisa and Venus de Milo.\n\n🏛️ Museum: Louvre\n🎨 Location: Paris, France\n⏰ Hours: 9am - 6pm (Closed Tuesdays)\n\n#Louvre #Museum #Art #Paris",
  "tags": ["Louvre", "Museum", "Art", "Paris", "Mona Lisa", "Culture"],
  "privacy": "public",
  "category": "27"
}
```

### Example 3: Multiple Videos in Queue

```bash
# Add multiple videos to content directory
mkdir -p content/videos
cp video1.mp4 video2.mp4 video3.mp4 content/videos/

# Refresh content (scan for new files)
python automation.py --mode refresh

# View queue
python automation.py --mode queue
```

**Output:**
```
=== Content Queue ===
Total items: 3
Pending: 3
Uploaded: 0

Pending items:
1. [video] Eiffel Tower Tour - Paris 2024
   File: content/videos/video1.mp4
2. [video] Louvre Museum Tour
   File: content/videos/video2.mp4
3. [video] Notre Dame Cathedral
   File: content/videos/video3.mp4
```

## Metadata Examples

### Category IDs

Common YouTube category IDs:
- `19` - Travel & Events (default for ParisExplorer)
- `27` - Education
- `22` - People & Blogs
- `24` - Entertainment
- `10` - Music

### Privacy Settings

- `public` - Visible to everyone
- `unlisted` - Only people with the link can view
- `private` - Only you can view

### Example: Educational Content

```json
{
  "title": "History of Paris: From Roman Times to Today",
  "description": "An educational journey through 2000 years of Parisian history. Learn about the founding of Lutetia, the medieval period, the French Revolution, and modern Paris.\n\n📚 Educational Series\n🏛️ History\n🇫🇷 France\n\nTimestamps:\n0:00 - Introduction\n1:30 - Roman Lutetia\n5:00 - Medieval Paris\n10:00 - French Revolution\n15:00 - Modern Paris",
  "tags": ["History", "Paris", "Education", "France", "Culture", "Learning"],
  "privacy": "public",
  "category": "27"
}
```

### Example: Short Video/Vlog Style

```json
{
  "title": "Hidden Gem in Paris 🇫🇷 #Paris #Travel #Shorts",
  "description": "Discovered this amazing hidden café in Montmartre! ☕️✨\n\nLocation: Le Consulat, Montmartre\n\n#ParisTravel #Montmartre #HiddenGems #ParisExplorer",
  "tags": ["Paris", "Travel", "Shorts", "Montmartre", "Café", "France"],
  "privacy": "public"
}
```

## Running Automation

### Scenario 1: Daily Automated Posts

**Configuration (config.yaml):**
```yaml
schedule:
  post_times:
    - "09:00"  # Morning audience
    - "18:00"  # Evening audience
  timezone: "Europe/Paris"
  enabled: true
```

**Run:**
```bash
# Start scheduler (runs continuously)
python automation.py --mode scheduler
```

**Output:**
```
2024-12-06 08:59:45 - INFO - Starting automation scheduler...
2024-12-06 08:59:45 - INFO - Scheduled jobs: 2
2024-12-06 08:59:45 - INFO -   - 09:00 (next: 2024-12-06 09:00:00)
2024-12-06 08:59:45 - INFO -   - 18:00 (next: 2024-12-06 18:00:00)
2024-12-06 09:00:00 - INFO - Executing scheduled post
2024-12-06 09:00:05 - INFO - Processing content: Eiffel Tower Tour
2024-12-06 09:02:30 - INFO - Upload progress: 50%
2024-12-06 09:04:15 - INFO - Upload progress: 100%
2024-12-06 09:04:15 - INFO - Video uploaded successfully. Video ID: abc123xyz
2024-12-06 09:04:16 - INFO - Scheduled post completed successfully
```

### Scenario 2: Manual Upload

```bash
# Upload next item in queue immediately
python automation.py --mode post-now
```

### Scenario 3: Refresh Content Without Posting

```bash
# Scan for new content and update queue
python automation.py --mode refresh

# View what was found
python automation.py --mode queue
```

## Advanced Configuration

### Example: External URL Configuration

**config.yaml:**
```yaml
content_sources:
  external_urls:
    enabled: true
    urls:
      - "https://cdn.example.com/paris_videos/sunset.mp4"
      - "https://storage.example.com/eiffel_timelapse.mp4"
```

**Run refresh to download:**
```bash
python automation.py --mode refresh
```

### Example: Custom Schedule for High Engagement

Based on YouTube analytics, post when your audience is most active:

**config.yaml:**
```yaml
schedule:
  post_times:
    - "07:00"   # Early morning Europe
    - "12:00"   # Lunch time Europe / Morning Americas
    - "19:00"   # Evening Europe / Afternoon Americas
    - "22:00"   # Evening Americas / Night Europe
  timezone: "Europe/Paris"
```

### Example: Testing Configuration

For testing, use more frequent posts:

**config.yaml (testing):**
```yaml
schedule:
  post_times:
    - "10:00"
    - "10:15"
    - "10:30"
    - "10:45"
  timezone: "Europe/Paris"
  enabled: true

youtube:
  default_privacy: "private"  # Keep test videos private
```

## Troubleshooting Examples

### Example 1: Video Upload Failed

**Check logs:**
```bash
tail -100 logs/automation.log
```

**Common issues:**
- Video format not supported → Convert to MP4
- File too large → Compress video
- API quota exceeded → Wait for quota reset
- Authentication expired → Re-run `python automation.py --mode channel-info`

### Example 2: Queue is Empty

```bash
# Check content directory
ls -la content/videos/

# Manually scan for content
python automation.py --mode refresh

# Check if files were found
python automation.py --mode queue
```

### Example 3: Authentication Issues

```bash
# Delete existing token
rm token.json

# Re-authenticate
python automation.py --mode channel-info

# Follow OAuth prompts in browser
```

### Example 4: Schedule Not Working

**Debug:**
```python
# Test schedule manually
python -c "
from scheduler import AutomationScheduler
import yaml

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

def test_post():
    print('Post callback triggered!')
    return True

scheduler = AutomationScheduler(config, test_post)
jobs = scheduler.list_jobs()
for job in jobs:
    print(f'Scheduled: {job}')
"
```

## Using with systemd (Linux)

### Service File: `/etc/systemd/system/paris-explorer.service`

```ini
[Unit]
Description=ParisExplorer YouTube Automation
After=network.target

[Service]
Type=simple
User=paris
Group=paris
WorkingDirectory=/home/paris/ParisExplorer
Environment="PATH=/home/paris/ParisExplorer/venv/bin"
ExecStart=/home/paris/ParisExplorer/venv/bin/python automation.py --mode scheduler
Restart=always
RestartSec=10

# Logging
StandardOutput=append:/var/log/paris-explorer/output.log
StandardError=append:/var/log/paris-explorer/error.log

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable paris-explorer
sudo systemctl start paris-explorer
sudo systemctl status paris-explorer
```

**View logs:**
```bash
sudo journalctl -u paris-explorer -f
```

## Using with Docker

### Build and run:
```bash
# Build image
docker build -t paris-explorer .

# Run container
docker run -d \
  --name paris-explorer \
  -v $(pwd)/content:/app/content \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/client_secrets.json:/app/client_secrets.json \
  -v $(pwd)/token.json:/app/token.json \
  -e TZ=Europe/Paris \
  paris-explorer

# View logs
docker logs -f paris-explorer

# Stop
docker stop paris-explorer
```

### Using docker-compose:
```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## API Quota Management

YouTube Data API has daily quotas. Here's how to manage them:

### Check Current Usage

Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Dashboard

### Quota Costs

- Video upload: ~1,600 units
- Thumbnail set: ~50 units
- Channel info: ~1 unit
- Default quota: 10,000 units/day

### Example Daily Limits

With 10,000 units:
- 6 videos + thumbnails per day (6 × 1,650 = 9,900 units)
- OR 200 thumbnails only
- OR Mix: 3 videos (4,800) + 100 thumbnails (5,000) = 9,800 units

### Configuration for Quota Management

**For 3 videos per day:**
```yaml
schedule:
  post_times:
    - "09:00"
    - "14:00"
    - "19:00"
```

**For 6 videos per day (requires monitoring):**
```yaml
schedule:
  post_times:
    - "06:00"
    - "09:00"
    - "12:00"
    - "15:00"
    - "18:00"
    - "21:00"
```

## Best Practices

1. **Test with private videos first**
   - Set `default_privacy: "private"` in config.yaml
   - Verify uploads work correctly
   - Switch to public after testing

2. **Monitor quota usage**
   - Check Google Cloud Console regularly
   - Adjust schedule if approaching limits

3. **Use descriptive filenames**
   - `paris_eiffel_tower_sunset_2024.mp4` ✓
   - `video1.mp4` ✗

4. **Always provide metadata**
   - Better SEO and discoverability
   - More professional appearance
   - Easier content management

5. **Custom thumbnails boost views**
   - 1280x720 resolution recommended
   - Clear, high-contrast images
   - Text should be readable on mobile

6. **Regular backups**
   ```bash
   # Backup queue and uploaded history
   cp content_queue.json backup/queue_$(date +%Y%m%d).json
   cp uploaded/uploaded_history.json backup/history_$(date +%Y%m%d).json
   ```

## Support

For more help:
- Check logs: `logs/automation.log`
- Run system test: `python test_system.py`
- View queue: `python automation.py --mode queue`
- Documentation: See [SETUP.md](SETUP.md)
