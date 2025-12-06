# ParisExplorer - YouTube Automation

Système d'automatisation pour publier des vidéos, images et textes sur la page YouTube "ParisExplorer" à des horaires programmés.

**Automated YouTube posting system for Paris content** - Schedule and publish videos, images, and text content to your YouTube channel at fixed times from local or external sources.

## Features ✨

- 🤖 **Automated Scheduling** - Post content at specific times daily
- 📹 **Video Upload** - Automatic video upload with metadata and thumbnails
- 🖼️ **Multiple Content Sources** - Local files, external URLs, or APIs
- 📅 **Flexible Scheduling** - Configure multiple posting times per day
- 🔄 **Queue Management** - Smart content queue with retry logic
- 📊 **Upload Tracking** - Archive and track all uploaded content
- 🌍 **Geolocation** - Add Paris location to videos automatically
- 🏷️ **Smart Tagging** - Default and custom tags for better discoverability
- 📝 **Metadata Support** - JSON files for rich video information
- 🔐 **Secure Authentication** - OAuth2 integration with YouTube API

## Quick Start 🚀

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/abelpaco/ParisExplorer.git
cd ParisExplorer

# Install dependencies
pip install -r requirements.txt
```

### 2. Setup YouTube API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop app)
4. Download as `client_secrets.json` in project root

See [SETUP.md](SETUP.md) for detailed instructions.

### 3. Configure

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano config.yaml
```

### 4. Run

```bash
# View channel info and authenticate
python automation.py --mode channel-info

# Add content to content/ directory
mkdir -p content/videos
cp your_video.mp4 content/videos/

# Start automated scheduler
python automation.py --mode scheduler
```

## Usage 📖

### Modes

```bash
# Run scheduler (continuous automation)
python automation.py --mode scheduler

# Post immediately
python automation.py --mode post-now

# Refresh content sources
python automation.py --mode refresh

# View queue
python automation.py --mode queue

# Show channel info
python automation.py --mode channel-info
```

### Content Structure

```
content/
├── videos/
│   ├── paris_tour.mp4
│   ├── paris_tour.json          # Metadata
│   └── paris_tour_thumb.jpg     # Custom thumbnail
├── images/
│   └── eiffel_tower.jpg
└── README.md
```

### Example Metadata File

Create `paris_tour.json`:

```json
{
  "title": "Beautiful Paris Tour 2024",
  "description": "Explore the magnificent city of Paris...",
  "tags": ["Paris", "Travel", "France", "Tourism"],
  "privacy": "public",
  "category": "19"
}
```

## Configuration ⚙️

Edit `config.yaml` to customize:

```yaml
schedule:
  post_times:
    - "09:00"  # Morning post
    - "14:00"  # Afternoon post  
    - "19:00"  # Evening post
  timezone: "Europe/Paris"

youtube:
  default_privacy: "public"
  default_tags:
    - "Paris"
    - "France"
    - "ParisExplorer"
  
  location:
    enabled: true
    latitude: 48.8566
    longitude: 2.3522
```

## Content Sources 📂

### Local Files
Place videos/images in `content/` directory - automatically scanned and queued.

### External URLs
Add to `config.yaml`:
```yaml
content_sources:
  external_urls:
    enabled: true
    urls:
      - "https://example.com/video.mp4"
```

### External API
Configure endpoint in `config.yaml`:
```yaml
content_sources:
  external_api:
    enabled: true
    endpoint: "https://api.example.com/content"
```

## Architecture 🏗️

```
ParisExplorer/
├── automation.py           # Main script
├── youtube_uploader.py     # YouTube API integration
├── content_manager.py      # Content scanning & queue
├── scheduler.py            # Scheduling logic
├── config.yaml             # Configuration
├── requirements.txt        # Dependencies
├── content/                # Content directory
├── logs/                   # Log files
└── uploaded/               # Archive of uploaded content
```

## Requirements 📋

- Python 3.8+
- YouTube Data API v3 access
- Google Cloud Project with OAuth2 credentials

See [requirements.txt](requirements.txt) for Python packages.

## Documentation 📚

- [SETUP.md](SETUP.md) - Detailed setup guide
- [content/README.md](content/README.md) - Content organization guide
- [config.yaml](config.yaml) - Configuration reference

## API Quotas ⚠️

YouTube Data API has daily limits:
- Default quota: 10,000 units/day
- Video upload: ~1,600 units
- Thumbnail upload: ~50 units

**Important**: Plan your posting schedule within these limits.

## Running as a Service 🔄

### Linux (systemd)
```bash
sudo systemctl enable paris-explorer
sudo systemctl start paris-explorer
```

### Windows (Task Scheduler)
Create a scheduled task to run `automation.py --mode scheduler` at startup.

### Docker
```bash
docker build -t paris-explorer .
docker run -d paris-explorer
```

See [SETUP.md](SETUP.md) for detailed instructions.

## Troubleshooting 🔧

### Authentication Issues
- Ensure `client_secrets.json` exists
- Delete `token.json` and re-authenticate
- Verify YouTube Data API v3 is enabled

### Upload Failures
- Check video format (MP4 recommended)
- Verify file size (< 128 GB)
- Review logs: `logs/automation.log`
- Check API quota in Google Cloud Console

### No Content in Queue
- Run: `python automation.py --mode refresh`
- Check files exist in `content/` directory
- Verify file extensions in config

## Security 🔒

- Never commit `client_secrets.json` or `token.json`
- Keep `.env` file private
- Use `.gitignore` for sensitive files
- Regularly rotate API keys

## Contributing 🤝

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License 📄

This project is open source. Check repository for license details.

## Support 💬

For issues:
- Check logs in `logs/automation.log`
- Review [SETUP.md](SETUP.md)
- Open an issue on GitHub

## About ParisExplorer 🗼

ParisExplorer is dedicated to showcasing the beauty, culture, and charm of Paris, France through engaging video content on YouTube.

---

**Made with ❤️ for Paris**
