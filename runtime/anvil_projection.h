#ifndef ANVIL_PROJECTION_H
#define ANVIL_PROJECTION_H

#include <math.h>
#include <stdint.h>

typedef struct {
  int min_x;
  int max_x;
  int min_y;
  int max_y;
} AnvilPixelBounds;

typedef struct {
  int x;
  int y;
  int width;
  int height;
} AnvilViewport;

/* Fit the fixed-aspect framebuffer into a resizable client area. */
static inline int anvil_compute_viewport(int client_width, int client_height,
                                         int image_width, int image_height,
                                         AnvilViewport *viewport) {
  if (!viewport || client_width <= 0 || client_height <= 0 || image_width <= 0 ||
      image_height <= 0)
    return 0;

  int width;
  int height;
  if ((int64_t)client_width * image_height <=
      (int64_t)client_height * image_width) {
    width = client_width;
    height = (int)((int64_t)client_width * image_height / image_width);
  } else {
    height = client_height;
    width = (int)((int64_t)client_height * image_width / image_height);
  }
  if (width < 1 || height < 1)
    return 0;

  viewport->x = (client_width - width) / 2;
  viewport->y = (client_height - height) / 2;
  viewport->width = width;
  viewport->height = height;
  return 1;
}

/* Return an integer screen-space rectangle enclosing a projected sphere. */
static inline int anvil_project_sphere_bounds(
    double camera_x, double camera_y, double camera_depth, double radius,
    double focal_length, int width, int height, AnvilPixelBounds *bounds) {
  if (!bounds || radius <= 0.0 || camera_depth + radius <= 0.08)
    return 0;

  if (camera_depth <= radius * 1.05) {
    bounds->min_x = 0;
    bounds->max_x = width - 1;
    bounds->min_y = 0;
    bounds->max_y = height - 1;
    return 1;
  }

  const double denominator = camera_depth * camera_depth - radius * radius;
  const double horizontal_root =
      radius * sqrt(camera_x * camera_x + denominator);
  const double vertical_root =
      radius * sqrt(camera_y * camera_y + denominator);
  const double horizontal_a =
      (camera_x * camera_depth - horizontal_root) / denominator;
  const double horizontal_b =
      (camera_x * camera_depth + horizontal_root) / denominator;
  const double vertical_a =
      (camera_y * camera_depth - vertical_root) / denominator;
  const double vertical_b =
      (camera_y * camera_depth + vertical_root) / denominator;

  const double screen_left = width * 0.5 +
      focal_length * fmin(horizontal_a, horizontal_b);
  const double screen_right = width * 0.5 +
      focal_length * fmax(horizontal_a, horizontal_b);
  const double screen_top = height * 0.54 -
      focal_length * fmax(vertical_a, vertical_b);
  const double screen_bottom = height * 0.54 -
      focal_length * fmin(vertical_a, vertical_b);

  bounds->min_x = (int)floor(screen_left) - 1;
  bounds->max_x = (int)ceil(screen_right) + 1;
  bounds->min_y = (int)floor(screen_top) - 1;
  bounds->max_y = (int)ceil(screen_bottom) + 1;
  if (bounds->min_x < 0) bounds->min_x = 0;
  if (bounds->min_y < 0) bounds->min_y = 0;
  if (bounds->max_x >= width) bounds->max_x = width - 1;
  if (bounds->max_y >= height) bounds->max_y = height - 1;
  return 1;
}

#endif

