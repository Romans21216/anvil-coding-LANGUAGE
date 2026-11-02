#define WIN32_LEAN_AND_MEAN
#include "anvil_runtime.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <io.h>

#define ANVIL_IMAGES 64
#define ANVIL_IMAGE_MAX_DIMENSION 8192
#define ANVIL_IMAGE_MEMORY_LIMIT ((size_t)128 * 1024 * 1024)

typedef struct {
  uint32_t *pixels;
  int width, height;
  uint32_t generation;
} AnvilImage;

static AnvilImage anvil_images[ANVIL_IMAGES];
static size_t anvil_image_memory_used;

static void anvil_image_blend_pixel(uint32_t *framebuffer, int x, int y,
                                    uint32_t color, int alpha) {
  if (!framebuffer || x < 0 || y < 0 || x >= ANVIL_FRAME_WIDTH ||
      y >= ANVIL_FRAME_HEIGHT || alpha <= 0)
    return;
  size_t index = (size_t)y * ANVIL_FRAME_WIDTH + (size_t)x;
  if (alpha >= 255) {
    framebuffer[index] = color;
    return;
  }
  uint32_t old = framebuffer[index];
  int inv = 255 - alpha;
  int r = (((color >> 16) & 255) * alpha + ((old >> 16) & 255) * inv) / 255;
  int g = (((color >> 8) & 255) * alpha + ((old >> 8) & 255) * inv) / 255;
  int b = ((color & 255) * alpha + (old & 255) * inv) / 255;
  framebuffer[index] = ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;
}

void anvil_image_shutdown(void) {
  for (int i = 0; i < ANVIL_IMAGES; ++i) {
    free(anvil_images[i].pixels);
    memset(&anvil_images[i], 0, sizeof(anvil_images[i]));
  }
  anvil_image_memory_used = 0;
}

static uint16_t anvil_read_u16_le(const unsigned char *bytes) {
  return (uint16_t)bytes[0] | (uint16_t)((uint16_t)bytes[1] << 8);
}
static uint32_t anvil_read_u32_le(const unsigned char *bytes) {
  return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
         ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}
