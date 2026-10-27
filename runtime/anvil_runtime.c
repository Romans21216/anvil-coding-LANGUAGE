#define WIN32_LEAN_AND_MEAN
#include "anvil_runtime.h"
#include "anvil_projection.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "Ws2_32.lib")

enum { ANVIL_WIDTH = 960, ANVIL_HEIGHT = 600, ANVIL_KEYS = 256 };
enum { ANVIL_TRACE_SPHERES = 32 };
typedef struct {
  double x, y, z;
} AnvilVec3;
typedef struct {
  AnvilVec3 center;
  double radius;
  int r, g, b, a;
} AnvilTraceSphere;
typedef struct {
  AnvilVec3 minimum, maximum;
  int left, right, sphere;
} AnvilBvhNode;
typedef struct {
  double x, y, depth;
} AnvilProjected;

static HWND anvil_window;
static HDC anvil_memory_dc;
static HBITMAP anvil_bitmap;
static HGDIOBJ anvil_old_bitmap;
static BITMAPINFO anvil_bitmap_info;
static uint32_t *anvil_pixels;
static double *anvil_depth_buffer;
static int anvil_running;
static int anvil_keys[ANVIL_KEYS];
static int anvil_pressed_keys[ANVIL_KEYS];
static int anvil_clear_color[4] = {12, 17, 29, 255};
static int anvil_scene_is_3d = 1;
static double anvil_camera_x = 0.0, anvil_camera_y = 3.0, anvil_camera_z = 8.0;
static double anvil_camera_yaw, anvil_camera_pitch;
static double anvil_camera_focal = 520.0;
static double anvil_camera_move_speed, anvil_camera_turn_speed;
static AnvilTraceSphere anvil_trace_spheres[ANVIL_TRACE_SPHERES];
static int anvil_trace_sphere_count;
static AnvilBvhNode anvil_trace_bvh[ANVIL_TRACE_SPHERES * 2];
static int anvil_trace_bvh_count;
static double anvil_delta_seconds = 1.0 / 60.0;
static int anvil_fixed_hz = 60;
static double anvil_elapsed_seconds;
static LARGE_INTEGER anvil_clock_frequency;
static LARGE_INTEGER anvil_clock_start;
static unsigned long long anvil_rng_state = 0x9e3779b97f4a7c15ULL;
static SOCKET anvil_net_socket = INVALID_SOCKET;
static SOCKADDR_IN anvil_net_peer;
static int anvil_net_has_peer;
static int anvil_winsock_started;
static double anvil_net_value;

static uint32_t anvil_color(int r, int g, int b) {
  if (r < 0)
    r = 0;
  if (r > 255)
    r = 255;
  if (g < 0)
    g = 0;
  if (g > 255)
    g = 255;
  if (b < 0)
    b = 0;
  if (b > 255)
    b = 255;
  return ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;
}

static void anvil_pixel(int x, int y, uint32_t color, int alpha) {
  if (!anvil_pixels || x < 0 || y < 0 || x >= ANVIL_WIDTH ||
      y >= ANVIL_HEIGHT || alpha <= 0)
    return;
  size_t index = (size_t)y * ANVIL_WIDTH + (size_t)x;
  if (alpha >= 255) {
    anvil_pixels[index] = color;
    return;
  }
  uint32_t old = anvil_pixels[index];
  int inv = 255 - alpha;
  int r = (((color >> 16) & 255) * alpha + ((old >> 16) & 255) * inv) / 255;
  int g = (((color >> 8) & 255) * alpha + ((old >> 8) & 255) * inv) / 255;
  int b = ((color & 255) * alpha + (old & 255) * inv) / 255;
  anvil_pixels[index] = anvil_color(r, g, b);
}

static void anvil_clear_frame(void) {
  anvil_trace_sphere_count = 0;
  uint32_t c = anvil_color(anvil_clear_color[0], anvil_clear_color[1],
                           anvil_clear_color[2]);
  size_t count = (size_t)ANVIL_WIDTH * ANVIL_HEIGHT;
  for (size_t i = 0; i < count; ++i)
    anvil_pixels[i] = c;
  for (size_t i = 0; i < count; ++i)
    anvil_depth_buffer[i] = 1.0e30;
}

static AnvilVec3 anvil_add(AnvilVec3 a, AnvilVec3 b) {
  return (AnvilVec3){a.x + b.x, a.y + b.y, a.z + b.z};
}
static AnvilVec3 anvil_sub(AnvilVec3 a, AnvilVec3 b) {
  return (AnvilVec3){a.x - b.x, a.y - b.y, a.z - b.z};
}
static AnvilVec3 anvil_cross(AnvilVec3 a, AnvilVec3 b) {
  return (AnvilVec3){a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z,
                     a.x * b.y - a.y * b.x};
}
static double anvil_dot(AnvilVec3 a, AnvilVec3 b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}
static AnvilVec3 anvil_normalize(AnvilVec3 v) {
  double n = sqrt(anvil_dot(v, v));
  return n > 1e-12 ? (AnvilVec3){v.x / n, v.y / n, v.z / n}
                   : (AnvilVec3){0, 1, 0};
}

static void anvil_camera_basis(AnvilVec3 *right, AnvilVec3 *up,
                               AnvilVec3 *forward) {
  const double radians = 0.017453292519943295769;
  double yaw = anvil_camera_yaw * radians;
  double pitch = anvil_camera_pitch * radians;
  *right = (AnvilVec3){cos(yaw), 0.0, sin(yaw)};
  *forward = (AnvilVec3){sin(yaw) * cos(pitch), sin(pitch),
                         -cos(yaw) * cos(pitch)};
  *up = anvil_normalize(anvil_cross(*right, *forward));
}

