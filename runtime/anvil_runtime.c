#define WIN32_LEAN_AND_MEAN
#include "anvil_runtime.h"
#include "anvil_projection.h"

#include <math.h>
#include <dwmapi.h>
#include <mmsystem.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <io.h>

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "winmm.lib")
#pragma comment(lib, "dwmapi.lib")

enum {
  ANVIL_WIDTH = 960,
  ANVIL_HEIGHT = 600,
  ANVIL_KEYS = 256,
  ANVIL_MOUSE_BUTTONS = 3,
  ANVIL_IMAGES = 64,
  ANVIL_IMAGE_MAX_DIMENSION = 8192
};
/* Bounded recursion: generated functions enter and leave a frame, and a call
   that grows the C stack past this budget stops with a diagnostic instead of
   an OS stack overflow. The base is captured on the first entry. */
enum { ANVIL_STACK_BUDGET_BYTES = 512 * 1024 };
static uintptr_t anvil_stack_base;
void anvil_frame_enter(void) {
  char marker;
  uintptr_t here = (uintptr_t)&marker;
  if (anvil_stack_base == 0) {
    anvil_stack_base = here;
    return;
  }
  if (here < anvil_stack_base &&
      anvil_stack_base - here > (uintptr_t)ANVIL_STACK_BUDGET_BYTES) {
    fprintf(stderr,
            "Anvil call depth exceeded the %d KiB stack budget; check for "
            "unbounded recursion\n",
            (int)(ANVIL_STACK_BUDGET_BYTES / 1024));
    exit(2);
  }
}
void anvil_frame_leave(void) {}
#define ANVIL_IMAGE_MEMORY_LIMIT ((size_t)128 * 1024 * 1024)
enum { ANVIL_TRACE_SPHERES = 32 };
static const double ANVIL_NEAR_DEPTH = 0.08;
enum {
  ANVIL_RAY_BACKEND_BVH,
  ANVIL_RAY_BACKEND_DXR,
  ANVIL_RAY_BACKEND_EMBREE
};
enum { ANVIL_PHYSICS_BODIES = 128, ANVIL_PHYSICS_SOLVER_ITERATIONS = 4 };
enum { ANVIL_PHYSICS_CIRCLE, ANVIL_PHYSICS_BOX };
#define ANVIL_PHYSICS_MAX_COORDINATE 1000000000.0
#define ANVIL_PHYSICS_MAX_RADIUS 1000000.0
#define ANVIL_PHYSICS_MAX_SPEED 1000000.0
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
typedef struct {
  double x, y, vx, vy, force_x, force_y;
  double radius, half_width, half_height, mass, restitution, friction;
  uint32_t generation;
  int active, shape;
} AnvilPhysicsBody;
typedef struct {
  uint32_t *pixels;
  int width, height;
  uint32_t generation;
  int tint_r, tint_g, tint_b;
  int flip_x, flip_y;
} AnvilImage;

static AnvilImage *anvil_image_from_handle(double handle);

static HWND anvil_window;
static LONG anvil_window_saved_style;
static RECT anvil_window_saved_rect;
static int anvil_window_is_fullscreen;
/* Display scaling: the framebuffer stays 960x600 and is letterboxed, but the
   window is sized so it looks the same physical size at any monitor DPI. */
static double anvil_dpi_factor = 1.0;
static double anvil_window_scale_factor = 1.0;
static HDC anvil_memory_dc;
/* Two framebuffers: the program draws into the back one while the front one is
   on screen, and they swap at present, so no frame is ever shown half-drawn. */
static HBITMAP anvil_bitmaps[2];
static uint32_t *anvil_buffers[2];
static uint32_t *anvil_display_pixels;
static int anvil_back_index;
static HGDIOBJ anvil_old_bitmap;
static BITMAPINFO anvil_bitmap_info;
static uint32_t *anvil_pixels;
static double *anvil_depth_buffer;
static int anvil_running;
static int anvil_keys[ANVIL_KEYS];
static int anvil_pressed_keys[ANVIL_KEYS];
static int anvil_mouse_buttons[ANVIL_MOUSE_BUTTONS];
static int anvil_mouse_pressed_buttons[ANVIL_MOUSE_BUTTONS];
static int anvil_mouse_client_x = -1;
static int anvil_mouse_client_y = -1;
static int anvil_mouse_has_position;
static double anvil_mouse_wheel_delta;
static int anvil_mouse_invalid_button_warned;
static AnvilImage anvil_images[ANVIL_IMAGES];
static size_t anvil_image_memory_used;
static size_t anvil_sound_bytes;
/* Where each live resource came from: the compiler passes the Anvil source
   file and line to every load, so memory_report() can name the call site
   instead of just a byte total. Declared up here because the image loader
   records its site long before the sound section is defined. */
typedef struct {
  const char *file;
  const char *path;
  int line;
  /* The Anvil call chain that reached the load, innermost last. The compiler
     pushes one name per function entry, so a load buried in helper functions
     reports "fn(main) > fn(setup) > fn(load_world)" instead of only a line. */
  const char *stack[8];
  int depth;
  int truncated;
} AnvilAllocSite;
static AnvilAllocSite anvil_image_sites[ANVIL_IMAGES];

enum {
  ANVIL_CALL_STACK_MAX = 64,
  ANVIL_ALLOC_STACK_SHOWN = 8
};
static const char *anvil_call_names[ANVIL_CALL_STACK_MAX];
static int anvil_call_depth;

void anvil_call_enter(const char *name) {
  if (anvil_call_depth < ANVIL_CALL_STACK_MAX)
    anvil_call_names[anvil_call_depth] = name;
  ++anvil_call_depth;
}

void anvil_call_leave(void) {
  if (anvil_call_depth > 0)
    --anvil_call_depth;
}

static void anvil_capture_site(AnvilAllocSite *site) {
  int depth = anvil_call_depth < ANVIL_CALL_STACK_MAX ? anvil_call_depth
                                                     : ANVIL_CALL_STACK_MAX;
  site->depth = depth < ANVIL_ALLOC_STACK_SHOWN ? depth : ANVIL_ALLOC_STACK_SHOWN;
  site->truncated = depth > ANVIL_ALLOC_STACK_SHOWN;
  for (int i = 0; i < site->depth; ++i)
    site->stack[i] = anvil_call_names[i];
}

/* "  file:line  from fn(a) > fn(b)  path" - the path stays last so a reader
   can still grab it with a plain suffix match. */
static void anvil_print_site(const AnvilAllocSite *site) {
  printf("  %s:%d  ", site->file ? site->file : "?", site->line);
  if (site->depth > 0) {
    printf("from ");
    for (int i = 0; i < site->depth; ++i)
      printf("%sfn(%s)", i ? " > " : "", site->stack[i]);
    if (site->truncated)
      printf(" > ...");
  } else {
    printf("from top level");
  }
  printf("  %s\n", site->path ? site->path : "?");
}
static int anvil_clear_color[4] = {12, 17, 29, 255};
static int anvil_scene_is_3d = 1;
static double anvil_camera_x = 0.0, anvil_camera_y = 3.0, anvil_camera_z = 8.0;
static double anvil_camera_yaw, anvil_camera_pitch;
static double anvil_camera_focal = 520.0;
static double anvil_camera_move_speed, anvil_camera_turn_speed;
/* 2D camera: screen = (world - pan) * zoom. Defaults are the identity, so
   existing programs draw exactly where they did before. */
static double anvil_camera2d_x, anvil_camera2d_y;
static double anvil_camera2d_zoom = 1.0;
/* Parallax scales how much of the camera pan a layer follows: 1 is the world
   layer, lower values scroll slower, 0 pins the layer to the screen. */
static double anvil_parallax_factor = 1.0;

static void anvil_camera2d_point(double *x, double *y) {
  *x = (*x - anvil_camera2d_x * anvil_parallax_factor) * anvil_camera2d_zoom;
  *y = (*y - anvil_camera2d_y * anvil_parallax_factor) * anvil_camera2d_zoom;
}

double anvil_parallax(double factor) {
  double previous = anvil_parallax_factor;
  if (isfinite(factor))
    anvil_parallax_factor = factor < 0.0 ? 0.0 : factor > 4.0 ? 4.0 : factor;
  return previous;
}

double anvil_camera2d(double x, double y, double zoom) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(zoom) || zoom <= 0.0)
    return 0.0;
  anvil_camera2d_x = x;
  anvil_camera2d_y = y;
  anvil_camera2d_zoom =
      zoom < 0.05 ? 0.05 : zoom > 20.0 ? 20.0 : zoom;
  return 1.0;
}
static AnvilTraceSphere anvil_trace_spheres[ANVIL_TRACE_SPHERES];
static int anvil_trace_sphere_count;
static AnvilBvhNode anvil_trace_bvh[ANVIL_TRACE_SPHERES * 2];
static int anvil_trace_bvh_count;
static int anvil_active_ray_backend = ANVIL_RAY_BACKEND_BVH;
static unsigned int anvil_ray_backend_warnings;
static double anvil_delta_seconds = 1.0 / 60.0;
static double anvil_frame_tick_seconds, anvil_frame_render_seconds,
    anvil_frame_present_seconds;
static int anvil_mesh_culling_enabled = 1;
static int anvil_mesh_culled_frame, anvil_mesh_drawn_frame;
/* Overhead shadow: the same geometry flattened onto a ground plane. */
static int anvil_shadows_enabled;
static double anvil_shadow_ground_y;
static int anvil_shadow_alpha_value = 150;
static void anvil_world_triangle(AnvilVec3 v[3], uint32_t base,
                                 double brightness, int alpha);
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
static AnvilPhysicsBody anvil_physics_bodies[ANVIL_PHYSICS_BODIES];
static int anvil_physics_active_capacity = ANVIL_PHYSICS_BODIES;
static double anvil_physics_gravity_x;
static double anvil_physics_gravity_y = -9.81;

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
  anvil_mesh_culled_frame = 0;
  anvil_mesh_drawn_frame = 0;
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

static AnvilCameraVertex anvil_to_camera(AnvilVec3 p) {
  AnvilVec3 right, up, forward;
  anvil_camera_basis(&right, &up, &forward);
  AnvilVec3 relative = {p.x - anvil_camera_x, p.y - anvil_camera_y,
                        p.z - anvil_camera_z};
  return (AnvilCameraVertex){anvil_dot(relative, right), anvil_dot(relative, up),
                             anvil_dot(relative, forward)};
}

static int anvil_project_camera(AnvilCameraVertex p, AnvilProjected *out) {
  if (p.depth < ANVIL_NEAR_DEPTH || !isfinite(p.depth))
    return 0;
  out->x = ANVIL_WIDTH * 0.5 + p.x * anvil_camera_focal / p.depth;
  out->y = ANVIL_HEIGHT * 0.54 - p.y * anvil_camera_focal / p.depth;
  out->depth = p.depth;
  return isfinite(out->x) && isfinite(out->y);
}

static int anvil_project(AnvilVec3 p, AnvilProjected *out) {
  if (!anvil_scene_is_3d) {
    const double pixels_per_unit = 64.0;
    out->x = ANVIL_WIDTH * 0.5 + p.x * pixels_per_unit;
    out->y = ANVIL_HEIGHT * 0.5 - p.y * pixels_per_unit;
    out->depth = 1000.0 - p.z;
    return 1;
  }
  return anvil_project_camera(anvil_to_camera(p), out);
}

static void anvil_triangle(AnvilProjected a, AnvilProjected b, AnvilProjected c,
                           uint32_t color, int alpha) {
  double area = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  if (!isfinite(area) || fabs(area) < 1e-8 || !isfinite(a.x) ||
      !isfinite(a.y) || !isfinite(b.x) || !isfinite(b.y) ||
      !isfinite(c.x) || !isfinite(c.y))
    return;
  double left = fmin(a.x, fmin(b.x, c.x));
  double right = fmax(a.x, fmax(b.x, c.x));
  double top = fmin(a.y, fmin(b.y, c.y));
  double bottom = fmax(a.y, fmax(b.y, c.y));
  if (right < 0.0 || bottom < 0.0 || left >= ANVIL_WIDTH ||
      top >= ANVIL_HEIGHT)
    return;
  int minx = left <= 0.0 ? 0 : (int)floor(left);
  int maxx = right >= ANVIL_WIDTH - 1 ? ANVIL_WIDTH - 1 : (int)ceil(right);
  int miny = top <= 0.0 ? 0 : (int)floor(top);
  int maxy = bottom >= ANVIL_HEIGHT - 1 ? ANVIL_HEIGHT - 1 : (int)ceil(bottom);
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

/* Textured variant: same barycentric rasteriser and depth buffer, with a
   nearest-neighbour texel lookup. Affine mapping (no perspective correction),
   which is fine for the flat quads the primitives produce. */
static AnvilImage *anvil_texture_image;
static int anvil_texture_handle_bits;

double anvil_texture(double handle) {
  AnvilImage *image = anvil_image_from_handle(handle);
  anvil_texture_image = image && image->pixels ? image : NULL;
  return anvil_texture_image ? 1.0 : 0.0;
}

static void anvil_triangle_textured(AnvilProjected p[3], double uv[3][2],
                                    double brightness, int alpha) {
  AnvilImage *texture = anvil_texture_image;
  if (!texture || !texture->pixels) {
    return;
  }
  double area =
      (p[1].x - p[0].x) * (p[2].y - p[0].y) - (p[1].y - p[0].y) * (p[2].x - p[0].x);
  if (!isfinite(area) || fabs(area) < 1e-8)
    return;
  double left = fmin(p[0].x, fmin(p[1].x, p[2].x));
  double right = fmax(p[0].x, fmax(p[1].x, p[2].x));
  double top = fmin(p[0].y, fmin(p[1].y, p[2].y));
  double bottom = fmax(p[0].y, fmax(p[1].y, p[2].y));
  if (right < 0.0 || bottom < 0.0 || left >= ANVIL_WIDTH || top >= ANVIL_HEIGHT)
    return;
  int minx = left <= 0.0 ? 0 : (int)floor(left);
  int maxx = right >= ANVIL_WIDTH - 1 ? ANVIL_WIDTH - 1 : (int)ceil(right);
  int miny = top <= 0.0 ? 0 : (int)floor(top);
  int maxy = bottom >= ANVIL_HEIGHT - 1 ? ANVIL_HEIGHT - 1 : (int)ceil(bottom);
  for (int y = miny; y <= maxy; ++y)
    for (int x = minx; x <= maxx; ++x) {
      double px = x + 0.5, py = y + 0.5;
      double w0 = ((p[1].x - px) * (p[2].y - py) - (p[1].y - py) * (p[2].x - px)) / area;
      double w1 = ((p[2].x - px) * (p[0].y - py) - (p[2].y - py) * (p[0].x - px)) / area;
      double w2 = 1.0 - w0 - w1;
      if (w0 < 0 || w1 < 0 || w2 < 0)
        continue;
      double z = w0 * p[0].depth + w1 * p[1].depth + w2 * p[2].depth;
      size_t index = (size_t)y * ANVIL_WIDTH + (size_t)x;
      if (!(z < anvil_depth_buffer[index]))
        continue;
      /* Perspective-correct: interpolate u/z and 1/z, then divide, otherwise
         textures on faces seen at an angle compress towards the horizon. */
      double i0 = 1.0 / p[0].depth, i1 = 1.0 / p[1].depth, i2 = 1.0 / p[2].depth;
      double inverse = w0 * i0 + w1 * i1 + w2 * i2;
      if (!(inverse > 1e-9))
        continue;
      double u = (w0 * uv[0][0] * i0 + w1 * uv[1][0] * i1 +
                  w2 * uv[2][0] * i2) /
                 inverse;
      double v = (w0 * uv[0][1] * i0 + w1 * uv[1][1] * i1 +
                  w2 * uv[2][1] * i2) /
                 inverse;
      u -= floor(u);
      v = 1.0 - v;
      v -= floor(v);
      int tx = (int)(u * texture->width);
      int ty = (int)(v * texture->height);
      if (tx < 0) tx = 0;
      if (ty < 0) ty = 0;
      if (tx >= texture->width) tx = texture->width - 1;
      if (ty >= texture->height) ty = texture->height - 1;
      uint32_t texel = texture->pixels[(size_t)ty * (size_t)texture->width + (size_t)tx];
      unsigned int ta = (texel >> 24) & 255u;
      if (ta == 0)
        continue;
      int r = (int)(((texel >> 16) & 255u) * brightness);
      int g = (int)(((texel >> 8) & 255u) * brightness);
      int b = (int)((texel & 255u) * brightness);
      anvil_depth_buffer[index] = z;
      anvil_pixel(x, y, anvil_color(r, g, b), (int)(ta * alpha / 255));
    }
}

void anvil_set_scene3d(int enabled) { anvil_scene_is_3d = enabled != 0; }
void anvil_camera_perspective(double x, double y, double z) {
  anvil_camera_x = x;
  anvil_camera_y = y;
  anvil_camera_z = z;
}
double anvil_camera_angle(double yaw, double pitch) {
  if (!isfinite(yaw) || !isfinite(pitch))
    return 0.0;
  if (pitch > 89.0)
    pitch = 89.0;
  if (pitch < -89.0)
    pitch = -89.0;
  anvil_camera_yaw = yaw;
  anvil_camera_pitch = pitch;
  return 1.0;
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
  anvil_camera2d_point(&x, &y);
  w *= anvil_camera2d_zoom;
  h *= anvil_camera2d_zoom;
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
  anvil_camera2d_point(&x, &y);
  radius *= anvil_camera2d_zoom;
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
  anvil_camera2d_point(&x1, &y1);
  anvil_camera2d_point(&x2, &y2);
  thickness *= anvil_camera2d_zoom;
  AnvilScreenPoint start = {x1, y1}, end = {x2, y2};
  if (!isfinite(thickness) ||
      !anvil_clip_screen_line(&start, &end, ANVIL_WIDTH, ANVIL_HEIGHT))
    return;
  x1 = start.x;
  y1 = start.y;
  x2 = end.x;
  y2 = end.y;
  int dx = abs((int)lrint(x2) - (int)lrint(x1)), sx = x1 < x2 ? 1 : -1,
      dy = -abs((int)lrint(y2) - (int)lrint(y1)), sy = y1 < y2 ? 1 : -1,
      err = dx + dy;
  int x = (int)lrint(x1), y = (int)lrint(y1),
      radius = (int)fmin(fmax(0.0, ceil(thickness * .5)), ANVIL_WIDTH);
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

/* One directional light shared by every 3D path. Ambient is the floor a face
   keeps when it faces away; intensity scales the lit part. */
static AnvilVec3 anvil_light_direction = {-0.35, 0.8, 0.55};
static double anvil_light_ambient_value = 0.28;
static double anvil_light_intensity_value = 1.0;

double anvil_light(double x, double y, double z) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(z))
    return 0.0;
  if (x == 0.0 && y == 0.0 && z == 0.0)
    return 0.0;
  anvil_light_direction = (AnvilVec3){x, y, z};
  return 1.0;
}

double anvil_light_ambient(double level) {
  double previous = anvil_light_ambient_value;
  if (isfinite(level))
    anvil_light_ambient_value = level < 0.0 ? 0.0 : level > 1.0 ? 1.0 : level;
  return previous;
}

double anvil_light_intensity(double level) {
  double previous = anvil_light_intensity_value;
  if (isfinite(level))
    anvil_light_intensity_value = level < 0.0 ? 0.0 : level > 2.0 ? 2.0 : level;
  return previous;
}

/* Lit fraction for a face normal; two-sided faces (models) light from either
   side, the primitives do not. */
static double anvil_light_level(AnvilVec3 normal, int two_sided) {
  AnvilVec3 light = anvil_normalize(anvil_light_direction);
  double facing = anvil_dot(normal, light);
  if (two_sided)
    facing = fabs(facing);
  if (!(facing > 0.0))
    facing = 0.0;
  double level = anvil_light_ambient_value +
                 (1.0 - anvil_light_ambient_value) *
                     anvil_light_intensity_value * facing;
  return level < 0.0 ? 0.0 : level > 1.0 ? 1.0 : level;
}

void anvil_cube(double x, double y, double z, double size, double rx, double ry,
                double rz, int r, int g, int b, int a) {
  double h = size * .5;
  AnvilVec3 v[8];
  for (int i = 0; i < 8; ++i) {
    AnvilVec3 q = {(i & 1) ? h : -h, (i & 2) ? h : -h, (i & 4) ? h : -h};
    q = anvil_rotate(q, rx, ry, rz);
    v[i] = (AnvilVec3){x + q.x, y + q.y, z + q.z};
  }
  static const int faces[6][4] = {{0, 4, 6, 2}, {1, 3, 7, 5}, {0, 1, 5, 4},
                                  {2, 6, 7, 3}, {0, 2, 3, 1}, {4, 5, 7, 6}};
  uint32_t base = anvil_color(r, g, b);
  if (anvil_shadows_enabled && a > 0) {
    AnvilVec3 shadow[8];
    for (int i = 0; i < 8; ++i) {
      shadow[i] = v[i];
      shadow[i].y = anvil_shadow_ground_y + 0.002;
    }
    for (int f = 0; f < 6; ++f) {
      const int triangles[2][3] = {{faces[f][0], faces[f][1], faces[f][2]},
                                   {faces[f][0], faces[f][2], faces[f][3]}};
      for (int t = 0; t < 2; ++t) {
        AnvilVec3 corners[3] = {shadow[triangles[t][0]],
                                shadow[triangles[t][1]],
                                shadow[triangles[t][2]]};
        anvil_world_triangle(corners, 0, 1.0, anvil_shadow_alpha_value);
      }
    }
  }
  for (int f = 0; f < 6; ++f) {
    AnvilVec3 n =
        anvil_normalize(anvil_cross(anvil_sub(v[faces[f][1]], v[faces[f][0]]),
                                    anvil_sub(v[faces[f][2]], v[faces[f][0]])));
    double brightness = anvil_light_level(n, 0);
    const int triangles[2][3] = {{faces[f][0], faces[f][1], faces[f][2]},
                                 {faces[f][0], faces[f][2], faces[f][3]}};
    for (int t = 0; t < 2; ++t) {
      AnvilProjected projected[4];
      int count;
      if (anvil_scene_is_3d) {
        AnvilCameraVertex camera[3] = {
            anvil_to_camera(v[triangles[t][0]]),
            anvil_to_camera(v[triangles[t][1]]),
            anvil_to_camera(v[triangles[t][2]])};
        AnvilCameraVertex clipped[4];
        count = anvil_clip_triangle_near(camera, ANVIL_NEAR_DEPTH, clipped);
        for (int i = 0; i < count; ++i)
          if (!anvil_project_camera(clipped[i], &projected[i])) {
            count = 0;
            break;
          }
      } else {
        count = 3;
        for (int i = 0; i < count; ++i)
          if (!anvil_project(v[triangles[t][i]], &projected[i])) {
            count = 0;
            break;
          }
      }
      static const double quad_uv[4][2] = {{0, 0}, {1, 0}, {1, 1}, {0, 1}};
      static const int uv_order[2][3] = {{0, 1, 2}, {0, 2, 3}};
      if (count == 3 && anvil_texture_image) {
        double uv[3][2] = {{
                               quad_uv[uv_order[t][0]][0],
                               quad_uv[uv_order[t][0]][1],
                           },
                           {
                               quad_uv[uv_order[t][1]][0],
                               quad_uv[uv_order[t][1]][1],
                           },
                           {
                               quad_uv[uv_order[t][2]][0],
                               quad_uv[uv_order[t][2]][1],
                           }};
        anvil_triangle_textured(projected, uv, brightness, a);
        continue;
      }
      for (int i = 1; i + 1 < count; ++i) {
        AnvilProjected clipped_triangle[3] = {projected[0], projected[i],
                                               projected[i + 1]};
        anvil_triangle_lit(clipped_triangle, base, brightness, a);
      }
    }
  }
}

/* Draw a baked triangle mesh. Each triangle is 12 doubles: nine coordinates for
   three vertices, then r, g, b in 0..255. Vertices are scaled and rotated about
   the model origin, translated to (x,y,z), flat-shaded with the scene light and
   rasterised through the same near-plane clip and depth buffer as the cube. */
double anvil_mesh_culled(void) { return (double)anvil_mesh_culled_frame; }
double anvil_mesh_drawn(void) { return (double)anvil_mesh_drawn_frame; }
double anvil_mesh_culling(double on) {
  anvil_mesh_culling_enabled = on != 0.0;
  return anvil_mesh_culling_enabled ? 1.0 : 0.0;
}

double anvil_shadow(double on) {
  anvil_shadows_enabled = on != 0.0;
  return anvil_shadows_enabled ? 1.0 : 0.0;
}

double anvil_shadow_height(double y) {
  if (!isfinite(y))
    return 0.0;
  anvil_shadow_ground_y = y;
  return y;
}

double anvil_shadow_alpha(double alpha) {
  if (!isfinite(alpha))
    return 0.0;
  int applied = (int)(alpha < 0.0 ? 0.0 : alpha > 255.0 ? 255.0 : alpha);
  anvil_shadow_alpha_value = applied;
  return (double)applied;
}

static void anvil_world_triangle(AnvilVec3 v[3], uint32_t base,
                                 double brightness, int alpha) {
  AnvilProjected projected[4];
  int count;
  if (anvil_scene_is_3d) {
    AnvilCameraVertex camera[3] = {
        anvil_to_camera(v[0]), anvil_to_camera(v[1]), anvil_to_camera(v[2])};
    AnvilCameraVertex clipped[4];
    count = anvil_clip_triangle_near(camera, ANVIL_NEAR_DEPTH, clipped);
    for (int i = 0; i < count; ++i)
      if (!anvil_project_camera(clipped[i], &projected[i])) {
        count = 0;
        break;
      }
  } else {
    count = 3;
    for (int i = 0; i < count; ++i)
      if (!anvil_project(v[i], &projected[i])) {
        count = 0;
        break;
      }
  }
  for (int i = 1; i + 1 < count; ++i) {
    AnvilProjected triangle[3] = {projected[0], projected[i],
                                  projected[i + 1]};
    anvil_triangle_lit(triangle, base, brightness, alpha);
  }
}

/* Bounding-sphere frustum test. The sphere is transformed to world space,
   then projected; if it lies entirely behind the near plane or completely
   outside the viewport it cannot contribute a pixel. */
static int anvil_mesh_visible(double cx, double cy, double cz, double radius,
                              double x, double y, double z, double scale,
                              double rx, double ry, double rz) {
  if (!anvil_scene_is_3d)
    return 1;
  AnvilVec3 center = {cx * scale, cy * scale, cz * scale};
  center = anvil_rotate(center, rx, ry, rz);
  center.x += x;
  center.y += y;
  center.z += z;
  double r = fabs(radius * scale);
  AnvilCameraVertex camera = anvil_to_camera(center);
  if (camera.depth + r < ANVIL_NEAR_DEPTH)
    return 0;
  if (camera.depth > ANVIL_NEAR_DEPTH) {
    double screen_radius = r * anvil_camera_focal / camera.depth;
    double sx = ANVIL_WIDTH * 0.5 + camera.x * anvil_camera_focal / camera.depth;
    double sy = ANVIL_HEIGHT * 0.54 - camera.y * anvil_camera_focal / camera.depth;
    if (sx + screen_radius < 0.0 || sx - screen_radius > ANVIL_WIDTH ||
        sy + screen_radius < 0.0 || sy - screen_radius > ANVIL_HEIGHT)
      return 0;
  }
  return 1;
}

