"""
YouTube Uploader Module
Handles authentication and uploading content to YouTube
"""

import os
import pickle
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# YouTube API scopes
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube']

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """Handles YouTube API authentication and content upload"""
    
    def __init__(self, credentials_file: str = 'client_secrets.json'):
        """
        Initialize YouTube uploader
        
        Args:
            credentials_file: Path to OAuth2 client secrets JSON file
        """
        self.credentials_file = credentials_file
        self.token_file = 'token.json'
        self.youtube = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with YouTube API using OAuth2"""
        creds = None
        
        # Load saved credentials if they exist
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load saved credentials: {e}")
        
        # If credentials are invalid or don't exist, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Refreshed expired credentials")
                except Exception as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Credentials file '{self.credentials_file}' not found. "
                        "Please download it from Google Cloud Console."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                # Use fixed port 8080 for better security and consistency
                creds = flow.run_local_server(port=8080)
                logger.info("Completed OAuth2 authentication")
            
            # Save credentials for future use
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info("YouTube API client initialized")
    
    def upload_video(
        self,
        video_file: str,
        title: str,
        description: str = "",
        tags: list = None,
        category: str = "19",
        privacy_status: str = "public",
        location: Optional[Dict[str, float]] = None
    ) -> Optional[str]:
        """
        Upload a video to YouTube
        
        Args:
            video_file: Path to video file
            title: Video title
            description: Video description
            tags: List of tags
            category: YouTube category ID (19 = Travel & Events)
            privacy_status: public, private, or unlisted
            location: Dict with latitude and longitude
        
        Returns:
            Video ID if successful, None otherwise
        """
        if not os.path.exists(video_file):
            logger.error(f"Video file not found: {video_file}")
            return None
        
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Add location if provided
        if location:
            body['recordingDetails'] = {
                'location': {
                    'latitude': location.get('latitude'),
                    'longitude': location.get('longitude')
                },
                'locationDescription': location.get('description', '')
            }
        
        try:
            media = MediaFileUpload(
                video_file,
                mimetype='video/*',
                resumable=True,
                chunksize=1024*1024
            )
            
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")
            
            video_id = response['id']
            logger.info(f"Video uploaded successfully. Video ID: {video_id}")
            return video_id
            
        except HttpError as e:
            logger.error(f"HTTP error during video upload: {e}")
            return None
        except Exception as e:
            logger.error(f"Error uploading video: {e}")
            return None
    
    def upload_thumbnail(self, video_id: str, thumbnail_file: str) -> bool:
        """
        Set custom thumbnail for a video
        
        Args:
            video_id: YouTube video ID
            thumbnail_file: Path to thumbnail image
        
        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(thumbnail_file):
            logger.error(f"Thumbnail file not found: {thumbnail_file}")
            return False
        
        try:
            request = self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_file)
            )
            request.execute()
            logger.info(f"Thumbnail set for video {video_id}")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error setting thumbnail: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting thumbnail: {e}")
            return False
    
    def create_community_post(
        self,
        text: str,
        image_file: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a community post (requires appropriate channel eligibility)
        
        Args:
            text: Post text
            image_file: Optional image to attach
        
        Returns:
            Post ID if successful, None otherwise
        
        Note:
            Community posts require channel to meet YouTube's eligibility requirements.
            This is a placeholder for when the API becomes available.
        """
        logger.warning(
            "Community posts API is limited. "
            "Consider using YouTube Studio directly for posts."
        )
        # The Community Posts API is not yet fully available
        # This is a placeholder for future implementation
        return None
    
    def get_channel_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the authenticated channel
        
        Returns:
            Channel information dict or None
        """
        try:
            request = self.youtube.channels().list(
                part="snippet,contentDetails,statistics",
                mine=True
            )
            response = request.execute()
            
            if response.get('items'):
                return response['items'][0]
            return None
            
        except HttpError as e:
            logger.error(f"HTTP error getting channel info: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            return None