static AnvilVec3 anvil_rotate(AnvilVec3 p, double rx, double ry, double rz) {
  const double d = 0.017453292519943295769;
  rx *= d;
  ry *= d;
  rz *= d;
  double c = cos(rx), s = sin(rx);
  p = (AnvilVec3){p.x, p.y * c - p.z * s, p.y * s + p.z * c};
  c = cos(ry);
  s = sin(ry);
  p = (AnvilVec3){p.x * c + p.z * s, p.y, -p.x * s + p.z * c};
  c = cos(rz);
  s = sin(rz);
  p = (AnvilVec3){p.x * c - p.y * s, p.x * s + p.y * c, p.z};
  return p;
}

static int anvil_project(AnvilVec3 p, AnvilProjected *out) {
  if (!anvil_scene_is_3d) {
    const double pixels_per_unit = 64.0;
    out->x = ANVIL_WIDTH * 0.5 + p.x * pixels_per_unit;
    out->y = ANVIL_HEIGHT * 0.5 - p.y * pixels_per_unit;
    out->depth = 1000.0 - p.z;
    return 1;
  }
  AnvilVec3 right, up, forward;
  anvil_camera_basis(&right, &up, &forward);
  AnvilVec3 relative = {p.x - anvil_camera_x, p.y - anvil_camera_y,
                        p.z - anvil_camera_z};
  double depth = anvil_dot(relative, forward);
  if (depth < 0.08)
    return 0;
  out->x = ANVIL_WIDTH * 0.5 + anvil_dot(relative, right) * anvil_camera_focal / depth;
  out->y = ANVIL_HEIGHT * 0.54 - anvil_dot(relative, up) * anvil_camera_focal / depth;
  out->depth = depth;
  return 1;
}

static void anvil_triangle(AnvilProjected a, AnvilProjected b, AnvilProjected c,
                           uint32_t color, int alpha) {
  double area = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  if (fabs(area) < 1e-8)
    return;
  int minx = (int)floor(fmin(a.x, fmin(b.x, c.x))),
      maxx = (int)ceil(fmax(a.x, fmax(b.x, c.x)));
  int miny = (int)floor(fmin(a.y, fmin(b.y, c.y))),
      maxy = (int)ceil(fmax(a.y, fmax(b.y, c.y)));
  if (minx < 0)
    minx = 0;
  if (miny < 0)
    miny = 0;
  if (maxx >= ANVIL_WIDTH)
    maxx = ANVIL_WIDTH - 1;
  if (maxy >= ANVIL_HEIGHT)
    maxy = ANVIL_HEIGHT - 1;
  for (int y = miny; y <= maxy; ++y)
    for (int x = minx; x <= maxx; ++x) {
      double px = x + 0.5, py = y + 0.5;
      double w0 = ((b.x - px) * (c.y - py) - (b.y - py) * (c.x - px)) / area;
      double w1 = ((c.x - px) * (a.y - py) - (c.y - py) * (a.x - px)) / area;
      double w2 = 1.0 - w0 - w1;
      if (w0 >= 0 && w1 >= 0 && w2 >= 0) {
        double z = w0 * a.depth + w1 * b.depth + w2 * c.depth;
        size_t index = (size_t)y * ANVIL_WIDTH + (size_t)x;
        if (z < anvil_depth_buffer[index]) {
          anvil_depth_buffer[index] = z;
          anvil_pixel(x, y, color, alpha);
        }
      }
    }
}

static void anvil_triangle_lit(AnvilProjected p[3], uint32_t base,
                               double brightness, int alpha) {
  int r = (int)(((base >> 16) & 255) * brightness),
      g = (int)(((base >> 8) & 255) * brightness),
      b = (int)((base & 255) * brightness);
  anvil_triangle(p[0], p[1], p[2], anvil_color(r, g, b), alpha);
}

void anvil_set_scene3d(int enabled) { anvil_scene_is_3d = enabled != 0; }
void anvil_camera_perspective(double x, double y, double z) {
  anvil_camera_x = x;
  anvil_camera_y = y;
  anvil_camera_z = z;
}
void anvil_camera_fov(double degrees) {
  if (degrees < 20.0)
    degrees = 20.0;
  if (degrees > 120.0)
    degrees = 120.0;
  anvil_camera_focal = (ANVIL_WIDTH * 0.5) / tan(degrees * 0.008726646259971647884);
}
void anvil_camera_control(double speed, double turn_degrees_per_second) {
  anvil_camera_move_speed = fmax(0.0, speed);
  anvil_camera_turn_speed = fmax(0.0, turn_degrees_per_second);
}
void anvil_clear(int r, int g, int b, int a) {
  anvil_clear_color[0] = r;
  anvil_clear_color[1] = g;
  anvil_clear_color[2] = b;
  anvil_clear_color[3] = a;
}

void anvil_rect(double x, double y, double w, double h, int r, int g, int b,
                int a) {
  int x0 = (int)floor(x), y0 = (int)floor(y), x1 = (int)ceil(x + w),
      y1 = (int)ceil(y + h);
  if (x0 < 0)
    x0 = 0;
  if (y0 < 0)
    y0 = 0;
  if (x1 > ANVIL_WIDTH)
    x1 = ANVIL_WIDTH;
  if (y1 > ANVIL_HEIGHT)
    y1 = ANVIL_HEIGHT;
  uint32_t c = anvil_color(r, g, b);
  for (int py = y0; py < y1; ++py)
    for (int px = x0; px < x1; ++px)
      anvil_pixel(px, py, c, a);
}