double anvil_mesh_draw(const double *data, int triangle_count, double cx,
                       double cy, double cz, double radius, double x, double y,
                       double z, double scale, double rx, double ry, double rz) {
  if (!data || triangle_count <= 0 || !isfinite(x) || !isfinite(y) ||
      !isfinite(z) || !isfinite(scale) || !isfinite(rx) || !isfinite(ry) ||
      !isfinite(rz) || scale == 0.0)
    return 0.0;
  if (anvil_mesh_culling_enabled &&
      !anvil_mesh_visible(cx, cy, cz, radius, x, y, z, scale, rx, ry, rz)) {
    anvil_mesh_culled_frame++;
    return 0.0;
  }
  anvil_mesh_drawn_frame++;
  if (anvil_shadows_enabled) {
    for (int t = 0; t < triangle_count; ++t) {
      const double *p = data + (size_t)t * 12;
      AnvilVec3 v[3];
      for (int i = 0; i < 3; ++i) {
        AnvilVec3 q = {p[i * 3] * scale, p[i * 3 + 1] * scale,
                       p[i * 3 + 2] * scale};
        q = anvil_rotate(q, rx, ry, rz);
        v[i] = (AnvilVec3){x + q.x, anvil_shadow_ground_y + 0.002, z + q.z};
      }
      anvil_world_triangle(v, 0, 1.0, anvil_shadow_alpha_value);
    }
  }
  for (int t = 0; t < triangle_count; ++t) {
    const double *p = data + (size_t)t * 12;
    AnvilVec3 v[3];
    for (int i = 0; i < 3; ++i) {
      AnvilVec3 q = {p[i * 3] * scale, p[i * 3 + 1] * scale,
                     p[i * 3 + 2] * scale};
      q = anvil_rotate(q, rx, ry, rz);
      v[i] = (AnvilVec3){x + q.x, y + q.y, z + q.z};
    }
    AnvilVec3 n = anvil_normalize(
        anvil_cross(anvil_sub(v[1], v[0]), anvil_sub(v[2], v[0])));
    double brightness = anvil_light_level(n, 1);
    uint32_t base =
        anvil_color((int)p[9], (int)p[10], (int)p[11]);
    anvil_world_triangle(v, base, brightness, 255);
  }
  return 1.0;
}

/* ---- Animated models ---------------------------------------------------- */

#define ANVIL_MODEL_STATES 32
#define ANVIL_MODEL_NODES 128
static double anvil_model_times[ANVIL_MODEL_STATES];

/* model_animate() stores a per-model clip clock; model_draw() reads it back
   through the generated anvil_model_clock(n) argument. */
double anvil_model_animate(int id, double seconds) {
  if (id < 0 || id >= ANVIL_MODEL_STATES || !isfinite(seconds))
    return 0.0;
  anvil_model_times[id] = seconds;
  return seconds;
}

double anvil_model_clock(int id) {
  return id >= 0 && id < ANVIL_MODEL_STATES ? anvil_model_times[id] : 0.0;
}

static void anvil_mat_trs(const double t[3], const double q[4],
                          const double s[3], double *m) {
  const double x = q[0], y = q[1], z = q[2], w = q[3];
  /* Column-major rotation * scale, then translation, like the importer. */
  m[0] = (1 - 2 * (y * y + z * z)) * s[0];
  m[1] = (2 * (x * y + z * w)) * s[0];
  m[2] = (2 * (x * z - y * w)) * s[0];
  m[3] = 0.0;
  m[4] = (2 * (x * y - z * w)) * s[1];
  m[5] = (1 - 2 * (x * x + z * z)) * s[1];
  m[6] = (2 * (y * z + x * w)) * s[1];
  m[7] = 0.0;
  m[8] = (2 * (x * z + y * w)) * s[2];
  m[9] = (2 * (y * z - x * w)) * s[2];
  m[10] = (1 - 2 * (x * x + y * y)) * s[2];
  m[11] = 0.0;
  m[12] = t[0];
  m[13] = t[1];
  m[14] = t[2];
  m[15] = 1.0;
}

static void anvil_mat_mul(const double *a, const double *b, double *out) {
  for (int column = 0; column < 4; ++column)
    for (int row = 0; row < 4; ++row)
      out[column * 4 + row] = a[0 * 4 + row] * b[column * 4 + 0] +
                              a[1 * 4 + row] * b[column * 4 + 1] +
                              a[2 * 4 + row] * b[column * 4 + 2] +
                              a[3 * 4 + row] * b[column * 4 + 3];
}

static void anvil_mat_point(const double *m, double x, double y, double z,
                            double out[3]) {
  out[0] = m[0] * x + m[4] * y + m[8] * z + m[12];
  out[1] = m[1] * x + m[5] * y + m[9] * z + m[13];
  out[2] = m[2] * x + m[6] * y + m[10] * z + m[14];
}

static void anvil_slerp(const double *a, const double *b, double u,
                        double *out) {
  double dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  double sign = 1.0;
  if (dot < 0.0) {
    sign = -1.0;
    dot = -dot;
  }
  if (dot > 0.9995) {
    for (int i = 0; i < 4; ++i)
      out[i] = a[i] + (sign * b[i] - a[i]) * u;
  } else {
    double theta = acos(dot);
    double sin_theta = sin(theta);
    double wa = sin((1.0 - u) * theta) / sin_theta;
    double wb = sin(u * theta) / sin_theta;
    for (int i = 0; i < 4; ++i)
      out[i] = a[i] * wa + sign * b[i] * wb;
  }
  double norm = (out[0] * out[0] + out[1] * out[1] + out[2] * out[2] +
                 out[3] * out[3]);
  if (norm > 0.0) {
    norm = sqrt(norm);
    for (int i = 0; i < 4; ++i)
      out[i] /= norm;
  }
}

/* One channel at a clip time: STEP holds the left key, LINEAR interpolates,
   and a rotation interpolates by slerp so a 180-degree step does not shrink
   through the origin. */
static void anvil_track_sample(const double *times, const double *values,
                               int first_time, int first_value, int count,
                               int path, int interpolation, double t,
                               double *out) {
  int width = path == 1 ? 4 : 3;
  const double *row;
  if (t <= times[first_time]) {
    row = values + first_value;
  } else if (t >= times[first_time + count - 1]) {
    row = values + first_value + (size_t)(count - 1) * (size_t)width;
  } else {
    int index = 0;
    while (index + 2 < count && times[first_time + index + 1] <= t)
      ++index;
    if (interpolation == 1) {
      row = values + first_value + (size_t)index * (size_t)width;
    } else {
      double t0 = times[first_time + index];
      double t1 = times[first_time + index + 1];
      double u = t1 > t0 ? (t - t0) / (t1 - t0) : 0.0;
      const double *left = values + first_value + (size_t)index * (size_t)width;
      const double *right = left + width;
      if (path == 1) {
        anvil_slerp(left, right, u, out);
        return;
      }
      for (int i = 0; i < width; ++i)
        out[i] = left[i] + (right[i] - left[i]) * u;
      return;
    }
  }
  for (int i = 0; i < width; ++i)
    out[i] = row[i];
}

static double anvil_model_local_t[ANVIL_MODEL_NODES][3];
static double anvil_model_local_r[ANVIL_MODEL_NODES][4];
static double anvil_model_local_s[ANVIL_MODEL_NODES][3];
static double anvil_model_world[ANVIL_MODEL_NODES][16];
static int anvil_model_resolving[ANVIL_MODEL_NODES];

static void anvil_model_resolve(int index, const int *parents, int depth) {
  if (anvil_model_resolving[index] == 2)
    return;
  if (anvil_model_resolving[index] == 1 || depth > 64) {
    anvil_mat_trs(anvil_model_local_t[index], anvil_model_local_r[index],
                  anvil_model_local_s[index], anvil_model_world[index]);
    anvil_model_resolving[index] = 2;
    return;
  }
  anvil_model_resolving[index] = 1;
  double local[16];
  anvil_mat_trs(anvil_model_local_t[index], anvil_model_local_r[index],
                anvil_model_local_s[index], local);
  int parent = parents[index];
  if (parent >= 0 && parent != index) {
    anvil_model_resolve(parent, parents, depth + 1);
    anvil_mat_mul(anvil_model_world[parent], local, anvil_model_world[index]);
  } else {
    for (int i = 0; i < 16; ++i)
      anvil_model_world[index][i] = local[i];
  }
  anvil_model_resolving[index] = 2;
}

/* Fill the static node tables from base TRS, override animated channels, then
   compose the hierarchy. Shared by the animated and skinned draw paths. */
static int anvil_model_pose(const double *nodes, int node_count,
                            const int *parents, const double *times,
                            const double *values, const int *tracks,
                            int track_count, double clip_length,
                            double clip_time) {
  if (!nodes || !parents || node_count <= 0 || node_count > ANVIL_MODEL_NODES)
    return 0;
  for (int node = 0; node < node_count; ++node) {
    for (int i = 0; i < 3; ++i) {
      anvil_model_local_t[node][i] = nodes[node * 10 + i];
      anvil_model_local_r[node][i] = nodes[node * 10 + 3 + i];
      anvil_model_local_s[node][i] = nodes[node * 10 + 7 + i];
    }
    anvil_model_local_r[node][3] = nodes[node * 10 + 6];
  }
  double t = 0.0;
  if (clip_length > 0.0 && isfinite(clip_length)) {
    t = fmod(clip_time, clip_length);
    if (t < 0.0)
      t += clip_length;
  }
  for (int i = 0; i < track_count; ++i) {
    const int *track = tracks + i * 6;
    int node = track[0];
    int path = track[1];
    if (node < 0 || node >= node_count)
      continue;
    double sampled[4] = {0.0, 0.0, 0.0, 0.0};
    anvil_track_sample(times, values, track[3], track[4], track[5], path,
                       track[2], t, sampled);
    if (path == 0)
      for (int k = 0; k < 3; ++k)
        anvil_model_local_t[node][k] = sampled[k];
    else if (path == 2)
      for (int k = 0; k < 3; ++k)
        anvil_model_local_s[node][k] = sampled[k];
    else
      for (int k = 0; k < 4; ++k)
        anvil_model_local_r[node][k] = sampled[k];
  }
  for (int node = 0; node < node_count; ++node) {
    anvil_model_resolving[node] = 0;
    anvil_model_resolve(node, parents, 0);
  }
  return 1;
}

double anvil_mesh_draw_animated(
    const double *data, int triangle_count, const double *nodes, int node_count,
    const int *parents, const int *groups, int group_count, const double *times,
    const double *values, const int *tracks, int track_count, double clip_length,
    double clip_time, double x, double y, double z, double scale, double rx,
    double ry, double rz) {
  if (!data || !groups || triangle_count <= 0 || group_count <= 0 ||
      !isfinite(x) || !isfinite(y) || !isfinite(z) || !isfinite(scale) ||
      !isfinite(rx) || !isfinite(ry) || !isfinite(rz) || scale == 0.0)
    return 0.0;
  if (!anvil_model_pose(nodes, node_count, parents, times, values, tracks,
                        track_count, clip_length, clip_time))
    return 0.0;
  anvil_mesh_drawn_frame++;
  for (int group = 0; group < group_count; ++group) {
    const int *entry = groups + group * 3;
    int node = entry[0];
    int first = entry[1];
    int count = entry[2];
    if (node < 0 || node >= node_count)
      continue;
    const double *matrix = anvil_model_world[node];
    for (int triangle = first; triangle < first + count; ++triangle) {
      const double *p = data + (size_t)triangle * 12;
      AnvilVec3 v[3];
      for (int corner = 0; corner < 3; ++corner) {
        double point[3];
        anvil_mat_point(matrix, p[corner * 3], p[corner * 3 + 1],
                        p[corner * 3 + 2], point);
        AnvilVec3 q = {point[0] * scale, point[1] * scale, point[2] * scale};
        q = anvil_rotate(q, rx, ry, rz);
        v[corner] = (AnvilVec3){x + q.x, y + q.y, z + q.z};
      }
      AnvilVec3 n = anvil_normalize(
          anvil_cross(anvil_sub(v[1], v[0]), anvil_sub(v[2], v[0])));
      double brightness = anvil_light_level(n, 1);
      uint32_t base = anvil_color((int)p[9], (int)p[10], (int)p[11]);
      anvil_world_triangle(v, base, brightness, 255);
    }
  }
  return 1.0;
}

/* Skinned draw: every vertex carries four joint indices and four weights, and
   the pose fuses them with jointMatrix = nodeWorld * inverseBindMatrix. */
double anvil_mesh_draw_skinned(
    const double *data, int triangle_count, const double *nodes, int node_count,
    const int *parents, const int *joint_nodes, int joint_count,
    const double *bind, const double *times, const double *values,
    const int *tracks, int track_count, double clip_length, double clip_time,
    double x, double y, double z, double scale, double rx, double ry,
    double rz) {
  if (!data || !joint_nodes || !bind || triangle_count <= 0 ||
      joint_count <= 0 || joint_count > 64 || !isfinite(x) || !isfinite(y) ||
      !isfinite(z) || !isfinite(scale) || !isfinite(rx) || !isfinite(ry) ||
      !isfinite(rz) || scale == 0.0)
    return 0.0;
  if (!anvil_model_pose(nodes, node_count, parents, times, values, tracks,
                        track_count, clip_length, clip_time))
    return 0.0;
  static double joint_matrices[64][16];
  for (int joint = 0; joint < joint_count; ++joint) {
    int node = joint_nodes[joint];
    if (node < 0 || node >= node_count) {
      for (int i = 0; i < 16; ++i)
        joint_matrices[joint][i] = i % 5 == 0 ? 1.0 : 0.0;
      continue;
    }
    anvil_mat_mul(anvil_model_world[node], bind + joint * 16,
                  joint_matrices[joint]);
  }
  anvil_mesh_drawn_frame++;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    const double *p = data + (size_t)triangle * 42;
    AnvilVec3 v[3];
    uint32_t base = anvil_color((int)p[3], (int)p[4], (int)p[5]);
    for (int corner = 0; corner < 3; ++corner) {
      const double *vertex = p + corner * 14;
      double px = 0.0, py = 0.0, pz = 0.0;
      double carried = 0.0;
      for (int k = 0; k < 4; ++k) {
        int joint = (int)vertex[6 + k];
        double weight = vertex[10 + k];
        if (weight <= 0.0 || joint < 0 || joint >= joint_count)
          continue;
        double point[3];
        anvil_mat_point(joint_matrices[joint], vertex[0], vertex[1], vertex[2],
                        point);
        px += point[0] * weight;
        py += point[1] * weight;
        pz += point[2] * weight;
        carried += weight;
      }
      if (carried <= 0.0) {
        px = vertex[0];
        py = vertex[1];
        pz = vertex[2];
      }
      AnvilVec3 q = {px * scale, py * scale, pz * scale};
      q = anvil_rotate(q, rx, ry, rz);
      v[corner] = (AnvilVec3){x + q.x, y + q.y, z + q.z};
    }
    AnvilVec3 n = anvil_normalize(
        anvil_cross(anvil_sub(v[1], v[0]), anvil_sub(v[2], v[0])));
    double brightness = anvil_light_level(n, 1);
    anvil_world_triangle(v, base, brightness, 255);
  }
  return 1.0;
}

/* ---- Morph targets ------------------------------------------------------ */

#define ANVIL_MORPH_TARGETS 8
static double anvil_morph_values[ANVIL_MODEL_STATES][ANVIL_MORPH_TARGETS];
static int anvil_morph_ready[ANVIL_MODEL_STATES];

/* Weights start at the mesh's default blend; the first draw initialises them
   and model_morph() edits them in place. */
const double *anvil_model_morph_weights(int id, const double *defaults,
                                        int count) {
  if (id < 0 || id >= ANVIL_MODEL_STATES)
    return defaults;
  if (!anvil_morph_ready[id]) {
    for (int i = 0; i < ANVIL_MORPH_TARGETS; ++i)
      anvil_morph_values[id][i] =
          (defaults && i < count) ? defaults[i] : 0.0;
    anvil_morph_ready[id] = 1;
  }
  return anvil_morph_values[id];
}

double anvil_model_morph(int id, int index, double weight,
                         const double *defaults, int count) {
  if (id < 0 || id >= ANVIL_MODEL_STATES || index < 0 ||
      index >= ANVIL_MORPH_TARGETS || !isfinite(weight))
    return 0.0;
  /* Initialise from the mesh defaults even when a program sets a weight
     before the first draw, so the untouched targets keep their rest blend. */
  anvil_model_morph_weights(id, defaults, count);
  double previous = anvil_morph_values[id][index];
  anvil_morph_values[id][index] =
      weight < 0.0 ? 0.0 : weight > 1.0 ? 1.0 : weight;
  return previous;
}

double anvil_mesh_draw_morphed(const double *data, int triangle_count,
                               const double *deltas, int targets,
                               const double *weights, double x, double y,
                               double z, double scale, double rx, double ry,
                               double rz) {
  if (!data || !deltas || !weights || triangle_count <= 0 || targets <= 0 ||
      targets > ANVIL_MORPH_TARGETS || !isfinite(x) || !isfinite(y) ||
      !isfinite(z) || !isfinite(scale) || !isfinite(rx) || !isfinite(ry) ||
      !isfinite(rz) || scale == 0.0)
    return 0.0;
  anvil_mesh_drawn_frame++;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    const double *p = data + (size_t)triangle * 12;
    AnvilVec3 v[3];
    for (int corner = 0; corner < 3; ++corner) {
      int vertex = triangle * 3 + corner;
      const double *base = p + corner * 3;
      const double *delta = deltas + (size_t)vertex * (size_t)targets * 3;
      double px = base[0], py = base[1], pz = base[2];
      for (int target = 0; target < targets; ++target) {
        double weight = weights[target];
        if (weight == 0.0)
          continue;
        const double *offset = delta + target * 3;
        px += offset[0] * weight;
        py += offset[1] * weight;
        pz += offset[2] * weight;
      }
      AnvilVec3 q = {px * scale, py * scale, pz * scale};
      q = anvil_rotate(q, rx, ry, rz);
      v[corner] = (AnvilVec3){x + q.x, y + q.y, z + q.z};
    }
    AnvilVec3 n = anvil_normalize(
        anvil_cross(anvil_sub(v[1], v[0]), anvil_sub(v[2], v[0])));
    double brightness = anvil_light_level(n, 1);
    uint32_t base = anvil_color((int)p[9], (int)p[10], (int)p[11]);
    anvil_world_triangle(v, base, brightness, 255);
  }
  return 1.0;
}

void anvil_sphere(double x, double y, double z, double radius, int r, int g,
                  int b, int a) {
  if (radius <= 0.0 || !isfinite(radius))
    return;
  if (!anvil_scene_is_3d) {
    AnvilProjected center;
    if (!anvil_project((AnvilVec3){x, y, z}, &center))
      return;
    const double screen_radius = radius * 64.0;
    int rr = (int)ceil(screen_radius);
    int cx = (int)lrint(center.x), cy = (int)lrint(center.y);
    uint32_t color = anvil_color(r, g, b);
    double radius_squared = screen_radius * screen_radius;
    for (int py = cy - rr; py <= cy + rr; ++py)
      for (int px = cx - rr; px <= cx + rr; ++px) {
        double dx = px - center.x, dy = py - center.y;
        if (dx * dx + dy * dy <= radius_squared)
          anvil_pixel(px, py, color, a);
      }
    return;
  }

  AnvilCameraVertex camera_center = anvil_to_camera((AnvilVec3){x, y, z});
  AnvilPixelBounds bounds;
  if (!anvil_project_sphere_bounds(
          camera_center.x, camera_center.y, camera_center.depth, radius,
          anvil_camera_focal, ANVIL_WIDTH, ANVIL_HEIGHT, &bounds))
    return;

  AnvilVec3 right, up, forward;
  anvil_camera_basis(&right, &up, &forward);
  AnvilVec3 world_light = anvil_normalize((AnvilVec3){-.4, .7, .6});
  AnvilCameraVertex light = {anvil_dot(world_light, right),
                             anvil_dot(world_light, up),
                             anvil_dot(world_light, forward)};
  const double ambient = 0.2;
  for (int py = bounds.min_y; py <= bounds.max_y; ++py)
    for (int px = bounds.min_x; px <= bounds.max_x; ++px) {
      double ray_x = (px + 0.5 - ANVIL_WIDTH * 0.5) / anvil_camera_focal;
      double ray_y = (ANVIL_HEIGHT * 0.54 - (py + 0.5)) / anvil_camera_focal;
      double depth, nx, ny, nz;
      int near_cap;
      if (!anvil_intersect_sphere_near(
              camera_center, radius, ray_x, ray_y, ANVIL_NEAR_DEPTH, &depth,
              &nx, &ny, &nz, &near_cap))
        continue;
      double shade = ambient +
                     (1.0 - ambient) *
                         fmax(0.0, nx * light.x + ny * light.y + nz * light.depth);
      if (near_cap)
        shade = ambient + (1.0 - ambient) * fmax(0.0, -light.depth);
      uint32_t color = anvil_color((int)(r * shade), (int)(g * shade),
                                   (int)(b * shade));
      size_t index = (size_t)py * ANVIL_WIDTH + (size_t)px;
      if (depth < anvil_depth_buffer[index]) {
        anvil_depth_buffer[index] = depth;
        anvil_pixel(px, py, color, a);
      }
    }
}

void anvil_plane(double x, double y, double z, double width, double depth,
                 int r, int g, int b, int a) {
  uint32_t base = anvil_color(r, g, b);
  for (int i = 0; i <= 10; ++i) {
    double t = (double)i / 10.0;
    AnvilProjected p0 = {0}, p1 = {0}, p2 = {0}, p3 = {0};
    AnvilVec3 a0 = {x - width * .5, y, z - depth * .5 + depth * t},
              a1 = {x + width * .5, y, z - depth * .5 + depth * t},
              a2 = {x - width * .5 + width * t, y, z - depth * .5},
              a3 = {x - width * .5 + width * t, y, z + depth * .5};
    int line0_visible = 0;
    if (anvil_scene_is_3d) {
      AnvilCameraVertex c0 = anvil_to_camera(a0), c1 = anvil_to_camera(a1);
      line0_visible = anvil_clip_segment_near(&c0, &c1, ANVIL_NEAR_DEPTH) &&
                      anvil_project_camera(c0, &p0) &&
                      anvil_project_camera(c1, &p1);
    } else {
      line0_visible = anvil_project(a0, &p0) && anvil_project(a1, &p1);
    }
    if (line0_visible)
      anvil_line(p0.x, p0.y, p1.x, p1.y, r, g, b, a, 1);
    int line1_visible = 0;
    if (anvil_scene_is_3d) {
      AnvilCameraVertex c2 = anvil_to_camera(a2), c3 = anvil_to_camera(a3);
      line1_visible = anvil_clip_segment_near(&c2, &c3, ANVIL_NEAR_DEPTH) &&
                      anvil_project_camera(c2, &p2) &&
                      anvil_project_camera(c3, &p3);
    } else {
      line1_visible = anvil_project(a2, &p2) && anvil_project(a3, &p3);
    }
    if (line1_visible)
      anvil_line(p2.x, p2.y, p3.x, p3.y, r, g, b, a, 1);
  }
  (void)base;
}

/* Glyphs scale with the 2D camera so world-space labels grow with zoom. 20 px
   is the original size, and the clamp keeps GDI inside sane limits. */
static int anvil_text_height(void) {
  int height = (int)lrint(20.0 * anvil_camera2d_zoom);
  if (height < 6)
    height = 6;
  if (height > 720)
    height = 720;
  return height;
}

static HFONT anvil_text_font(int height) {
  /* A wide font with DEFAULT_CHARSET lets GDI font-link a fallback face for
     scripts Segoe UI does not cover, so a CJK or Cyrillic line still draws
     instead of turning into boxes. */
  return CreateFontW(height, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
                     DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                     CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE,
                     L"Segoe UI");
}

/* Anvil strings are UTF-8; GDI's text API is UTF-16. Every draw and every
   measurement converts through this one buffer, and a malformed byte becomes
   U+FFFD instead of swallowing the rest of the line. */
enum { ANVIL_TEXT_WIDE_CAP = 1024 };
static wchar_t anvil_text_wide[ANVIL_TEXT_WIDE_CAP];

static const wchar_t *anvil_text_utf16(const char *text) {
  int out = 0;
  const unsigned char *p = (const unsigned char *)text;
  while (*p && out < ANVIL_TEXT_WIDE_CAP - 2) {
    unsigned int code = *p++;
    if (code < 0x80u) {
      anvil_text_wide[out++] = (wchar_t)code;
    } else if ((code & 0xE0u) == 0xC0u && (p[0] & 0xC0u) == 0x80u) {
      anvil_text_wide[out++] =
          (wchar_t)(((code & 0x1Fu) << 6) | (p[0] & 0x3Fu));
      p += 1;
    } else if ((code & 0xF0u) == 0xE0u && (p[0] & 0xC0u) == 0x80u &&
               (p[1] & 0xC0u) == 0x80u) {
      anvil_text_wide[out++] = (wchar_t)(((code & 0x0Fu) << 12) |
                                         ((p[0] & 0x3Fu) << 6) |
                                         (p[1] & 0x3Fu));
      p += 2;
    } else if ((code & 0xF8u) == 0xF0u && (p[0] & 0xC0u) == 0x80u &&
               (p[1] & 0xC0u) == 0x80u && (p[2] & 0xC0u) == 0x80u) {
      unsigned int point = ((code & 0x07u) << 18) | ((p[0] & 0x3Fu) << 12) |
                           ((p[1] & 0x3Fu) << 6) | (p[2] & 0x3Fu);
      p += 3;
      if (point >= 0x10000u && point <= 0x10FFFFu) {
        point -= 0x10000u;
        anvil_text_wide[out++] = (wchar_t)(0xD800u + (point >> 10));
        anvil_text_wide[out++] = (wchar_t)(0xDC00u + (point & 0x3FFu));
      } else {
        anvil_text_wide[out++] = (wchar_t)0xFFFD;
      }
    } else {
      anvil_text_wide[out++] = (wchar_t)0xFFFD;
    }
  }
  anvil_text_wide[out] = 0;
  return anvil_text_wide;
}

/* GDI has no alpha for text, so a run with a < 255 is rendered white on
   black into a scratch DIB and composited with the same per-pixel blend the
   other primitives use. The scratch read-back gives the glyph coverage,
   including the antialiased edge. */
static void anvil_text_wide_blend(double x, double y, const wchar_t *text,
                                  int r, int g, int b, int a) {
  int height = anvil_text_height();
  HFONT font = anvil_text_font(height);
  HGDIOBJ old = SelectObject(anvil_memory_dc, font);
  SIZE size = {0, 0};
  GetTextExtentPoint32W(anvil_memory_dc, text, (int)wcslen(text), &size);
  SelectObject(anvil_memory_dc, old);
  DeleteObject(font);
  int width = size.cx + 8;
  int tall = size.cy + 8;
  if (size.cx <= 0 || size.cy <= 0)
    return;
  BITMAPINFO info;
  memset(&info, 0, sizeof(info));
  info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
  info.bmiHeader.biWidth = width;
  info.bmiHeader.biHeight = -tall; /* top-down, matching the loop below */
  info.bmiHeader.biPlanes = 1;
  info.bmiHeader.biBitCount = 32;
  info.bmiHeader.biCompression = BI_RGB;
  void *bits = NULL;
  HDC scratch = CreateCompatibleDC(NULL);
  HBITMAP bitmap =
      scratch ? CreateDIBSection(scratch, &info, DIB_RGB_COLORS, &bits, NULL, 0)
              : NULL;
  if (!scratch || !bitmap || !bits) {
    if (bitmap)
      DeleteObject(bitmap);
    if (scratch)
      DeleteDC(scratch);
    return;
  }
  HGDIOBJ old_bitmap = SelectObject(scratch, bitmap);
  memset(bits, 0, (size_t)width * (size_t)tall * 4);
  SetBkMode(scratch, TRANSPARENT);
  SetTextColor(scratch, RGB(255, 255, 255));
  HFONT scratch_font = anvil_text_font(height);
  HGDIOBJ old_font = SelectObject(scratch, scratch_font);
  TextOutW(scratch, 4, 4, text, (int)wcslen(text));
  SelectObject(scratch, old_font);
  DeleteObject(scratch_font);
  int left = (int)floor(x) - 4;
  int top = (int)floor(y) - 4;
  const uint32_t *source = (const uint32_t *)bits;
  for (int row = 0; row < tall; ++row) {
    for (int column = 0; column < width; ++column) {
      uint32_t pixel = source[row * width + column];
      int cr = (int)((pixel >> 16) & 255u);
      int cg = (int)((pixel >> 8) & 255u);
      int cb = (int)(pixel & 255u);
      int coverage = cr > cg ? cr : cg;
      if (cb > coverage)
        coverage = cb;
      if (!coverage)
        continue;
      anvil_pixel(left + column, top + row, anvil_color(r, g, b),
                  coverage * a / 255);
    }
  }
  SelectObject(scratch, old_bitmap);
  DeleteObject(bitmap);
  DeleteDC(scratch);
}