static AnvilImage *anvil_image_from_handle(double handle) {
  const uint64_t max_handle = (uint64_t)UINT32_MAX * ANVIL_IMAGES;
  if (!isfinite(handle) || handle < 1.0 || handle > (double)max_handle ||
      floor(handle) != handle)
    return NULL;
  uint64_t encoded = (uint64_t)handle - 1;
  int slot = (int)(encoded % ANVIL_IMAGES);
  uint32_t generation = (uint32_t)(encoded / ANVIL_IMAGES) + 1;
  AnvilImage *image = &anvil_images[slot];
  return image->pixels && image->generation == generation ? image : NULL;
}
double anvil_image_load(const char *path) {
  if (!path || !*path)
    return 0.0;
  int slot = -1;
  for (int i = 0; i < ANVIL_IMAGES; ++i) {
    if (!anvil_images[i].pixels &&
        anvil_images[i].generation < UINT32_MAX) {
      slot = i;
      break;
    }
  }
  if (slot < 0)
    return 0.0;

  FILE *file = fopen(path, "rb");
  if (!file)
    return 0.0;
  unsigned char header[54] = {0};
  int ok = fread(header, 1, sizeof(header), file) == sizeof(header) &&
           header[0] == 'B' && header[1] == 'M';
  int64_t file_size = -1;
  if (ok && _fseeki64(file, 0, SEEK_END) == 0)
    file_size = _ftelli64(file);
  if (file_size < (int64_t)sizeof(header))
    ok = 0;
  int64_t pixel_offset = (int64_t)anvil_read_u32_le(header + 10);
  uint32_t dib_size = anvil_read_u32_le(header + 14);
  int32_t width = (int32_t)anvil_read_u32_le(header + 18);
  int32_t signed_height = (int32_t)anvil_read_u32_le(header + 22);
  uint16_t planes = anvil_read_u16_le(header + 26);
  uint16_t bits_per_pixel = anvil_read_u16_le(header + 28);
  uint32_t compression = anvil_read_u32_le(header + 30);
  if (dib_size < 40 || pixel_offset < 14 + (int64_t)dib_size || width <= 0 ||
      signed_height == 0 || signed_height == INT32_MIN || planes != 1 ||
      (bits_per_pixel != 24 && bits_per_pixel != 32) || compression != BI_RGB)
    ok = 0;
  int height = signed_height < 0 ? -signed_height : signed_height;
  if (width > ANVIL_IMAGE_MAX_DIMENSION ||
      height > ANVIL_IMAGE_MAX_DIMENSION)
    ok = 0;
  uint64_t pixel_count = ok ? (uint64_t)(unsigned int)width *
                                  (uint64_t)(unsigned int)height
                            : 0;
  uint64_t output_bytes = pixel_count * sizeof(uint32_t);
  uint64_t row_bytes = ok ? (uint64_t)(unsigned int)width *
                                (bits_per_pixel / 8)
                          : 0;
  uint64_t row_stride = (row_bytes + 3u) & ~UINT64_C(3);
  if (pixel_count == 0 || pixel_count > 16u * 1024u * 1024u ||
      output_bytes > ANVIL_IMAGE_MEMORY_LIMIT - anvil_image_memory_used ||
      row_stride > SIZE_MAX ||
      pixel_offset + (int64_t)(row_stride * (uint64_t)(unsigned int)height) >
          file_size)
    ok = 0;

  uint32_t *pixels = NULL;
  unsigned char *row = NULL;
  if (ok) {
    pixels = (uint32_t *)malloc((size_t)output_bytes);
    row = (unsigned char *)malloc((size_t)row_stride);
    if (!pixels || !row)
      ok = 0;
  }
  int any_alpha = 0;
  for (int source_y = 0; ok && source_y < height; ++source_y) {
    int64_t row_offset = pixel_offset + (int64_t)row_stride * source_y;
    if (_fseeki64(file, row_offset, SEEK_SET) != 0 ||
        fread(row, 1, (size_t)row_stride, file) != (size_t)row_stride) {
      ok = 0;
      break;
    }
    int target_y = signed_height > 0 ? height - source_y - 1 : source_y;
    for (int x = 0; x < width; ++x) {
      const unsigned char *source = row + (size_t)x * (bits_per_pixel / 8);
      unsigned int alpha = bits_per_pixel == 32 ? source[3] : 255u;
      any_alpha |= alpha != 0;
      pixels[(size_t)target_y * (size_t)width + (size_t)x] =
          ((uint32_t)alpha << 24) | ((uint32_t)source[2] << 16) |
          ((uint32_t)source[1] << 8) | (uint32_t)source[0];
    }
  }
  free(row);
  fclose(file);
  if (!ok) {
    free(pixels);
    return 0.0;
  }
  if (bits_per_pixel == 32 && !any_alpha) {
    for (uint64_t i = 0; i < pixel_count; ++i)
      pixels[i] |= UINT32_C(0xff000000);
  }
  if (!anvil_runtime_register_shutdown_hook(anvil_image_shutdown)) {
    free(pixels);
    return 0.0;
  }
  anvil_images[slot].pixels = pixels;
  anvil_images[slot].width = width;
  anvil_images[slot].height = height;
  ++anvil_images[slot].generation;
  anvil_image_memory_used += (size_t)output_bytes;
  return (double)(anvil_images[slot].generation - 1) * ANVIL_IMAGES + slot + 1;
}
double anvil_image_width(double handle) {
  AnvilImage *image = anvil_image_from_handle(handle);
  return image ? (double)image->width : 0.0;
}
double anvil_image_height(double handle) {
  AnvilImage *image = anvil_image_from_handle(handle);
  return image ? (double)image->height : 0.0;
}
double anvil_image_destroy(double handle) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image)
    return 0.0;
  anvil_image_memory_used -=
      (size_t)image->width * (size_t)image->height * sizeof(uint32_t);
  free(image->pixels);
  image->pixels = NULL;
  image->width = 0;
  image->height = 0;
  return 1.0;
}
double anvil_image_draw_scaled(double handle, double x, double y, double width,
                               double height) {
  AnvilImage *image = anvil_image_from_handle(handle);
  uint32_t *framebuffer = anvil_runtime_framebuffer();
  if (!image || !framebuffer || !isfinite(x) || !isfinite(y) ||
      !isfinite(width) || !isfinite(height) || width <= 0.0 || height <= 0.0 ||
      !isfinite(x + width) || !isfinite(y + height))
    return 0.0;
  double left = fmax(0.0, floor(x));
  double top = fmax(0.0, floor(y));
  double right = fmin((double)ANVIL_FRAME_WIDTH, ceil(x + width));
  double bottom = fmin((double)ANVIL_FRAME_HEIGHT, ceil(y + height));
  if (left >= right || top >= bottom)
    return 1.0;
  int x0 = (int)left, y0 = (int)top, x1 = (int)right, y1 = (int)bottom;
  for (int dy = y0; dy < y1; ++dy) {
    int source_y = (int)(((dy + 0.5 - y) / height) * image->height);
    if (source_y < 0)
      source_y = 0;
    if (source_y >= image->height)
      source_y = image->height - 1;
    for (int dx = x0; dx < x1; ++dx) {
      int source_x = (int)(((dx + 0.5 - x) / width) * image->width);
      if (source_x < 0)
        source_x = 0;
      if (source_x >= image->width)
        source_x = image->width - 1;
      uint32_t color = image->pixels[(size_t)source_y * image->width + source_x];
      anvil_image_blend_pixel(framebuffer, dx, dy,
                              color & UINT32_C(0x00ffffff),
                              (int)(color >> 24));
    }
  }
  return 1.0;
}
double anvil_image_draw(double handle, double x, double y) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image)
    return 0.0;
  return anvil_image_draw_scaled(handle, x, y, image->width, image->height);
}