void anvil_circle(double x, double y, double radius, int r, int g, int b,
                  int a) {
  int rr = (int)ceil(fabs(radius)), cx = (int)lrint(x), cy = (int)lrint(y);
  uint32_t c = anvil_color(r, g, b);
  double r2 = radius * radius;
  for (int py = cy - rr; py <= cy + rr; ++py)
    for (int px = cx - rr; px <= cx + rr; ++px) {
      double dx = px - x, dy = py - y;
      if (dx * dx + dy * dy <= r2)
        anvil_pixel(px, py, c, a);
    }
}

void anvil_line(double x1, double y1, double x2, double y2, int r, int g, int b,
                int a, double thickness) {
  int dx = abs((int)lrint(x2) - (int)lrint(x1)), sx = x1 < x2 ? 1 : -1,
      dy = -abs((int)lrint(y2) - (int)lrint(y1)), sy = y1 < y2 ? 1 : -1,
      err = dx + dy;
  int x = (int)lrint(x1), y = (int)lrint(y1),
      radius = (int)fmax(0.0, ceil(thickness * .5));
  uint32_t c = anvil_color(r, g, b);
  for (;;) {
    for (int oy = -radius; oy <= radius; ++oy)
      for (int ox = -radius; ox <= radius; ++ox)
        anvil_pixel(x + ox, y + oy, c, a);
    if (x == (int)lrint(x2) && y == (int)lrint(y2))
      break;
    int e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y += sy;
    }
  }
}

void anvil_cube(double x, double y, double z, double size, double rx, double ry,
                double rz, int r, int g, int b, int a) {
  double h = size * .5;
  AnvilVec3 v[8];
  AnvilProjected p[8];
  for (int i = 0; i < 8; ++i) {
    AnvilVec3 q = {(i & 1) ? h : -h, (i & 2) ? h : -h, (i & 4) ? h : -h};
    q = anvil_rotate(q, rx, ry, rz);
    v[i] = (AnvilVec3){x + q.x, y + q.y, z + q.z};
    if (!anvil_project(v[i], &p[i]))
      return;
  }
  static const int faces[6][4] = {{0, 4, 6, 2}, {1, 3, 7, 5}, {0, 1, 5, 4},
                                  {2, 6, 7, 3}, {0, 2, 3, 1}, {4, 5, 7, 6}};
  AnvilVec3 light = anvil_normalize((AnvilVec3){-0.35, 0.8, 0.55});
  uint32_t base = anvil_color(r, g, b);
  for (int f = 0; f < 6; ++f) {
    AnvilVec3 n =
        anvil_normalize(anvil_cross(anvil_sub(v[faces[f][1]], v[faces[f][0]]),
                                    anvil_sub(v[faces[f][2]], v[faces[f][0]])));
    double brightness = .28 + .72 * fmax(0.0, anvil_dot(n, light));
    AnvilProjected t0[3] = {p[faces[f][0]], p[faces[f][1]], p[faces[f][2]]},
                   t1[3] = {p[faces[f][0]], p[faces[f][2]], p[faces[f][3]]};
    anvil_triangle_lit(t0, base, brightness, a);
    anvil_triangle_lit(t1, base, brightness, a);
  }
}

void anvil_sphere(double x, double y, double z, double radius, int r, int g,
                  int b, int a) {
  AnvilProjected center;
  if (!anvil_project((AnvilVec3){x, y, z}, &center))
    return;
  double sr = radius * 520.0 / center.depth;
  int rr = (int)ceil(sr), cx = (int)lrint(center.x), cy = (int)lrint(center.y);
  uint32_t base = anvil_color(r, g, b);
  AnvilVec3 light = anvil_normalize((AnvilVec3){-.4, .7, .6});
  for (int py = cy - rr; py <= cy + rr; ++py)
    for (int px = cx - rr; px <= cx + rr; ++px) {
      double nx = (px - center.x) / sr, ny = (center.y - py) / sr,
             q = nx * nx + ny * ny;
      if (q > 1)
        continue;
      double nz = sqrt(1 - q);
      double shade =
          .2 + .8 * fmax(0.0, nx * light.x + ny * light.y + nz * light.z);
      uint32_t c =
          anvil_color((int)(r * shade), (int)(g * shade), (int)(b * shade));
      double depth = center.depth - radius * nz;
      size_t i = (size_t)py * ANVIL_WIDTH + (size_t)px;
      if (px >= 0 && py >= 0 && px < ANVIL_WIDTH && py < ANVIL_HEIGHT &&
          depth < anvil_depth_buffer[i]) {
        anvil_depth_buffer[i] = depth;
        anvil_pixel(px, py, c, a);
      }
    }
}

void anvil_plane(double x, double y, double z, double width, double depth,
                 int r, int g, int b, int a) {
  uint32_t base = anvil_color(r, g, b);
  for (int i = 0; i <= 10; ++i) {
    double t = (double)i / 10.0;
    AnvilProjected p0, p1, p2, p3;
    AnvilVec3 a0 = {x - width * .5, y, z - depth * .5 + depth * t},
              a1 = {x + width * .5, y, z - depth * .5 + depth * t},
              a2 = {x - width * .5 + width * t, y, z - depth * .5},
              a3 = {x - width * .5 + width * t, y, z + depth * .5};
    if (anvil_project(a0, &p0) && anvil_project(a1, &p1))
      anvil_line(p0.x, p0.y, p1.x, p1.y, r, g, b, a, 1);
    if (anvil_project(a2, &p2) && anvil_project(a3, &p3))
      anvil_line(p2.x, p2.y, p3.x, p3.y, r, g, b, a, 1);
  }
  (void)base;
}