static void anvil_text_wide_out(double x, double y, const wchar_t *text,
                                int r, int g, int b, int a) {
  anvil_camera2d_point(&x, &y);
  if (!(a >= 255)) {
    anvil_text_wide_blend(x, y, text, r, g, b, a < 0 ? 0 : a);
    return;
  }
  int height = anvil_text_height();
  SetBkMode(anvil_memory_dc, TRANSPARENT);
  SetTextColor(anvil_memory_dc, RGB(r, g, b));
  HFONT font = anvil_text_font(height);
  HGDIOBJ old = SelectObject(anvil_memory_dc, font);
  TextOutW(anvil_memory_dc, (int)x, (int)y, text, (int)wcslen(text));
  SelectObject(anvil_memory_dc, old);
  DeleteObject(font);
}

void anvil_text(double x, double y, const char *text, int r, int g, int b,
                int a) {
  if (!anvil_memory_dc || !text)
    return;
  anvil_text_wide_out(x, y, anvil_text_utf16(text), r, g, b, a);
}

double anvil_text_width(const char *text) {
  if (!anvil_memory_dc || !text)
    return 0.0;
  const wchar_t *wide = anvil_text_utf16(text);
  HFONT font = anvil_text_font(anvil_text_height());
  HGDIOBJ old = SelectObject(anvil_memory_dc, font);
  SIZE size = {0, 0};
  GetTextExtentPoint32W(anvil_memory_dc, wide, (int)wcslen(wide), &size);
  SelectObject(anvil_memory_dc, old);
  DeleteObject(font);
  return (double)size.cx;
}

/* Greedy word wrap: fill each line with as many whole words as fit inside
   max_width, measured with the same font the text is drawn with. A word wider
   than the whole limit is broken at the last character that fits, which is what
   lets CJK text (no spaces) and long tokens wrap instead of overflowing. */
void anvil_text_wrap(double x, double y, double max_width, const char *text,
                     int r, int g, int b, int a) {
  if (!anvil_memory_dc || !text)
    return;
  if (!(max_width > 0.0) || !isfinite(max_width)) {
    anvil_text(x, y, text, r, g, b, a);
    return;
  }
  int height = anvil_text_height();
  HFONT font = anvil_text_font(height);
  HGDIOBJ old = SelectObject(anvil_memory_dc, font);
  /* Convert once and split on UTF-16 code units, so a multi-byte character
     can never be cut in half at a line break. */
  const wchar_t *source = anvil_text_utf16(text);
  size_t length = wcslen(source);
  wchar_t line[ANVIL_TEXT_WIDE_CAP];
  size_t at = 0;
  double line_y = y;
  while (at < length) {
    size_t best = at;
    size_t scan = at;
    while (scan < length) {
      size_t word_end = scan;
      while (word_end < length && source[word_end] != L' ')
        ++word_end;
      size_t count = word_end - at;
      if (count >= ANVIL_TEXT_WIDE_CAP - 1)
        count = ANVIL_TEXT_WIDE_CAP - 1;
      memcpy(line, source + at, count * sizeof(wchar_t));
      line[count] = 0;
      SIZE size = {0, 0};
      GetTextExtentPoint32W(anvil_memory_dc, line, (int)count, &size);
      if ((double)size.cx > max_width) {
        if (best > at)
          break;
        /* The first word alone is wider than the limit. Break it at the last
           character that fits so a long token or a run of CJK text still wraps
           instead of running off the panel. */
        size_t fit = 0;
        for (size_t take = 1; take <= count; ++take) {
          SIZE part = {0, 0};
          GetTextExtentPoint32W(anvil_memory_dc, line, (int)take, &part);
          if ((double)part.cx > max_width)
            break;
          fit = take;
        }
        best = at + (fit ? fit : 1);
        break;
      }
      best = word_end;
      scan = word_end;
      while (scan < length && source[scan] == L' ')
        ++scan;
      if (scan >= length) {
        best = length;
        break;
      }
    }
    if (best <= at)
      best = length;
    size_t count = best - at;
    if (count >= ANVIL_TEXT_WIDE_CAP - 1)
      count = ANVIL_TEXT_WIDE_CAP - 1;
    memcpy(line, source + at, count * sizeof(wchar_t));
    line[count] = 0;
    size_t drawn = wcslen(line);
    while (drawn > 0 && line[drawn - 1] == L' ')
      line[--drawn] = 0;
    SelectObject(anvil_memory_dc, old);
    DeleteObject(font);
    anvil_text_wide_out(x, line_y, line, r, g, b, a);
    font = anvil_text_font(height);
    old = SelectObject(anvil_memory_dc, font);
    line_y += (double)height * 1.35;
    at = best;
    while (at < length && source[at] == L' ')
      ++at;
  }
  SelectObject(anvil_memory_dc, old);
  DeleteObject(font);
}
void anvil_text_number(double x, double y, const char *format, double value,
                       int r, int g, int b, int a) {
  char buffer[256];
  _snprintf_s(buffer, sizeof(buffer), _TRUNCATE, format, value);
  anvil_text(x, y, buffer, r, g, b, a);
}

double anvil_time(void) { return anvil_elapsed_seconds; }
double anvil_clock(void) { return (double)GetTickCount64(); }
double anvil_delta(void) { return anvil_delta_seconds; }

/* Phase timings for the last frame, in seconds. The main loop records how long
   the fixed-step update, the draw pass and the presentation each took, so a
   benchmark can report real per-frame work instead of the 60 Hz pacing. */
double anvil_frame_tick(void) { return anvil_frame_tick_seconds; }
double anvil_frame_render(void) { return anvil_frame_render_seconds; }
double anvil_frame_present(void) { return anvil_frame_present_seconds; }
double anvil_check_number(double value, const char *path, int line) {
  if (!isfinite(value)) {
    fprintf(stderr, "%s:%d: numeric overflow or non-finite result\n",
            path ? path : "<Anvil>", line);
    exit(2);
  }
  return value;
}
double anvil_divide(double numerator, double denominator, const char *path,
                    int line) {
  numerator = anvil_check_number(numerator, path, line);
  denominator = anvil_check_number(denominator, path, line);
  if (denominator == 0.0) {
    fprintf(stderr, "%s:%d: division by zero\n", path ? path : "<Anvil>", line);
    exit(2);
  }
  return anvil_check_number(numerator / denominator, path, line);
}
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
static int anvil_mouse_button_index(const char *button) {
  if (button && _stricmp(button, "left") == 0)
    return 0;
  if (button && _stricmp(button, "right") == 0)
    return 1;
  if (button && _stricmp(button, "middle") == 0)
    return 2;
  if (!anvil_mouse_invalid_button_warned) {
    fprintf(stderr,
            "Anvil: unknown mouse button '%s'; choose 'left', 'right', or 'middle'.\n",
            button ? button : "<null>");
    anvil_mouse_invalid_button_warned = 1;
  }
  return -1;
}
double anvil_mouse_pressed(const char *button) {
  int index = anvil_mouse_button_index(button);
  return index >= 0 ? anvil_mouse_pressed_buttons[index] != 0 : 0.0;
}
double anvil_mouse_held(const char *button) {
  int index = anvil_mouse_button_index(button);
  return index >= 0 ? anvil_mouse_buttons[index] != 0 : 0.0;
}
/* Map a client-area point into world coordinates. Separate from the pointer
   state because a press is hit-tested at the point it was made, even if the
   pointer has since left the window. */
static int anvil_client_to_world(int client_x, int client_y, double *out_x,
                                 double *out_y) {
  if (!anvil_window)
    return 0;
  RECT client;
  AnvilViewport viewport;
  if (!GetClientRect(anvil_window, &client) ||
      !anvil_compute_viewport(client.right - client.left,
                             client.bottom - client.top, ANVIL_WIDTH,
                             ANVIL_HEIGHT, &viewport))
    return 0;
  if (client_x < viewport.x || client_y < viewport.y ||
      client_x >= viewport.x + viewport.width ||
      client_y >= viewport.y + viewport.height)
    return 0;
  /* Inverse of the 2D camera so pointer coordinates are world coordinates. */
  *out_x = (double)(client_x - viewport.x) * ANVIL_WIDTH / viewport.width /
               anvil_camera2d_zoom +
           anvil_camera2d_x;
  *out_y = (double)(client_y - viewport.y) * ANVIL_HEIGHT / viewport.height /
               anvil_camera2d_zoom +
           anvil_camera2d_y;
  return 1;
}
static int anvil_mouse_world_point(double *out_x, double *out_y) {
  if (!anvil_window || !anvil_mouse_has_position)
    return 0;
  return anvil_client_to_world(anvil_mouse_client_x, anvil_mouse_client_y,
                               out_x, out_y);
}
static double anvil_mouse_coordinate(int horizontal) {
  double x = 0.0, y = 0.0;
  if (!anvil_mouse_world_point(&x, &y))
    return -1.0;
  return horizontal ? x : y;
}
double anvil_mouse_x(void) { return anvil_mouse_coordinate(1); }
double anvil_mouse_y(void) { return anvil_mouse_coordinate(0); }
double anvil_mouse_wheel(void) { return anvil_mouse_wheel_delta; }

/* ---- UI focus and accessible labels -------------------------------------
   A custom-drawn UI has no window controls for the OS to focus, so the engine
   keeps a small registry of focusable rectangles. The program draws whatever
   it likes and declares where a control is plus the label a screen reader
   should read; the engine owns the part that is easy to get wrong - which
   region is focused, what a click or Enter/Space activates, and announcing the
   label when accessibility is switched on. */

enum { ANVIL_FOCUS_REGIONS = 64, ANVIL_FOCUS_LABEL_MAX = 96 };

typedef struct {
  int used;
  double x, y, width, height;
  char label[ANVIL_FOCUS_LABEL_MAX];
} AnvilFocusRegion;

static AnvilFocusRegion anvil_focus_regions[ANVIL_FOCUS_REGIONS];
static int anvil_focus_count;
static int anvil_focus_current;   /* region index + 1, 0 = nothing focused */
static int anvil_focus_activated; /* region index + 1 activated this frame */
static int anvil_focus_accessible;
static int anvil_focus_announced;
static HWND anvil_focus_announcer;
static int anvil_focus_full_warned;
static int anvil_focus_label_warned;

static AnvilFocusRegion *anvil_focus_region(double handle) {
  if (!isfinite(handle) || handle < 1.0 ||
      handle > (double)ANVIL_FOCUS_REGIONS || floor(handle) != handle)
    return NULL;
  AnvilFocusRegion *region = &anvil_focus_regions[(int)handle - 1];
  return region->used ? region : NULL;
}

double anvil_ui_focus_add(double x, double y, double width, double height,
                          const char *label) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(width) || !isfinite(height))
    return 0.0;
  /* A negative size is a rectangle drawn upwards or leftwards; normalise it so
     hit testing only ever compares against a positive extent. */
  if (width < 0.0) {
    x += width;
    width = -width;
  }
  if (height < 0.0) {
    y += height;
    height = -height;
  }
  const char *text = label ? label : "";
  size_t length = strlen(text);
  if (length >= ANVIL_FOCUS_LABEL_MAX) {
    /* Truncating would announce a different control than the one drawn. */
    if (!anvil_focus_label_warned) {
      anvil_focus_label_warned = 1;
      fprintf(stderr,
              "Anvil UI focus: a label is longer than %d bytes and was not "
              "registered.\n",
              ANVIL_FOCUS_LABEL_MAX - 1);
    }
    return 0.0;
  }
  for (int index = 0; index < ANVIL_FOCUS_REGIONS; index++) {
    AnvilFocusRegion *region = &anvil_focus_regions[index];
    if (region->used)
      continue;
    region->used = 1;
    region->x = x;
    region->y = y;
    region->width = width;
    region->height = height;
    memcpy(region->label, text, length + 1);
    anvil_focus_count++;
    return (double)(index + 1);
  }
  if (!anvil_focus_full_warned) {
    anvil_focus_full_warned = 1;
    fprintf(stderr,
            "Anvil UI focus: %d regions are already registered; the extra "
            "region was ignored.\n",
            ANVIL_FOCUS_REGIONS);
  }
  return 0.0;
}

double anvil_ui_focus_clear(void) {
  double removed = (double)anvil_focus_count;
  memset(anvil_focus_regions, 0, sizeof(anvil_focus_regions));
  anvil_focus_count = 0;
  anvil_focus_current = 0;
  anvil_focus_activated = 0;
  anvil_focus_announced = 0;
  return removed;
}

double anvil_ui_focus_count(void) { return (double)anvil_focus_count; }

double anvil_ui_focus(void) {
  return anvil_focus_region((double)anvil_focus_current) != NULL
             ? (double)anvil_focus_current
             : 0.0;
}

double anvil_ui_focus_next(void) {
  if (!anvil_focus_count)
    return 0.0;
  int start = anvil_focus_current - 1;
  for (int step = 1; step <= ANVIL_FOCUS_REGIONS; step++) {
    int index = (start + step + ANVIL_FOCUS_REGIONS) % ANVIL_FOCUS_REGIONS;
    if (anvil_focus_regions[index].used) {
      anvil_focus_current = index + 1;
      return (double)anvil_focus_current;
    }
  }
  return 0.0;
}

double anvil_ui_focus_prev(void) {
  if (!anvil_focus_count)
    return 0.0;
  int start = anvil_focus_current ? anvil_focus_current - 1
                                  : ANVIL_FOCUS_REGIONS;
  for (int step = 1; step <= ANVIL_FOCUS_REGIONS; step++) {
    int index = (start - step + ANVIL_FOCUS_REGIONS) % ANVIL_FOCUS_REGIONS;
    if (anvil_focus_regions[index].used) {
      anvil_focus_current = index + 1;
      return (double)anvil_focus_current;
    }
  }
  return 0.0;
}

/* Returns the handle that was focused before the call. An unknown handle or 0
   leaves the focus where it was. */
double anvil_ui_focus_set(double handle) {
  double previous = anvil_ui_focus();
  if (handle == 0.0) {
    anvil_focus_current = 0;
    return previous;
  }
  if (!anvil_focus_region(handle))
    return previous;
  anvil_focus_current = (int)handle;
  return previous;
}

/* Topmost region under a point: the last one registered wins, so a later
   popup covers an earlier panel. */
double anvil_ui_focus_at(double x, double y) {
  if (!isfinite(x) || !isfinite(y))
    return 0.0;
  for (int index = ANVIL_FOCUS_REGIONS - 1; index >= 0; index--) {
    const AnvilFocusRegion *region = &anvil_focus_regions[index];
    if (!region->used)
      continue;
    if (x >= region->x && x < region->x + region->width && y >= region->y &&
        y < region->y + region->height)
      return (double)(index + 1);
  }
  return 0.0;
}

double anvil_ui_focus_activate(void) { return (double)anvil_focus_activated; }

const char *anvil_ui_focus_label(void) {
  const AnvilFocusRegion *region =
      anvil_focus_region((double)anvil_focus_current);
  return region ? region->label : "";
}

/* Announce the focused label through MSAA: a 1x1 static child just outside the
   client area carries the text as its accessible name, and the focus event
   tells a screen reader to read it. Verified by reading the child's text, not
   against a live screen reader. */
static void anvil_focus_announce(const char *label) {
  if (!anvil_window || !label)
    return;
  if (!anvil_focus_announcer) {
    anvil_focus_announcer =
        CreateWindowExW(0, L"STATIC", L"", WS_CHILD, -4, -4, 1, 1, anvil_window,
                        NULL, GetModuleHandleW(NULL), NULL);
  }
  if (!anvil_focus_announcer)
    return;
  SetWindowTextW(anvil_focus_announcer, anvil_text_utf16(label));
  NotifyWinEvent(EVENT_OBJECT_FOCUS, anvil_focus_announcer, OBJID_CLIENT,
                 CHILDID_SELF);
}

/* ui_accessible(1) switches announcements on and returns 1 when the channel is
   available; 0 switches them off and returns 0. */
double anvil_ui_accessible(double on) {
  if (on == 0.0) {
    anvil_focus_accessible = 0;
    anvil_focus_announced = 0;
    return 0.0;
  }
  anvil_focus_accessible = 1;
  anvil_focus_announced = 0; /* the current region is announced again */
  return 1.0;
}

/* Once per frame, before update(): a click focuses the topmost region under the
   pointer and activates it, Enter/Space activates the focused region, and a
   changed focus announces its label. */
static void anvil_focus_frame(void) {
  anvil_focus_activated = 0;
  if (!anvil_focus_count) {
    anvil_focus_current = 0;
    return;
  }
  double mouse_x = 0.0, mouse_y = 0.0;
  /* Hit-test the press point itself: a click can be delivered after the
     pointer left the window, and the click still belongs where it landed. */
  if (anvil_mouse_pressed_buttons[0] &&
      anvil_client_to_world(anvil_mouse_client_x, anvil_mouse_client_y,
                            &mouse_x, &mouse_y)) {
    double hit = anvil_ui_focus_at(mouse_x, mouse_y);
    if (hit != 0.0) {
      anvil_focus_current = (int)hit;
      anvil_focus_activated = (int)hit;
    }
  }
  if (!anvil_focus_activated && anvil_focus_current &&
      (anvil_pressed_keys[VK_RETURN] || anvil_pressed_keys[VK_SPACE]))
    anvil_focus_activated = anvil_focus_current;
  if (anvil_focus_accessible && anvil_focus_current != anvil_focus_announced) {
    anvil_focus_announced = anvil_focus_current;
    const AnvilFocusRegion *region =
        anvil_focus_region((double)anvil_focus_current);
    if (region)
      anvil_focus_announce(region->label);
  }
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
static const char *anvil_image_error_text = "";
static char anvil_image_error_detail[192];

static void anvil_image_error_note(const char *format, ...) {
  va_list arguments;
  va_start(arguments, format);
  _vsnprintf_s(anvil_image_error_detail, sizeof(anvil_image_error_detail),
               _TRUNCATE, format, arguments);
  va_end(arguments);
  anvil_image_error_text = anvil_image_error_detail;
}

const char *anvil_image_error(void) { return anvil_image_error_text; }

double anvil_image_load(const char *path) {
  anvil_image_error_text = "";
  if (!path || !*path) {
    anvil_image_error_text = "the path is empty";
    return 0.0;
  }
  int slot = -1;
  for (int i = 0; i < ANVIL_IMAGES; ++i) {
    if (!anvil_images[i].pixels &&
        anvil_images[i].generation < UINT32_MAX) {
      slot = i;
      break;
    }
  }
  if (slot < 0) {
    anvil_image_error_text = "no free image slot";
    return 0.0;
  }

  FILE *file = fopen(path, "rb");
  if (!file) {
    anvil_image_error_text = "cannot open the file";
    return 0.0;
  }
  unsigned char header[54] = {0};
  if (fread(header, 1, sizeof(header), file) != sizeof(header) ||
      header[0] != 'B' || header[1] != 'M') {
    fclose(file);
    anvil_image_error_text = "the file is not a readable 24- or 32-bit BMP";
    return 0.0;
  }
  int64_t file_size = -1;
  if (_fseeki64(file, 0, SEEK_END) == 0)
    file_size = _ftelli64(file);
  int64_t pixel_offset = (int64_t)anvil_read_u32_le(header + 10);
  uint32_t dib_size = anvil_read_u32_le(header + 14);
  int32_t width = (int32_t)anvil_read_u32_le(header + 18);
  int32_t signed_height = (int32_t)anvil_read_u32_le(header + 22);
  uint16_t planes = anvil_read_u16_le(header + 26);
  uint16_t bits_per_pixel = anvil_read_u16_le(header + 28);
  uint32_t compression = anvil_read_u32_le(header + 30);
  if (dib_size < 40 || pixel_offset < 14 + (int64_t)dib_size || width <= 0 ||
      signed_height == 0 || signed_height == INT32_MIN || planes != 1 ||
      (bits_per_pixel != 4 && bits_per_pixel != 8 &&
       bits_per_pixel != 24 && bits_per_pixel != 32) ||
      compression != BI_RGB) {
    fclose(file);
    anvil_image_error_text =
        "the file is not a readable 4-, 8-, 24- or 32-bit BMP";
    return 0.0;
  }
  int height = signed_height < 0 ? -signed_height : signed_height;
  if (width > ANVIL_IMAGE_MAX_DIMENSION) {
    fclose(file);
    anvil_image_error_note("the image is %d pixels wide; the limit is %d",
                           (int)width, (int)ANVIL_IMAGE_MAX_DIMENSION);
    return 0.0;
  }
  if (height > ANVIL_IMAGE_MAX_DIMENSION) {
    fclose(file);
    anvil_image_error_note("the image is %d pixels tall; the limit is %d",
                           height, (int)ANVIL_IMAGE_MAX_DIMENSION);
    return 0.0;
  }
  uint64_t pixel_count =
      (uint64_t)(unsigned int)width * (uint64_t)(unsigned int)height;
  uint64_t output_bytes = pixel_count * sizeof(uint32_t);
  if (pixel_count == 0 || pixel_count > 16u * 1024u * 1024u) {
    fclose(file);
    anvil_image_error_note("the image has %llu pixels; the limit is %d",
                           (unsigned long long)pixel_count, 16 * 1024 * 1024);
    return 0.0;
  }
  if (output_bytes > ANVIL_IMAGE_MEMORY_LIMIT - anvil_image_memory_used) {
    fclose(file);
    anvil_image_error_note(
        "the image needs %llu MiB; only %llu MiB of the 128 MiB image budget "
        "remain",
        (unsigned long long)((output_bytes + 1048575u) / 1048576u),
        (unsigned long long)((ANVIL_IMAGE_MEMORY_LIMIT -
                              anvil_image_memory_used) /
                             1048576u));
    return 0.0;
  }
  unsigned char palette_r[256] = {0};
  unsigned char palette_g[256] = {0};
  unsigned char palette_b[256] = {0};
  int palette_colors = 0;
  if (bits_per_pixel == 4 || bits_per_pixel == 8) {
    palette_colors = (int)anvil_read_u32_le(header + 46);
    if (palette_colors == 0)
      palette_colors = 1 << bits_per_pixel;
    if (palette_colors > (1 << bits_per_pixel))
      palette_colors = 1 << bits_per_pixel;
    int64_t palette_offset = 14 + (int64_t)dib_size;
    if (palette_offset + (int64_t)palette_colors * 4 > pixel_offset) {
      fclose(file);
      anvil_image_error_text = "the BMP palette runs past the pixel data";
      return 0.0;
    }
    if (_fseeki64(file, palette_offset, SEEK_SET) != 0) {
      fclose(file);
      anvil_image_error_text = "the BMP palette could not be read";
      return 0.0;
    }
    for (int i = 0; i < palette_colors; ++i) {
      unsigned char entry[4];
      if (fread(entry, 1, 4, file) != 4) {
        fclose(file);
        anvil_image_error_text = "the BMP palette ended early";
        return 0.0;
      }
      palette_b[i] = entry[0];
      palette_g[i] = entry[1];
      palette_r[i] = entry[2];
    }
  }
  uint64_t row_bytes =
      ((uint64_t)(unsigned int)width * (uint64_t)bits_per_pixel + 7u) / 8u;
  uint64_t row_stride = (row_bytes + 3u) & ~UINT64_C(3);
  if (pixel_offset + (int64_t)(row_stride * (uint64_t)(unsigned int)height) >
      file_size) {
    fclose(file);
    anvil_image_error_text = "the file is too short for the declared image size";
    return 0.0;
  }

  uint32_t *pixels = (uint32_t *)malloc((size_t)output_bytes);
  unsigned char *row = (unsigned char *)malloc((size_t)row_stride);
  if (!pixels || !row) {
    free(pixels);
    free(row);
    fclose(file);
    anvil_image_error_text = "the image could not be allocated";
    return 0.0;
  }
  int ok = 1;
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
      uint32_t output;
      if (bits_per_pixel == 4) {
        unsigned int packed = row[(size_t)x / 2];
        unsigned int index = (x & 1) ? (packed & 0x0fu) : (packed >> 4);
        if ((int)index >= palette_colors)
          index = 0;
        output = UINT32_C(0xff000000) | ((uint32_t)palette_r[index] << 16) |
                 ((uint32_t)palette_g[index] << 8) | (uint32_t)palette_b[index];
      } else if (bits_per_pixel == 8) {
        unsigned int index = row[(size_t)x];
        if ((int)index >= palette_colors)
          index = 0;
        output = UINT32_C(0xff000000) | ((uint32_t)palette_r[index] << 16) |
                 ((uint32_t)palette_g[index] << 8) | (uint32_t)palette_b[index];
      } else {
        const unsigned char *source = row + (size_t)x * (bits_per_pixel / 8);
        unsigned int alpha = bits_per_pixel == 32 ? source[3] : 255u;
        any_alpha |= alpha != 0;
        output = ((uint32_t)alpha << 24) | ((uint32_t)source[2] << 16) |
                 ((uint32_t)source[1] << 8) | (uint32_t)source[0];
      }
      pixels[(size_t)target_y * (size_t)width + (size_t)x] = output;
    }
  }
  free(row);
  fclose(file);
  if (!ok) {
    free(pixels);
    anvil_image_error_text = "the file ended before the image data did";
    return 0.0;
  }
  if (bits_per_pixel == 32 && !any_alpha) {
    for (uint64_t i = 0; i < pixel_count; ++i)
      pixels[i] |= UINT32_C(0xff000000);
  }
  anvil_images[slot].pixels = pixels;
  anvil_images[slot].width = width;
  anvil_images[slot].height = height;
  anvil_images[slot].tint_r = 255;
  anvil_images[slot].tint_g = 255;
  anvil_images[slot].tint_b = 255;
  anvil_images[slot].flip_x = 0;
  anvil_images[slot].flip_y = 0;
  ++anvil_images[slot].generation;
  anvil_image_memory_used += (size_t)output_bytes;
  return (double)(anvil_images[slot].generation - 1) * ANVIL_IMAGES + slot + 1;
}
double anvil_image_load_site(const char *path, const char *file, int line) {
  double handle = anvil_image_load(path);
  if (handle >= 1.0) {
    int slot = ((int)handle - 1) % ANVIL_IMAGES;
    anvil_image_sites[slot].file = file;
    anvil_image_sites[slot].path = path;
    anvil_image_sites[slot].line = line;
    anvil_capture_site(&anvil_image_sites[slot]);
  }
  return handle;
}

double anvil_memory_images(void) { return (double)anvil_image_memory_used; }
double anvil_memory_audio(void) { return (double)anvil_sound_bytes; }
double anvil_memory_video(void) {
  return (double)ANVIL_WIDTH * (double)ANVIL_HEIGHT * 4.0;
}
double anvil_memory_total(void) {
  return anvil_memory_images() + anvil_memory_audio() + anvil_memory_video();
}
/* Snapshot the frame that was just drawn into a new image, so it can be
   drawn again as a sprite: portals, reflections, thumbnails and a cheap
   render-to-texture path on the software renderer. */
double anvil_frame_capture(void) {
  if (!anvil_pixels)
    return 0.0;
  size_t bytes = (size_t)ANVIL_WIDTH * (size_t)ANVIL_HEIGHT * sizeof(uint32_t);
  if (bytes > ANVIL_IMAGE_MEMORY_LIMIT - anvil_image_memory_used) {
    anvil_image_error_note(
        "the capture needs %llu MiB; only %llu MiB of the 128 MiB image budget "
        "remain",
        (unsigned long long)(bytes / 1048576u),
        (unsigned long long)((ANVIL_IMAGE_MEMORY_LIMIT -
                              anvil_image_memory_used) /
                             1048576u));
    return 0.0;
  }
  int slot = -1;
  for (int i = 0; i < ANVIL_IMAGES; ++i) {
    if (!anvil_images[i].pixels && anvil_images[i].generation < UINT32_MAX) {
      slot = i;
      break;
    }
  }
  if (slot < 0) {
    anvil_image_error_text = "no free image slot";
    return 0.0;
  }
  uint32_t *pixels = (uint32_t *)malloc(bytes);
  if (!pixels) {
    anvil_image_error_text = "the capture could not be allocated";
    return 0.0;
  }
  memcpy(pixels, anvil_pixels, bytes);
  /* The framebuffer stores 0x00RRGGBB, so a captured image would be fully
     transparent; mark every texel opaque before it becomes a drawable image. */
  for (size_t i = 0; i < (size_t)ANVIL_WIDTH * (size_t)ANVIL_HEIGHT; ++i)
    pixels[i] |= UINT32_C(0xff000000);
  anvil_images[slot].pixels = pixels;
  anvil_images[slot].width = ANVIL_WIDTH;
  anvil_images[slot].height = ANVIL_HEIGHT;
  anvil_images[slot].tint_r = 255;
  anvil_images[slot].tint_g = 255;
  anvil_images[slot].tint_b = 255;
  anvil_images[slot].flip_x = 0;
  anvil_images[slot].flip_y = 0;
  ++anvil_images[slot].generation;
  anvil_image_memory_used += bytes;
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
double anvil_image_pixel(double handle, double x, double y) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image || !image->pixels)
    return 0.0;
  if (!(x >= 0.0) || !(y >= 0.0) || x >= (double)image->width ||
      y >= (double)image->height)
    return 0.0;
  return (double)image->pixels[(size_t)y * (size_t)image->width + (size_t)x];
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
  image->tint_r = 255;
  image->tint_g = 255;
  image->tint_b = 255;
  image->flip_x = 0;
  image->flip_y = 0;
  return 1.0;
}

