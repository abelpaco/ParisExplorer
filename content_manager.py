"""
Content Manager Module
Handles content discovery, loading, and queue management
"""

import os
import json
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from PIL import Image

logger = logging.getLogger(__name__)


class ContentItem:
    """Represents a content item to be posted"""
    
    def __init__(
        self,
        content_type: str,
        title: str,
        description: str = "",
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        tags: List[str] = None,
        thumbnail: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ):
        self.content_type = content_type  # 'video', 'image', 'text'
        self.title = title
        self.description = description
        self.file_path = file_path
        self.url = url
        self.tags = tags or []
        self.thumbnail = thumbnail
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.upload_attempts = 0
        self.uploaded = False
        self.video_id = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'content_type': self.content_type,
            'title': self.title,
            'description': self.description,
            'file_path': self.file_path,
            'url': self.url,
            'tags': self.tags,
            'thumbnail': self.thumbnail,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'upload_attempts': self.upload_attempts,
            'uploaded': self.uploaded,
            'video_id': self.video_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentItem':
        """Create ContentItem from dictionary"""
        item = cls(
            content_type=data['content_type'],
            title=data['title'],
            description=data.get('description', ''),
            file_path=data.get('file_path'),
            url=data.get('url'),
            tags=data.get('tags', []),
            thumbnail=data.get('thumbnail'),
            metadata=data.get('metadata', {})
        )
        item.upload_attempts = data.get('upload_attempts', 0)
        item.uploaded = data.get('uploaded', False)
        item.video_id = data.get('video_id')
        return item