void anvil_text(double x, double y, const char *text, int r, int g, int b,
                int a) {
  if (!anvil_memory_dc || !text)
    return;
  SetBkMode(anvil_memory_dc, TRANSPARENT);
  SetTextColor(anvil_memory_dc, RGB(r, g, b));
  HFONT font =
      CreateFontA(20, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
                  DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                  CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, "Segoe UI");
  HGDIOBJ old = SelectObject(anvil_memory_dc, font);
  TextOutA(anvil_memory_dc, (int)x, (int)y, text, (int)strlen(text));
  SelectObject(anvil_memory_dc, old);
  DeleteObject(font);
  (void)a;
}
void anvil_text_number(double x, double y, const char *format, double value,
                       int r, int g, int b, int a) {
  char buffer[256];
  _snprintf_s(buffer, sizeof(buffer), _TRUNCATE, format, value);
  anvil_text(x, y, buffer, r, g, b, a);
}

double anvil_time(void) { return anvil_elapsed_seconds; }
double anvil_delta(void) { return anvil_delta_seconds; }
void anvil_set_fixed_hz(int hz) {
  if (hz >= 1 && hz <= 240)
    anvil_fixed_hz = hz;
}
double anvil_pressed(int key) {
  return key >= 0 && key < ANVIL_KEYS ? anvil_pressed_keys[key] != 0 : 0.0;
}
double anvil_held(int key) {
  return key >= 0 && key < ANVIL_KEYS ? anvil_keys[key] != 0 : 0.0;
}
static void anvil_camera_update(void) {
  if (anvil_camera_move_speed <= 0.0 && anvil_camera_turn_speed <= 0.0)
    return;
  double step = anvil_delta_seconds;
  anvil_camera_yaw += (anvil_keys[VK_RIGHT] - anvil_keys[VK_LEFT]) *
                      anvil_camera_turn_speed * step;
  anvil_camera_pitch += (anvil_keys[VK_UP] - anvil_keys[VK_DOWN]) *
                        anvil_camera_turn_speed * step;
  if (anvil_camera_pitch > 89.0)
    anvil_camera_pitch = 89.0;
  if (anvil_camera_pitch < -89.0)
    anvil_camera_pitch = -89.0;
  const double radians = 0.017453292519943295769;
  double yaw = anvil_camera_yaw * radians;
  double dx = sin(yaw), dz = -cos(yaw);
  double right_x = cos(yaw), right_z = sin(yaw);
  double distance = anvil_camera_move_speed * step;
  anvil_camera_x += (anvil_keys['W'] - anvil_keys['S']) * dx * distance;
  anvil_camera_z += (anvil_keys['W'] - anvil_keys['S']) * dz * distance;
  anvil_camera_x += (anvil_keys['D'] - anvil_keys['A']) * right_x * distance;
  anvil_camera_z += (anvil_keys['D'] - anvil_keys['A']) * right_z * distance;
  anvil_camera_y += (anvil_keys['E'] - anvil_keys['Q']) * distance;
}
void anvil_seed(unsigned long long seed) {
  anvil_rng_state = seed ? seed : 0x9e3779b97f4a7c15ULL;
}
static unsigned long long anvil_random_u64(void) {
  unsigned long long x = anvil_rng_state;
  x ^= x >> 12;
  x ^= x << 25;
  x ^= x >> 27;
  anvil_rng_state = x;
  return x * 2685821657736338717ULL;
}
double anvil_rnd(double min_value, double max_value) {
  if (min_value > max_value) {
    double t = min_value;
    min_value = max_value;
    max_value = t;
  }
  long long lo = (long long)ceil(min_value), hi = (long long)floor(max_value);
  if (hi <= lo)
    return (double)lo;
  unsigned long long span = (unsigned long long)(hi - lo) + 1ULL;
  return (double)(lo + (long long)(anvil_random_u64() % span));
}

static int anvil_hash(int x, int y, int z) {
  unsigned int h = (unsigned int)x * 374761393u + (unsigned int)y * 668265263u +
                   (unsigned int)z * 2147483647u;
  h = (h ^ (h >> 13)) * 1274126177u;
  return (int)(h ^ (h >> 16));
}
static double anvil_grad(int hash, double x, double y, double z) {
  switch ((unsigned int)hash & 15u) {
  case 0:
    return x + y;
  case 1:
    return -x + y;
  case 2:
    return x - y;
  case 3:
    return -x - y;
  case 4:
    return x + z;
  case 5:
    return -x + z;
  case 6:
    return x - z;
  case 7:
    return -x - z;
  case 8:
    return y + z;
  case 9:
    return -y + z;
  case 10:
    return y - z;
  case 11:
    return -y - z;
  case 12:
    return x + y;
  case 13:
    return -x + y;
  case 14:
    return -y + z;
  default:
    return -y - z;
  }
}

void anvil_trace_sphere(double x, double y, double z, double radius, int r,
                        int g, int b, int a) {
  if (radius <= 0.0 || anvil_trace_sphere_count >= ANVIL_TRACE_SPHERES)
    return;
  AnvilTraceSphere *sphere = &anvil_trace_spheres[anvil_trace_sphere_count++];
  sphere->center = (AnvilVec3){x, y, z};
  sphere->radius = radius;
  sphere->r = r;
  sphere->g = g;
  sphere->b = b;
  sphere->a = a;
}

