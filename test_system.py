"""
Basic tests for ParisExplorer automation system
"""

import os
import sys
import yaml
import json
from pathlib import Path

def test_config_loading():
    """Test configuration file loading"""
    print("Testing config loading...")
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        assert config is not None, "Config is None"
        assert 'schedule' in config, "Missing schedule config"
        assert 'youtube' in config, "Missing youtube config"
        assert 'content_sources' in config, "Missing content_sources config"
        
        print("✓ Config loading successful")
        return True
    except Exception as e:
        print(f"✗ Config loading failed: {e}")
        return False


def test_directory_structure():
    """Test required directories exist"""
    print("\nTesting directory structure...")
    
    required_dirs = [
        'content',
        'content/videos',
        'content/images',
        'content/metadata',
        'logs',
        'temp'
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✓ {dir_path} exists")
        else:
            print(f"✗ {dir_path} missing")
            all_exist = False
    
    return all_exist


def test_required_files():
    """Test required files exist"""
    print("\nTesting required files...")
    
    required_files = [
        'requirements.txt',
        'config.yaml',
        '.env.example',
        '.gitignore',
        'automation.py',
        'youtube_uploader.py',
        'content_manager.py',
        'scheduler.py'
    ]
    
    all_exist = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✓ {file_path} exists")
        else:
            print(f"✗ {file_path} missing")
            all_exist = False
    
    return all_exist


def test_imports():
    """Test Python module imports"""
    print("\nTesting module imports...")
    
    modules = [
        ('yaml', 'PyYAML'),
        ('schedule', 'schedule'),
        ('dotenv', 'python-dotenv'),
        ('requests', 'requests'),
        ('PIL', 'Pillow'),
    ]
    
    all_imported = True
    for module_name, package_name in modules:
        try:
            __import__(module_name)
            print(f"✓ {package_name} imported successfully")
        except ImportError:
            print(f"✗ {package_name} not installed - run: pip install {package_name}")
            all_imported = False
    
    return all_imported


def test_content_structure():
    """Test content directory structure"""
    print("\nTesting content structure...")
    
    content_readme = Path('content/README.md')
    if content_readme.exists():
        print("✓ Content README exists")
    else:
        print("✗ Content README missing")
        return False
    
    example_json = Path('content/example_video.json')
    if example_json.exists():
        print("✓ Example metadata exists")
        
        try:
            with open(example_json, 'r') as f:
                data = json.load(f)
            assert 'title' in data, "Missing title in example"
            assert 'description' in data, "Missing description in example"
            print("✓ Example metadata is valid JSON")
        except Exception as e:
            print(f"✗ Example metadata invalid: {e}")
            return False
    else:
        print("✗ Example metadata missing")
        return False
    
    return True


def test_gitignore():
    """Test .gitignore contains sensitive files"""
    print("\nTesting .gitignore...")
    
    with open('.gitignore', 'r') as f:
        gitignore_content = f.read()
    
    sensitive_files = [
        '.env',
        'token.json',
        'client_secrets.json',
        '__pycache__'
    ]
    
    all_present = True
    for pattern in sensitive_files:
        if pattern in gitignore_content:
            print(f"✓ {pattern} in .gitignore")
        else:
            print(f"✗ {pattern} missing from .gitignore")
            all_present = False
    
    return all_present


def test_schedule_config():
    """Test schedule configuration is valid"""
    print("\nTesting schedule configuration...")
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    schedule_config = config.get('schedule', {})
    post_times = schedule_config.get('post_times', [])
    
    if not post_times:
        print("✗ No post times configured")
        return False
    
    print(f"✓ {len(post_times)} post times configured:")
    for time_str in post_times:
        print(f"  - {time_str}")
    
    timezone = schedule_config.get('timezone', '')
    print(f"✓ Timezone: {timezone}")
    
    return True


def main():
    """Run all tests"""
    print("=" * 50)
    print("ParisExplorer Automation System Tests")
    print("=" * 50)
    
    tests = [
        test_required_files,
        test_directory_structure,
        test_config_loading,
        test_schedule_config,
        test_content_structure,
        test_gitignore,
        test_imports,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 50)
    
    if all(results):
        print("\n✓ All tests passed! System is ready.")
        print("\nNext steps:")
        print("1. Setup YouTube API credentials (see SETUP.md)")
        print("2. Place content in content/ directory")
        print("3. Run: python automation.py --mode channel-info")
        return 0
    else:
        print("\n✗ Some tests failed. Please fix issues above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
