"""
ParisExplorer YouTube Automation
Main automation script for scheduled content posting
"""

import os
import sys
import logging
import yaml
import argparse
from pathlib import Path
from dotenv import load_dotenv

from youtube_uploader import YouTubeUploader
from content_manager import ContentManager
from scheduler import AutomationScheduler

# Load environment variables
load_dotenv()


def setup_logging(config):
    """Setup logging configuration"""
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO'))
    log_file = log_config.get('file', './logs/automation.log')
    console = log_config.get('console', True)
    
    # Create logs directory
    log_path = Path(log_file).parent
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Setup logging format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = []
    
    # File handler
    handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    # Console handler
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers
    )


def load_config(config_file='config.yaml'):
    """Load configuration from YAML file"""
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


class ParisExplorerAutomation:
    """Main automation class"""
    
    def __init__(self, config_file='config.yaml'):
        """Initialize automation system"""
        self.config = load_config(config_file)
        setup_logging(self.config)
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("Initializing ParisExplorer Automation...")
        
        # Initialize components
        try:
            self.uploader = YouTubeUploader()
            self.content_manager = ContentManager(self.config)
            self.scheduler = AutomationScheduler(self.config, self.post_content)
            
            self.logger.info("Automation system initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize automation: {e}")
            raise
    
    def post_content(self):
        """Post next content from queue"""
        try:
            # Get next item from queue
            item = self.content_manager.get_next_item()
            
            if not item:
                self.logger.info("No content in queue to post")
                # Refresh content sources
                self.content_manager.refresh_content()
                item = self.content_manager.get_next_item()
                
                if not item:
                    self.logger.warning("Still no content available after refresh")
                    return False
            
            self.logger.info(f"Processing content: {item.title}")
            
            # Get YouTube settings
            youtube_config = self.config.get('youtube', {})
            default_tags = youtube_config.get('default_tags', [])
            privacy = youtube_config.get('default_privacy', 'public')
            category = youtube_config.get('default_category', '19')
            
            # Combine default tags with item-specific tags
            all_tags = list(set(default_tags + item.tags))
            
            # Prepare location
            location = None
            if youtube_config.get('location', {}).get('enabled', False):
                location = {
                    'latitude': youtube_config['location']['latitude'],
                    'longitude': youtube_config['location']['longitude'],
                    'description': youtube_config['location'].get('description', '')
                }
            
            # Upload based on content type
            video_id = None
            
            if item.content_type == 'video':
                # Upload video
                video_id = self.uploader.upload_video(
                    video_file=item.file_path,
                    title=item.title,
                    description=item.description,
                    tags=all_tags,
                    category=category,
                    privacy_status=privacy,
                    location=location
                )
                
                # Upload custom thumbnail if available
                if video_id and item.thumbnail:
                    self.uploader.upload_thumbnail(video_id, item.thumbnail)
            
            elif item.content_type == 'image':
                # For images, we could create a simple video or community post
                # Community posts require special eligibility
                self.logger.info(f"Image content: {item.title}")
                self.logger.info("Note: Image posting as community posts requires channel eligibility")
                # For now, log the image - you could extend this to create a slideshow video
                return True
            
            elif item.content_type == 'text':
                # Text content could be used for community posts
                self.logger.info(f"Text content: {item.title}")
                self.logger.info("Note: Text posting as community posts requires channel eligibility")
                return True
            
            # Mark as uploaded if successful
            if video_id:
                self.content_manager.mark_uploaded(item, video_id)
                self.logger.info(f"Successfully posted content. Video ID: {video_id}")
                return True
            else:
                self.content_manager.mark_failed(item)
                self.logger.error(f"Failed to post content: {item.title}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error posting content: {e}")
            return False
    
    def run_scheduler(self):
        """Run the automation scheduler"""
        self.logger.info("Starting automation scheduler...")
        
        # Initial content refresh
        self.content_manager.refresh_content()
        
        # Display schedule
        jobs = self.scheduler.list_jobs()
        self.logger.info(f"Scheduled jobs: {len(jobs)}")
        for job in jobs:
            self.logger.info(f"  - {job['time']} (next: {job['next_run']})")
        
        # Start scheduler
        self.scheduler.start()
    
    def post_now(self):
        """Post content immediately"""
        self.logger.info("Manual post requested")
        return self.post_content()
    
    def refresh_content(self):
        """Manually refresh content sources"""
        self.logger.info("Manual content refresh requested")
        self.content_manager.refresh_content()
    
    def show_queue(self):
        """Display current content queue"""
        queue = self.content_manager.queue
        pending = [item for item in queue if not item.uploaded]
        
        print("\n=== Content Queue ===")
        print(f"Total items: {len(queue)}")
        print(f"Pending: {len(pending)}")
        print(f"Uploaded: {len(queue) - len(pending)}")
        
        if pending:
            print("\nPending items:")
            for i, item in enumerate(pending[:10], 1):
                print(f"{i}. [{item.content_type}] {item.title}")
                if item.file_path:
                    print(f"   File: {item.file_path}")
                if item.upload_attempts > 0:
                    print(f"   Attempts: {item.upload_attempts}")
        
        print()
    
    def show_channel_info(self):
        """Display YouTube channel information"""
        info = self.uploader.get_channel_info()
        
        if info:
            snippet = info.get('snippet', {})
            statistics = info.get('statistics', {})
            
            print("\n=== Channel Information ===")
            print(f"Channel: {snippet.get('title', 'N/A')}")
            print(f"Description: {snippet.get('description', 'N/A')[:100]}...")
            print(f"Subscribers: {statistics.get('subscriberCount', 'N/A')}")
            print(f"Videos: {statistics.get('videoCount', 'N/A')}")
            print(f"Views: {statistics.get('viewCount', 'N/A')}")
            print()
        else:
            print("Could not retrieve channel information")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='ParisExplorer YouTube Automation'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--mode',
        choices=['scheduler', 'post-now', 'refresh', 'queue', 'channel-info'],
        default='scheduler',
        help='Operation mode'
    )
    
    args = parser.parse_args()
    
    try:
        automation = ParisExplorerAutomation(args.config)
        
        if args.mode == 'scheduler':
            automation.run_scheduler()
        elif args.mode == 'post-now':
            automation.post_now()
        elif args.mode == 'refresh':
            automation.refresh_content()
        elif args.mode == 'queue':
            automation.show_queue()
        elif args.mode == 'channel-info':
            automation.show_channel_info()
            
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
