"""
Utility functions for ParisExplorer automation
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


def setup_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        'content',
        'content/videos',
        'content/images',
        'content/metadata',
        'logs',
        'temp',
        'uploaded'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)


def validate_video_file(filepath: str) -> bool:
    """
    Validate video file
    
    Args:
        filepath: Path to video file
    
    Returns:
        True if valid, False otherwise
    """
    if not os.path.exists(filepath):
        return False
    
    # Check file size (YouTube limit is 128 GB)
    max_size = 128 * 1024 * 1024 * 1024  # 128 GB in bytes
    file_size = os.path.getsize(filepath)
    
    if file_size > max_size:
        logging.warning(f"File too large: {file_size} bytes (max: {max_size})")
        return False
    
    if file_size == 0:
        logging.warning(f"File is empty: {filepath}")
        return False
    
    # Check extension
    valid_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
    ext = Path(filepath).suffix.lower()
    
    if ext not in valid_extensions:
        logging.warning(f"Invalid video extension: {ext}")
        return False
    
    return True


def validate_image_file(filepath: str) -> bool:
    """
    Validate image file for thumbnail
    
    Args:
        filepath: Path to image file
    
    Returns:
        True if valid, False otherwise
    """
    if not os.path.exists(filepath):
        return False
    
    # Check file size (YouTube recommends 2MB max for thumbnails)
    max_size = 2 * 1024 * 1024  # 2 MB
    file_size = os.path.getsize(filepath)
    
    if file_size > max_size:
        logging.warning(f"Thumbnail too large: {file_size} bytes (recommended: {max_size})")
    
    # Check extension
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
    ext = Path(filepath).suffix.lower()
    
    if ext not in valid_extensions:
        logging.warning(f"Invalid image extension: {ext}")
        return False
    
    return True


def create_metadata_template(
    video_path: str,
    title: str = None,
    description: str = "",
    tags: List[str] = None
) -> Dict[str, Any]:
    """
    Create metadata template for a video
    
    Args:
        video_path: Path to video file
        title: Video title (defaults to filename)
        description: Video description
        tags: List of tags
    
    Returns:
        Metadata dictionary
    """
    video_file = Path(video_path)
    
    if title is None:
        title = video_file.stem.replace('_', ' ').replace('-', ' ').title()
    
    metadata = {
        'title': title,
        'description': description or f"Video: {title}",
        'tags': tags or ['Paris', 'France', 'Travel'],
        'privacy': 'public',
        'category': '19'  # Travel & Events
    }
    
    return metadata


def save_metadata(video_path: str, metadata: Dict[str, Any]):
    """
    Save metadata to JSON file
    
    Args:
        video_path: Path to video file
        metadata: Metadata dictionary
    """
    video_file = Path(video_path)
    metadata_file = video_file.with_suffix('.json')
    
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Saved metadata to {metadata_file}")


def generate_report(queue_file: str = 'content_queue.json') -> Dict[str, Any]:
    """
    Generate statistics report
    
    Args:
        queue_file: Path to queue file
    
    Returns:
        Report dictionary
    """
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_items': 0,
        'pending': 0,
        'uploaded': 0,
        'failed': 0,
        'by_type': {}
    }
    
    if not os.path.exists(queue_file):
        return report
    
    with open(queue_file, 'r', encoding='utf-8') as f:
        queue = json.load(f)
    
    report['total_items'] = len(queue)
    
    for item in queue:
        content_type = item.get('content_type', 'unknown')
        
        if content_type not in report['by_type']:
            report['by_type'][content_type] = {
                'total': 0,
                'uploaded': 0,
                'pending': 0
            }
        
        report['by_type'][content_type]['total'] += 1
        
        if item.get('uploaded', False):
            report['uploaded'] += 1
            report['by_type'][content_type]['uploaded'] += 1
        else:
            report['pending'] += 1
            report['by_type'][content_type]['pending'] += 1
        
        if item.get('upload_attempts', 0) >= 3:
            report['failed'] += 1
    
    return report


def print_report(report: Dict[str, Any]):
    """Print formatted report"""
    print("\n" + "=" * 50)
    print("ParisExplorer Automation Report")
    print("=" * 50)
    print(f"\nGenerated: {report['timestamp']}")
    print(f"\nTotal items: {report['total_items']}")
    print(f"  ✓ Uploaded: {report['uploaded']}")
    print(f"  ⏳ Pending: {report['pending']}")
    print(f"  ✗ Failed: {report['failed']}")
    
    if report['by_type']:
        print("\nBy content type:")
        for ctype, stats in report['by_type'].items():
            print(f"\n  {ctype.upper()}:")
            print(f"    Total: {stats['total']}")
            print(f"    Uploaded: {stats['uploaded']}")
            print(f"    Pending: {stats['pending']}")
    
    print("\n" + "=" * 50 + "\n")


def clean_old_temp_files(temp_dir: str = 'temp', days: int = 7):
    """
    Clean old temporary files
    
    Args:
        temp_dir: Temporary directory path
        days: Files older than this many days will be deleted
    """
    temp_path = Path(temp_dir)
    if not temp_path.exists():
        return
    
    now = datetime.now()
    deleted_count = 0
    
    for file_path in temp_path.glob('*'):
        if file_path.is_file():
            file_age = now - datetime.fromtimestamp(file_path.stat().st_mtime)
            
            if file_age.days > days:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logging.info(f"Deleted old temp file: {file_path}")
                except Exception as e:
                    logging.error(f"Error deleting {file_path}: {e}")
    
    if deleted_count > 0:
        logging.info(f"Cleaned {deleted_count} old temporary files")


def backup_queue(queue_file: str = 'content_queue.json'):
    """
    Backup queue file
    
    Args:
        queue_file: Path to queue file
    """
    if not os.path.exists(queue_file):
        return
    
    backup_dir = Path('uploaded/backups')
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = backup_dir / f"queue_backup_{timestamp}.json"
    
    with open(queue_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Queue backed up to {backup_file}")


def get_upload_statistics(archive_file: str = 'uploaded/uploaded_history.json') -> Dict[str, Any]:
    """
    Get upload statistics from archive
    
    Args:
        archive_file: Path to archive file
    
    Returns:
        Statistics dictionary
    """
    stats = {
        'total_uploads': 0,
        'by_date': {},
        'by_type': {},
        'total_size': 0
    }
    
    if not os.path.exists(archive_file):
        return stats
    
    with open(archive_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
    
    stats['total_uploads'] = len(history)
    
    for item in history:
        # By type
        content_type = item.get('content_type', 'unknown')
        stats['by_type'][content_type] = stats['by_type'].get(content_type, 0) + 1
        
        # By date
        created_at = item.get('created_at', '')
        if created_at:
            date = created_at.split('T')[0]
            stats['by_date'][date] = stats['by_date'].get(date, 0) + 1
    
    return stats


if __name__ == '__main__':
    # When run directly, generate and print report
    setup_directories()
    report = generate_report()
    print_report(report)
    
    # Show upload statistics
    stats = get_upload_statistics()
    if stats['total_uploads'] > 0:
        print("Upload Statistics:")
        print(f"Total uploads: {stats['total_uploads']}")
        print(f"\nBy type:")
        for ctype, count in stats['by_type'].items():
            print(f"  {ctype}: {count}")