static int anvil_ray_sphere_hit(AnvilVec3 origin, AnvilVec3 direction,
                                const AnvilTraceSphere *sphere, double *hit_t) {
  AnvilVec3 offset = anvil_sub(origin, sphere->center);
  double half_b = anvil_dot(offset, direction);
  double c = anvil_dot(offset, offset) - sphere->radius * sphere->radius;
  double discriminant = half_b * half_b - c;
  if (discriminant < 0.0)
    return 0;
  double root = sqrt(discriminant);
  double t = -half_b - root;
  if (t <= 0.001)
    t = -half_b + root;
  if (t <= 0.001)
    return 0;
  *hit_t = t;
  return 1;
}

static double anvil_axis_value(AnvilVec3 v, int axis) {
  return axis == 0 ? v.x : axis == 1 ? v.y : v.z;
}

static void anvil_bvh_include(AnvilVec3 *minimum, AnvilVec3 *maximum,
                              AnvilVec3 point) {
  if (point.x < minimum->x) minimum->x = point.x;
  if (point.y < minimum->y) minimum->y = point.y;
  if (point.z < minimum->z) minimum->z = point.z;
  if (point.x > maximum->x) maximum->x = point.x;
  if (point.y > maximum->y) maximum->y = point.y;
  if (point.z > maximum->z) maximum->z = point.z;
}

static int anvil_bvh_build(int *indices, int start, int count) {
  int node_index = anvil_trace_bvh_count++;
  AnvilBvhNode *node = &anvil_trace_bvh[node_index];
  node->minimum = (AnvilVec3){1.0e30, 1.0e30, 1.0e30};
  node->maximum = (AnvilVec3){-1.0e30, -1.0e30, -1.0e30};
  node->left = node->right = -1;
  node->sphere = -1;
  for (int i = start; i < start + count; ++i) {
    const AnvilTraceSphere *sphere = &anvil_trace_spheres[indices[i]];
    AnvilVec3 radius = {sphere->radius, sphere->radius, sphere->radius};
    anvil_bvh_include(&node->minimum, &node->maximum,
                      anvil_sub(sphere->center, radius));
    anvil_bvh_include(&node->minimum, &node->maximum,
                      anvil_add(sphere->center, radius));
  }
  if (count == 1) {
    node->sphere = indices[start];
    return node_index;
  }

  AnvilVec3 extent = anvil_sub(node->maximum, node->minimum);
  int axis = extent.y > extent.x ? 1 : 0;
  if (anvil_axis_value(extent, 2) > anvil_axis_value(extent, axis))
    axis = 2;
  for (int i = start + 1; i < start + count; ++i) {
    int value = indices[i];
    double center = anvil_axis_value(anvil_trace_spheres[value].center, axis);
    int j = i;
    while (j > start &&
           anvil_axis_value(anvil_trace_spheres[indices[j - 1]].center, axis) >
               center) {
      indices[j] = indices[j - 1];
      --j;
    }
    indices[j] = value;
  }
  int left_count = count / 2;
  node->left = anvil_bvh_build(indices, start, left_count);
  node->right = anvil_bvh_build(indices, start + left_count, count - left_count);
  return node_index;
}

static int anvil_ray_box_hit(AnvilVec3 origin, AnvilVec3 direction,
                             const AnvilBvhNode *node, double max_t,
                             double *near_t) {
  double t_min = 0.001, t_max = max_t;
  for (int axis = 0; axis < 3; ++axis) {
    double o = anvil_axis_value(origin, axis);
    double d = anvil_axis_value(direction, axis);
    double low = anvil_axis_value(node->minimum, axis);
    double high = anvil_axis_value(node->maximum, axis);
    if (fabs(d) < 1.0e-12) {
      if (o < low || o > high)
        return 0;
      continue;
    }
    double a = (low - o) / d, b = (high - o) / d;
    if (a > b) { double swap = a; a = b; b = swap; }
    if (a > t_min) t_min = a;
    if (b < t_max) t_max = b;
    if (t_min > t_max)
      return 0;
  }
  *near_t = t_min;
  return 1;
}

static int anvil_bvh_trace(int node_index, AnvilVec3 origin,
                           AnvilVec3 direction, double max_t,
                           double *hit_t, int *hit_sphere) {
  double near_t;
  const AnvilBvhNode *node = &anvil_trace_bvh[node_index];
  if (!anvil_ray_box_hit(origin, direction, node, max_t, &near_t))
    return 0;
  if (node->sphere >= 0) {
    double t;
    if (anvil_ray_sphere_hit(origin, direction,
                             &anvil_trace_spheres[node->sphere], &t) &&
        t < max_t) {
      *hit_t = t;
      *hit_sphere = node->sphere;
      return 1;
    }
    return 0;
  }
  double left_near = 0.0, right_near = 0.0;
  int hit_left = anvil_ray_box_hit(origin, direction,
                                   &anvil_trace_bvh[node->left], max_t,
                                   &left_near);
  int hit_right = anvil_ray_box_hit(origin, direction,
                                    &anvil_trace_bvh[node->right], max_t,
                                    &right_near);
  int first = node->left, second = node->right;
  double first_near = left_near, second_near = right_near;
  int first_hit = hit_left, second_hit = hit_right;
  if (hit_right && (!hit_left || right_near < left_near)) {
    first = node->right;
    second = node->left;
    first_near = right_near;
    second_near = left_near;
    first_hit = hit_right;
    second_hit = hit_left;
  }
  int found = 0;
  if (first_hit)
    found = anvil_bvh_trace(first, origin, direction, max_t, hit_t, hit_sphere);
  if (found)
    max_t = *hit_t;
  if (second_hit && second_near < max_t) {
    int second_found = anvil_bvh_trace(second, origin, direction, max_t,
                                        hit_t, hit_sphere);
    found = found || second_found;
  }
  return found;
}