class ContentManager:
    """Manages content discovery and queue"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize content manager
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.queue: List[ContentItem] = []
        self.queue_file = 'content_queue.json'
        self._load_queue()
    
    def _load_queue(self):
        """Load queue from file"""
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.queue = [ContentItem.from_dict(item) for item in data]
                logger.info(f"Loaded {len(self.queue)} items from queue")
            except Exception as e:
                logger.error(f"Error loading queue: {e}")
                self.queue = []
    
    def _save_queue(self):
        """Save queue to file"""
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                data = [item.to_dict() for item in self.queue]
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved queue with {len(self.queue)} items")
        except Exception as e:
            logger.error(f"Error saving queue: {e}")
    
    def scan_local_content(self) -> List[ContentItem]:
        """
        Scan local directory for content
        
        Returns:
            List of new ContentItem objects
        """
        local_config = self.config.get('content_sources', {}).get('local', {})
        if not local_config.get('enabled', False):
            logger.info("Local content scanning disabled")
            return []
        
        content_path = Path(local_config.get('path', './content'))
        if not content_path.exists():
            logger.warning(f"Local content path does not exist: {content_path}")
            return []
        
        video_formats = local_config.get('video_formats', [])
        image_formats = local_config.get('image_formats', [])
        text_formats = local_config.get('text_formats', [])
        
        new_items = []
        
        # Scan for videos
        for ext in video_formats:
            for video_file in content_path.glob(f"**/*{ext}"):
                if self._is_content_processed(str(video_file)):
                    continue
                
                # Look for metadata file
                metadata = self._load_metadata(video_file)
                
                item = ContentItem(
                    content_type='video',
                    title=metadata.get('title', video_file.stem),
                    description=metadata.get('description', ''),
                    file_path=str(video_file),
                    tags=metadata.get('tags', []),
                    thumbnail=self._find_thumbnail(video_file),
                    metadata=metadata
                )
                new_items.append(item)
        
        # Scan for images (as potential thumbnails or community posts)
        for ext in image_formats:
            for image_file in content_path.glob(f"**/*{ext}"):
                if self._is_content_processed(str(image_file)):
                    continue
                
                metadata = self._load_metadata(image_file)
                
                # Skip if this is a thumbnail for a video
                if image_file.stem.endswith('_thumb') or image_file.stem.endswith('_thumbnail'):
                    continue
                
                item = ContentItem(
                    content_type='image',
                    title=metadata.get('title', image_file.stem),
                    description=metadata.get('description', ''),
                    file_path=str(image_file),
                    tags=metadata.get('tags', []),
                    metadata=metadata
                )
                new_items.append(item)
        
        logger.info(f"Scanned local content: found {len(new_items)} new items")
        return new_items
    
    def _load_metadata(self, content_file: Path) -> Dict[str, Any]:
        """Load metadata for a content file"""
        metadata_file = content_file.with_suffix('.json')
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading metadata for {content_file}: {e}")
        return {}
    
    def _find_thumbnail(self, video_file: Path) -> Optional[str]:
        """Find thumbnail for a video file"""
        # Check for common thumbnail naming patterns
        for suffix in ['_thumb', '_thumbnail', '.thumb']:
            for ext in ['.jpg', '.jpeg', '.png']:
                thumb_path = video_file.with_stem(video_file.stem + suffix).with_suffix(ext)
                if thumb_path.exists():
                    return str(thumb_path)
        return None
    
    def _is_content_processed(self, file_path: str) -> bool:
        """Check if content has already been processed"""
        # Check if file is in the queue or has been uploaded
        for item in self.queue:
            if item.file_path == file_path:
                return True
        return False
    
    def fetch_from_external_url(self, url: str) -> Optional[ContentItem]:
        """
        Fetch content from external URL
        
        Args:
            url: URL to fetch content from
        
        Returns:
            ContentItem if successful, None otherwise
        """
        try:
            # Validate URL scheme (only allow http/https)
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                logger.error(f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed.")
                return None
            
            # Add headers to identify as a bot
            headers = {
                'User-Agent': 'ParisExplorer-Bot/1.0'
            }
            
            response = requests.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            
            # Validate content type
            content_type = response.headers.get('content-type', '').lower()
            
            if 'video' in content_type:
                ext = '.mp4'
                ctype = 'video'
            elif 'image' in content_type:
                ext = '.jpg'
                ctype = 'image'
            elif 'text' in content_type:
                ext = '.txt'
                ctype = 'text'
            else:
                logger.warning(f"Unknown content type from URL {url}: {content_type}")
                return None
            
            # Check content length
            content_length = int(response.headers.get('content-length', 0))
            max_size = 128 * 1024 * 1024 * 1024  # 128 GB
            if content_length > max_size:
                logger.error(f"Content too large: {content_length} bytes")
                return None
            
            # Create temp directory
            temp_dir = Path('./temp')
            temp_dir.mkdir(exist_ok=True)
            
            filename = f"external_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
            file_path = temp_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            item = ContentItem(
                content_type=ctype,
                title=f"Content from {url}",
                description=f"Fetched from external URL: {url}",
                file_path=str(file_path),
                url=url
            )
            
            logger.info(f"Fetched content from URL: {url}")
            return item
            
        except Exception as e:
            logger.error(f"Error fetching content from URL {url}: {e}")
            return None
    
    def fetch_from_external_api(self) -> List[ContentItem]:
        """
        Fetch content from external API
        
        Returns:
            List of ContentItem objects
        """
        api_config = self.config.get('content_sources', {}).get('external_api', {})
        if not api_config.get('enabled', False):
            return []
        
        endpoint = api_config.get('endpoint')
        if not endpoint:
            logger.warning("External API endpoint not configured")
            return []
        
        try:
            headers = {}
            auth_type = api_config.get('auth_type', 'bearer')
            api_key = os.getenv('EXTERNAL_API_KEY', '')
            
            if auth_type == 'bearer' and api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            elif auth_type == 'api_key' and api_key:
                headers['X-API-Key'] = api_key
            
            response = requests.get(endpoint, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            # Process API response (format depends on API)
            # This is a generic implementation
            items = []
            
            if isinstance(data, list):
                for item_data in data:
                    # Adapt this based on your API structure
                    item = ContentItem(
                        content_type=item_data.get('type', 'video'),
                        title=item_data.get('title', 'Untitled'),
                        description=item_data.get('description', ''),
                        url=item_data.get('url'),
                        tags=item_data.get('tags', []),
                        metadata=item_data
                    )
                    items.append(item)
            
            logger.info(f"Fetched {len(items)} items from external API")
            return items
            
        except Exception as e:
            logger.error(f"Error fetching from external API: {e}")
            return []
    
    def add_to_queue(self, item: ContentItem):
        """Add content item to queue"""
        max_size = self.config.get('queue', {}).get('max_size', 100)
        if len(self.queue) >= max_size:
            logger.warning(f"Queue is full (max: {max_size})")
            return False
        
        self.queue.append(item)
        self._save_queue()
        logger.info(f"Added item to queue: {item.title}")
        return True
    
    def get_next_item(self) -> Optional[ContentItem]:
        """Get next item from queue"""
        # Filter out uploaded items
        pending_items = [item for item in self.queue if not item.uploaded]
        
        if not pending_items:
            return None
        
        return pending_items[0]
    
    def mark_uploaded(self, item: ContentItem, video_id: Optional[str] = None):
        """Mark item as uploaded"""
        item.uploaded = True
        item.video_id = video_id
        self._save_queue()
        
        # Archive if configured
        if self.config.get('queue', {}).get('archive_uploaded', False):
            self._archive_item(item)
        
        logger.info(f"Marked item as uploaded: {item.title}")
    
    def mark_failed(self, item: ContentItem):
        """Mark upload attempt as failed"""
        item.upload_attempts += 1
        max_retries = self.config.get('queue', {}).get('max_retries', 3)
        
        if item.upload_attempts >= max_retries:
            logger.error(f"Item failed after {max_retries} attempts: {item.title}")
            # Save to failed queue before removing
            self._save_to_failed_queue(item)
            self.queue.remove(item)
        
        self._save_queue()
    
    def _save_to_failed_queue(self, item: ContentItem):
        """Save failed item to a separate failed queue for later review"""
        failed_queue_file = 'failed_uploads.json'
        failed_items = []
        
        if os.path.exists(failed_queue_file):
            try:
                with open(failed_queue_file, 'r', encoding='utf-8') as f:
                    failed_items = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading failed queue: {e}")
        
        failed_items.append(item.to_dict())
        
        try:
            with open(failed_queue_file, 'w', encoding='utf-8') as f:
                json.dump(failed_items, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved failed item to {failed_queue_file}")
        except Exception as e:
            logger.error(f"Error saving to failed queue: {e}")
    
    def _archive_item(self, item: ContentItem):
        """Archive uploaded item"""
        archive_path = Path(self.config.get('queue', {}).get('archive_path', './uploaded'))
        archive_path.mkdir(parents=True, exist_ok=True)
        
        archive_file = archive_path / 'uploaded_history.json'
        history = []
        
        if archive_file.exists():
            try:
                with open(archive_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading archive: {e}")
        
        history.append(item.to_dict())
        
        try:
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving archive: {e}")
    
    def refresh_content(self):
        """Refresh content from all sources"""
        logger.info("Refreshing content from all sources...")
        
        # Scan local content
        new_items = self.scan_local_content()
        for item in new_items:
            self.add_to_queue(item)
        
        # Fetch from external API
        api_items = self.fetch_from_external_api()
        for item in api_items:
            self.add_to_queue(item)
        
        # Process configured URLs
        url_config = self.config.get('content_sources', {}).get('external_urls', {})
        if url_config.get('enabled', False):
            urls = url_config.get('urls', [])
            for url in urls:
                item = self.fetch_from_external_url(url)
                if item:
                    self.add_to_queue(item)
        
        logger.info(f"Content refresh complete. Queue size: {len(self.queue)}")
