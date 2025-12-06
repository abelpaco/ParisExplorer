# Content Directory

Place your content files in this directory for automated posting.

## Structure

```
content/
├── videos/          # Video files (.mp4, .avi, .mov, .mkv)
├── images/          # Image files (.jpg, .jpeg, .png, .gif)
└── metadata/        # Optional metadata files (.json)
```

## Metadata Files

You can create a JSON metadata file with the same name as your content file to provide additional information:

### Example: `my_paris_video.json`

```json
{
  "title": "Beautiful Paris at Sunset",
  "description": "A stunning view of the Eiffel Tower at sunset. Paris is always a good idea!",
  "tags": ["EiffelTower", "Sunset", "Beautiful", "City"],
  "privacy": "public",
  "category": "19"
}
```

## Thumbnail Files

For videos, you can provide a custom thumbnail by creating an image file with the same base name:

- `my_video.mp4` → `my_video_thumb.jpg` or `my_video_thumbnail.jpg`

## File Naming

- Use descriptive names for your files
- Avoid special characters
- Use underscores or hyphens instead of spaces
- Examples:
  - `paris_eiffel_tower_2024.mp4`
  - `louvre_museum_tour.mp4`
  - `notre_dame_cathedral.jpg`

## Supported Formats

### Videos
- .mp4 (recommended)
- .avi
- .mov
- .mkv

### Images
- .jpg / .jpeg (recommended)
- .png
- .gif

### Text
- .txt
- .md (Markdown)

## Processing

The automation system will:
1. Scan this directory for new content
2. Load metadata if available
3. Add content to the upload queue
4. Upload at scheduled times
5. Archive uploaded content information

## Notes

- Files are processed in alphabetical order
- Once uploaded, files remain in place but are tracked to avoid re-uploading
- To re-upload a file, you'll need to modify the content queue manually or rename the file