void anvil_trace_finish(void) {
  if (anvil_trace_sphere_count == 0 || !anvil_pixels || !anvil_depth_buffer ||
      !anvil_scene_is_3d)
    return;

  int indices[ANVIL_TRACE_SPHERES];
  anvil_trace_bvh_count = 0;
  for (int i = 0; i < anvil_trace_sphere_count; ++i)
    indices[i] = i;
  (void)anvil_bvh_build(indices, 0, anvil_trace_sphere_count);

  AnvilVec3 right, up, forward;
  anvil_camera_basis(&right, &up, &forward);
  AnvilVec3 origin = {anvil_camera_x, anvil_camera_y, anvil_camera_z};
  AnvilVec3 light = anvil_normalize((AnvilVec3){-0.4, 0.75, 0.55});

  for (int object = 0; object < anvil_trace_sphere_count; ++object) {
    const AnvilTraceSphere *bound = &anvil_trace_spheres[object];
    AnvilVec3 relative = {bound->center.x - origin.x,
                          bound->center.y - origin.y,
                          bound->center.z - origin.z};
    double camera_x = anvil_dot(relative, right);
    double camera_y = anvil_dot(relative, up);
    double camera_depth = anvil_dot(relative, forward);
    AnvilPixelBounds bounds;
    if (!anvil_project_sphere_bounds(camera_x, camera_y, camera_depth,
                                     bound->radius, anvil_camera_focal,
                                     ANVIL_WIDTH, ANVIL_HEIGHT, &bounds))
      continue;

    for (int py = bounds.min_y; py <= bounds.max_y; ++py) {
      double vertical = (ANVIL_HEIGHT * 0.54 - (py + 0.5)) / anvil_camera_focal;
      for (int px = bounds.min_x; px <= bounds.max_x; ++px) {
        double horizontal = (px + 0.5 - ANVIL_WIDTH * 0.5) / anvil_camera_focal;
        AnvilVec3 direction = anvil_normalize(anvil_add(
            forward, anvil_add((AnvilVec3){right.x * horizontal,
                                           right.y * horizontal,
                                           right.z * horizontal},
                               (AnvilVec3){up.x * vertical, up.y * vertical,
                                           up.z * vertical})));
        double closest = 1.0e30;
        int hit_index = -1;
        if (!anvil_bvh_trace(0, origin, direction, closest,
                             &closest, &hit_index))
          continue;

        const AnvilTraceSphere *hit = &anvil_trace_spheres[hit_index];
        AnvilVec3 point = anvil_add(origin, (AnvilVec3){direction.x * closest,
                                                        direction.y * closest,
                                                        direction.z * closest});
        AnvilVec3 normal = anvil_normalize(anvil_sub(point, hit->center));
        double diffuse = fmax(0.0, anvil_dot(normal, light));
        int shadowed = 0;
        if (diffuse > 0.0) {
          AnvilVec3 shadow_origin = anvil_add(point, (AnvilVec3){normal.x * 0.002,
                                                                normal.y * 0.002,
                                                                normal.z * 0.002});
          double shadow_t;
          int shadow_index;
          shadowed = anvil_bvh_trace(0, shadow_origin, light, 1.0e30,
                                     &shadow_t, &shadow_index);
        }
        double brightness = shadowed ? 0.13 : 0.16 + 0.78 * diffuse;
        AnvilVec3 view = {-direction.x, -direction.y, -direction.z};
        AnvilVec3 halfway = anvil_normalize(anvil_add(light, view));
        double specular = pow(fmax(0.0, anvil_dot(normal, halfway)), 28.0) * 0.22;
        int red = (int)(hit->r * brightness + 255.0 * specular);
        int green = (int)(hit->g * brightness + 255.0 * specular);
        int blue = (int)(hit->b * brightness + 255.0 * specular);
        uint32_t color = anvil_color(red, green, blue);
        double camera_depth = anvil_dot(anvil_sub(point, origin), forward);
        size_t pixel = (size_t)py * ANVIL_WIDTH + (size_t)px;
        if (camera_depth < anvil_depth_buffer[pixel]) {
          anvil_depth_buffer[pixel] = camera_depth;
          anvil_pixel(px, py, color, hit->a);
        }
      }
    }
  }
  anvil_trace_sphere_count = 0;
}
static double anvil_fade(double t) {
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}
static double anvil_lerp(double a, double b, double t) {
  return a + t * (b - a);
}
double anvil_noise(double x, double y, double z) {
  int xi = (int)floor(x), yi = (int)floor(y), zi = (int)floor(z);
  double xf = x - xi, yf = y - yi, zf = z - zi, u = anvil_fade(xf),
         v = anvil_fade(yf), w = anvil_fade(zf);
  double c[8];
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 2; ++j)
      for (int k = 0; k < 2; ++k)
        c[i * 4 + j * 2 + k] = anvil_grad(anvil_hash(xi + i, yi + j, zi + k),
                                          xf - i, yf - j, zf - k);
  double x00 = anvil_lerp(c[0], c[4], u), x10 = anvil_lerp(c[2], c[6], u),
         x01 = anvil_lerp(c[1], c[5], u), x11 = anvil_lerp(c[3], c[7], u);
  return anvil_lerp(anvil_lerp(x00, x10, v), anvil_lerp(x01, x11, v), w) * 0.7;
}
double anvil_fbm(double x, double y, double z, int octaves, double lacunarity,
                 double gain) {
  double sum = 0, amp = 0.5, norm = 0;
  for (int i = 0; i < octaves && i < 16; ++i) {
    sum += anvil_noise(x, y, z) * amp;
    norm += amp;
    x *= lacunarity;
    y *= lacunarity;
    z *= lacunarity;
    amp *= gain;
  }
  return norm ? sum / norm : 0;
}

