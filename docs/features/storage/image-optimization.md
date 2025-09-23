# Image Optimization

**Automatic image processing with intelligent caching**

FastEdgy automatically optimizes images on-the-fly with intelligent caching. Transform, resize, and convert your images directly through URL parameters without any additional setup.

## Key Features

- **Automatic resizing**: Resize images by width, height, or both
- **Smart caching**: Generated images are cached to avoid reprocessing
- **Format conversion**: Convert between JPEG, PNG, and WebP formats
- **Responsive images**: Perfect for modern web applications
- **No upscaling**: Never enlarges images beyond their original size
- **Memory efficient**: Optimized processing with quality control

## Common Use Cases

- **User avatars**: Square thumbnails with consistent sizing
- **Responsive images**: Different sizes for mobile and desktop
- **Product galleries**: Uniform thumbnails for better layouts
- **Performance optimization**: WebP conversion for faster loading
- **Modern formats**: Automatic format selection for better compression

## Basic Usage

Add URL parameters to any image download URL:

```bash
# Resize to 300px width (maintains aspect ratio)
GET /storage/download/photos/image.jpg?w=300

# Create 150x150 square thumbnail with cropping
GET /storage/download/photos/image.jpg?w=150&h=150&m=cover

# Convert to WebP format with resizing
GET /storage/download/photos/image.jpg?w=800&e=webp
```

## URL Parameters

- **`w`**: Width in pixels
- **`h`**: Height in pixels
- **`m`**: Resize mode (`contain` or `cover`)
- **`e`**: Output format (`jpg`, `png`, `webp`)
- **`force_download`**: Force file download instead of display

## Resize Modes

**Contain mode** (default): Fits the image inside the specified dimensions without cropping. May leave empty space if aspect ratios don't match.

**Cover mode**: Fills the entire specified dimensions, cropping the image if necessary to maintain perfect fit.

## Configuration

Set image quality in your environment file:

```env
IMAGE_QUALITY=80  # 1-100, higher = better quality but larger files
```

## How It Works

1. **Request**: Client requests image with optimization parameters
2. **Cache check**: System checks if optimized version already exists
3. **Generation**: If not cached, image is processed and saved
4. **Serving**: Optimized image is served with proper content type
5. **Cleanup**: Cache is automatically cleaned when source files are deleted

## Performance Benefits

- **Bandwidth savings**: Smaller file sizes with WebP conversion
- **Faster loading**: Optimized images load quicker on all devices
- **CDN friendly**: Cached images work perfectly with CDNs
- **Server efficient**: Processing happens once, served many times

Ready to optimize your images? Check out practical examples:

[Usage Guide](guide.md#image-optimization){ .md-button .md-button--primary }