static uint32_t anvil_image_shaded(const AnvilImage *image, uint32_t color) {
  int alpha = (int)(color >> 24);
  int r = (int)((color >> 16) & 255) * image->tint_r / 255;
  int g = (int)((color >> 8) & 255) * image->tint_g / 255;
  int b = (int)(color & 255) * image->tint_b / 255;
  return ((uint32_t)alpha << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) |
         (uint32_t)b;
}

double anvil_image_tint(double handle, double r, double g, double b) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image || !isfinite(r) || !isfinite(g) || !isfinite(b))
    return 0.0;
  image->tint_r = (int)(r < 0.0 ? 0.0 : r > 255.0 ? 255.0 : r);
  image->tint_g = (int)(g < 0.0 ? 0.0 : g > 255.0 ? 255.0 : g);
  image->tint_b = (int)(b < 0.0 ? 0.0 : b > 255.0 ? 255.0 : b);
  return 1.0;
}

double anvil_image_flip(double handle, double x, double y) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image || !isfinite(x) || !isfinite(y))
    return 0.0;
  image->flip_x = x != 0.0;
  image->flip_y = y != 0.0;
  return 1.0;
}
/* ---- Sprite queue ------------------------------------------------------
   sprite_batch(1) defers image draws to the end of the frame so they can be
   ordered by sprite_depth() instead of submission order — the y-sorting every
   2D game ends up writing by hand. With batching off (the default) draws go
   straight to the framebuffer, so existing programs are unchanged. */
enum { ANVIL_SPRITE_QUEUE = 4096 };

typedef struct {
  double args[9];
  double depth;
  int kind;
} AnvilSpriteDraw;

static double anvil_image_draw_scaled_now(double handle, double x, double y,
                                          double width, double height);
static double anvil_image_draw_rotated_now(double handle, double cx, double cy,
                                           double angle, double scale);
static double anvil_image_draw_region_now(double handle, double sx, double sy,
                                          double sw, double sh, double dx,
                                          double dy, double dw, double dh);
static void anvil_sprite_flush(void);

static AnvilSpriteDraw anvil_sprite_queue[ANVIL_SPRITE_QUEUE];
static int anvil_sprite_count;
static int anvil_sprite_batch_on;
static double anvil_sprite_depth_value;
static int anvil_sprite_flushed_last_frame;

double anvil_sprite_batch(double on) {
  int previous = anvil_sprite_batch_on;
  anvil_sprite_batch_on = on != 0.0;
  if (!anvil_sprite_batch_on)
    anvil_sprite_flush();
  return (double)previous;
}

double anvil_sprite_depth(double depth) {
  double previous = anvil_sprite_depth_value;
  if (isfinite(depth))
    anvil_sprite_depth_value = depth;
  return previous;
}

double anvil_sprite_queued(void) { return (double)anvil_sprite_flushed_last_frame; }

static int anvil_sprite_push(int kind, const double *args) {
  if (anvil_sprite_count >= ANVIL_SPRITE_QUEUE)
    return 0;
  AnvilSpriteDraw *entry = &anvil_sprite_queue[anvil_sprite_count++];
  for (int i = 0; i < 9; ++i)
    entry->args[i] = args[i];
  entry->depth = anvil_sprite_depth_value;
  entry->kind = kind;
  return 1;
}

static void anvil_sprite_flush(void) {
  int count = anvil_sprite_count;
  anvil_sprite_count = 0;
  anvil_sprite_flushed_last_frame = count;
  if (count == 0)
    return;
  /* Stable insertion sort: equal depths keep submission order. */
  for (int i = 1; i < count; ++i) {
    AnvilSpriteDraw entry = anvil_sprite_queue[i];
    int j = i - 1;
    while (j >= 0 && anvil_sprite_queue[j].depth > entry.depth) {
      anvil_sprite_queue[j + 1] = anvil_sprite_queue[j];
      --j;
    }
    anvil_sprite_queue[j + 1] = entry;
  }
  for (int i = 0; i < count; ++i) {
    AnvilSpriteDraw *entry = &anvil_sprite_queue[i];
    const double *a = entry->args;
    if (entry->kind == 0)
      anvil_image_draw_scaled_now(a[0], a[1], a[2], a[3], a[4]);
    else if (entry->kind == 1)
      anvil_image_draw_rotated_now(a[0], a[1], a[2], a[3], a[4]);
    else
      anvil_image_draw_region_now(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7],
                                  a[8]);
  }
}

static double anvil_sprite_dispatch(int kind, const double *args) {
  if (anvil_sprite_batch_on && anvil_sprite_push(kind, args))
    return 1.0;
  return 0.0;
}

double anvil_image_draw_scaled_now(double handle, double x, double y, double width,
                               double height) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image || !anvil_pixels || !isfinite(x) || !isfinite(y) ||
      !isfinite(width) || !isfinite(height) || width <= 0.0 || height <= 0.0 ||
      !isfinite(x + width) || !isfinite(y + height))
    return 0.0;
  anvil_camera2d_point(&x, &y);
  width *= anvil_camera2d_zoom;
  height *= anvil_camera2d_zoom;
  double left = fmax(0.0, floor(x));
  double top = fmax(0.0, floor(y));
  double right = fmin((double)ANVIL_WIDTH, ceil(x + width));
  double bottom = fmin((double)ANVIL_HEIGHT, ceil(y + height));
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
      int sample_x = image->flip_x ? image->width - 1 - source_x : source_x;
      int sample_y = image->flip_y ? image->height - 1 - source_y : source_y;
      uint32_t color =
          image->pixels[(size_t)sample_y * image->width + sample_x];
      anvil_pixel(dx, dy, anvil_image_shaded(image, color) & UINT32_C(0x00ffffff),
                  (int)(color >> 24));
    }
  }
  return 1.0;
}

/* Draw an image centred on (cx, cy), rotated clockwise by degrees and scaled
   uniformly. Nearest-neighbour sampling matches the scaled draw; tint and flip
   are the image's own state, so both draw paths share them. */
static double anvil_image_draw_rotated_now(double handle, double cx, double cy,
                                double degrees, double scale) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image || !anvil_pixels || !isfinite(cx) || !isfinite(cy) ||
      !isfinite(degrees) || !isfinite(scale) || scale <= 0.0)
    return 0.0;
  anvil_camera2d_point(&cx, &cy);
  scale *= anvil_camera2d_zoom;
  const double radians = 0.017453292519943295769 * degrees;
  double cos_angle = cos(radians);
  double sin_angle = sin(radians);
  double half_width = (double)image->width * scale * 0.5;
  double half_height = (double)image->height * scale * 0.5;
  double extent =
      ceil(sqrt(half_width * half_width + half_height * half_height)) + 1.0;
  int x0 = (int)fmax(0.0, floor(cx - extent));
  int x1 = (int)fmin((double)ANVIL_WIDTH, ceil(cx + extent));
  int y0 = (int)fmax(0.0, floor(cy - extent));
  int y1 = (int)fmin((double)ANVIL_HEIGHT, ceil(cy + extent));
  if (x0 >= x1 || y0 >= y1)
    return 1.0;
  for (int dy = y0; dy < y1; ++dy) {
    for (int dx = x0; dx < x1; ++dx) {
      double px = dx + 0.5 - cx;
      double py = dy + 0.5 - cy;
      double sx = px * cos_angle + py * sin_angle;
      double sy = -px * sin_angle + py * cos_angle;
      double u = sx / scale + (double)image->width * 0.5;
      double v = sy / scale + (double)image->height * 0.5;
      if (u < 0.0 || v < 0.0 || u >= (double)image->width ||
          v >= (double)image->height)
        continue;
      int source_x = (int)u;
      int source_y = (int)v;
      if (image->flip_x)
        source_x = image->width - 1 - source_x;
      if (image->flip_y)
        source_y = image->height - 1 - source_y;
      uint32_t color =
          image->pixels[(size_t)source_y * image->width + source_x];
      anvil_pixel(dx, dy, anvil_image_shaded(image, color) & UINT32_C(0x00ffffff),
                  (int)(color >> 24));
    }
  }
  return 1.0;
}
/* Draw a sub-rectangle of an image (an atlas cell) into a destination
   rectangle. The source rect must lie fully inside the image; a rect that does
   not is a layout bug, so it returns 0 instead of silently clamping. Flip and
   tint are the image's state, with flip mirrored inside the source rect. */
static double anvil_image_draw_region_now(double handle, double sx, double sy, double sw,
                               double sh, double dx, double dy, double dw,
                               double dh) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image || !anvil_pixels || !isfinite(sx) || !isfinite(sy) ||
      !isfinite(sw) || !isfinite(sh) || !isfinite(dx) || !isfinite(dy) ||
      !isfinite(dw) || !isfinite(dh) || sw <= 0.0 || sh <= 0.0 || dw <= 0.0 ||
      dh <= 0.0)
    return 0.0;
  if (sx < 0.0 || sy < 0.0 || sx + sw > (double)image->width ||
      sy + sh > (double)image->height || !isfinite(sx + sw) ||
      !isfinite(sy + sh))
    return 0.0;
  int isx = (int)sx, isy = (int)sy, isw = (int)sw, ish = (int)sh;
  anvil_camera2d_point(&dx, &dy);
  dw *= anvil_camera2d_zoom;
  dh *= anvil_camera2d_zoom;
  double left = fmax(0.0, floor(dx));
  double top = fmax(0.0, floor(dy));
  double right = fmin((double)ANVIL_WIDTH, ceil(dx + dw));
  double bottom = fmin((double)ANVIL_HEIGHT, ceil(dy + dh));
  if (left >= right || top >= bottom)
    return 1.0;
  int x0 = (int)left, y0 = (int)top, x1 = (int)right, y1 = (int)bottom;
  for (int py = y0; py < y1; ++py) {
    int v = isy + (int)(((py + 0.5 - dy) / dh) * sh);
    if (v < isy)
      v = isy;
    if (v >= isy + ish)
      v = isy + ish - 1;
    for (int px = x0; px < x1; ++px) {
      int u = isx + (int)(((px + 0.5 - dx) / dw) * sw);
      if (u < isx)
        u = isx;
      if (u >= isx + isw)
        u = isx + isw - 1;
      int sample_x = image->flip_x ? isx + (isw - 1 - (u - isx)) : u;
      int sample_y = image->flip_y ? isy + (ish - 1 - (v - isy)) : v;
      uint32_t color =
          image->pixels[(size_t)sample_y * image->width + sample_x];
      anvil_pixel(px, py, anvil_image_shaded(image, color) & UINT32_C(0x00ffffff),
                  (int)(color >> 24));
    }
  }
  return 1.0;
}


double anvil_image_draw_scaled(double handle, double x, double y, double width,
                               double height) {
  if (!anvil_image_from_handle(handle))
    return 0.0;
  const double args[9] = {handle, x, y, width, height, 0, 0, 0, 0};
  if (anvil_sprite_dispatch(0, args))
    return 1.0;
  return anvil_image_draw_scaled_now(handle, x, y, width, height);
}

double anvil_image_draw_rotated(double handle, double cx, double cy, double angle,
                                double scale) {
  if (!anvil_image_from_handle(handle))
    return 0.0;
  const double args[9] = {handle, cx, cy, angle, scale, 0, 0, 0, 0};
  if (anvil_sprite_dispatch(1, args))
    return 1.0;
  return anvil_image_draw_rotated_now(handle, cx, cy, angle, scale);
}


/* ---- Tilemaps ------------------------------------------------------------
   A tilemap is a grid of cells, each naming a tile in an image sheet. Tile t
   sits at (t % tiles_per_row, t / tiles_per_row) in the sheet, so a 4x4
   tileset is addressed left to right, top to bottom. Tile -1 is empty, which
   lets a cell be cleared without borrowing a real tile. Cells are allocated
   per map, so an unused slot costs nothing. */
enum {
  ANVIL_TILEMAPS = 16,
  ANVIL_TILEMAP_MAX = 512,
  ANVIL_TILEMAP_EMPTY = -1
};

typedef struct {
  int used;
  uint32_t generation;
  double image_handle;
  int tile_w, tile_h;
  int columns, rows;
  int tiles;
  int tiles_per_row;
  int *cells;
  unsigned char *solid; /* bitset of solid tile indices, allocated on demand */
  unsigned short *anim_frames; /* per-tile frame count, 0 = not animated */
  float *anim_fps;
} AnvilTilemap;

static AnvilTilemap anvil_tilemaps[ANVIL_TILEMAPS];
static const char *anvil_tilemap_error_text = "";

const char *anvil_tilemap_error(void) { return anvil_tilemap_error_text; }

static AnvilTilemap *anvil_tilemap_from_handle(double handle) {
  const uint64_t max_handle = (uint64_t)UINT32_MAX * ANVIL_TILEMAPS;
  if (!isfinite(handle) || handle < 1.0 || handle > (double)max_handle ||
      floor(handle) != handle)
    return NULL;
  uint64_t encoded = (uint64_t)handle - 1;
  int slot = (int)(encoded % ANVIL_TILEMAPS);
  uint32_t generation = (uint32_t)(encoded / ANVIL_TILEMAPS) + 1;
  AnvilTilemap *map = &anvil_tilemaps[slot];
  return map->used && map->generation == generation ? map : NULL;
}

static int anvil_tilemap_cell_ok(const AnvilTilemap *map, double column,
                                 double row) {
  if (!isfinite(column) || !isfinite(row) || floor(column) != column ||
      floor(row) != row || column < 0.0 || row < 0.0 ||
      column >= (double)map->columns || row >= (double)map->rows)
    return 0;
  return 1;
}

static int anvil_tilemap_tile_ok(const AnvilTilemap *map, double tile) {
  if (!isfinite(tile) || floor(tile) != tile)
    return 0;
  if (tile == (double)ANVIL_TILEMAP_EMPTY)
    return 1;
  return tile >= 0.0 && tile < (double)map->tiles;
}

double anvil_tilemap_new(double image_handle, double tile_w, double tile_h,
                         double columns, double rows) {
  anvil_tilemap_error_text = "";
  AnvilImage *image = anvil_image_from_handle(image_handle);
  if (!image) {
    anvil_tilemap_error_text = "the tileset is not a loaded image";
    return 0.0;
  }
  if (!isfinite(tile_w) || !isfinite(tile_h) || floor(tile_w) != tile_w ||
      floor(tile_h) != tile_h || tile_w < 1.0 || tile_h < 1.0) {
    anvil_tilemap_error_text = "the tile size must be whole pixels of at least 1";
    return 0.0;
  }
  if (tile_w > (double)image->width || tile_h > (double)image->height) {
    anvil_tilemap_error_text = "the tile is larger than the tileset image";
    return 0.0;
  }
  if (!isfinite(columns) || !isfinite(rows) || floor(columns) != columns ||
      floor(rows) != rows || columns < 1.0 || rows < 1.0 ||
      columns > (double)ANVIL_TILEMAP_MAX || rows > (double)ANVIL_TILEMAP_MAX) {
    anvil_tilemap_error_text = "the map must be 1..512 cells on each side";
    return 0.0;
  }
  int slot = -1;
  for (int i = 0; i < ANVIL_TILEMAPS; ++i) {
    if (!anvil_tilemaps[i].used && anvil_tilemaps[i].generation < UINT32_MAX) {
      slot = i;
      break;
    }
  }
  if (slot < 0) {
    anvil_tilemap_error_text = "the tilemap slots are full";
    return 0.0;
  }
  int columns_i = (int)columns;
  int rows_i = (int)rows;
  int *cells = (int *)malloc((size_t)columns_i * (size_t)rows_i * sizeof(int));
  if (!cells) {
    anvil_tilemap_error_text = "there is not enough memory for the map";
    return 0.0;
  }
  for (int i = 0; i < columns_i * rows_i; ++i)
    cells[i] = ANVIL_TILEMAP_EMPTY;
  AnvilTilemap *map = &anvil_tilemaps[slot];
  uint32_t generation = map->generation + 1;
  memset(map, 0, sizeof(*map));
  map->generation = generation;
  map->used = 1;
  map->image_handle = image_handle;
  map->tile_w = (int)tile_w;
  map->tile_h = (int)tile_h;
  map->columns = columns_i;
  map->rows = rows_i;
  map->tiles_per_row = image->width / (int)tile_w;
  map->tiles = map->tiles_per_row * (image->height / (int)tile_h);
  map->cells = cells;
  return (double)(generation - 1) * ANVIL_TILEMAPS + slot + 1;
}

double anvil_tilemap_free(double handle) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map)
    return 0.0;
  free(map->cells);
  free(map->solid);
  free(map->anim_frames);
  free(map->anim_fps);
  uint32_t generation = map->generation;
  memset(map, 0, sizeof(*map));
  map->generation = generation;
  return 1.0;
}

double anvil_tilemap_columns(double handle) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  return map ? (double)map->columns : 0.0;
}

double anvil_tilemap_rows(double handle) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  return map ? (double)map->rows : 0.0;
}

double anvil_tilemap_tiles(double handle) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  return map ? (double)map->tiles : 0.0;
}

double anvil_tilemap_set(double handle, double column, double row, double tile) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_cell_ok(map, column, row))
    return 0.0;
  if (!anvil_tilemap_tile_ok(map, tile))
    return 0.0;
  map->cells[(size_t)(int)row * (size_t)map->columns + (size_t)(int)column] =
      (int)tile;
  return 1.0;
}

double anvil_tilemap_get(double handle, double column, double row) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_cell_ok(map, column, row))
    return -1.0;
  return (double)map->cells[(size_t)(int)row * (size_t)map->columns +
                            (size_t)(int)column];
}

double anvil_tilemap_fill(double handle, double tile) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_tile_ok(map, tile))
    return 0.0;
  int count = map->columns * map->rows;
  for (int i = 0; i < count; ++i)
    map->cells[i] = (int)tile;
  return 1.0;
}

double anvil_tilemap_area(double handle, double tile, double column, double row,
                          double columns, double rows) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_tile_ok(map, tile))
    return 0.0;
  if (!isfinite(column) || !isfinite(row) || !isfinite(columns) ||
      !isfinite(rows) || floor(column) != column || floor(row) != row ||
      floor(columns) != columns || floor(rows) != rows)
    return 0.0;
  int x0 = (int)column, y0 = (int)row;
  int x1 = x0 + (int)columns, y1 = y0 + (int)rows;
  if (x0 < 0)
    x0 = 0;
  if (y0 < 0)
    y0 = 0;
  if (x1 > map->columns)
    x1 = map->columns;
  if (y1 > map->rows)
    y1 = map->rows;
  if (x0 >= x1 || y0 >= y1)
    return 0.0;
  for (int y = y0; y < y1; ++y)
    for (int x = x0; x < x1; ++x)
      map->cells[(size_t)y * (size_t)map->columns + (size_t)x] = (int)tile;
  return 1.0;
}

/* Solid tiles are a per-map bitset, allocated the first time a map marks one,
   so a map that never collides costs nothing. */
static int anvil_tilemap_solid_ensure(AnvilTilemap *map) {
  if (map->solid)
    return 1;
  if (map->tiles > 1000000) {
    anvil_tilemap_error_text =
        "the tileset has too many tiles to mark solid (over 1,000,000)";
    return 0;
  }
  size_t bytes = ((size_t)map->tiles + 7u) / 8u;
  map->solid = (unsigned char *)calloc(bytes ? bytes : 1u, 1u);
  if (!map->solid) {
    anvil_tilemap_error_text = "there is not enough memory for the solid map";
    return 0;
  }
  return 1;
}

double anvil_tilemap_solid(double handle, double tile, double on) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_tile_ok(map, tile) ||
      tile == (double)ANVIL_TILEMAP_EMPTY)
    return 0.0;
  if (!anvil_tilemap_solid_ensure(map))
    return 0.0;
  int index = (int)tile;
  if (on != 0.0)
    map->solid[index >> 3] |= (unsigned char)(1u << (index & 7));
  else
    map->solid[index >> 3] &= (unsigned char)~(1u << (index & 7));
  return 1.0;
}

double anvil_tilemap_is_solid(double handle, double tile) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_tile_ok(map, tile) ||
      tile == (double)ANVIL_TILEMAP_EMPTY || !map->solid)
    return 0.0;
  int index = (int)tile;
  return ((map->solid[index >> 3] >> (index & 7)) & 1u) ? 1.0 : 0.0;
}

/* The tile under a world point, using the placement rule of
   tilemap_draw(map, 0, 0, scale): cells are tile_w*scale wide. */
double anvil_tilemap_cell(double handle, double x, double y, double scale) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !isfinite(x) || !isfinite(y) || !isfinite(scale) || scale <= 0.0)
    return -1.0;
  if (x < 0.0 || y < 0.0)
    return -1.0;
  double step_x = (double)map->tile_w * scale;
  double step_y = (double)map->tile_h * scale;
  double column = floor(x / step_x);
  double row = floor(y / step_y);
  if (column >= (double)map->columns || row >= (double)map->rows)
    return -1.0;
  return (double)map->cells[(size_t)row * (size_t)map->columns + (size_t)column];
}

/* Does the world-space rectangle [x, x+width) x [y, y+height) touch a solid
   cell? The map is treated as drawn at the origin with `scale`, exactly like
   tilemap_draw(map, 0, 0, scale), so world coordinates are the same ones the
   draws use. Returns 1 on a hit and 0 otherwise. */
double anvil_tilemap_collide(double handle, double x, double y, double width,
                             double height, double scale) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !isfinite(x) || !isfinite(y) || !isfinite(width) ||
      !isfinite(height) || !isfinite(scale) || scale <= 0.0 || width <= 0.0 ||
      height <= 0.0 || !map->solid)
    return 0.0;
  double step_x = (double)map->tile_w * scale;
  double step_y = (double)map->tile_h * scale;
  double left = floor(x / step_x);
  double right = ceil((x + width) / step_x) - 1.0;
  double top = floor(y / step_y);
  double bottom = ceil((y + height) / step_y) - 1.0;
  if (left < 0.0)
    left = 0.0;
  if (top < 0.0)
    top = 0.0;
  if (right > (double)(map->columns - 1))
    right = (double)(map->columns - 1);
  if (bottom > (double)(map->rows - 1))
    bottom = (double)(map->rows - 1);
  if (left > right || top > bottom)
    return 0.0;
  for (int row = (int)top; row <= (int)bottom; ++row) {
    for (int column = (int)left; column <= (int)right; ++column) {
      int tile = map->cells[(size_t)row * (size_t)map->columns + (size_t)column];
      if (tile < 0 || tile >= map->tiles)
        continue;
      if ((map->solid[tile >> 3] >> (tile & 7)) & 1u)
        return 1.0;
    }
  }
  return 0.0;
}

/* Tile animations are a render-time substitution: the cell keeps its base
   tile (so solid flags and tilemap_get stay stable) and the draw maps it to
   the current frame. Frames advance left to right inside the base tile's row
   of the sheet and wrap at the row end, so an animation can never bleed into
   the row below. Like the solid bitset, the tables are allocated on demand. */
static int anvil_tilemap_anim_ensure(AnvilTilemap *map) {
  if (map->anim_frames)
    return 1;
  if (map->tiles > 1000000) {
    anvil_tilemap_error_text =
        "the tileset has too many tiles to animate (over 1,000,000)";
    return 0;
  }
  size_t count = (size_t)map->tiles;
  map->anim_frames = (unsigned short *)calloc(count ? count : 1u,
                                              sizeof(unsigned short));
  map->anim_fps = (float *)calloc(count ? count : 1u, sizeof(float));
  if (!map->anim_frames || !map->anim_fps) {
    free(map->anim_frames);
    free(map->anim_fps);
    map->anim_frames = NULL;
    map->anim_fps = NULL;
    anvil_tilemap_error_text = "there is not enough memory for tile animation";
    return 0;
  }
  return 1;
}

static int anvil_tilemap_frame_at(const AnvilTilemap *map, int tile) {
  if (!map->anim_frames || tile < 0 || tile >= map->tiles)
    return tile;
  int frames = (int)map->anim_frames[tile];
  if (frames <= 1)
    return tile;
  double fps = (double)map->anim_fps[tile];
  if (!(fps > 0.0))
    return tile;
  int column = tile % map->tiles_per_row;
  int step = (int)fmod(floor(anvil_elapsed_seconds * fps), (double)frames);
  if (step < 0)
    step = 0;
  return tile - column + (column + step) % map->tiles_per_row;
}

double anvil_tilemap_animate(double handle, double tile, double frames,
                             double fps) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_tile_ok(map, tile) ||
      tile == (double)ANVIL_TILEMAP_EMPTY)
    return 0.0;
  if (!isfinite(frames) || floor(frames) != frames || frames < 1.0 ||
      frames > (double)map->tiles_per_row || frames > 65535.0)
    return 0.0;
  if (!isfinite(fps) || fps <= 0.0)
    return 0.0;
  if (!anvil_tilemap_anim_ensure(map))
    return 0.0;
  int index = (int)tile;
  map->anim_frames[index] = (unsigned short)(frames <= 1.0 ? 0.0 : frames);
  map->anim_fps[index] = frames <= 1.0 ? 0.0f : (float)fps;
  return 1.0;
}

double anvil_tilemap_frame(double handle, double tile) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map || !anvil_tilemap_tile_ok(map, tile) ||
      tile == (double)ANVIL_TILEMAP_EMPTY)
    return -1.0;
  return (double)anvil_tilemap_frame_at(map, (int)tile);
}

double anvil_tilemap_draw(double handle, double x, double y, double scale) {
  AnvilTilemap *map = anvil_tilemap_from_handle(handle);
  if (!map) {
    anvil_tilemap_error_text = "the tilemap handle is not live";
    return 0.0;
  }
  if (!anvil_image_from_handle(map->image_handle)) {
    anvil_tilemap_error_text = "the tileset image was destroyed";
    return 0.0;
  }
  if (!anvil_pixels) {
    anvil_tilemap_error_text = "there is no window to draw into";
    return 0.0;
  }
  if (!isfinite(x) || !isfinite(y) || !isfinite(scale) || scale <= 0.0)
    return 0.0;
  double step_x = (double)map->tile_w * scale;
  double step_y = (double)map->tile_h * scale;
  /* Only walk the cells that can reach the framebuffer. The visible world
     rectangle follows from the camera (pan scaled by the parallax factor) and
     the zoom, so the cost of a draw is the size of the viewport, not of the
     map: a 512x512 world costs the same as a 20x12 one. */
  double zoom = anvil_camera2d_zoom > 0.0 ? anvil_camera2d_zoom : 1.0;
  double view_left = anvil_camera2d_x * anvil_parallax_factor;
  double view_top = anvil_camera2d_y * anvil_parallax_factor;
  double view_right = view_left + (double)ANVIL_WIDTH / zoom;
  double view_bottom = view_top + (double)ANVIL_HEIGHT / zoom;
  double first_column = floor((view_left - x) / step_x);
  double last_column = floor((view_right - x) / step_x);
  double first_row = floor((view_top - y) / step_y);
  double last_row = floor((view_bottom - y) / step_y);
  /* Clamp in the double domain before the cast: a wild camera pan or a tiny
     scale could otherwise overflow int. */
  if (!(first_column > -1.0))
    first_column = -1.0;
  if (!(first_row > -1.0))
    first_row = -1.0;
  if (!(last_column < (double)map->columns))
    last_column = (double)map->columns;
  if (!(last_row < (double)map->rows))
    last_row = (double)map->rows;
  int column_start = (int)first_column;
  int column_end = (int)last_column;
  int row_start = (int)first_row;
  int row_end = (int)last_row;
  if (column_start < 0)
    column_start = 0;
  if (row_start < 0)
    row_start = 0;
  if (column_end > map->columns - 1)
    column_end = map->columns - 1;
  if (row_end > map->rows - 1)
    row_end = map->rows - 1;
  if (column_start > column_end || row_start > row_end)
    return 1.0;
  for (int row = row_start; row <= row_end; ++row) {
    for (int column = column_start; column <= column_end; ++column) {
      int tile = map->cells[(size_t)row * (size_t)map->columns + (size_t)column];
      if (tile < 0 || tile >= map->tiles)
        continue;
      /* Animated tiles draw their current frame; the cell keeps its base. */
      tile = anvil_tilemap_frame_at(map, tile);
      if (tile < 0 || tile >= map->tiles)
        continue;
      double dx = x + (double)column * step_x;
      double dy = y + (double)row * step_y;
      double source_x = (double)((tile % map->tiles_per_row) * map->tile_w);
      double source_y = (double)((tile / map->tiles_per_row) * map->tile_h);
      if (anvil_sprite_batch_on) {
        const double args[9] = {map->image_handle, source_x, source_y,
                                (double)map->tile_w, (double)map->tile_h,
                                dx, dy, step_x, step_y};
        if (anvil_sprite_push(2, args))
          continue;
      }
      anvil_image_draw_region_now(map->image_handle, source_x, source_y,
                                  (double)map->tile_w, (double)map->tile_h,
                                  dx, dy, step_x, step_y);
    }
  }
  return 1.0;
}

