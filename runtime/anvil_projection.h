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

typedef struct {
  double x;
  double y;
  double depth;
} AnvilCameraVertex;

typedef struct {
  double x;
  double y;
} AnvilScreenPoint;

static inline int anvil_interpolation_parameter(double a, double b,
                                               double target, double *t) {
  double scale = fmax(fabs(a), fmax(fabs(b), fabs(target)));
  if (!t || !isfinite(scale) || scale == 0.0)
    return 0;
  double scaled_a = a / scale;
  double scaled_b = b / scale;
  double denominator = scaled_b - scaled_a;
  if (denominator == 0.0 || !isfinite(denominator))
    return 0;
  *t = (target / scale - scaled_a) / denominator;
  return isfinite(*t) && *t >= 0.0 && *t <= 1.0;
}

static inline double anvil_lerp_stable(double a, double b, double t) {
  return a * (1.0 - t) + b * t;
}

/* Clip one camera-space segment against the forward near plane. */
static inline int anvil_clip_segment_near(AnvilCameraVertex *a,
                                          AnvilCameraVertex *b,
                                          double near_depth) {
  if (!a || !b || !isfinite(near_depth) || near_depth <= 0.0 ||
      !isfinite(a->x) || !isfinite(a->y) || !isfinite(a->depth) ||
      !isfinite(b->x) || !isfinite(b->y) || !isfinite(b->depth))
    return 0;

  int a_inside = a->depth >= near_depth;
  int b_inside = b->depth >= near_depth;
  if (!a_inside && !b_inside)
    return 0;
  if (a_inside && b_inside)
    return 1;

  AnvilCameraVertex *outside = a_inside ? b : a;
  const AnvilCameraVertex *inside = a_inside ? a : b;
  double t;
  if (!anvil_interpolation_parameter(outside->depth, inside->depth,
                                     near_depth, &t))
    return 0;
  outside->x = anvil_lerp_stable(outside->x, inside->x, t);
  outside->y = anvil_lerp_stable(outside->y, inside->y, t);
  outside->depth = near_depth;
  return isfinite(outside->x) && isfinite(outside->y);
}

/* Clip a camera-space triangle; output contains up to four polygon vertices. */
static inline int anvil_clip_triangle_near(const AnvilCameraVertex input[3],
                                           double near_depth,
                                           AnvilCameraVertex output[4]) {
  if (!input || !output || !isfinite(near_depth) || near_depth <= 0.0)
    return 0;

  int count = 0;
  AnvilCameraVertex previous = input[2];
  if (!isfinite(previous.x) || !isfinite(previous.y) ||
      !isfinite(previous.depth))
    return 0;
  int previous_inside = previous.depth >= near_depth;
  for (int i = 0; i < 3; ++i) {
    AnvilCameraVertex current = input[i];
    if (!isfinite(current.x) || !isfinite(current.y) ||
        !isfinite(current.depth))
      return 0;
    int current_inside = current.depth >= near_depth;
    if (current_inside != previous_inside) {
      double t;
      if (!anvil_interpolation_parameter(previous.depth, current.depth,
                                         near_depth, &t))
        return 0;
      output[count++] = (AnvilCameraVertex){
          anvil_lerp_stable(previous.x, current.x, t),
          anvil_lerp_stable(previous.y, current.y, t), near_depth};
      if (!isfinite(output[count - 1].x) ||
          !isfinite(output[count - 1].y))
        return 0;
    }
    if (current_inside)
      output[count++] = current;
    previous = current;
    previous_inside = current_inside;
  }
  return count;
}

