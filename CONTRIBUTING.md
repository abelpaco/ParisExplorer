# Contributing to ParisExplorer

Thank you for your interest in contributing to ParisExplorer! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant log excerpts from `logs/automation.log`

### Suggesting Features

Feature requests are welcome! Please open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternative solutions you've considered
- How this benefits the ParisExplorer community

### Code Contributions

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Update documentation as needed

4. **Test your changes**
   ```bash
   python test_system.py
   python -m py_compile *.py
   ```

5. **Commit with clear messages**
   ```bash
   git commit -m "Add feature: description of what you added"
   ```

6. **Push and create a Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/ParisExplorer.git
cd ParisExplorer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
python test_system.py
```

## Code Style

- Follow PEP 8 style guide
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small
- Use type hints where appropriate

### Example:

```python
def upload_video(
    self,
    video_file: str,
    title: str,
    description: str = "",
    tags: List[str] = None
) -> Optional[str]:
    """
    Upload a video to YouTube
    
    Args:
        video_file: Path to video file
        title: Video title
        description: Video description
        tags: List of tags
    
    Returns:
        Video ID if successful, None otherwise
    """
    # Implementation
```

## Testing

Before submitting:

1. **Syntax check**
   ```bash
   python -m py_compile automation.py youtube_uploader.py content_manager.py scheduler.py
   ```

2. **Run system tests**
   ```bash
   python test_system.py
   ```

3. **Manual testing**
   - Test with a small video file
   - Verify logs are generated correctly
   - Check queue management works

## Documentation

Update documentation when you:
- Add new features
- Change configuration options
- Modify command-line arguments
- Update dependencies

Files to update:
- `README.md` - High-level overview
- `SETUP.md` - Setup instructions
- `EXAMPLES.md` - Usage examples
- Inline code comments
- Docstrings

## Pull Request Guidelines

Your PR should:
- Have a clear title and description
- Reference any related issues
- Include tests if applicable
- Update documentation
- Pass all existing tests
- Follow the code style guidelines

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Code refactoring

## Testing
How did you test your changes?

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Tests pass
- [ ] No new warnings
```

## Project Structure

```
ParisExplorer/
├── automation.py           # Main entry point
├── youtube_uploader.py     # YouTube API integration
├── content_manager.py      # Content handling
├── scheduler.py            # Scheduling logic
├── utils.py                # Utility functions
├── config.yaml             # Configuration
├── requirements.txt        # Dependencies
├── test_system.py          # System tests
├── quickstart.py           # Quick start guide
├── content/                # Content directory
├── logs/                   # Log files
└── docs/                   # Documentation
```

## Areas for Contribution

### High Priority
- Enhanced error handling
- More content source integrations
- Better thumbnail generation
- Improved queue management UI
- Performance optimizations

### Medium Priority
- Support for YouTube Shorts
- Playlist management
- Analytics integration
- Multi-language support
- Mobile app integration

### Documentation
- Video tutorials
- More usage examples
- Translation to other languages
- API documentation

## Questions?

Feel free to:
- Open an issue for discussion
- Join our community discussions
- Reach out to maintainers

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Help others learn and grow
- Focus on what's best for the community

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to ParisExplorer! 🗼❤️