double anvil_image_draw_region(double handle, double sx, double sy, double sw,
                               double sh, double dx, double dy, double dw,
                               double dh) {
  if (!anvil_image_from_handle(handle))
    return 0.0;
  const double args[9] = {handle, sx, sy, sw, sh, dx, dy, dw, dh};
  if (anvil_sprite_dispatch(2, args))
    return 1.0;
  return anvil_image_draw_region_now(handle, sx, sy, sw, sh, dx, dy, dw, dh);
}

double anvil_image_draw(double handle, double x, double y) {
  AnvilImage *image = anvil_image_from_handle(handle);
  if (!image)
    return 0.0;
  return anvil_image_draw_scaled(handle, x, y, image->width, image->height);
}
/* ---- Particles ---------------------------------------------------------- */
enum { ANVIL_PARTICLE_MAX = 4096 };

typedef struct {
  double x, y, vx, vy;
  double age, life, size;
  int r, g, b;
  int alive;
} AnvilParticle;

static AnvilParticle anvil_particles[ANVIL_PARTICLE_MAX];
static int anvil_particle_live;
static double anvil_particle_gravity_y;

double anvil_particle_emit(double x, double y, double vx, double vy,
                           double life, double size, double r, double g,
                           double b) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(vx) || !isfinite(vy) ||
      !isfinite(life) || !isfinite(size) || !isfinite(r) || !isfinite(g) ||
      !isfinite(b) || life <= 0.0 || size <= 0.0)
    return 0.0;
  for (int i = 0; i < ANVIL_PARTICLE_MAX; ++i) {
    AnvilParticle *particle = &anvil_particles[i];
    if (particle->alive)
      continue;
    particle->x = x;
    particle->y = y;
    particle->vx = vx;
    particle->vy = vy;
    particle->age = 0.0;
    particle->life = life;
    particle->size = size;
    particle->r = (int)(r < 0 ? 0 : r > 255 ? 255 : r);
    particle->g = (int)(g < 0 ? 0 : g > 255 ? 255 : g);
    particle->b = (int)(b < 0 ? 0 : b > 255 ? 255 : b);
    particle->alive = 1;
    anvil_particle_live++;
    return 1.0;
  }
  return 0.0;
}

double anvil_particle_count(void) { return (double)anvil_particle_live; }

double anvil_particle_clear(void) {
  int cleared = anvil_particle_live;
  memset(anvil_particles, 0, sizeof(anvil_particles));
  anvil_particle_live = 0;
  return (double)cleared;
}

double anvil_particle_gravity(double gravity) {
  if (!isfinite(gravity))
    return 0.0;
  anvil_particle_gravity_y = gravity;
  return gravity;
}

static void anvil_particles_update(double dt) {
  if (anvil_particle_live == 0)
    return;
  for (int i = 0; i < ANVIL_PARTICLE_MAX; ++i) {
    AnvilParticle *particle = &anvil_particles[i];
    if (!particle->alive)
      continue;
    particle->age += dt;
    if (particle->age >= particle->life) {
      particle->alive = 0;
      anvil_particle_live--;
      continue;
    }
    particle->vy += anvil_particle_gravity_y * dt;
    particle->x += particle->vx * dt;
    particle->y += particle->vy * dt;
  }
}

/* Drawn after the program's own draw pass, so particles sit above the scene. */
static void anvil_particles_draw(void) {
  if (anvil_particle_live == 0)
    return;
  for (int i = 0; i < ANVIL_PARTICLE_MAX; ++i) {
    AnvilParticle *particle = &anvil_particles[i];
    if (!particle->alive)
      continue;
    double fade = 1.0 - particle->age / particle->life;
    int alpha = (int)(255.0 * fade);
    anvil_rect(particle->x - particle->size * 0.5,
               particle->y - particle->size * 0.5, particle->size,
               particle->size, particle->r, particle->g, particle->b, alpha);
  }
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
#define ANVIL_STR_CAP 256
#define ANVIL_STR_SLOTS 256
char anvil_str_scratch[ANVIL_STR_SLOTS][ANVIL_STR_CAP];

void anvil_print_bool(double value) {
  fputs(value != 0.0 ? "true" : "false", stdout);
}

void anvil_text_list_remove(char block[][256], int index, double count) {
  int total = (int)count;
  if (index < 0 || index >= total) {
    return;
  }
  for (int slot = index; slot + 1 < total; slot++) {
    memcpy(block[slot], block[slot + 1], 256);
  }
  block[total - 1][0] = '\0';
}

const char *anvil_text_list_get(const char block[][256], int index, double count,
                                const char *path, int line) {
  if (index < 0 || index >= (int)count) {
    fprintf(stderr, "%s:%d: list index %d is outside 0..%d\n", path,
            line, index, (int)count - 1);
    exit(2);
  }
  return block[index];
}

void anvil_text_list_set(char block[][256], int index, double count,
                         const char *value, const char *path, int line) {
  (void)count;
  if (index < 0 || index >= 256) {
    fprintf(stderr, "%s:%d: text list is full (256 values)\n", path, line);
    exit(2);
  }
  anvil_str_set(block[index], value, path, line);
}


__declspec(noreturn) static void anvil_str_overflow(const char *path, int line) {
  fprintf(stderr, "%s:%d: text is limited to %d characters\n", path ? path : "<Anvil>",
          line, ANVIL_STR_CAP - 1);
  exit(2);
}

void anvil_str_set(char *dest, const char *value, const char *path, int line) {
  size_t len = strlen(value);
  if (len >= ANVIL_STR_CAP) {
    anvil_str_overflow(path, line);
  }
  memcpy(dest, value, len + 1);
}

char *anvil_str_cat(char *dest, const char *a, const char *b,
                    const char *path, int line) {
  size_t la = strlen(a), lb = strlen(b);
  char tail[ANVIL_STR_CAP];
  int a_inside = a >= dest && a < dest + ANVIL_STR_CAP;
  int b_inside = b >= dest && b < dest + ANVIL_STR_CAP;
  if (la + lb >= ANVIL_STR_CAP) {
    anvil_str_overflow(path, line);
  }
  /* A text-returning function joins into its own return buffer, and a recursive
     call hands back that same buffer, so `a` or `b` can alias `dest`. Copy the
     aliased tail aside before dest is rewritten, or the join reads text it just
     overwrote (a recursive reverse produced "ccb" instead of "cba"). */
  if (b_inside) {
    memcpy(tail, b, lb + 1);
    b = tail;
  }
  if (!a_inside) {
    memcpy(dest, a, la);
  }
  memcpy(dest + la, b, lb + 1);
  return dest;
}

char *anvil_str_from_number(int slot, double value) {
  if (slot < 0 || slot >= ANVIL_STR_SLOTS) {
    anvil_str_overflow(NULL, 0);
  }
  _snprintf_s(anvil_str_scratch[slot], ANVIL_STR_CAP, _TRUNCATE, "%s",
              anvil_format_number(value));
  return anvil_str_scratch[slot];
}

void anvil_ask(const char *prompt, char *dest) {
  if (prompt && *prompt) {
    printf("%s", prompt);
    fflush(stdout);
  }
  if (fgets(dest, 256, stdin)) {
    size_t len = strlen(dest);
    while (len && (dest[len - 1] == '\n' || dest[len - 1] == '\r')) {
      dest[--len] = 0;
    }
  } else {
    dest[0] = 0;
  }
}

double anvil_ask_number(const char *prompt) {
  char buffer[256];
  if (prompt && *prompt) {
    printf("%s", prompt);
    fflush(stdout);
  }
  if (!fgets(buffer, sizeof(buffer), stdin)) {
    return 0.0;
  }
  /* strtod reads the leading number; anything unread stays in the buffer. */
  return strtod(buffer, NULL);
}

void anvil_press_enter(void) {
  printf("Press Enter to continue...\n");
  fflush(stdout);
  int ch;
  while ((ch = getchar()) != '\n' && ch != EOF) {
  }
}

void anvil_wait(double seconds) {
  /* Pause the console program; negative and non-finite values do not sleep. */
  if (!(seconds > 0.0)) {
    return;
  }
  if (seconds > 86400.0) {
    seconds = 86400.0;
  }
  Sleep((DWORD)(seconds * 1000.0));
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

static int anvil_ray_backend_id(const char *name) {
  if (!name)
    return -1;
  if (_stricmp(name, "bvh") == 0)
    return ANVIL_RAY_BACKEND_BVH;
  if (_stricmp(name, "dxr") == 0)
    return ANVIL_RAY_BACKEND_DXR;
  if (_stricmp(name, "embree") == 0)
    return ANVIL_RAY_BACKEND_EMBREE;
  return -1;
}

int anvil_ray_backend_available(const char *name) {
  /* BVH is the only backend with a renderer implementation in this build. */
  return anvil_ray_backend_id(name) == ANVIL_RAY_BACKEND_BVH;
}

int anvil_ray_backend(const char *name) {
  int requested = anvil_ray_backend_id(name);
  if (requested == ANVIL_RAY_BACKEND_BVH) {
    anvil_active_ray_backend = requested;
    return 1;
  }
  if (requested >= ANVIL_RAY_BACKEND_DXR &&
      requested <= ANVIL_RAY_BACKEND_EMBREE) {
    unsigned int warning = 1u << (unsigned int)requested;
    if (!(anvil_ray_backend_warnings & warning)) {
      const char *backend_name = requested == ANVIL_RAY_BACKEND_DXR ? "dxr" : "embree";
      fprintf(stderr,
              "Anvil: ray backend '%s' is unavailable in this build; active backend remains BVH.\n",
              backend_name);
      anvil_ray_backend_warnings |= warning;
    }
    return 0;
  }
  if (!(anvil_ray_backend_warnings & (1u << 31))) {
    fprintf(stderr,
            "Anvil: unknown ray backend '%s'; choose 'bvh', 'dxr', or 'embree'.\n",
            name ? name : "(null)");
    anvil_ray_backend_warnings |= 1u << 31;
  }
  return 0;
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
  if (anvil_active_ray_backend != ANVIL_RAY_BACKEND_BVH) {
    anvil_trace_sphere_count = 0;
    return;
  }

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
        double pixel_depth = anvil_dot(anvil_sub(point, origin), forward);
        size_t pixel = (size_t)py * ANVIL_WIDTH + (size_t)px;
        if (pixel_depth < anvil_depth_buffer[pixel]) {
          anvil_depth_buffer[pixel] = pixel_depth;
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
static int anvil_noise_lattice(double value) {
  /* Match the native backend: every coordinate must be finite and inside
     [-2147483648, 2147483647) so floor() and the +1 lattice corner both stay
     representable as int.  A NaN fails every comparison and is rejected too. */
  if (!(value >= -2147483648.0) || !(value < 2147483647.0)) {
    fprintf(stderr, "Anvil noise coordinate range error\n");
    exit(2);
  }
  return (int)floor(value);
}
double anvil_noise(double x, double y, double z) {
  int xi = anvil_noise_lattice(x), yi = anvil_noise_lattice(y),
      zi = anvil_noise_lattice(z);
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
    /* A NaN or infinite payload is not a usable number and would poison every
       later comparison, so it is ignored rather than stored. */
    if (!isfinite(value)) {
      return anvil_net_value;
    }
    anvil_net_value = value;
    if (!anvil_net_has_peer) {
      anvil_net_peer = from;
      anvil_net_has_peer = 1;
    }
  }
  return anvil_net_value;
}
int anvil_net_send(double value) {
  if (anvil_net_socket == INVALID_SOCKET || !anvil_net_has_peer)
    return 0;
  int sent = (int)sendto(anvil_net_socket, (const char *)&value,
                         (int)sizeof(value), 0, (SOCKADDR *)&anvil_net_peer,
                         sizeof(anvil_net_peer));
  return sent == (int)sizeof(value);
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

static AnvilPhysicsBody *anvil_physics_body(double handle, int *slot_out) {
  const double max_handle = (double)UINT32_MAX * ANVIL_PHYSICS_BODIES +
                            (ANVIL_PHYSICS_BODIES - 1);
  if (!isfinite(handle) || handle < 0.0 || handle > max_handle ||
      floor(handle) != handle)
    return NULL;
  uint64_t encoded = (uint64_t)handle;
  int slot = (int)(encoded % ANVIL_PHYSICS_BODIES);
  uint32_t generation = (uint32_t)(encoded / ANVIL_PHYSICS_BODIES);
  AnvilPhysicsBody *body = &anvil_physics_bodies[slot];
  if (!generation || !body->active || body->generation != generation)
    return NULL;
  if (slot_out)
    *slot_out = slot;
  return body;
}

static double anvil_physics_allocate_body(double x, double y, double radius,
                                          double half_width,
                                          double half_height, double mass,
                                          int shape) {
  for (int slot = 0; slot < anvil_physics_active_capacity; ++slot) {
    AnvilPhysicsBody *body = &anvil_physics_bodies[slot];
    if (body->active)
      continue;
    uint32_t generation = body->generation + 1;
    if (!generation)
      generation = 1;
    memset(body, 0, sizeof(*body));
    body->generation = generation;
    body->active = 1;
    body->shape = shape;
    body->x = x;
    body->y = y;
    body->radius = radius;
    body->half_width = half_width;
    body->half_height = half_height;
    body->mass = mass;
    body->friction = 0.5;
    return (double)generation * ANVIL_PHYSICS_BODIES + slot;
  }
  return -1.0;
}

double anvil_body_create(double x, double y, double radius, double mass) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(radius) || !isfinite(mass) ||
      fabs(x) > ANVIL_PHYSICS_MAX_COORDINATE ||
      fabs(y) > ANVIL_PHYSICS_MAX_COORDINATE || radius < 1.0e-6 ||
      radius > ANVIL_PHYSICS_MAX_RADIUS || mass < 0.0 || mass > 1.0e12 ||
      (mass > 0.0 && mass < 1.0e-6))
    return -1.0;
  return anvil_physics_allocate_body(x, y, radius, 0.0, 0.0, mass,
                                     ANVIL_PHYSICS_CIRCLE);
}

double anvil_body_create_box(double x, double y, double width, double height,
                             double mass) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(width) || !isfinite(height) ||
      !isfinite(mass) || fabs(x) > ANVIL_PHYSICS_MAX_COORDINATE ||
      fabs(y) > ANVIL_PHYSICS_MAX_COORDINATE || width < 2.0e-6 ||
      width > 2.0 * ANVIL_PHYSICS_MAX_RADIUS || height < 2.0e-6 ||
      height > 2.0 * ANVIL_PHYSICS_MAX_RADIUS || mass < 0.0 || mass > 1.0e12 ||
      (mass > 0.0 && mass < 1.0e-6))
    return -1.0;
  return anvil_physics_allocate_body(x, y, 0.0, width * 0.5, height * 0.5,
                                     mass, ANVIL_PHYSICS_BOX);
}

double anvil_physics_capacity(double requested_capacity) {
  if (!isfinite(requested_capacity) || floor(requested_capacity) != requested_capacity ||
      requested_capacity < 1.0 || requested_capacity > ANVIL_PHYSICS_BODIES)
    return -1.0;
  int capacity = (int)requested_capacity;
  for (int slot = capacity; slot < anvil_physics_active_capacity; ++slot) {
    if (anvil_physics_bodies[slot].active)
      return -1.0;
  }
  anvil_physics_active_capacity = capacity;
  return (double)anvil_physics_active_capacity;
}

double anvil_body_destroy(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body)
    return 0.0;
  body->active = 0;
  body->force_x = 0.0;
  body->force_y = 0.0;
  return 1.0;
}

double anvil_body_active(double handle) {
  return anvil_physics_body(handle, NULL) ? 1.0 : 0.0;
}

double anvil_body_x(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->x : -1.0;
}

double anvil_body_y(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->y : -1.0;
}

double anvil_body_vx(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->vx : -1.0;
}

double anvil_body_vy(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->vy : -1.0;
}

double anvil_body_set_velocity(double handle, double vx, double vy) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || body->mass <= 0.0 || !isfinite(vx) || !isfinite(vy) ||
      fabs(vx) > ANVIL_PHYSICS_MAX_SPEED || fabs(vy) > ANVIL_PHYSICS_MAX_SPEED)
    return 0.0;
  body->vx = vx;
  body->vy = vy;
  return 1.0;
}

double anvil_body_force(double handle, double force_x, double force_y) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || body->mass <= 0.0 || !isfinite(force_x) || !isfinite(force_y) ||
      fabs(force_x) > 1.0e12 || fabs(force_y) > 1.0e12)
    return 0.0;
  double next_force_x = body->force_x + force_x;
  double next_force_y = body->force_y + force_y;
  if (!isfinite(next_force_x) || !isfinite(next_force_y) ||
      fabs(next_force_x) > 1.0e12 || fabs(next_force_y) > 1.0e12)
    return 0.0;
  body->force_x = next_force_x;
  body->force_y = next_force_y;
  return 1.0;
}

double anvil_body_restitution(double handle, double restitution) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || !isfinite(restitution) || restitution < 0.0 || restitution > 1.0)
    return 0.0;
  body->restitution = restitution;
  return 1.0;
}

double anvil_body_friction(double handle, double friction) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || !isfinite(friction) || friction < 0.0 || friction > 1.0)
    return 0.0;
  body->friction = friction;
  return 1.0;
}

static int anvil_physics_contact(const AnvilPhysicsBody *a,
                                 const AnvilPhysicsBody *b, double *normal_x,
                                 double *normal_y, double *penetration) {
  if (a->shape == ANVIL_PHYSICS_CIRCLE &&
      b->shape == ANVIL_PHYSICS_CIRCLE) {
    double dx = b->x - a->x, dy = b->y - a->y;
    double radius = a->radius + b->radius;
    double distance_sq = dx * dx + dy * dy;
    if (distance_sq >= radius * radius)
      return 0;
    double distance = sqrt(distance_sq);
    *normal_x = distance > 1.0e-12 ? dx / distance : 1.0;
    *normal_y = distance > 1.0e-12 ? dy / distance : 0.0;
    *penetration = radius - distance;
    return 1;
  }

  if (a->shape == ANVIL_PHYSICS_BOX && b->shape == ANVIL_PHYSICS_BOX) {
    double dx = b->x - a->x, dy = b->y - a->y;
    double overlap_x = a->half_width + b->half_width - fabs(dx);
    double overlap_y = a->half_height + b->half_height - fabs(dy);
    if (overlap_x <= 0.0 || overlap_y <= 0.0)
      return 0;
    if (overlap_x < overlap_y) {
      *normal_x = dx >= 0.0 ? 1.0 : -1.0;
      *normal_y = 0.0;
      *penetration = overlap_x;
    } else {
      *normal_x = 0.0;
      *normal_y = dy >= 0.0 ? 1.0 : -1.0;
      *penetration = overlap_y;
    }
    return 1;
  }

  const AnvilPhysicsBody *circle = a->shape == ANVIL_PHYSICS_CIRCLE ? a : b;
  const AnvilPhysicsBody *box = a->shape == ANVIL_PHYSICS_BOX ? a : b;
  double closest_x = fmax(box->x - box->half_width,
                          fmin(circle->x, box->x + box->half_width));
  double closest_y = fmax(box->y - box->half_height,
                          fmin(circle->y, box->y + box->half_height));
  double dx = closest_x - circle->x, dy = closest_y - circle->y;
  double distance_sq = dx * dx + dy * dy;
  if (distance_sq >= circle->radius * circle->radius)
    return 0;
  if (distance_sq > 1.0e-24) {
    double distance = sqrt(distance_sq);
    *normal_x = dx / distance;
    *normal_y = dy / distance;
    *penetration = circle->radius - distance;
  } else {
    double left = circle->x - (box->x - box->half_width);
    double right = box->x + box->half_width - circle->x;
    double bottom = circle->y - (box->y - box->half_height);
    double top = box->y + box->half_height - circle->y;
    double nearest = left;
    *normal_x = 1.0;
    *normal_y = 0.0;
    if (right < nearest) {
      nearest = right;
      *normal_x = -1.0;
      *normal_y = 0.0;
    }
    if (bottom < nearest) {
      nearest = bottom;
      *normal_x = 0.0;
      *normal_y = 1.0;
    }
    if (top < nearest) {
      nearest = top;
      *normal_x = 0.0;
      *normal_y = -1.0;
    }
    *penetration = circle->radius + nearest;
  }
  if (a->shape == ANVIL_PHYSICS_BOX) {
    *normal_x = -*normal_x;
    *normal_y = -*normal_y;
  }
  return 1;
}

double anvil_body_collision(double first, double second) {
  int first_slot, second_slot;
  AnvilPhysicsBody *a = anvil_physics_body(first, &first_slot);
  AnvilPhysicsBody *b = anvil_physics_body(second, &second_slot);
  if (!a || !b || first_slot == second_slot)
    return 0.0;
  double normal_x, normal_y, penetration;
  return anvil_physics_contact(a, b, &normal_x, &normal_y, &penetration)
             ? 1.0
             : 0.0;
}

double anvil_physics_gravity(double x, double y) {
  if (!isfinite(x) || !isfinite(y) || fabs(x) > 1.0e6 || fabs(y) > 1.0e6)
    return 0.0;
  anvil_physics_gravity_x = x;
  anvil_physics_gravity_y = y;
  return 1.0;
}

double anvil_physics_step(void) {
  double dt = anvil_delta_seconds;
  if (!isfinite(dt) || dt <= 0.0 || dt > 0.25)
    dt = 1.0 / (double)anvil_fixed_hz;

  int contact_count = 0;
  for (int i = 0; i < anvil_physics_active_capacity; ++i) {
    AnvilPhysicsBody *a = &anvil_physics_bodies[i];
    if (!a->active)
      continue;
    for (int j = i + 1; j < anvil_physics_active_capacity; ++j) {
      AnvilPhysicsBody *b = &anvil_physics_bodies[j];
      if (!b->active)
        continue;
      double normal_x, normal_y, penetration;
      if (anvil_physics_contact(a, b, &normal_x, &normal_y, &penetration))
        ++contact_count;
    }
  }

  for (int i = 0; i < anvil_physics_active_capacity; ++i) {
    AnvilPhysicsBody *body = &anvil_physics_bodies[i];
    if (!body->active)
      continue;
    if (body->mass > 0.0) {
      body->vx += (anvil_physics_gravity_x + body->force_x / body->mass) * dt;
      body->vy += (anvil_physics_gravity_y + body->force_y / body->mass) * dt;
      body->vx = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                      fmin(ANVIL_PHYSICS_MAX_SPEED, body->vx));
      body->vy = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                      fmin(ANVIL_PHYSICS_MAX_SPEED, body->vy));
      body->x += body->vx * dt;
      body->y += body->vy * dt;
      if (body->x > ANVIL_PHYSICS_MAX_COORDINATE) {
        body->x = ANVIL_PHYSICS_MAX_COORDINATE;
        body->vx = 0.0;
      } else if (body->x < -ANVIL_PHYSICS_MAX_COORDINATE) {
        body->x = -ANVIL_PHYSICS_MAX_COORDINATE;
        body->vx = 0.0;
      }
      if (body->y > ANVIL_PHYSICS_MAX_COORDINATE) {
        body->y = ANVIL_PHYSICS_MAX_COORDINATE;
        body->vy = 0.0;
      } else if (body->y < -ANVIL_PHYSICS_MAX_COORDINATE) {
        body->y = -ANVIL_PHYSICS_MAX_COORDINATE;
        body->vy = 0.0;
      }
      if (!isfinite(body->x) || !isfinite(body->y) || !isfinite(body->vx) ||
          !isfinite(body->vy)) {
        body->x = body->y = body->vx = body->vy = 0.0;
      }
    }
    body->force_x = 0.0;
    body->force_y = 0.0;
  }

  for (int iteration = 0; iteration < ANVIL_PHYSICS_SOLVER_ITERATIONS;
       ++iteration) {
    for (int i = 0; i < anvil_physics_active_capacity; ++i) {
      AnvilPhysicsBody *a = &anvil_physics_bodies[i];
      if (!a->active)
        continue;
      for (int j = i + 1; j < anvil_physics_active_capacity; ++j) {
        AnvilPhysicsBody *b = &anvil_physics_bodies[j];
        if (!b->active)
          continue;
        double nx, ny, penetration;
        if (!anvil_physics_contact(a, b, &nx, &ny, &penetration))
          continue;
        double inverse_a = a->mass > 0.0 ? 1.0 / a->mass : 0.0;
        double inverse_b = b->mass > 0.0 ? 1.0 / b->mass : 0.0;
        double inverse_sum = inverse_a + inverse_b;
        if (inverse_sum <= 0.0)
          continue;

        double correction = fmax(penetration - 0.0001, 0.0) * 0.8 / inverse_sum;
        a->x -= nx * correction * inverse_a;
        a->y -= ny * correction * inverse_a;
        b->x += nx * correction * inverse_b;
        b->y += ny * correction * inverse_b;

        double relative_x = b->vx - a->vx;
        double relative_y = b->vy - a->vy;
        double along_normal = relative_x * nx + relative_y * ny;
        double normal_impulse = 0.0;
        if (along_normal < 0.0) {
          double restitution = fmin(a->restitution, b->restitution);
          normal_impulse = -(1.0 + restitution) * along_normal / inverse_sum;
          a->vx -= normal_impulse * nx * inverse_a;
          a->vy -= normal_impulse * ny * inverse_a;
          b->vx += normal_impulse * nx * inverse_b;
          b->vy += normal_impulse * ny * inverse_b;
        }

        if (normal_impulse > 0.0) {
          relative_x = b->vx - a->vx;
          relative_y = b->vy - a->vy;
          double tangent_x = relative_x - (relative_x * nx + relative_y * ny) * nx;
          double tangent_y = relative_y - (relative_x * nx + relative_y * ny) * ny;
          double tangent_length = hypot(tangent_x, tangent_y);
          if (tangent_length > 1.0e-12) {
            tangent_x /= tangent_length;
            tangent_y /= tangent_length;
            double tangent_impulse = -(relative_x * tangent_x +
                                       relative_y * tangent_y) / inverse_sum;
            double coefficient = sqrt(a->friction * b->friction);
            double maximum = coefficient * normal_impulse;
            tangent_impulse = fmax(-maximum, fmin(tangent_impulse, maximum));
            a->vx -= tangent_impulse * tangent_x * inverse_a;
            a->vy -= tangent_impulse * tangent_y * inverse_a;
            b->vx += tangent_impulse * tangent_x * inverse_b;
            b->vy += tangent_impulse * tangent_y * inverse_b;
          }
        }
      }
    }
  }

  /* Collision impulses and positional corrections can exceed the integration
   * limits above. Reapply the public bounds after the solver has finished. */
  for (int i = 0; i < anvil_physics_active_capacity; ++i) {
    AnvilPhysicsBody *body = &anvil_physics_bodies[i];
    if (!body->active)
      continue;
    body->vx = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                    fmin(ANVIL_PHYSICS_MAX_SPEED, body->vx));
    body->vy = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                    fmin(ANVIL_PHYSICS_MAX_SPEED, body->vy));
    if (body->x > ANVIL_PHYSICS_MAX_COORDINATE) {
      body->x = ANVIL_PHYSICS_MAX_COORDINATE;
      body->vx = 0.0;
    } else if (body->x < -ANVIL_PHYSICS_MAX_COORDINATE) {
      body->x = -ANVIL_PHYSICS_MAX_COORDINATE;
      body->vx = 0.0;
    }
    if (body->y > ANVIL_PHYSICS_MAX_COORDINATE) {
      body->y = ANVIL_PHYSICS_MAX_COORDINATE;
      body->vy = 0.0;
    } else if (body->y < -ANVIL_PHYSICS_MAX_COORDINATE) {
      body->y = -ANVIL_PHYSICS_MAX_COORDINATE;
      body->vy = 0.0;
    }
    if (!isfinite(body->x) || !isfinite(body->y) || !isfinite(body->vx) ||
        !isfinite(body->vy)) {
      body->x = body->y = body->vx = body->vy = 0.0;
    }
  }
  return (double)contact_count;
}