/* Clip a finite screen-space line before integer conversion or rasterization. */
static inline int anvil_clip_screen_line(AnvilScreenPoint *a,
                                         AnvilScreenPoint *b, int width,
                                         int height) {
  if (!a || !b || width <= 0 || height <= 0 || !isfinite(a->x) ||
      !isfinite(a->y) || !isfinite(b->x) || !isfinite(b->y))
    return 0;

  for (int iteration = 0; iteration < 8; ++iteration) {
    int code_a = (a->x < 0.0 ? 1 : a->x > width - 1 ? 2 : 0) |
                 (a->y < 0.0 ? 4 : a->y > height - 1 ? 8 : 0);
    int code_b = (b->x < 0.0 ? 1 : b->x > width - 1 ? 2 : 0) |
                 (b->y < 0.0 ? 4 : b->y > height - 1 ? 8 : 0);
    if ((code_a | code_b) == 0)
      return 1;
    if ((code_a & code_b) != 0)
      return 0;

    int outside_code = code_a ? code_a : code_b;
    AnvilScreenPoint clipped;
    double t;
    if (outside_code & 4) {
      if (!anvil_interpolation_parameter(a->y, b->y, 0.0, &t))
        return 0;
      clipped = (AnvilScreenPoint){anvil_lerp_stable(a->x, b->x, t), 0.0};
    } else if (outside_code & 8) {
      double edge = height - 1.0;
      if (!anvil_interpolation_parameter(a->y, b->y, edge, &t))
        return 0;
      clipped = (AnvilScreenPoint){anvil_lerp_stable(a->x, b->x, t), edge};
    } else if (outside_code & 1) {
      if (!anvil_interpolation_parameter(a->x, b->x, 0.0, &t))
        return 0;
      clipped = (AnvilScreenPoint){0.0, anvil_lerp_stable(a->y, b->y, t)};
    } else {
      double edge = width - 1.0;
      if (!anvil_interpolation_parameter(a->x, b->x, edge, &t))
        return 0;
      clipped = (AnvilScreenPoint){edge, anvil_lerp_stable(a->y, b->y, t)};
    }
    if (!isfinite(clipped.x) || !isfinite(clipped.y))
      return 0;
    if (outside_code == code_a)
      *a = clipped;
    else
      *b = clipped;
  }
  return 0;
}

/* Intersect a camera ray with a sphere, clipping its surface at the near plane. */
static inline int anvil_intersect_sphere_near(
    AnvilCameraVertex center, double radius, double ray_x, double ray_y,
    double near_depth, double *hit_depth, double *normal_x, double *normal_y,
    double *normal_z, int *near_cap) {
  if (!hit_depth || !normal_x || !normal_y || !normal_z || !near_cap ||
      !isfinite(center.x) || !isfinite(center.y) || !isfinite(center.depth) ||
      !isfinite(radius) || radius <= 0.0 || !isfinite(ray_x) ||
      !isfinite(ray_y) || !isfinite(near_depth) || near_depth <= 0.0)
    return 0;

  const double a = ray_x * ray_x + ray_y * ray_y + 1.0;
  const double b = -2.0 * (ray_x * center.x + ray_y * center.y + center.depth);
  const double c = center.x * center.x + center.y * center.y +
                   center.depth * center.depth - radius * radius;
  const double discriminant = b * b - 4.0 * a * c;
  if (!isfinite(discriminant) || discriminant < 0.0)
    return 0;

  const double root = sqrt(discriminant);
  const double near_hit = (-b - root) / (2.0 * a);
  const double far_hit = (-b + root) / (2.0 * a);
  if (far_hit < near_depth)
    return 0;

  if (near_hit < near_depth) {
    *hit_depth = near_depth;
    *normal_x = 0.0;
    *normal_y = 0.0;
    *normal_z = -1.0;
    *near_cap = 1;
    return 1;
  }

  *hit_depth = near_hit;
  *normal_x = (ray_x * near_hit - center.x) / radius;
  *normal_y = (ray_y * near_hit - center.y) / radius;
  *normal_z = (near_hit - center.depth) / radius;
  *near_cap = 0;
  return isfinite(*normal_x) && isfinite(*normal_y) && isfinite(*normal_z);
}

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
  if (!isfinite(screen_left) || !isfinite(screen_right) ||
      !isfinite(screen_top) || !isfinite(screen_bottom) || screen_right < 0.0 ||
      screen_bottom < 0.0 || screen_left >= width || screen_top >= height)
    return 0;

  bounds->min_x = screen_left <= 1.0 ? 0 : (int)floor(screen_left) - 1;
  bounds->max_x = screen_right >= width - 2.0
                      ? width - 1
                      : (int)ceil(screen_right) + 1;
  bounds->min_y = screen_top <= 1.0 ? 0 : (int)floor(screen_top) - 1;
  bounds->max_y = screen_bottom >= height - 2.0
                      ? height - 1
                      : (int)ceil(screen_bottom) + 1;
  return 1;
}

#endif

