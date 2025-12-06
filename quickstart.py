#!/usr/bin/env python
"""
Quick Start Guide for ParisExplorer Automation
Interactive setup and verification
"""

import os
import sys
from pathlib import Path

def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def check_file(filepath, description):
    """Check if a file exists"""
    if os.path.exists(filepath):
        print(f"✓ {description}: Found")
        return True
    else:
        print(f"✗ {description}: Missing")
        return False


def check_dependencies():
    """Check if Python dependencies are installed"""
    print_header("Checking Dependencies")
    
    required = [
        ('yaml', 'PyYAML'),
        ('google.auth', 'google-auth'),
        ('googleapiclient', 'google-api-python-client'),
        ('schedule', 'schedule'),
        ('dotenv', 'python-dotenv'),
        ('requests', 'requests'),
        ('PIL', 'Pillow')
    ]
    
    missing = []
    for module, package in required:
        try:
            __import__(module)
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} - Missing")
            missing.append(package)
    
    if missing:
        print("\n⚠️  Some dependencies are missing.")
        print("\nInstall them with:")
        print("  pip install -r requirements.txt")
        print("\nOr install individually:")
        for package in missing:
            print(f"  pip install {package}")
        return False
    
    print("\n✓ All dependencies installed!")
    return True


def check_structure():
    """Check project structure"""
    print_header("Checking Project Structure")
    
    checks = [
        ('automation.py', 'Main script'),
        ('youtube_uploader.py', 'YouTube uploader'),
        ('content_manager.py', 'Content manager'),
        ('scheduler.py', 'Scheduler'),
        ('config.yaml', 'Configuration'),
        ('requirements.txt', 'Requirements'),
        ('.env.example', 'Environment template'),
        ('SETUP.md', 'Setup guide'),
    ]
    
    all_good = True
    for filepath, desc in checks:
        if not check_file(filepath, desc):
            all_good = False
    
    # Check directories
    dirs = ['content', 'logs', 'temp']
    for dir_path in dirs:
        if os.path.isdir(dir_path):
            print(f"✓ Directory '{dir_path}': Exists")
        else:
            print(f"✗ Directory '{dir_path}': Missing")
            all_good = False
    
    return all_good


def check_credentials():
    """Check YouTube API credentials"""
    print_header("Checking YouTube API Credentials")
    
    has_secrets = check_file('client_secrets.json', 'OAuth2 credentials')
    has_token = check_file('token.json', 'Access token')
    
    if not has_secrets:
        print("\n⚠️  You need to setup YouTube API credentials.")
        print("\nSteps:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project or select existing")
        print("3. Enable YouTube Data API v3")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download JSON and save as 'client_secrets.json'")
        print("\nSee SETUP.md for detailed instructions.")
        return False
    
    if not has_token:
        print("\n⚠️  No access token found (this is normal for first run).")
        print("Run authentication with:")
        print("  python automation.py --mode channel-info")
        return False
    
    print("\n✓ Credentials configured!")
    return True


def check_content():
    """Check content directory"""
    print_header("Checking Content")
    
    content_path = Path('content')
    video_files = list(content_path.glob('**/*.mp4'))
    image_files = list(content_path.glob('**/*.jpg')) + list(content_path.glob('**/*.png'))
    
    print(f"Videos found: {len(video_files)}")
    print(f"Images found: {len(image_files)}")
    
    if video_files or image_files:
        print("\n✓ Content files found!")
        if video_files:
            print("\nSample videos:")
            for vf in video_files[:3]:
                print(f"  - {vf}")
        return True
    else:
        print("\n⚠️  No content files found.")
        print("\nAdd content to get started:")
        print("  mkdir -p content/videos")
        print("  cp your_video.mp4 content/videos/")
        print("\nOr run:")
        print("  python automation.py --mode refresh")
        return False


def show_next_steps():
    """Show next steps to user"""
    print_header("Next Steps")
    
    print("1. Authenticate with YouTube:")
    print("   python automation.py --mode channel-info")
    print()
    print("2. Add content to content/ directory")
    print()
    print("3. Test immediate upload:")
    print("   python automation.py --mode post-now")
    print()
    print("4. Start automated scheduler:")
    print("   python automation.py --mode scheduler")
    print()
    print("See SETUP.md for detailed documentation.")


def main():
    """Main quickstart function"""
    print_header("ParisExplorer YouTube Automation - Quick Start")
    
    # Check all components
    results = []
    
    results.append(("Project Structure", check_structure()))
    results.append(("Dependencies", check_dependencies()))
    results.append(("YouTube Credentials", check_credentials()))
    results.append(("Content", check_content()))
    
    # Summary
    print_header("Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ Ready" if result else "✗ Needs Setup"
        print(f"{status:12} - {name}")
    
    print(f"\n{passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 System is ready to use!")
        show_next_steps()
        return 0
    else:
        print("\n⚠️  Please complete the setup steps above.")
        print("\nFor detailed instructions, see:")
        print("  cat SETUP.md")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup interrupted.")
        sys.exit(1)