/* Present the frame straight to the window DC. Going through
   InvalidateRect + UpdateWindow forced a WM_PAINT per frame, which repainted
   the black background and re-scaled the image inside the paint handler; at
   60 Hz that repaint churn is what read as flicker. WM_PAINT is still handled
   for occlusion, resize and the first frame. */
static int anvil_present_full_fill = 1;

/* Screen fade: a black overlay composited after every draw and before the
   present, which is what a scene transition needs - a menu, a level change or
   a hit can dim the frame without touching what the scene drew. alpha is
   0..255; fade_to() walks it over real seconds using the frame clock. */
static double anvil_screen_fade_value;
static double anvil_screen_fade_target;
static double anvil_screen_fade_speed; /* alpha units per second */
static int anvil_screen_fade_active;

double anvil_screen_fade(double alpha) {
  double previous = anvil_screen_fade_value;
  if (isfinite(alpha)) {
    anvil_screen_fade_value = alpha < 0.0 ? 0.0 : alpha > 255.0 ? 255.0 : alpha;
    anvil_screen_fade_active = 0;
  }
  return previous;
}

double anvil_screen_fade_to(double target, double seconds) {
  double previous = anvil_screen_fade_value;
  if (!isfinite(target))
    return previous;
  double clamped = target < 0.0 ? 0.0 : target > 255.0 ? 255.0 : target;
  if (!isfinite(seconds) || seconds <= 0.0) {
    anvil_screen_fade_value = clamped;
    anvil_screen_fade_active = 0;
    return previous;
  }
  anvil_screen_fade_target = clamped;
  anvil_screen_fade_speed = fabs(clamped - anvil_screen_fade_value) / seconds;
  anvil_screen_fade_active = anvil_screen_fade_speed > 0.0;
  return previous;
}

double anvil_screen_fade_alpha(void) { return anvil_screen_fade_value; }

static void anvil_screen_fade_advance(double seconds) {
  if (!anvil_screen_fade_active)
    return;
  double step = anvil_screen_fade_speed * seconds;
  if (anvil_screen_fade_value < anvil_screen_fade_target) {
    anvil_screen_fade_value += step;
    if (anvil_screen_fade_value >= anvil_screen_fade_target) {
      anvil_screen_fade_value = anvil_screen_fade_target;
      anvil_screen_fade_active = 0;
    }
  } else {
    anvil_screen_fade_value -= step;
    if (anvil_screen_fade_value <= anvil_screen_fade_target) {
      anvil_screen_fade_value = anvil_screen_fade_target;
      anvil_screen_fade_active = 0;
    }
  }
}

/* Whole-screen dim, straight into the backbuffer: out = in * (255 - alpha)/255.
   Runs only while alpha is above zero, so a program that never fades pays one
   comparison per frame. */
static void anvil_screen_fade_apply(void) {
  if (!anvil_pixels)
    return;
  int alpha = (int)lrint(anvil_screen_fade_value);
  if (alpha <= 0)
    return;
  if (alpha > 255)
    alpha = 255;
  size_t count = (size_t)ANVIL_WIDTH * (size_t)ANVIL_HEIGHT;
  if (alpha >= 255) {
    for (size_t i = 0; i < count; ++i)
      anvil_pixels[i] = 0u;
    return;
  }
  int keep = 255 - alpha;
  for (size_t i = 0; i < count; ++i) {
    uint32_t pixel = anvil_pixels[i];
    int r = (int)((pixel >> 16) & 255u) * keep / 255;
    int g = (int)((pixel >> 8) & 255u) * keep / 255;
    int b = (int)(pixel & 255u) * keep / 255;
    anvil_pixels[i] = anvil_color(r, g, b);
  }
}

/* Double buffering is on unless a program turns it off with buffer(0). */
static int anvil_double_buffer = 1;

double anvil_buffer(double on) {
  int previous = anvil_double_buffer;
  anvil_double_buffer = on != 0.0;
  anvil_present_full_fill = 1;
  return (double)previous;
}

static void anvil_present_window(void) {
  if (!anvil_window || !anvil_pixels || IsIconic(anvil_window))
    return;
  RECT client;
  if (!GetClientRect(anvil_window, &client))
    return;
  int width = client.right - client.left, height = client.bottom - client.top;
  AnvilViewport viewport;
  if (!anvil_compute_viewport(width, height, ANVIL_WIDTH, ANVIL_HEIGHT,
                              &viewport))
    return;
  const uint32_t *source = anvil_pixels;
  if (anvil_double_buffer) {
    /* The frame just finished becomes the one on screen; drawing continues in
       the other buffer, so the image being displayed is never touched again. */
    anvil_display_pixels = anvil_pixels;
    source = anvil_display_pixels;
    anvil_back_index ^= 1;
    SelectObject(anvil_memory_dc, anvil_bitmaps[anvil_back_index]);
    anvil_pixels = anvil_buffers[anvil_back_index];
  } else {
    anvil_display_pixels = anvil_pixels;
    source = anvil_pixels;
  }
  HDC dc = GetDC(anvil_window);
  if (!dc)
    return;
  /* One scaled copy straight to the window. With double buffering the source is
     a finished frame that will not be drawn on again, so there is nothing to
     tear and no reason to stage it through a second surface; the staging bitmap
     stays for WM_PAINT repaints, which need to redraw from the display buffer
     without holding a DC across the message. */
  if (anvil_present_full_fill) {
    RECT full = {0, 0, width, height};
    FillRect(dc, &full, (HBRUSH)GetStockObject(BLACK_BRUSH));
    anvil_present_full_fill = 0;
  }
  StretchDIBits(dc, viewport.x, viewport.y, viewport.width, viewport.height, 0, 0,
                ANVIL_WIDTH, ANVIL_HEIGHT, source, &anvil_bitmap_info,
                DIB_RGB_COLORS, SRCCOPY);
  ReleaseDC(anvil_window, dc);
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
  case WM_SIZE:
    anvil_present_full_fill = 1;
    InvalidateRect(window, NULL, FALSE);
    break;
  case WM_MOUSEMOVE: {
    anvil_mouse_client_x = (short)LOWORD(lparam);
    anvil_mouse_client_y = (short)HIWORD(lparam);
    anvil_mouse_has_position = 1;
    TRACKMOUSEEVENT tracking = {sizeof(tracking), TME_LEAVE, window, 0};
    TrackMouseEvent(&tracking);
    return 0;
  }
  case WM_MOUSELEAVE:
    anvil_mouse_has_position = 0;
    return 0;
  case WM_LBUTTONDOWN:
  case WM_RBUTTONDOWN:
  case WM_MBUTTONDOWN: {
    int index = message == WM_LBUTTONDOWN ? 0
                : message == WM_RBUTTONDOWN ? 1
                                            : 2;
    /* Record the press position too: a posted or synthetic click can arrive
       without a preceding WM_MOUSEMOVE. */
    anvil_mouse_client_x = (short)LOWORD(lparam);
    anvil_mouse_client_y = (short)HIWORD(lparam);
    anvil_mouse_has_position = 1;
    if (!anvil_mouse_buttons[index])
      anvil_mouse_pressed_buttons[index] = 1;
    anvil_mouse_buttons[index] = 1;
    SetCapture(window);
    return 0;
  }
  case WM_LBUTTONUP:
  case WM_RBUTTONUP:
  case WM_MBUTTONUP: {
    int index = message == WM_LBUTTONUP ? 0
                : message == WM_RBUTTONUP ? 1
                                          : 2;
    anvil_mouse_buttons[index] = 0;
    if (!anvil_mouse_buttons[0] && !anvil_mouse_buttons[1] &&
        !anvil_mouse_buttons[2] && GetCapture() == window)
      ReleaseCapture();
    return 0;
  }
  case WM_MOUSEWHEEL:
    anvil_mouse_wheel_delta +=
        (double)(short)HIWORD(wparam) / (double)WHEEL_DELTA;
    return 0;
  case WM_CAPTURECHANGED:
    if ((HWND)lparam != window)
      memset(anvil_mouse_buttons, 0, sizeof(anvil_mouse_buttons));
    return 0;
  case WM_KILLFOCUS:
    memset(anvil_keys, 0, sizeof(anvil_keys));
    memset(anvil_mouse_buttons, 0, sizeof(anvil_mouse_buttons));
    anvil_mouse_has_position = 0;
    if (GetCapture() == window)
      ReleaseCapture();
    return 0;
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
    RECT client;
    if (GetClientRect(window, &client)) {
      int width = client.right - client.left, height = client.bottom - client.top;
      AnvilViewport viewport;
      int have_viewport =
          anvil_pixels && anvil_compute_viewport(width, height, ANVIL_WIDTH,
                                                 ANVIL_HEIGHT, &viewport);
      /* Repaint from the frame that is currently on screen. It is a finished
         buffer that nothing is drawing into, so one scaled blit is enough and
         the black background never shows between the fill and the image. */
      FillRect(dc, &client, (HBRUSH)GetStockObject(BLACK_BRUSH));
      if (have_viewport)
        StretchDIBits(dc, viewport.x, viewport.y, viewport.width, viewport.height,
                      0, 0, ANVIL_WIDTH, ANVIL_HEIGHT,
                      anvil_display_pixels ? anvil_display_pixels : anvil_pixels,
                      &anvil_bitmap_info, DIB_RGB_COLORS, SRCCOPY);
    }
    EndPaint(window, &ps);
    return 0;
  }
  }
  return DefWindowProcA(window, message, wparam, lparam);
}

/* ---- Saves -------------------------------------------------------------
   A small key/value store for game state: one number or one text value per
   named slot, written atomically into %LOCALAPPDATA%\Anvil\<project> (or
   $ANVIL_SAVE_DIR when a host sets it). Each file carries a magic and a type
   byte so a wrong-type read is a readable error instead of a reinterpreted
   value, and slot names are restricted to a safe character set so a save can
   never escape its directory. */
enum {
  ANVIL_SAVE_SLOT_MAX = 64,
  ANVIL_SAVE_TEXT_MAX = 255,
  ANVIL_SAVE_BUFFERS = 8
};

static const char ANVIL_SAVE_MAGIC[8] = {'A', 'N', 'V', 'S',
                                         'A', 'V', 'E', '1'};
static char anvil_project_name[64] = "Anvil Game";
static char anvil_save_error_detail[192];
static const char *anvil_save_error_text = "";
static char anvil_save_buffers[ANVIL_SAVE_BUFFERS][ANVIL_SAVE_TEXT_MAX + 1];
static int anvil_save_buffer_index;

static void anvil_save_error_note(const char *format, ...) {
  va_list arguments;
  va_start(arguments, format);
  _vsnprintf_s(anvil_save_error_detail, sizeof(anvil_save_error_detail),
               _TRUNCATE, format, arguments);
  va_end(arguments);
  anvil_save_error_text = anvil_save_error_detail;
}

const char *anvil_save_error(void) { return anvil_save_error_text; }