static int anvil_net_ready(void) {
  if (anvil_winsock_started)
    return 1;
  WSADATA data;
  if (WSAStartup(MAKEWORD(2, 2), &data) != 0)
    return 0;
  anvil_winsock_started = 1;
  return 1;
}
int anvil_net_host(int port) {
  if (!anvil_net_ready())
    return 0;
  if (anvil_net_socket != INVALID_SOCKET)
    closesocket(anvil_net_socket);
  anvil_net_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (anvil_net_socket == INVALID_SOCKET)
    return 0;
  SOCKADDR_IN local;
  memset(&local, 0, sizeof(local));
  local.sin_family = AF_INET;
  local.sin_addr.s_addr = htonl(INADDR_ANY);
  local.sin_port = htons((u_short)port);
  u_long nonblocking = 1;
  ioctlsocket(anvil_net_socket, FIONBIO, &nonblocking);
  anvil_net_has_peer = 0;
  return bind(anvil_net_socket, (SOCKADDR *)&local, sizeof(local)) == 0;
}
int anvil_net_join(const char *address, int port) {
  if (!anvil_net_ready())
    return 0;
  if (anvil_net_socket != INVALID_SOCKET)
    closesocket(anvil_net_socket);
  anvil_net_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (anvil_net_socket == INVALID_SOCKET)
    return 0;
  memset(&anvil_net_peer, 0, sizeof(anvil_net_peer));
  anvil_net_peer.sin_family = AF_INET;
  anvil_net_peer.sin_port = htons((u_short)port);
  if (inet_pton(AF_INET, address, &anvil_net_peer.sin_addr) != 1) {
    closesocket(anvil_net_socket);
    anvil_net_socket = INVALID_SOCKET;
    return 0;
  }
  u_long nonblocking = 1;
  ioctlsocket(anvil_net_socket, FIONBIO, &nonblocking);
  anvil_net_has_peer = 1;
  return 1;
}
double anvil_net_receive(void) {
  if (anvil_net_socket == INVALID_SOCKET)
    return anvil_net_value;
  double value;
  SOCKADDR_IN from;
  int from_len = sizeof(from);
  int count = recvfrom(anvil_net_socket, (char *)&value, (int)sizeof(value), 0,
                       (SOCKADDR *)&from, &from_len);
  if (count == (int)sizeof(value)) {
    anvil_net_value = value;
    if (!anvil_net_has_peer) {
      anvil_net_peer = from;
      anvil_net_has_peer = 1;
    }
  }
  return anvil_net_value;
}
void anvil_net_send(double value) {
  if (anvil_net_socket == INVALID_SOCKET || !anvil_net_has_peer)
    return;
  (void)sendto(anvil_net_socket, (const char *)&value, (int)sizeof(value), 0,
               (SOCKADDR *)&anvil_net_peer, sizeof(anvil_net_peer));
}
void anvil_net_close(void) {
  if (anvil_net_socket != INVALID_SOCKET) {
    closesocket(anvil_net_socket);
    anvil_net_socket = INVALID_SOCKET;
  }
  if (anvil_winsock_started) {
    WSACleanup();
    anvil_winsock_started = 0;
  }
  anvil_net_has_peer = 0;
}

static LRESULT CALLBACK anvil_window_proc(HWND window, UINT message,
                                          WPARAM wparam, LPARAM lparam) {
  switch (message) {
  case WM_CLOSE:
    DestroyWindow(window);
    return 0;
  case WM_DESTROY:
    anvil_running = 0;
    anvil_window = NULL;
    PostQuitMessage(0);
    return 0;
  case WM_ERASEBKGND:
    return 1;
  case WM_KEYDOWN:
    if (wparam < ANVIL_KEYS) {
      if (!anvil_keys[wparam])
        anvil_pressed_keys[wparam] = 1;
      anvil_keys[wparam] = 1;
    }
    return 0;
  case WM_KEYUP:
    if (wparam < ANVIL_KEYS)
      anvil_keys[wparam] = 0;
    return 0;
  case WM_PAINT: {
    PAINTSTRUCT ps;
    HDC dc = BeginPaint(window, &ps);
    if (anvil_pixels)
      StretchDIBits(dc, 0, 0, ANVIL_WIDTH, ANVIL_HEIGHT, 0, 0, ANVIL_WIDTH,
                    ANVIL_HEIGHT, anvil_pixels, &anvil_bitmap_info,
                    DIB_RGB_COLORS, SRCCOPY);
    EndPaint(window, &ps);
    return 0;
  }
  }
  return DefWindowProcA(window, message, wparam, lparam);
}

static void anvil_release_frame_resources(void) {
  if (anvil_memory_dc && anvil_old_bitmap)
    SelectObject(anvil_memory_dc, anvil_old_bitmap);
  if (anvil_bitmap)
    DeleteObject(anvil_bitmap);
  if (anvil_memory_dc)
    DeleteDC(anvil_memory_dc);
  /* CreateDIBSection owns this pixel memory; DeleteObject releases it. */
  free(anvil_depth_buffer);
  anvil_pixels = NULL;
  anvil_depth_buffer = NULL;
  anvil_bitmap = NULL;
  anvil_old_bitmap = NULL;
  anvil_memory_dc = NULL;
}

void anvil_run(AnvilCallback update, AnvilCallback draw, const char *title) {
  HINSTANCE instance = GetModuleHandleA(NULL);
  WNDCLASSEXA wc;
  memset(&wc, 0, sizeof(wc));
  wc.cbSize = sizeof(wc);
  wc.style = CS_HREDRAW | CS_VREDRAW;
  wc.lpfnWndProc = anvil_window_proc;
  wc.hInstance = instance;
  wc.hCursor = LoadCursor(NULL, IDC_ARROW);
  wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
  wc.lpszClassName = "AnvilNativeGameWindow";
  RegisterClassExA(&wc);
  RECT rect = {0, 0, ANVIL_WIDTH, ANVIL_HEIGHT};
  AdjustWindowRect(&rect, WS_OVERLAPPEDWINDOW, FALSE);
  anvil_window = CreateWindowExA(
      0, wc.lpszClassName, title ? title : "Anvil Game", WS_OVERLAPPEDWINDOW,
      CW_USEDEFAULT, CW_USEDEFAULT, rect.right - rect.left,
      rect.bottom - rect.top, NULL, NULL, instance, NULL);
  if (!anvil_window) {
    UnregisterClassA(wc.lpszClassName, instance);
    return;
  }
  anvil_memory_dc = CreateCompatibleDC(NULL);
  if (!anvil_memory_dc)
    goto failed_startup;
  memset(&anvil_bitmap_info, 0, sizeof(anvil_bitmap_info));
  anvil_bitmap_info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
  anvil_bitmap_info.bmiHeader.biWidth = ANVIL_WIDTH;
  anvil_bitmap_info.bmiHeader.biHeight = -ANVIL_HEIGHT;
  anvil_bitmap_info.bmiHeader.biPlanes = 1;
  anvil_bitmap_info.bmiHeader.biBitCount = 32;
  anvil_bitmap_info.bmiHeader.biCompression = BI_RGB;
  anvil_bitmap =
      CreateDIBSection(anvil_memory_dc, &anvil_bitmap_info, DIB_RGB_COLORS,
                       (void **)&anvil_pixels, NULL, 0);
  anvil_old_bitmap = SelectObject(anvil_memory_dc, anvil_bitmap);
  anvil_depth_buffer =
      (double *)malloc((size_t)ANVIL_WIDTH * ANVIL_HEIGHT * sizeof(double));
  if (!anvil_bitmap || !anvil_pixels || !anvil_depth_buffer)
    goto failed_startup;
  QueryPerformanceFrequency(&anvil_clock_frequency);
  QueryPerformanceCounter(&anvil_clock_start);
  LARGE_INTEGER prev = anvil_clock_start;
  double step_seconds = 1.0 / (double)anvil_fixed_hz;
  double accumulator = 0.0;
  ShowWindow(anvil_window, SW_SHOW);
  UpdateWindow(anvil_window);
  anvil_running = 1;
  MSG msg;
  while (anvil_running) {
    while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) {
      if (msg.message == WM_QUIT) {
        anvil_running = 0;
        break;
      }
      TranslateMessage(&msg);
      DispatchMessageA(&msg);
    }
    if (!anvil_running)
      break;
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    double frame_elapsed = (double)(now.QuadPart - prev.QuadPart) /
                           (double)anvil_clock_frequency.QuadPart;
    if (frame_elapsed > 0.25)
      frame_elapsed = 0.25;
    prev = now;
    anvil_elapsed_seconds =
        (double)(now.QuadPart - anvil_clock_start.QuadPart) /
        (double)anvil_clock_frequency.QuadPart;
    accumulator += frame_elapsed;
    int update_count = 0;
    while (accumulator >= step_seconds) {
      anvil_delta_seconds = step_seconds;
      anvil_camera_update();
      if (update)
        update();
      accumulator -= step_seconds;
      update_count++;
      if (update_count == 1)
        memset(anvil_pressed_keys, 0, sizeof(anvil_pressed_keys));
    }
    anvil_clear_frame();
    if (draw)
      draw();
    anvil_trace_finish();
    if (!update)
      memset(anvil_pressed_keys, 0, sizeof(anvil_pressed_keys));
    InvalidateRect(anvil_window, NULL, FALSE);
    UpdateWindow(anvil_window);
    double sleep_seconds = step_seconds - accumulator;
    if (sleep_seconds > 0.002)
      Sleep((DWORD)(sleep_seconds * 1000.0));
    else
      Sleep(0);
  }
  anvil_release_frame_resources();
  UnregisterClassA(wc.lpszClassName, instance);
  return;

failed_startup:
  anvil_release_frame_resources();
  if (anvil_window)
    DestroyWindow(anvil_window);
  UnregisterClassA(wc.lpszClassName, instance);
}

static size_t anvil_array_checked_index(const double *values, int size,
                                        double index, const char *source,
                                        int line) {
  if (!values || size <= 0 || !isfinite(index) || index < 0.0 ||
      index >= (double)size || floor(index) != index) {
    fprintf(stderr,
            "%s:%d: array index %.15g is invalid; expected an integer from 0 "
            "through %d\n",
            source ? source : "<generated>", line, index, size - 1);
    exit(2);
  }
  return (size_t)index;
}

double anvil_array_get(const double *values, int size, double index,
                       const char *source, int line) {
  return values[anvil_array_checked_index(values, size, index, source, line)];
}

void anvil_array_set(double *values, int size, double index, double value,
                     const char *source, int line) {
  values[anvil_array_checked_index(values, size, index, source, line)] = value;
}