void anvil_set_project(const char *name) {
  if (!name || name[0] == '\0')
    return;
  size_t index = 0;
  for (; name[index] != '\0' && index < sizeof(anvil_project_name) - 1; ++index) {
    char c = name[index];
    int safe = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
               (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_';
    anvil_project_name[index] = safe ? c : '_';
  }
  anvil_project_name[index] = '\0';
  if (anvil_project_name[0] == '\0' ||
      strcmp(anvil_project_name, ".") == 0 ||
      strcmp(anvil_project_name, "..") == 0)
    strcpy_s(anvil_project_name, sizeof(anvil_project_name), "Anvil Game");
}

static int anvil_save_slot_ok(const char *slot) {
  if (!slot || slot[0] == '\0')
    return 0;
  size_t length = strlen(slot);
  if (length > ANVIL_SAVE_SLOT_MAX)
    return 0;
  if (slot[0] == '.')
    return 0;
  for (size_t i = 0; i < length; ++i) {
    char c = slot[i];
    int safe = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
               (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_';
    if (!safe)
      return 0;
  }
  return strstr(slot, "..") == NULL;
}

/* Create every missing component of a path that names a directory. */
static int anvil_save_make_dirs(const char *path) {
  char buffer[MAX_PATH];
  size_t length = strlen(path);
  if (length == 0 || length >= sizeof(buffer))
    return 0;
  memcpy(buffer, path, length + 1);
  for (size_t i = 1; i < length; ++i) {
    if (buffer[i] == '\\' || buffer[i] == '/') {
      char saved = buffer[i];
      buffer[i] = '\0';
      if (!CreateDirectoryA(buffer, NULL) &&
          GetLastError() != ERROR_ALREADY_EXISTS) {
        buffer[i] = saved;
        return 0;
      }
      buffer[i] = saved;
    }
  }
  if (!CreateDirectoryA(buffer, NULL) && GetLastError() != ERROR_ALREADY_EXISTS)
    return 0;
  return 1;
}

static int anvil_save_root(char *destination, size_t capacity) {
  const char *override = getenv("ANVIL_SAVE_DIR");
  if (override && override[0] != '\0') {
    if (strlen(override) >= capacity - 1)
      return 0;
    strcpy_s(destination, capacity, override);
    return 1;
  }
  const char *base = getenv("LOCALAPPDATA");
  if (!base || base[0] == '\0')
    base = ".";
  int written = _snprintf_s(destination, capacity, _TRUNCATE, "%s\\Anvil\\%s",
                            base, anvil_project_name);
  return written > 0;
}

static int anvil_save_path(const char *slot, const char *extension,
                           char *destination, size_t capacity) {
  if (!anvil_save_slot_ok(slot)) {
    anvil_save_error_text = "the save slot is invalid";
    return 0;
  }
  char root[MAX_PATH];
  if (!anvil_save_root(root, sizeof(root))) {
    anvil_save_error_text = "the save folder is too long";
    return 0;
  }
  int written = _snprintf_s(destination, capacity, _TRUNCATE, "%s\\%s.%s", root,
                            slot, extension);
  if (written <= 0) {
    anvil_save_error_text = "the save path is too long";
    return 0;
  }
  if (!anvil_save_make_dirs(root)) {
    anvil_save_error_text = "the save folder could not be created";
    return 0;
  }
  return 1;
}

static int anvil_save_write(const char *slot, unsigned char type,
                            const void *payload, size_t bytes) {
  char path[MAX_PATH];
  if (!anvil_save_path(slot, "sav", path, sizeof(path)))
    return 0;
  char temporary[MAX_PATH];
  int written = _snprintf_s(temporary, sizeof(temporary), _TRUNCATE, "%s.tmp",
                            path);
  if (written <= 0) {
    anvil_save_error_text = "the save path is too long";
    return 0;
  }
  FILE *file = fopen(temporary, "wb");
  if (!file) {
    anvil_save_error_text = "the save could not be opened for writing";
    return 0;
  }
  unsigned char header[9];
  memcpy(header, ANVIL_SAVE_MAGIC, sizeof(ANVIL_SAVE_MAGIC));
  header[8] = type;
  int ok = fwrite(header, 1, sizeof(header), file) == sizeof(header) &&
           fwrite(payload, 1, bytes, file) == bytes;
  ok = (fclose(file) == 0) && ok;
  if (!ok) {
    DeleteFileA(temporary);
    anvil_save_error_text = "the save could not be written";
    return 0;
  }
  if (!MoveFileExA(temporary, path, MOVEFILE_REPLACE_EXISTING)) {
    DeleteFileA(temporary);
    anvil_save_error_text = "the save could not replace the previous file";
    return 0;
  }
  anvil_save_error_text = "";
  return 1;
}

static int anvil_save_read(const char *slot, unsigned char expected,
                           void *payload, size_t bytes, int exact) {
  char path[MAX_PATH];
  if (!anvil_save_path(slot, "sav", path, sizeof(path)))
    return 0;
  FILE *file = fopen(path, "rb");
  if (!file) {
    /* A slot that was never written is a normal first run, not an error. */
    anvil_save_error_text = "";
    return 0;
  }
  unsigned char header[9];
  int ok = fread(header, 1, sizeof(header), file) == sizeof(header) &&
           memcmp(header, ANVIL_SAVE_MAGIC, sizeof(ANVIL_SAVE_MAGIC)) == 0;
  if (!ok) {
    fclose(file);
    anvil_save_error_text = "the save is not a readable Anvil save";
    return 0;
  }
  if (header[8] != expected) {
    fclose(file);
    anvil_save_error_text = expected == 1
                                ? "the save holds text, not a number"
                                : "the save holds a number, not text";
    return 0;
  }
  size_t got = fread(payload, 1, bytes, file);
  fclose(file);
  if (exact) {
    if (got != bytes) {
      anvil_save_error_text = "the save ended before its value did";
      return 0;
    }
  } else {
    /* Text is stored with its terminator; a shorter file is still valid. */
    if (got == bytes)
      got = bytes - 1;
    ((char *)payload)[got] = '\0';
  }
  anvil_save_error_text = "";
  return 1;
}

double anvil_save_number(const char *slot, double value) {
  double stored = value;
  return anvil_save_write(slot, 1, &stored, sizeof(stored)) ? 1.0 : 0.0;
}

double anvil_load_number(const char *slot) {
  double stored = 0.0;
  if (!anvil_save_read(slot, 1, &stored, sizeof(stored), 1))
    return 0.0;
  if (!isfinite(stored)) {
    anvil_save_error_text = "the save holds a non-finite number";
    return 0.0;
  }
  return stored;
}

double anvil_save_text(const char *slot, const char *text) {
  const char *value = text ? text : "";
  size_t length = strlen(value);
  if (length > ANVIL_SAVE_TEXT_MAX) {
    anvil_save_error_note(
        "the text is %llu bytes; the save limit is %d",
        (unsigned long long)length, ANVIL_SAVE_TEXT_MAX);
    return 0.0;
  }
  return anvil_save_write(slot, 2, value, length + 1) ? 1.0 : 0.0;
}

const char *anvil_load_text(const char *slot) {
  char *buffer = anvil_save_buffers[anvil_save_buffer_index &
                                    (ANVIL_SAVE_BUFFERS - 1)];
  anvil_save_buffer_index += 1;
  buffer[0] = '\0';
  if (!anvil_save_read(slot, 2, buffer, ANVIL_SAVE_TEXT_MAX + 1, 0))
    return buffer;
  buffer[ANVIL_SAVE_TEXT_MAX] = '\0';
  return buffer;
}

double anvil_save_exists(const char *slot) {
  char path[MAX_PATH];
  if (!anvil_save_path(slot, "sav", path, sizeof(path)))
    return 0.0;
  DWORD attributes = GetFileAttributesA(path);
  return attributes != INVALID_FILE_ATTRIBUTES ? 1.0 : 0.0;
}

double anvil_save_delete(const char *slot) {
  char path[MAX_PATH];
  if (!anvil_save_path(slot, "sav", path, sizeof(path)))
    return 0.0;
  if (DeleteFileA(path))
    return 1.0;
  return 0.0;
}

/* ---- Audio -------------------------------------------------------------
   A bounded WAV player: at most 16 loaded sounds, 8 simultaneous voices and
   48 MiB of decoded audio, mixed at 48 kHz stereo into three 10 ms buffers
   driven by waveOut. Everything is 16-bit PCM after load, so playback is a
   linear resample by pitch. The device is opened lazily on the first play and
   a missing or lost device degrades to silence with a readable error rather
   than a crash. */
enum {
  ANVIL_SOUND_SLOTS = 16,
  ANVIL_SOUND_VOICES = 8,
  ANVIL_AUDIO_RATE = 48000,
  ANVIL_AUDIO_FRAMES = 480,
  ANVIL_AUDIO_BUFFERS = 3,
  ANVIL_SOUND_SLOT_BYTES = 8 * 1024 * 1024,
  ANVIL_SOUND_TOTAL_BYTES = 48 * 1024 * 1024
};

typedef struct {
  short *frames;
  size_t frame_count;
  int used;
  int group;  /* 1..3; master is group 0 and applies to every sound */
} AnvilSound;

typedef struct {
  int sound;
  double position;
  double pitch;
  double volume;
  double pan;
  int loop;
} AnvilVoice;

/* AnvilAllocSite itself is declared up with the image table; the sound slots
   just need their own array of it. */
static AnvilAllocSite anvil_sound_sites[ANVIL_SOUND_SLOTS];

static AnvilSound anvil_sounds[ANVIL_SOUND_SLOTS];
static AnvilVoice anvil_voices[ANVIL_SOUND_VOICES];
/* Index 0 is the master gain; 1..3 are mixer groups. Muting is separate so a
   group keeps its volume while silent. */
static double anvil_group_gain[4] = {1.0, 1.0, 1.0, 1.0};
static int anvil_group_muted[4];
static CRITICAL_SECTION anvil_audio_lock;
static int anvil_audio_lock_ready;
static HWAVEOUT anvil_audio_device;
static WAVEHDR anvil_audio_headers[ANVIL_AUDIO_BUFFERS];
static short anvil_audio_buffers[ANVIL_AUDIO_BUFFERS][ANVIL_AUDIO_FRAMES * 2];
static HANDLE anvil_audio_event;
static HANDLE anvil_audio_thread;
static volatile LONG anvil_audio_running;
static char anvil_sound_error_detail[192];
static const char *anvil_sound_error_text = "";

static void anvil_sound_error_note(const char *format, ...) {
  va_list arguments;
  va_start(arguments, format);
  _vsnprintf_s(anvil_sound_error_detail, sizeof(anvil_sound_error_detail),
               _TRUNCATE, format, arguments);
  va_end(arguments);
  anvil_sound_error_text = anvil_sound_error_detail;
}

const char *anvil_sound_error(void) { return anvil_sound_error_text; }

static unsigned anvil_sound_u16(const unsigned char *bytes) {
  return (unsigned)bytes[0] | ((unsigned)bytes[1] << 8);
}

static unsigned long anvil_sound_u32(const unsigned char *bytes) {
  return (unsigned long)bytes[0] | ((unsigned long)bytes[1] << 8) |
         ((unsigned long)bytes[2] << 16) | ((unsigned long)bytes[3] << 24);
}

static int anvil_audio_lock_init(void) {
  if (!anvil_audio_lock_ready) {
    InitializeCriticalSection(&anvil_audio_lock);
    anvil_audio_lock_ready = 1;
  }
  return 1;
}

static void anvil_audio_shutdown(void);
static int anvil_audio_atexit_registered;

static void anvil_audio_at_exit(void) { anvil_audio_shutdown(); }

static void anvil_audio_register_atexit(void) {
  if (!anvil_audio_atexit_registered) {
    atexit(anvil_audio_at_exit);
    anvil_audio_atexit_registered = 1;
  }
}

static double anvil_audio_clamp(double value, double low, double high) {
  if (!isfinite(value))
    return low;
  if (value < low)
    return low;
  if (value > high)
    return high;
  return value;
}

/* ---- Streaming music ---------------------------------------------------
   One track at a time, decoded from disk as it plays instead of being held in
   memory. The mixer keeps an 8192-frame (about 170 ms) staging buffer that is
   refilled from the file; linear interpolation converts any source rate to the
   fixed 48 kHz mix. */
enum { ANVIL_MUSIC_BUFFER_FRAMES = 8192 };

typedef struct {
  FILE *file;
  long data_offset;
  long data_bytes;
  int frame_bytes;
  int channels;
  int bits;
  int rate;
  int loop;
  int playing;
  int draining;
  int adpcm;
  int block_align;
  int block_frames;
  unsigned char *block_bytes;
  short *block_pcm;
  int block_count;
  int block_index;
  long bytes_left;
  double volume;
  double length;
  double seconds;
  double step;
  double phase;
  short last_l, last_r, next_l, next_r;
  long frames_left;
} AnvilMusic;

static AnvilMusic anvil_music;
static short anvil_music_buffer[ANVIL_MUSIC_BUFFER_FRAMES * 2];
static size_t anvil_music_buffer_frames, anvil_music_buffer_index;
static const char *anvil_music_error_text = "";
static int anvil_music_volume_seeded;

static int anvil_music_read_frame(short *left, short *right) {
  if (anvil_music.adpcm) {
    if (anvil_music.block_index >= anvil_music.block_count) {
      if (anvil_music.bytes_left < anvil_music.block_align) {
        if (!anvil_music.loop)
          return 0;
        fseek(anvil_music.file, anvil_music.data_offset, SEEK_SET);
        anvil_music.bytes_left = anvil_music.data_bytes;
      }
      if (fread(anvil_music.block_bytes, 1, (size_t)anvil_music.block_align,
                anvil_music.file) != (size_t)anvil_music.block_align) {
        if (!anvil_music.loop)
          return 0;
        fseek(anvil_music.file, anvil_music.data_offset, SEEK_SET);
        anvil_music.bytes_left = anvil_music.data_bytes;
        if (fread(anvil_music.block_bytes, 1, (size_t)anvil_music.block_align,
                  anvil_music.file) != (size_t)anvil_music.block_align)
          return 0;
      }
      anvil_music.bytes_left -= anvil_music.block_align;
      anvil_music.block_count = anvil_ima_decode_block(
          anvil_music.block_bytes, anvil_music.block_align,
          anvil_music.channels, anvil_music.block_pcm);
      anvil_music.block_index = 0;
      if (anvil_music.block_count <= 0)
        return 0;
    }
    int at = anvil_music.block_index * anvil_music.channels;
    *left = anvil_music.block_pcm[at];
    *right = anvil_music.channels == 2 ? anvil_music.block_pcm[at + 1] : *left;
    anvil_music.block_index++;
    return 1;
  }
  unsigned char raw[6];
  size_t bytes = (size_t)anvil_music.frame_bytes;
  if (anvil_music.frames_left <= 0) {
    if (!anvil_music.loop)
      return 0;
    fseek(anvil_music.file, anvil_music.data_offset, SEEK_SET);
    anvil_music.frames_left = anvil_music.data_bytes / anvil_music.frame_bytes;
    if (anvil_music.frames_left <= 0)
      return 0;
  }
  if (fread(raw, 1, bytes, anvil_music.file) != bytes) {
    if (!anvil_music.loop)
      return 0;
    fseek(anvil_music.file, anvil_music.data_offset, SEEK_SET);
    anvil_music.frames_left = anvil_music.data_bytes / anvil_music.frame_bytes;
    if (fread(raw, 1, bytes, anvil_music.file) != bytes)
      return 0;
  }
  anvil_music.frames_left--;
  if (anvil_music.bits == 16) {
    *left = (short)(raw[0] | (raw[1] << 8));
    *right = anvil_music.channels == 2 ? (short)(raw[2] | (raw[3] << 8)) : *left;
  } else {
    *left = (short)((raw[0] - 128) << 8);
    *right = anvil_music.channels == 2 ? (short)((raw[1] - 128) << 8) : *left;
  }
  return 1;
}

static void anvil_music_prime(void) {
  anvil_music.phase = 0.0;
  anvil_music_buffer_frames = 0;
  anvil_music_buffer_index = 0;
  if (!anvil_music_read_frame(&anvil_music.last_l, &anvil_music.last_r)) {
    anvil_music.last_l = anvil_music.last_r = 0;
    anvil_music.next_l = anvil_music.next_r = 0;
    return;
  }
  if (!anvil_music_read_frame(&anvil_music.next_l, &anvil_music.next_r)) {
    anvil_music.next_l = anvil_music.last_l;
    anvil_music.next_r = anvil_music.last_r;
  }
}

static void anvil_music_fill(void) {
  size_t produced = 0;
  anvil_music_buffer_index = 0;
  anvil_music_buffer_frames = 0;
  while (produced < ANVIL_MUSIC_BUFFER_FRAMES) {
    while (anvil_music.phase >= 1.0) {
      anvil_music.last_l = anvil_music.next_l;
      anvil_music.last_r = anvil_music.next_r;
      if (!anvil_music_read_frame(&anvil_music.next_l, &anvil_music.next_r)) {
        anvil_music.draining = 1;
        anvil_music_buffer_frames = produced;
        return;
      }
      anvil_music.phase -= 1.0;
    }
    double fraction = anvil_music.phase;
    anvil_music_buffer[produced * 2] = (short)lrint(
        anvil_music.last_l + (anvil_music.next_l - anvil_music.last_l) * fraction);
    anvil_music_buffer[produced * 2 + 1] = (short)lrint(
        anvil_music.last_r + (anvil_music.next_r - anvil_music.last_r) * fraction);
    produced++;
    anvil_music.phase += anvil_music.step;
    anvil_music.seconds += 1.0 / 48000.0;
    if (anvil_music.length > 0.0 && anvil_music.seconds >= anvil_music.length)
      anvil_music.seconds -= anvil_music.length;
  }
  anvil_music_buffer_frames = produced;
}

static void anvil_audio_mix(short *out, int frames) {
  memset(out, 0, (size_t)frames * 2 * sizeof(short));
  if (!anvil_audio_lock_ready)
    return;
  EnterCriticalSection(&anvil_audio_lock);
  for (int v = 0; v < ANVIL_SOUND_VOICES; ++v) {
    AnvilVoice *voice = &anvil_voices[v];
    if (!voice->sound)
      continue;
    AnvilSound *sound = &anvil_sounds[voice->sound - 1];
    if (!sound->used || !sound->frames || sound->frame_count == 0) {
      voice->sound = 0;
      continue;
    }
    double master = anvil_group_muted[0] ? 0.0 : anvil_group_gain[0];
    int group = sound->group >= 1 && sound->group <= 3 ? sound->group : 1;
    double group_gain = anvil_group_muted[group] ? 0.0 : anvil_group_gain[group];
    double gain = voice->volume * group_gain * master;
    double left = gain * (voice->pan > 0.0 ? 1.0 - voice->pan : 1.0);
    double right = gain * (voice->pan < 0.0 ? 1.0 + voice->pan : 1.0);
    for (int i = 0; i < frames; ++i) {
      if (voice->position >= (double)sound->frame_count) {
        if (!voice->loop) {
          voice->sound = 0;
          break;
        }
        voice->position -= (double)sound->frame_count;
      }
      size_t index = (size_t)voice->position;
      double fraction = voice->position - (double)index;
      size_t next = index + 1 < sound->frame_count ? index + 1 : index;
      double l = (double)sound->frames[index * 2] +
                 ((double)sound->frames[next * 2] -
                  (double)sound->frames[index * 2]) * fraction;
      double r = (double)sound->frames[index * 2 + 1] +
                 ((double)sound->frames[next * 2 + 1] -
                  (double)sound->frames[index * 2 + 1]) * fraction;
      int sl = (int)out[i * 2] + (int)(l * left);
      int sr = (int)out[i * 2 + 1] + (int)(r * right);
      out[i * 2] = (short)(sl < -32768 ? -32768 : sl > 32767 ? 32767 : sl);
      out[i * 2 + 1] =
          (short)(sr < -32768 ? -32768 : sr > 32767 ? 32767 : sr);
      voice->position += voice->pitch;
    }
  }
  if (anvil_music.playing) {
    if (anvil_music_buffer_index >= anvil_music_buffer_frames)
      anvil_music_fill();
    size_t available = anvil_music_buffer_frames - anvil_music_buffer_index;
    size_t use = available < (size_t)frames ? available : (size_t)frames;
    double gain = anvil_music.volume * (anvil_group_muted[0] ? 0.0 : anvil_group_gain[0]);
    for (size_t i = 0; i < use; ++i) {
      int sl = (int)out[i * 2] +
               (int)(anvil_music_buffer[(anvil_music_buffer_index + i) * 2] * gain);
      int sr = (int)out[i * 2 + 1] +
               (int)(anvil_music_buffer[(anvil_music_buffer_index + i) * 2 + 1] * gain);
      out[i * 2] = (short)(sl < -32768 ? -32768 : sl > 32767 ? 32767 : sl);
      out[i * 2 + 1] =
          (short)(sr < -32768 ? -32768 : sr > 32767 ? 32767 : sr);
    }
    anvil_music_buffer_index += use;
    if (use == 0 && anvil_music.draining)
      anvil_music.playing = 0;
  }
  LeaveCriticalSection(&anvil_audio_lock);
}

static DWORD WINAPI anvil_audio_thread_main(LPVOID parameter) {
  (void)parameter;
  while (anvil_audio_running) {
    DWORD wait = WaitForSingleObject(anvil_audio_event, 50);
    if (!anvil_audio_running)
      break;
    if (wait != WAIT_OBJECT_0 && wait != WAIT_TIMEOUT)
      break;
    for (int i = 0; i < ANVIL_AUDIO_BUFFERS; ++i) {
      WAVEHDR *header = &anvil_audio_headers[i];
      if ((header->dwFlags & WHDR_DONE) == 0)
        continue;
      anvil_audio_mix(anvil_audio_buffers[i], ANVIL_AUDIO_FRAMES);
      header->dwFlags &= ~WHDR_DONE;
      if (waveOutWrite(anvil_audio_device, header, sizeof(WAVEHDR)) !=
          MMSYSERR_NOERROR) {
        /* Device loss: stop mixing and let the next play retry the device. */
        anvil_audio_running = 0;
        anvil_sound_error_text = "the audio device was lost";
        break;
      }
    }
  }
  return 0;
}

static int anvil_audio_start(void) {
  if (anvil_audio_device)
    return 1;
  anvil_audio_lock_init();
  anvil_audio_register_atexit();
  if (!anvil_audio_event)
    anvil_audio_event = CreateEventA(NULL, FALSE, FALSE, NULL);
  if (!anvil_audio_event) {
    anvil_sound_error_text = "the audio event could not be created";
    return 0;
  }
  WAVEFORMATEX format;
  memset(&format, 0, sizeof(format));
  format.wFormatTag = WAVE_FORMAT_PCM;
  format.nChannels = 2;
  format.nSamplesPerSec = ANVIL_AUDIO_RATE;
  format.wBitsPerSample = 16;
  format.nBlockAlign = (WORD)(format.nChannels * format.wBitsPerSample / 8);
  format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;
  if (waveOutOpen(&anvil_audio_device, WAVE_MAPPER, &format,
                  (DWORD_PTR)anvil_audio_event, 0, CALLBACK_EVENT) !=
      MMSYSERR_NOERROR) {
    anvil_audio_device = NULL;
    anvil_sound_error_text = "the audio device is unavailable";
    return 0;
  }
  memset(anvil_audio_headers, 0, sizeof(anvil_audio_headers));
  for (int i = 0; i < ANVIL_AUDIO_BUFFERS; ++i) {
    WAVEHDR *header = &anvil_audio_headers[i];
    header->lpData = (LPSTR)anvil_audio_buffers[i];
    header->dwBufferLength = (DWORD)sizeof(anvil_audio_buffers[i]);
    if (waveOutPrepareHeader(anvil_audio_device, header, sizeof(WAVEHDR)) !=
        MMSYSERR_NOERROR) {
      waveOutClose(anvil_audio_device);
      anvil_audio_device = NULL;
      anvil_sound_error_text = "the audio buffers could not be prepared";
      return 0;
    }
    anvil_audio_mix(anvil_audio_buffers[i], ANVIL_AUDIO_FRAMES);
    waveOutWrite(anvil_audio_device, header, sizeof(WAVEHDR));
  }
  anvil_audio_running = 1;
  anvil_audio_thread =
      CreateThread(NULL, 0, anvil_audio_thread_main, NULL, 0, NULL);
  if (!anvil_audio_thread) {
    anvil_audio_running = 0;
    waveOutReset(anvil_audio_device);
    for (int i = 0; i < ANVIL_AUDIO_BUFFERS; ++i)
      waveOutUnprepareHeader(anvil_audio_device, &anvil_audio_headers[i],
                             sizeof(WAVEHDR));
    waveOutClose(anvil_audio_device);
    anvil_audio_device = NULL;
    anvil_sound_error_text = "the audio thread could not be started";
    return 0;
  }
  return 1;
}

static void anvil_audio_shutdown(void) {
  if (anvil_audio_thread) {
    anvil_audio_running = 0;
    if (anvil_audio_event)
      SetEvent(anvil_audio_event);
    WaitForSingleObject(anvil_audio_thread, 2000);
    CloseHandle(anvil_audio_thread);
    anvil_audio_thread = NULL;
  }
  if (anvil_audio_device) {
    waveOutReset(anvil_audio_device);
    for (int i = 0; i < ANVIL_AUDIO_BUFFERS; ++i)
      waveOutUnprepareHeader(anvil_audio_device, &anvil_audio_headers[i],
                             sizeof(WAVEHDR));
    waveOutClose(anvil_audio_device);
    anvil_audio_device = NULL;
  }
  if (anvil_audio_event) {
    CloseHandle(anvil_audio_event);
    anvil_audio_event = NULL;
  }
  if (anvil_audio_lock_ready) {
    EnterCriticalSection(&anvil_audio_lock);
    memset(anvil_voices, 0, sizeof(anvil_voices));
    LeaveCriticalSection(&anvil_audio_lock);
  }
  for (int i = 0; i < ANVIL_SOUND_SLOTS; ++i) {
    free(anvil_sounds[i].frames);
    memset(&anvil_sounds[i], 0, sizeof(anvil_sounds[i]));
  }
  anvil_sound_bytes = 0;
}

/* Load a PCM WAV and convert it to the mixer's 48 kHz stereo 16-bit form. */
/* ---- IMA ADPCM ---------------------------------------------------------
   Standard 4-bit IMA ADPCM blocks as written by WAV format tag 0x0011: each
   channel starts with a 4-byte header (int16 predictor, step index, reserved)
   followed by 4-byte groups of nibbles per channel, low nibble first. */
static const int anvil_ima_step[89] = {
    7,     8,     9,     10,    11,    12,    13,    14,    16,    17,
    19,    21,    23,    25,    28,    31,    34,    37,    41,    45,
    50,    55,    60,    66,    73,    80,    88,    97,    107,   118,
    130,   143,   157,   173,   190,   209,   230,   253,   279,   307,
    337,   371,   408,   449,   494,   544,   598,   658,   724,   796,
    876,   963,   1060,  1166,  1282,  1411,  1552,  1707,  1878,  2066,
    2272,  2499,  2749,  3024,  3327,  3660,  4026,  4428,  4871,  5358,
    5894,  6484,  7132,  7845,  8630,  9493,  10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};

static const int anvil_ima_index[16] = {-1, -1, -1, -1, 2, 4, 6, 8,
                                        -1, -1, -1, -1, 2, 4, 6, 8};

static int anvil_ima_nibble(int nibble, int *predictor, int *index) {
  int step = anvil_ima_step[*index];
  int diff = step >> 3;
  if (nibble & 1)
    diff += step >> 2;
  if (nibble & 2)
    diff += step >> 1;
  if (nibble & 4)
    diff += step;
  if (nibble & 8)
    diff = -diff;
  *predictor += diff;
  if (*predictor > 32767)
    *predictor = 32767;
  if (*predictor < -32768)
    *predictor = -32768;
  *index += anvil_ima_index[nibble];
  if (*index < 0)
    *index = 0;
  if (*index > 88)
    *index = 88;
  return *predictor;
}

static int anvil_ima_decode_block(const unsigned char *block, int block_align,
                                  int channels, short *out) {
  if (!block || block_align < 4 * channels + 4 || channels < 1 || channels > 2)
    return 0;
  int predictor[2] = {0, 0}, index[2] = {0, 0};
  for (int ch = 0; ch < channels; ++ch) {
    int at = ch * 4;
    predictor[ch] = (short)((unsigned)block[at] | ((unsigned)block[at + 1] << 8));
    index[ch] = block[at + 2];
    if (index[ch] > 88)
      index[ch] = 88;
    out[ch] = (short)predictor[ch];
  }
  int max_frames = (block_align - 4 * channels) * 2 / channels + 1;
  int frame = 1;
  int offset = 4 * channels;
  while (frame < max_frames) {
    for (int ch = 0; ch < channels; ++ch) {
      for (int byte = 0; byte < 4 && offset < block_align; ++byte) {
        unsigned char value = block[offset++];
        for (int half = 0; half < 2; ++half) {
          int nibble = half == 0 ? (value & 0x0F) : (value >> 4);
          int sample = anvil_ima_nibble(nibble, &predictor[ch], &index[ch]);
          int target = frame + byte * 2 + half;
          if (target < max_frames)
            out[target * channels + ch] = (short)sample;
        }
      }
    }
    frame += 8;
  }
  return max_frames;
}

double anvil_sound_load(const char *path) {
  anvil_sound_error_text = "";
  if (!path || path[0] == '\0') {
    anvil_sound_error_text = "the path is empty";
    return 0.0;
  }
  int slot = -1;
  for (int i = 0; i < ANVIL_SOUND_SLOTS; ++i) {
    if (!anvil_sounds[i].used) {
      slot = i;
      break;
    }
  }
  if (slot < 0) {
    anvil_sound_error_text = "no free sound slot";
    return 0.0;
  }
  FILE *file = fopen(path, "rb");
  if (!file) {
    anvil_sound_error_text = "cannot open the file";
    return 0.0;
  }
  unsigned char riff[12];
  if (fread(riff, 1, 12, file) != 12 || memcmp(riff, "RIFF", 4) != 0 ||
      memcmp(riff + 8, "WAVE", 4) != 0) {
    fclose(file);
    anvil_sound_error_text = "the file is not a readable WAV";
    return 0.0;
  }
  unsigned channels = 0, bits = 0, format = 0, rate = 0, block = 0;
  long data_offset = -1;
  unsigned long data_size = 0;
  const char *parse_error = NULL;
  for (;;) {
    unsigned char chunk[8];
    if (fread(chunk, 1, 8, file) != 8)
      break;
    unsigned long size = anvil_sound_u32(chunk + 4);
    if (memcmp(chunk, "fmt ", 4) == 0) {
      unsigned char fmt[16];
      if (size < 16 || fread(fmt, 1, 16, file) != 16) {
        parse_error = "the WAV format chunk is truncated";
        break;
      }
      format = anvil_sound_u16(fmt);
      channels = anvil_sound_u16(fmt + 2);
      rate = anvil_sound_u32(fmt + 4);
      block = anvil_sound_u16(fmt + 12);
      bits = anvil_sound_u16(fmt + 14);
      if (size > 16)
        fseek(file, (long)(size - 16), SEEK_CUR);
    } else if (memcmp(chunk, "data", 4) == 0) {
      data_offset = ftell(file);
      data_size = size;
      fseek(file, (long)size, SEEK_CUR);
    } else {
      fseek(file, (long)size, SEEK_CUR);
    }
    if (size & 1)
      fseek(file, 1, SEEK_CUR);
    if (data_offset >= 0 && channels)
      break;
  }
  if (!parse_error) {
    if (format == 0 || channels == 0)
      parse_error = "the file has no format chunk";
    else if (format != 1 && format != 17)
      parse_error = "only PCM and IMA ADPCM WAV files are supported";
    else if (channels != 1 && channels != 2)
      parse_error = "only mono or stereo WAV is supported";
    else if (format == 1 && bits != 8 && bits != 16)
      parse_error = "only 8- or 16-bit PCM WAV is supported";
    else if (format == 17 && bits != 4)
      parse_error = "IMA ADPCM WAV files must be 4-bit";
    else if (rate < 8000 || rate > 192000)
      parse_error = "the sample rate is outside 8000..192000 Hz";
    else if (format == 1 && block != (unsigned)channels * (bits / 8))
      parse_error = "the WAV block alignment is inconsistent";
    else if (format == 17 && (block < 4u * channels + 4u || block > 4096u))
      parse_error = "the ADPCM block alignment is invalid";
    else if (data_offset < 0)
      parse_error = "the file has no data chunk";
  }
  if (parse_error) {
    fclose(file);
    anvil_sound_error_text = parse_error;
    return 0.0;
  }
  size_t samples_per_block = 0;
  size_t source_frames = 0;
  if (format == 17) {
    samples_per_block = (size_t)(block - 4 * channels) * 2 / channels + 1;
    source_frames = (size_t)(data_size / block) * samples_per_block;
  } else {
    source_frames = (size_t)(data_size / block);
  }
  size_t frame_count =
      (size_t)((double)source_frames * (double)ANVIL_AUDIO_RATE / (double)rate +
               0.5);
  size_t bytes = frame_count * 2 * sizeof(short);
  if (frame_count == 0) {
    fclose(file);
    anvil_sound_error_text = "the WAV has no audio frames";
    return 0.0;
  }
  if (bytes > (size_t)ANVIL_SOUND_SLOT_BYTES) {
    fclose(file);
    anvil_sound_error_note(
        "the sound needs %llu KiB decoded; the per-sound limit is %d KiB",
        (unsigned long long)(bytes / 1024), ANVIL_SOUND_SLOT_BYTES / 1024);
    return 0.0;
  }
  if (anvil_sound_bytes + bytes > (size_t)ANVIL_SOUND_TOTAL_BYTES) {
    fclose(file);
    anvil_sound_error_note(
        "loading the sound would exceed the %d MiB audio budget",
        ANVIL_SOUND_TOTAL_BYTES / (1024 * 1024));
    return 0.0;
  }
  unsigned char *source = NULL;
  short *frames = (short *)malloc(bytes);
  if (format == 17) {
    size_t decoded_bytes = source_frames * channels * sizeof(short);
    if (decoded_bytes > 64u * 1024u * 1024u) {
      free(frames);
      fclose(file);
      anvil_sound_error_text =
          "the ADPCM sound decodes to more than the 64 MiB decode budget";
      return 0.0;
    }
    unsigned char *block_bytes = (unsigned char *)malloc(block);
    short *decoded = (short *)malloc(decoded_bytes ? decoded_bytes : 1);
    if (!block_bytes || !decoded || !frames) {
      free(block_bytes);
      free(decoded);
      free(frames);
      fclose(file);
      anvil_sound_error_text = "the sound could not be allocated";
      return 0.0;
    }
    if (fseek(file, data_offset, SEEK_SET) != 0) {
      free(block_bytes);
      free(decoded);
      free(frames);
      fclose(file);
      anvil_sound_error_text = "the file ended before the sound data did";
      return 0.0;
    }
    size_t blocks = (size_t)(data_size / block);
    for (size_t b = 0; b < blocks; ++b) {
      if (fread(block_bytes, 1, block, file) != (size_t)block) {
        free(block_bytes);
        free(decoded);
        free(frames);
        fclose(file);
        anvil_sound_error_text = "the file ended before the sound data did";
        return 0.0;
      }
      anvil_ima_decode_block(block_bytes, (int)block, (int)channels,
                             decoded + b * samples_per_block * channels);
    }
    free(block_bytes);
    source = (unsigned char *)decoded;
    bits = 16;
  } else {
    source = (unsigned char *)malloc(data_size ? data_size : 1);
    if (!source || !frames) {
      free(source);
      free(frames);
      fclose(file);
      anvil_sound_error_text = "the sound could not be allocated";
      return 0.0;
    }
    if (fseek(file, data_offset, SEEK_SET) != 0 ||
        fread(source, 1, data_size, file) != data_size) {
      free(source);
      free(frames);
      fclose(file);
      anvil_sound_error_text = "the file ended before the sound data did";
      return 0.0;
    }
  }
  fclose(file);
  for (size_t i = 0; i < frame_count; ++i) {
    double position = (double)i * (double)rate / (double)ANVIL_AUDIO_RATE;
    size_t index = (size_t)position;
    double fraction = position - (double)index;
    if (index >= source_frames)
      index = source_frames - 1;
    size_t next = index + 1 < source_frames ? index + 1 : index;
    for (int channel = 0; channel < 2; ++channel) {
      int source_channel = channels == 1 ? 0 : channel;
      double first, second;
      if (bits == 16) {
        size_t at = (index * channels + (size_t)source_channel) * 2;
        size_t after = (next * channels + (size_t)source_channel) * 2;
        first = (double)(short)((unsigned)source[at] |
                                ((unsigned)source[at + 1] << 8));
        second = (double)(short)((unsigned)source[after] |
                                 ((unsigned)source[after + 1] << 8));
      } else {
        size_t at = index * channels + (size_t)source_channel;
        size_t after = next * channels + (size_t)source_channel;
        first = ((double)source[at] - 128.0) * 256.0;
        second = ((double)source[after] - 128.0) * 256.0;
      }
      double value = first + (second - first) * fraction;
      frames[i * 2 + channel] =
          (short)(value < -32768.0 ? -32768 : value > 32767.0 ? 32767 : value);
    }
  }
  free(source);
  anvil_sounds[slot].frames = frames;
  anvil_sounds[slot].frame_count = frame_count;
  anvil_sounds[slot].used = 1;
  anvil_sounds[slot].group = 1;
  anvil_sound_bytes += bytes;
  return (double)(slot + 1);
}

double anvil_sound_load_site(const char *path, const char *file, int line) {
  double handle = anvil_sound_load(path);
  if (handle >= 1.0 && handle <= (double)ANVIL_SOUND_SLOTS) {
    int slot = (int)handle - 1;
    anvil_sound_sites[slot].file = file;
    anvil_sound_sites[slot].path = path;
    anvil_sound_sites[slot].line = line;
    anvil_capture_site(&anvil_sound_sites[slot]);
  }
  return handle;
}

/* Print every live image and sound with its size and the source line that
   created it. Returns the number of live allocations so a program can react
   (for example, log a warning above a threshold). Lives down here because it
   walks the sound table, which is only defined in this section. */
double anvil_memory_report(void) {
  int live = 0;
  size_t image_bytes = 0, audio_bytes = 0;
  printf("Anvil memory report\n");
  for (int i = 0; i < ANVIL_IMAGES; ++i) {
    if (!anvil_images[i].pixels)
      continue;
    size_t bytes = (size_t)anvil_images[i].width * (size_t)anvil_images[i].height * 4u;
    image_bytes += bytes;
    printf("  image %d  %dx%d  %llu bytes  ", i, anvil_images[i].width,
           anvil_images[i].height, (unsigned long long)bytes);
    anvil_print_site(&anvil_image_sites[i]);
    ++live;
  }
  for (int i = 0; i < ANVIL_SOUND_SLOTS; ++i) {
    if (!anvil_sounds[i].used)
      continue;
    size_t bytes = anvil_sounds[i].frame_count * 2u * sizeof(short);
    audio_bytes += bytes;
    printf("  sound %d  %llu frames  %llu bytes  ", i,
           (unsigned long long)anvil_sounds[i].frame_count,
           (unsigned long long)bytes);
    anvil_print_site(&anvil_sound_sites[i]);
    ++live;
  }
  printf("  live allocations: %d  (%llu image bytes, %llu audio bytes)\n", live,
         (unsigned long long)image_bytes, (unsigned long long)audio_bytes);
  fflush(stdout);
  return (double)live;
}

static int anvil_sound_valid(double handle) {
  if (!isfinite(handle) || handle < 1.0 || handle > (double)ANVIL_SOUND_SLOTS ||
      floor(handle) != handle)
    return 0;
  return anvil_sounds[(int)handle - 1].used;
}

static int anvil_voice_valid(double handle) {
  if (!isfinite(handle) || handle < 1.0 || handle > (double)ANVIL_SOUND_VOICES ||
      floor(handle) != handle)
    return 0;
  return anvil_voices[(int)handle - 1].sound != 0;
}

static double anvil_sound_play_internal(double handle, int loop) {
  anvil_sound_error_text = "";
  if (!anvil_sound_valid(handle)) {
    anvil_sound_error_text = "the sound handle is not loaded";
    return 0.0;
  }
  if (!anvil_audio_start())
    return 0.0;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  int voice = -1;
  for (int i = 0; i < ANVIL_SOUND_VOICES; ++i) {
    if (!anvil_voices[i].sound) {
      voice = i;
      break;
    }
  }
  if (voice < 0) {
    LeaveCriticalSection(&anvil_audio_lock);
    anvil_sound_error_text = "all voices are busy";
    return 0.0;
  }
  anvil_voices[voice].sound = (int)handle;
  anvil_voices[voice].position = 0.0;
  anvil_voices[voice].pitch = 1.0;
  anvil_voices[voice].volume = 1.0;
  anvil_voices[voice].pan = 0.0;
  anvil_voices[voice].loop = loop;
  LeaveCriticalSection(&anvil_audio_lock);
  return (double)(voice + 1);
}

double anvil_sound_play(double handle) {
  return anvil_sound_play_internal(handle, 0);
}

double anvil_sound_play_loop(double handle) {
  return anvil_sound_play_internal(handle, 1);
}

double anvil_sound_stop(double voice_handle) {
  if (!anvil_voice_valid(voice_handle))
    return 0.0;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  memset(&anvil_voices[(int)voice_handle - 1], 0, sizeof(AnvilVoice));
  LeaveCriticalSection(&anvil_audio_lock);
  return 1.0;
}

double anvil_sound_stop_all(void) {
  if (!anvil_audio_lock_ready)
    return 0.0;
  int stopped = 0;
  EnterCriticalSection(&anvil_audio_lock);
  for (int i = 0; i < ANVIL_SOUND_VOICES; ++i) {
    if (anvil_voices[i].sound) {
      memset(&anvil_voices[i], 0, sizeof(AnvilVoice));
      stopped++;
    }
  }
  LeaveCriticalSection(&anvil_audio_lock);
  return (double)stopped;
}

/* Mixer groups: 0 is the master gain, 1..3 are assignable groups. A sound is
   in group 1 until moved, so existing programs are unaffected. */
static int anvil_sound_group_index(double value, int allow_master) {
  int low = allow_master ? 0 : 1;
  if (!isfinite(value) || value < (double)low || value > 3.0 ||
      floor(value) != value)
    return -1;
  return (int)value;
}

double anvil_sound_group(double handle, double group) {
  int index = anvil_sound_group_index(group, 0);
  if (!anvil_sound_valid(handle) || index < 0)
    return 0.0;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_sounds[(int)handle - 1].group = index;
  LeaveCriticalSection(&anvil_audio_lock);
  return (double)index;
}

double anvil_sound_group_volume(double group, double volume) {
  int index = anvil_sound_group_index(group, 1);
  if (index < 0)
    return 0.0;
  double applied = anvil_audio_clamp(volume, 0.0, 1.0);
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_group_gain[index] = applied;
  LeaveCriticalSection(&anvil_audio_lock);
  return applied;
}

double anvil_sound_group_mute(double group, double on) {
  int index = anvil_sound_group_index(group, 1);
  if (index < 0)
    return 0.0;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_group_muted[index] = on != 0.0;
  int muted = anvil_group_muted[index];
  LeaveCriticalSection(&anvil_audio_lock);
  return muted ? 1.0 : 0.0;
}

double anvil_sound_group_gain(double group) {
  int index = anvil_sound_group_index(group, 1);
  if (index < 0 || anvil_group_muted[index])
    return 0.0;
  return anvil_group_gain[index];
}

double anvil_sound_group_stop(double group) {
  int index = anvil_sound_group_index(group, 1);
  if (index < 0 || !anvil_audio_lock_ready)
    return 0.0;
  int stopped = 0;
  EnterCriticalSection(&anvil_audio_lock);
  for (int i = 0; i < ANVIL_SOUND_VOICES; ++i) {
    if (!anvil_voices[i].sound)
      continue;
    int slot = anvil_voices[i].sound - 1;
    int voice_group = anvil_sounds[slot].used ? anvil_sounds[slot].group : 0;
    if (index == 0 || voice_group == index) {
      memset(&anvil_voices[i], 0, sizeof(AnvilVoice));
      stopped++;
    }
  }
  LeaveCriticalSection(&anvil_audio_lock);
  return (double)stopped;
}

double anvil_sound_volume(double voice_handle, double volume) {
  if (!anvil_voice_valid(voice_handle))
    return 0.0;
  double applied = anvil_audio_clamp(volume, 0.0, 1.0);
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_voices[(int)voice_handle - 1].volume = applied;
  LeaveCriticalSection(&anvil_audio_lock);
  return applied;
}

double anvil_sound_pan(double voice_handle, double pan) {
  if (!anvil_voice_valid(voice_handle))
    return 0.0;
  double applied = anvil_audio_clamp(pan, -1.0, 1.0);
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_voices[(int)voice_handle - 1].pan = applied;
  LeaveCriticalSection(&anvil_audio_lock);
  return applied;
}

double anvil_sound_pitch(double voice_handle, double pitch) {
  if (!anvil_voice_valid(voice_handle))
    return 0.0;
  double applied = anvil_audio_clamp(pitch, 0.25, 4.0);
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_voices[(int)voice_handle - 1].pitch = applied;
  LeaveCriticalSection(&anvil_audio_lock);
  return applied;
}

double anvil_sound_active(void) {
  if (!anvil_audio_lock_ready)
    return 0.0;
  int active = 0;
  EnterCriticalSection(&anvil_audio_lock);
  for (int i = 0; i < ANVIL_SOUND_VOICES; ++i)
    if (anvil_voices[i].sound)
      active++;
  LeaveCriticalSection(&anvil_audio_lock);
  return (double)active;
}

double anvil_sound_duration(double handle) {
  if (!anvil_sound_valid(handle))
    return 0.0;
  return (double)anvil_sounds[(int)handle - 1].frame_count / 48000.0;
}

double anvil_sound_rms(double handle) {
  if (!anvil_sound_valid(handle))
    return 0.0;
  AnvilSound *sound = &anvil_sounds[(int)handle - 1];
  if (!sound->frames || sound->frame_count == 0)
    return 0.0;
  double total = 0.0;
  size_t samples = sound->frame_count * 2;
  for (size_t i = 0; i < samples; ++i) {
    double value = (double)sound->frames[i];
    total += value * value;
  }
  return sqrt(total / (double)samples);
}

double anvil_sound_destroy(double handle) {
  if (!anvil_sound_valid(handle))
    return 0.0;
  int slot = (int)handle - 1;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  for (int i = 0; i < ANVIL_SOUND_VOICES; ++i)
    if (anvil_voices[i].sound == slot + 1)
      memset(&anvil_voices[i], 0, sizeof(AnvilVoice));
  anvil_sound_bytes -= anvil_sounds[slot].frame_count * 2 * sizeof(short);
  free(anvil_sounds[slot].frames);
  memset(&anvil_sounds[slot], 0, sizeof(anvil_sounds[slot]));
  LeaveCriticalSection(&anvil_audio_lock);
  return 1.0;
}

/* ---- Streaming music API ----------------------------------------------- */

static int anvil_music_parse_wav(FILE *file, long *data_offset, long *data_bytes,
                                 int *channels, int *bits, int *rate,
                                 int *format_out, int *block_out) {
  unsigned char header[12];
  if (fread(header, 1, 12, file) != 12 || memcmp(header, "RIFF", 4) != 0 ||
      memcmp(header + 8, "WAVE", 4) != 0)
    return 0;
  int have_format = 0;
  for (;;) {
    unsigned char chunk[8];
    if (fread(chunk, 1, 8, file) != 8)
      return 0;
    unsigned long size = (unsigned long)chunk[4] |
                         ((unsigned long)chunk[5] << 8) |
                         ((unsigned long)chunk[6] << 16) |
                         ((unsigned long)chunk[7] << 24);
    if (memcmp(chunk, "fmt ", 4) == 0) {
      unsigned char fmt[16];
      if (size < 16 || fread(fmt, 1, 16, file) != 16)
        return 0;
      int format = fmt[0] | (fmt[1] << 8);
      *format_out = format;
      *channels = fmt[2] | (fmt[3] << 8);
      *rate = fmt[4] | (fmt[5] << 8) | (fmt[6] << 16) | (fmt[7] << 24);
      *bits = fmt[14] | (fmt[15] << 8);
      *block_out = fmt[12] | (fmt[13] << 8);
      have_format = 1;
      long skip = (long)size - 16;
      if (skip > 0)
        fseek(file, skip + (skip & 1), SEEK_CUR);
    } else if (memcmp(chunk, "data", 4) == 0) {
      if (!have_format)
        return 0;
      *data_offset = ftell(file);
      *data_bytes = (long)size;
      return 1;
    } else {
      fseek(file, (long)size + (long)(size & 1), SEEK_CUR);
    }
  }
}

double anvil_music_load(const char *path) {
  anvil_music_error_text = "";
  if (!path || path[0] == '\0') {
    anvil_music_error_text = "the path is empty";
    return 0.0;
  }
  FILE *file = fopen(path, "rb");
  if (!file) {
    anvil_music_error_text = "cannot open the file";
    return 0.0;
  }
  long data_offset = 0, data_bytes = 0;
  int channels = 0, bits = 0, rate = 0, format = 0, block_align = 0;
  if (!anvil_music_parse_wav(file, &data_offset, &data_bytes, &channels, &bits,
                             &rate, &format, &block_align)) {
    fclose(file);
    anvil_music_error_text = "not a readable WAV file";
    return 0.0;
  }
  if (channels < 1 || channels > 2) {
    fclose(file);
    anvil_music_error_text = "only mono and stereo music is supported";
    return 0.0;
  }
  if (format != 1 && format != 17) {
    fclose(file);
    anvil_music_error_text = "only PCM and IMA ADPCM music is supported";
    return 0.0;
  }
  if (format == 1 && bits != 8 && bits != 16) {
    fclose(file);
    anvil_music_error_text = "music must be 8-bit or 16-bit PCM";
    return 0.0;
  }
  if (format == 17 && bits != 4) {
    fclose(file);
    anvil_music_error_text = "IMA ADPCM music must be 4-bit";
    return 0.0;
  }
  if (format == 17 && (block_align < 4 * channels + 4 || block_align > 4096)) {
    fclose(file);
    anvil_music_error_text = "the ADPCM block alignment is invalid";
    return 0.0;
  }
  if (rate < 8000 || rate > 192000) {
    fclose(file);
    anvil_music_error_text = "music rate must be 8000-192000 Hz";
    return 0.0;
  }
  if (data_bytes <= 0) {
    fclose(file);
    anvil_music_error_text = "the music has no samples";
    return 0.0;
  }
  int frame_bytes = format == 17 ? block_align : channels * (bits / 8);
  int block_frames = 0;
  if (format == 17)
    block_frames = (block_align - 4 * channels) * 2 / channels + 1;
  unsigned char *block_bytes = NULL;
  short *block_pcm = NULL;
  if (format == 17) {
    block_bytes = (unsigned char *)malloc((size_t)block_align);
    block_pcm = (short *)malloc((size_t)block_frames * channels * sizeof(short));
    if (!block_bytes || !block_pcm) {
      free(block_bytes);
      free(block_pcm);
      fclose(file);
      anvil_music_error_text = "the music could not be allocated";
      return 0.0;
    }
  }
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  double previous_volume = anvil_music_volume_seeded ? anvil_music.volume : 1.0;
  if (anvil_music.file)
    fclose(anvil_music.file);
  free(anvil_music.block_bytes);
  free(anvil_music.block_pcm);
  memset(&anvil_music, 0, sizeof(anvil_music));
  anvil_music.file = file;
  anvil_music.data_offset = data_offset;
  anvil_music.data_bytes = data_bytes;
  anvil_music.frame_bytes = frame_bytes;
  anvil_music.channels = channels;
  anvil_music.bits = bits;
  anvil_music.rate = rate;
  anvil_music.adpcm = format == 17;
  anvil_music.block_align = block_align;
  anvil_music.block_frames = block_frames;
  anvil_music.block_bytes = block_bytes;
  anvil_music.block_pcm = block_pcm;
  anvil_music.bytes_left = data_bytes;
  anvil_music.length = anvil_music.adpcm
                          ? (double)((data_bytes / block_align) * block_frames) /
                                (double)rate
                          : (double)(data_bytes / frame_bytes) / (double)rate;
  anvil_music.volume = previous_volume;
  anvil_music_volume_seeded = 1;
  anvil_music.frames_left = data_bytes / frame_bytes;
  anvil_music.step = (double)rate / 48000.0;
  LeaveCriticalSection(&anvil_audio_lock);
  return 1.0;
}

static double anvil_music_start(int loop) {
  anvil_music_error_text = "";
  if (!anvil_music.file) {
    anvil_music_error_text = "no music is loaded";
    return 0.0;
  }
  if (!anvil_audio_start())
    return 0.0;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_music.loop = loop;
  anvil_music.playing = 1;
  anvil_music.draining = 0;
  anvil_music.seconds = 0.0;
  anvil_music.step = (double)anvil_music.rate / 48000.0;
  fseek(anvil_music.file, anvil_music.data_offset, SEEK_SET);
  anvil_music.frames_left = anvil_music.data_bytes / anvil_music.frame_bytes;
  anvil_music.bytes_left = anvil_music.data_bytes;
  anvil_music.block_count = 0;
  anvil_music.block_index = 0;
  anvil_music_prime();
  LeaveCriticalSection(&anvil_audio_lock);
  return 1.0;
}

double anvil_music_play(void) { return anvil_music_start(0); }
double anvil_music_play_loop(void) { return anvil_music_start(1); }

double anvil_music_stop(void) {
  if (!anvil_music.file)
    return 0.0;
  anvil_audio_lock_init();
  EnterCriticalSection(&anvil_audio_lock);
  anvil_music.playing = 0;
  anvil_music.draining = 0;
  anvil_music.seconds = 0.0;
  anvil_music_buffer_frames = 0;
  anvil_music_buffer_index = 0;
  fseek(anvil_music.file, anvil_music.data_offset, SEEK_SET);
  anvil_music.frames_left = anvil_music.data_bytes / anvil_music.frame_bytes;
  anvil_music.bytes_left = anvil_music.data_bytes;
  anvil_music.block_count = 0;
  anvil_music.block_index = 0;
  LeaveCriticalSection(&anvil_audio_lock);
  return 1.0;
}

double anvil_music_playing(void) { return anvil_music.playing ? 1.0 : 0.0; }

double anvil_music_volume(double volume) {
  if (!anvil_music.file || !isfinite(volume))
    return 0.0;
  double applied = anvil_audio_clamp(volume, 0.0, 1.0);
  anvil_music.volume = applied;
  return applied;
}

double anvil_music_position(void) { return anvil_music.seconds; }
double anvil_music_length(void) { return anvil_music.length; }
const char *anvil_music_error(void) { return anvil_music_error_text; }

static void anvil_release_frame_resources(void) {
  anvil_audio_shutdown();
  memset(anvil_particles, 0, sizeof(anvil_particles));
  anvil_particle_live = 0;
  if (anvil_music.file) {
    fclose(anvil_music.file);
    anvil_music.file = NULL;
  }
  free(anvil_music.block_bytes);
  free(anvil_music.block_pcm);
  anvil_music.block_bytes = NULL;
  anvil_music.block_pcm = NULL;
  anvil_music.playing = 0;
  for (int i = 0; i < ANVIL_IMAGES; ++i) {
    free(anvil_images[i].pixels);
    memset(&anvil_images[i], 0, sizeof(anvil_images[i]));
  }
  anvil_image_memory_used = 0;
  if (anvil_memory_dc && anvil_old_bitmap)
    SelectObject(anvil_memory_dc, anvil_old_bitmap);
  for (int i = 0; i < 2; ++i)
    if (anvil_bitmaps[i])
      DeleteObject(anvil_bitmaps[i]);
  if (anvil_memory_dc)
    DeleteDC(anvil_memory_dc);
  /* CreateDIBSection owns this pixel memory; DeleteObject releases it. */
  free(anvil_depth_buffer);
  anvil_pixels = NULL;
  anvil_depth_buffer = NULL;
  anvil_bitmaps[0] = anvil_bitmaps[1] = NULL;
  anvil_buffers[0] = anvil_buffers[1] = NULL;
  anvil_display_pixels = NULL;
  anvil_old_bitmap = NULL;
  anvil_memory_dc = NULL;
}

double anvil_window_on_top(double on) {
  if (!anvil_window)
    return 0.0;
  HWND after = on != 0.0 ? HWND_TOPMOST : HWND_NOTOPMOST;
  return SetWindowPos(anvil_window, after, 0, 0, 0, 0,
                      SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
             ? 1.0
             : 0.0;
}

double anvil_window_fullscreen(double on) {
  if (!anvil_window)
    return 0.0;
  if ((on != 0.0) == anvil_window_is_fullscreen)
    return 1.0;
  if (on != 0.0) {
    MONITORINFO info;
    memset(&info, 0, sizeof(info));
    info.cbSize = sizeof(info);
    HMONITOR monitor = MonitorFromWindow(anvil_window, MONITOR_DEFAULTTONEAREST);
    if (!GetMonitorInfoA(monitor, &info))
      return 0.0;
    anvil_window_saved_style = (LONG)GetWindowLongPtrA(anvil_window, GWL_STYLE);
    if (!GetWindowRect(anvil_window, &anvil_window_saved_rect))
      return 0.0;
    SetWindowLongPtrA(anvil_window, GWL_STYLE, (LONG_PTR)(WS_POPUP | WS_VISIBLE));
    int width = info.rcMonitor.right - info.rcMonitor.left;
    int height = info.rcMonitor.bottom - info.rcMonitor.top;
    if (!SetWindowPos(anvil_window, HWND_TOP, info.rcMonitor.left,
                      info.rcMonitor.top, width, height,
                      SWP_FRAMECHANGED | SWP_NOOWNERZORDER)) {
      SetWindowLongPtrA(anvil_window, GWL_STYLE,
                        (LONG_PTR)anvil_window_saved_style);
      return 0.0;
    }
    anvil_window_is_fullscreen = 1;
  } else {
    SetWindowLongPtrA(anvil_window, GWL_STYLE,
                      (LONG_PTR)anvil_window_saved_style);
    int width = anvil_window_saved_rect.right - anvil_window_saved_rect.left;
    int height = anvil_window_saved_rect.bottom - anvil_window_saved_rect.top;
    if (!SetWindowPos(anvil_window, NULL, anvil_window_saved_rect.left,
                      anvil_window_saved_rect.top, width, height,
                      SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOOWNERZORDER))
      return 0.0;
    anvil_window_is_fullscreen = 0;
  }
  InvalidateRect(anvil_window, NULL, FALSE);
  return 1.0;
}

double anvil_dpi_scale(void) { return anvil_dpi_factor; }

/* Resize the window's client area to 960x600 times `factor`, keeping the
   framebuffer letterboxed inside it. Returns the previous scale. */
double anvil_window_scale(double factor) {
  double previous = anvil_window_scale_factor;
  if (!isfinite(factor))
    return previous;
  double clamped = factor < 0.25 ? 0.25 : factor > 4.0 ? 4.0 : factor;
  anvil_window_scale_factor = clamped;
  if (anvil_window && !anvil_window_is_fullscreen) {
    RECT rect = {0, 0, (LONG)lrint((double)ANVIL_WIDTH * clamped),
                 (LONG)lrint((double)ANVIL_HEIGHT * clamped)};
    AdjustWindowRect(&rect, WS_OVERLAPPEDWINDOW, FALSE);
    SetWindowPos(anvil_window, NULL, 0, 0, rect.right - rect.left,
                 rect.bottom - rect.top,
                 SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    InvalidateRect(anvil_window, NULL, FALSE);
  }
  return previous;
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
  /* Ask for per-monitor DPI awareness before any window exists; without it
     Windows bitmap-stretches the whole window on a scaled display. The
     context entry point is looked up so the build still starts on systems
     that predate it. */
  {
    typedef BOOL(WINAPI * AnvilDpiContext)(void *);
    HMODULE user32 = GetModuleHandleA("user32.dll");
    AnvilDpiContext set_context =
        user32 ? (AnvilDpiContext)(void *)GetProcAddress(
                     user32, "SetProcessDpiAwarenessContext")
               : NULL;
    if (set_context)
      set_context((void *)-4); /* PER_MONITOR_AWARE_V2 */
    else
      SetProcessDPIAware();
  }
  {
    HDC screen = GetDC(NULL);
    int dpi = screen ? GetDeviceCaps(screen, LOGPIXELSX) : 96;
    if (screen)
      ReleaseDC(NULL, screen);
    if (dpi > 0)
      anvil_dpi_factor = (double)dpi / 96.0;
  }
  anvil_window_scale_factor = anvil_dpi_factor;
  RECT rect = {0, 0, (LONG)lrint((double)ANVIL_WIDTH * anvil_window_scale_factor),
               (LONG)lrint((double)ANVIL_HEIGHT * anvil_window_scale_factor)};
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
  for (int i = 0; i < 2; ++i) {
    anvil_bitmaps[i] =
        CreateDIBSection(anvil_memory_dc, &anvil_bitmap_info, DIB_RGB_COLORS,
                         (void **)&anvil_buffers[i], NULL, 0);
    if (!anvil_bitmaps[i] || !anvil_buffers[i])
      goto failed_startup;
  }
  anvil_depth_buffer =
      (double *)malloc((size_t)ANVIL_WIDTH * ANVIL_HEIGHT * sizeof(double));
  if (!anvil_depth_buffer)
    goto failed_startup;
  anvil_back_index = 0;
  anvil_pixels = anvil_buffers[0];
  anvil_display_pixels = anvil_buffers[0];
  anvil_old_bitmap = SelectObject(anvil_memory_dc, anvil_bitmaps[0]);
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
    LARGE_INTEGER phase_start, phase_update_end, phase_render_end, phase_present_end;
    /* Wait for the compositor before touching the frame: pacing here keeps
       the blit in step with the monitor and leaves frame_present() reporting
       the actual present cost rather than the wait. */
    DwmFlush();
    QueryPerformanceCounter(&phase_start);
    /* Before update(), so the frame sees this frame's focus and activation. */
    anvil_focus_frame();
    int update_count = 0;
    while (accumulator >= step_seconds) {
      anvil_delta_seconds = step_seconds;
      anvil_camera_update();
      anvil_particles_update(step_seconds);
      if (update)
        update();
      accumulator -= step_seconds;
      update_count++;
      if (update_count == 1)
        memset(anvil_pressed_keys, 0, sizeof(anvil_pressed_keys));
      if (update_count == 1) {
        memset(anvil_mouse_pressed_buttons, 0,
               sizeof(anvil_mouse_pressed_buttons));
        anvil_mouse_wheel_delta = 0.0;
      }
    }
    QueryPerformanceCounter(&phase_update_end);
    anvil_screen_fade_advance(frame_elapsed);
    anvil_clear_frame();
    if (draw)
      draw();
    anvil_sprite_flush();
    anvil_particles_draw();
    anvil_trace_finish();
    anvil_screen_fade_apply();
    if (!update) {
      memset(anvil_pressed_keys, 0, sizeof(anvil_pressed_keys));
      memset(anvil_mouse_pressed_buttons, 0,
             sizeof(anvil_mouse_pressed_buttons));
      anvil_mouse_wheel_delta = 0.0;
    }
    QueryPerformanceCounter(&phase_render_end);
    anvil_present_window();
    QueryPerformanceCounter(&phase_present_end);
    anvil_frame_tick_seconds =
        (double)(phase_update_end.QuadPart - phase_start.QuadPart) /
        (double)anvil_clock_frequency.QuadPart;
    anvil_frame_render_seconds =
        (double)(phase_render_end.QuadPart - phase_update_end.QuadPart) /
        (double)anvil_clock_frequency.QuadPart;
    anvil_frame_present_seconds =
        (double)(phase_present_end.QuadPart - phase_render_end.QuadPart) /
        (double)anvil_clock_frequency.QuadPart;
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

/* Lists are arrays with a used count. Reading past the count is a mistake even
   though the slot exists, so it gets the same treatment as text lists. */
double anvil_list_get(const double *values, int index, double count,
                      const char *path, int line) {
  if (!values || index < 0 || index >= (int)count) {
    fprintf(stderr, "%s:%d: list index %d is outside 0..%d\n", path, line, index,
            (int)count - 1);
    exit(2);
  }
  return values[index];
}



#define ANVIL_TEXT_BUFFERS 64
#define ANVIL_TEXT_CAPACITY 256
static char anvil_text_buffers[ANVIL_TEXT_BUFFERS][ANVIL_TEXT_CAPACITY];
static int anvil_text_buffer_index = 0;

static char *anvil_text_buffer(void) {
    char *destination = anvil_text_buffers[anvil_text_buffer_index & (ANVIL_TEXT_BUFFERS - 1)];
    anvil_text_buffer_index += 1;
    return destination;
}

static char *anvil_text_case(const char *source, int to_lower) {
    char *destination = anvil_text_buffer();
    size_t index = 0;
    for (; source[index] != '\0' && index < 255; ++index) {
        char letter = source[index];
        if (to_lower) {
            if (letter >= 'A' && letter <= 'Z') {
                letter = (char)(letter + 32);
            }
        } else {
            if (letter >= 'a' && letter <= 'z') {
                letter = (char)(letter - 32);
            }
        }
        destination[index] = letter;
    }
    destination[index] = '\0';
    return destination;
}

char *anvil_text_upper(const char *source) {
    return anvil_text_case(source, 0);
}

char *anvil_text_lower(const char *source) {
    return anvil_text_case(source, 1);
}

/* Clamp a numeric text argument into [0, limit] without converting a value
   whose truncation C leaves undefined.  NaN and non-finite values become 0,
   and anything at or past the limit clamps to the limit. */
static size_t anvil_text_index(double value, size_t limit) {
    if (!(value == value) || value <= 0.0) {
        return 0;
    }
    if (value >= (double)limit) {
        return limit;
    }
    return (size_t)value;
}

char *anvil_text_chr(double code) {
    char *destination = anvil_text_buffer();
    if (!(code == code) || code < 0.0 || code > 255.0) {
        fprintf(stderr, "Anvil chr out of range\n");
        exit(1);
    }
    destination[0] = (char)(int)code;
    destination[1] = '\0';
    return destination;
}

double anvil_text_ord(const char *source) {
    return (double)(unsigned char)source[0];
}

char *anvil_text_trim(const char *source) {
    char *destination = anvil_text_buffer();
    size_t length = strlen(source);
    size_t start = 0;
    size_t end = length;
    while (start < end && (source[start] == ' ' || source[start] == '\t')) {
        start += 1;
    }
    while (end > start && (source[end - 1] == ' ' || source[end - 1] == '\t')) {
        end -= 1;
    }
    memcpy(destination, source + start, end - start);
    destination[end - start] = '\0';
    return destination;
}

double anvil_text_to_number(const char *source) {
    /* Decimal only, matching the native backend: optional leading spaces, a
       sign, digits, an optional fraction, an optional exponent, optional
       trailing spaces and then the end of the text.  Hex, "inf" and "nan" read
       as 0 instead of strtod's surprises, and so does any text that is not a
       complete number: a valid prefix followed by junk reads 0 rather than a
       silently truncated value.  At most nine fraction digits are accumulated,
       so the fixed-point accumulator cannot overflow; further digits are
       skipped and the value stays within the documented rounding rule. */
    const char *cursor = source;
    while (*cursor == ' ' || *cursor == '\t') {
        cursor++;
    }
    int negative = 0;
    if (*cursor == '-') {
        negative = 1;
        cursor++;
    } else if (*cursor == '+') {
        cursor++;
    }
    double value = 0.0;
    int digits = 0;
    while (*cursor >= '0' && *cursor <= '9') {
        value = value * 10.0 + (double)(*cursor - '0');
        cursor++;
        digits++;
    }
    if (*cursor == '.') {
        cursor++;
        long long fraction = 0;
        long long scale = 1;
        while (*cursor >= '0' && *cursor <= '9') {
            /* Nine fraction digits stay well inside signed 64-bit range; extra
               digits are skipped so the accumulator can never overflow. */
            if (scale < 1000000000LL) {
                fraction = fraction * 10 + (*cursor - '0');
                scale *= 10;
            }
            cursor++;
            digits++;
        }
        if (scale > 1) {
            value += (double)fraction / (double)scale;
        }
    }
    if (digits == 0) {
        return 0.0;
    }
    if (*cursor == 'e' || *cursor == 'E') {
        cursor++;
        int exponent_negative = 0;
        if (*cursor == '-') {
            exponent_negative = 1;
            cursor++;
        } else if (*cursor == '+') {
            cursor++;
        }
        int exponent = 0;
        int exponent_digits = 0;
        while (*cursor >= '0' && *cursor <= '9' && exponent < 1000) {
            exponent = exponent * 10 + (*cursor - '0');
            cursor++;
            exponent_digits++;
        }
        if (exponent_digits == 0) {
            /* 'e' with no exponent digits is malformed, not a mantissa. */
            return 0.0;
        }
        while (exponent-- > 0) {
            value = exponent_negative ? value / 10.0 : value * 10.0;
        }
    }
    if (!(value <= 1.7976931348623157e308)) {
        /* Overflow to infinity (or a NaN) is not a usable number: both
           backends read it as 0 instead of one overflowing and the other
           clamping silently. */
        return 0.0;
    }
    while (*cursor == ' ' || *cursor == '\t') {
        cursor++;
    }
    if (*cursor != '\0') {
        /* A valid prefix followed by junk is not a number. */
        return 0.0;
    }
    return negative ? -value : value;
}

char *anvil_text_char(const char *source, double index) {
    char *destination = anvil_text_buffer();
    size_t length = strlen(source);
    /* Fractional indexes truncate toward zero.  NaN and the infinities have no
       sensible character, so they read as empty text. */
    if (!(index == index) || index < 0.0 || index >= (double)length) {
        destination[0] = '\0';
        return destination;
    }
    destination[0] = source[(size_t)index];
    destination[1] = '\0';
    return destination;
}

int anvil_str_contains(const char *source, const char *needle) {
    return strstr(source, needle) != NULL;
}

char *anvil_text_mid(const char *source, double start, double count) {
    char *destination = anvil_text_buffer();
    size_t length = strlen(source);
    size_t from = anvil_text_index(start, length);
    size_t take = anvil_text_index(count, length);
    if (take > length - from) {
        take = length - from;
    }
    memcpy(destination, source + from, take);
    destination[take] = '\0';
    return destination;
}

char *anvil_text_left(const char *source, double count) {
    char *destination = anvil_text_buffer();
    size_t length = strlen(source);
    size_t take = anvil_text_index(count, length);
    memcpy(destination, source, take);
    destination[take] = '\0';
    return destination;
}

char *anvil_text_right(const char *source, double count) {
    char *destination = anvil_text_buffer();
    size_t length = strlen(source);
    size_t take = anvil_text_index(count, length);
    memcpy(destination, source + (length - take), take);
    destination[take] = '\0';
    return destination;
}

double anvil_zero_clean(double value) {
    /* printf renders negative zero as "-0", which reads as a bug to beginners. */
    return value == 0.0 ? 0.0 : value;
}

const char *anvil_format_number(double value) {
    /* Matches the native backend: up to six fractional digits, no trailing
       zeros, and no exponent notation for ordinary magnitudes. */
    static char buffers[4][64];
    static unsigned index = 0;
    char *text = buffers[index++ & 3u];
    if (value == 0.0) {
        memcpy(text, "0", 2);
        return text;
    }
    _snprintf_s(text, 64, _TRUNCATE, "%.6f", value);
    size_t length = strlen(text);
    while (length > 0 && text[length - 1] == '0') {
        length--;
    }
    if (length > 0 && text[length - 1] == '.') {
        length--;
    }
    text[length] = '\0';
    if (strcmp(text, "-0") == 0) {
        memcpy(text, "0", 2);
    }
    return text;
}

int anvil_str_starts(const char *source, const char *prefix) {
    return strncmp(source, prefix, strlen(prefix)) == 0;
}

int anvil_str_ends(const char *source, const char *suffix) {
    size_t source_length = strlen(source);
    size_t suffix_length = strlen(suffix);
    if (suffix_length > source_length) {
        return 0;
    }
    return strcmp(source + source_length - suffix_length, suffix) == 0;
}
