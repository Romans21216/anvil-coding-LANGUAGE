/* WebAssembly console runtime for Anvil.

   Provides the small C surface the generated program needs, with output sent to
   the host through the imported `env.write` function. No OS, no libc: strings,
   memory and number formatting are implemented here. */
#include "anvil_wasm.h"

__attribute__((import_module("env"), import_name("write")))
extern void anvil_host_write(int fd, const void *bytes, int length);
__attribute__((import_module("env"), import_name("clear")))
extern void anvil_host_clear(int r, int g, int b, int a);
__attribute__((import_module("env"), import_name("rect")))
extern void anvil_host_rect(double x, double y, double w, double h, int r,
                            int g, int b, int a);
__attribute__((import_module("env"), import_name("circle")))
extern void anvil_host_circle(double x, double y, double radius, int r, int g,
                              int b, int a);
__attribute__((import_module("env"), import_name("line")))
extern void anvil_host_line(double x1, double y1, double x2, double y2,
                            double thickness, int r, int g, int b, int a);
__attribute__((import_module("env"), import_name("text")))
extern void anvil_host_text(double x, double y, const char *text, int length,
                            int r, int g, int b, int a);
__attribute__((import_module("env"), import_name("present")))
extern void anvil_host_present(void);
__attribute__((import_module("env"), import_name("save_read")))
extern int anvil_host_save_read(const char *key, char *out, int capacity);
__attribute__((import_module("env"), import_name("save_write")))
extern void anvil_host_save_write(const char *key, const char *value);
__attribute__((import_module("env"), import_name("save_delete")))
extern int anvil_host_save_delete(const char *key);
__attribute__((import_module("env"), import_name("scene_mode")))
extern void anvil_host_scene_mode(int enabled);

__attribute__((import_module("env"), import_name("triangle")))
extern void anvil_host_triangle(double x1, double y1, double z1, double x2,
                                double y2, double z2, double x3, double y3,
                                double z3, int r, int g, int b, int a,
                                int layer);

__attribute__((import_module("env"), import_name("image_region")))
extern void anvil_host_image_region(const unsigned int *pixels, int width,
                                    int height, double sx, double sy, double sw,
                                    double sh, double dx, double dy, double dw,
                                    double dh, int tint_r, int tint_g, int tint_b,
                                    int flip_x, int flip_y);
__attribute__((import_module("env"), import_name("image_draw")))
extern void anvil_host_image_draw(const unsigned int *pixels, int width,
                                  int height, double dx, double dy, double dw,
                                  double dh, double angle, int tint_r,
                                  int tint_g, int tint_b, int flip_x,
                                  int flip_y);

#define ANVIL_TEXT_BUFFERS 64
static char anvil_text_buffers[ANVIL_TEXT_BUFFERS][ANVIL_STR_CAP];
static int anvil_text_buffer_index;
char anvil_str_scratch[256][ANVIL_STR_CAP];
static int anvil_fixed_hz = 60;
static int anvil_frame_depth;

static char *anvil_text_buffer(void) {
  char *destination = anvil_text_buffers[anvil_text_buffer_index & (ANVIL_TEXT_BUFFERS - 1)];
  anvil_text_buffer_index += 1;
  return destination;
}

void *memcpy(void *dest, const void *source, size_t count) {
  unsigned char *to = (unsigned char *)dest;
  const unsigned char *from = (const unsigned char *)source;
  for (size_t i = 0; i < count; ++i)
    to[i] = from[i];
  return dest;
}

void *memset(void *dest, int value, size_t count) {
  unsigned char *to = (unsigned char *)dest;
  for (size_t i = 0; i < count; ++i)
    to[i] = (unsigned char)value;
  return dest;
}

size_t strlen(const char *text) {
  size_t length = 0;
  while (text && text[length])
    length++;
  return length;
}

int strcmp(const char *a, const char *b) {
  while (*a && *a == *b) {
    a++;
    b++;
  }
  return (unsigned char)*a - (unsigned char)*b;
}

static unsigned char anvil_heap[1 << 20];
static size_t anvil_heap_used;

void *calloc(size_t count, size_t size) {
  size_t bytes = count * size;
  size_t rounded = (bytes + 7u) & ~(size_t)7u;
  if (anvil_heap_used + rounded > sizeof(anvil_heap))
    return NULL;
  void *block = &anvil_heap[anvil_heap_used];
  anvil_heap_used += rounded;
  memset(block, 0, rounded);
  return block;
}

void *malloc(size_t size) { return calloc(1, size); }
void free(void *pointer) { (void)pointer; }

void exit(int code) {
  (void)code;
  __builtin_trap();
}

static void anvil_wasm_write(const char *text, size_t length) {
  if (length > 0)
    anvil_host_write(1, text, (int)length);
}

/* Supports the specifiers generated code uses: %s, %d, %c and %%. */
int printf(const char *format, ...) {
  char buffer[1024];
  size_t used = 0;
  va_list args;
  va_start(args, format);
  for (const char *cursor = format; *cursor && used < sizeof(buffer); ++cursor) {
    if (*cursor != '%') {
      buffer[used++] = *cursor;
      continue;
    }
    ++cursor;
    if (*cursor == 's') {
      const char *text = va_arg(args, const char *);
      while (text && *text && used < sizeof(buffer))
        buffer[used++] = *text++;
    } else if (*cursor == 'd') {
      long value = va_arg(args, int);
      char digits[24];
      int count = 0;
      unsigned long magnitude = value < 0 ? (unsigned long)(-value) : (unsigned long)value;
      if (magnitude == 0)
        digits[count++] = '0';
      while (magnitude > 0) {
        digits[count++] = (char)('0' + magnitude % 10);
        magnitude /= 10;
      }
      if (value < 0)
        buffer[used++] = '-';
      while (count > 0 && used < sizeof(buffer))
        buffer[used++] = digits[--count];
    } else if (*cursor == 'c') {
      buffer[used++] = (char)va_arg(args, int);
    } else if (*cursor == '%') {
      buffer[used++] = '%';
    } else {
      buffer[used++] = '%';
      if (*cursor)
        buffer[used++] = *cursor;
    }
    if (!*cursor)
      break;
  }
  va_end(args);
  anvil_wasm_write(buffer, used);
  return (int)used;
}

int putchar(int character) {
  char byte = (char)character;
  anvil_host_write(1, &byte, 1);
  return character;
}

int fflush(void *stream) {
  (void)stream;
  return 0;
}

const char *anvil_format_number(double value) {
  static char buffers[4][64];
  static unsigned index = 0;
  char *text = buffers[index++ & 3u];
  if (value != value) {
    memcpy(text, "nan", 4);
    return text;
  }
  if (value == 0.0) {
    memcpy(text, "0", 2);
    return text;
  }
  int negative = value < 0.0;
  double magnitude = negative ? -value : value;
  unsigned long long whole = (unsigned long long)magnitude;
  double fraction = magnitude - (double)whole;
  unsigned long long scaled = (unsigned long long)(fraction * 1000000.0 + 0.5);
  if (scaled >= 1000000ULL) {
    whole += 1;
    scaled = 0;
  }
  char digits[48];
  int count = 0;
  if (whole == 0) {
    digits[count++] = '0';
  } else {
    while (whole > 0) {
      digits[count++] = (char)('0' + (whole % 10));
      whole /= 10;
    }
  }
  size_t used = 0;
  if (negative)
    text[used++] = '-';
  while (count > 0)
    text[used++] = digits[--count];
  if (scaled > 0) {
    char fraction_digits[7];
    for (int i = 5; i >= 0; --i) {
      fraction_digits[i] = (char)('0' + (scaled % 10));
      scaled /= 10;
    }
    int last = 6;
    while (last > 0 && fraction_digits[last - 1] == '0')
      last--;
    text[used++] = '.';
    for (int i = 0; i < last; ++i)
      text[used++] = fraction_digits[i];
  }
  text[used] = '\0';
  if (strcmp(text, "-0") == 0)
    memcpy(text, "0", 2);
  return text;
}

static void anvil_runtime_error(const char *message) {
  anvil_wasm_write(message, strlen(message));
  anvil_wasm_write("\n", 1);
  __builtin_trap();
}

double anvil_check_number(double value, const char *path, int line) {
  (void)path;
  (void)line;
  if (value != value || value > 1.7976931348623157e308 ||
      value < -1.7976931348623157e308)
    anvil_runtime_error("numeric overflow or non-finite result");
  return value;
}

double anvil_divide(double numerator, double denominator, const char *path,
                    int line) {
  (void)path;
  (void)line;
  if (denominator == 0.0)
    anvil_runtime_error("division by zero");
  return numerator / denominator;
}

void anvil_set_fixed_hz(int hz) { anvil_fixed_hz = hz; }
void anvil_net_close(void) {}

void anvil_frame_enter(void) {
  anvil_frame_depth += 1;
  if (anvil_frame_depth > 1000)
    anvil_runtime_error("call depth exceeded the wasm frame budget");
}

void anvil_frame_leave(void) { anvil_frame_depth -= 1; }

double anvil_array_get(const double *values, int size, double index,
                       const char *path, int line) {
  (void)path;
  (void)line;
  if (!values || size <= 0 || index < 0.0 || index >= (double)size ||
      floor(index) != index)
    anvil_runtime_error("array index is invalid");
  return values[(int)index];
}

void anvil_array_set(double *values, int size, double index, double value,
                     const char *path, int line) {
  (void)path;
  (void)line;
  if (!values || size <= 0 || index < 0.0 || index >= (double)size ||
      floor(index) != index)
    anvil_runtime_error("array index is invalid");
  values[(int)index] = value;
}

void anvil_str_set(char *dest, const char *value, const char *path, int line) {
  (void)path;
  (void)line;
  size_t length = strlen(value);
  if (length >= ANVIL_STR_CAP)
    anvil_runtime_error("text value exceeds 255 bytes");
  memcpy(dest, value, length + 1);
}

char *anvil_str_cat(char *dest, const char *a, const char *b, const char *path,
                    int line) {
  (void)path;
  (void)line;
  size_t la = strlen(a);
  size_t lb = strlen(b);
  char tail[ANVIL_STR_CAP];
  int a_inside = a >= dest && a < dest + ANVIL_STR_CAP;
  int b_inside = b >= dest && b < dest + ANVIL_STR_CAP;
  if (la + lb >= ANVIL_STR_CAP)
    anvil_runtime_error("text value exceeds 255 bytes");
  if (b_inside) {
    memcpy(tail, b, lb + 1);
    b = tail;
  }
  if (!a_inside)
    memcpy(dest, a, la);
  memcpy(dest + la, b, lb + 1);
  return dest;
}

char *anvil_text_upper(const char *source) {
  char *destination = anvil_text_buffer();
  size_t index = 0;
  for (; source[index] && index + 1 < ANVIL_STR_CAP; ++index) {
    char c = source[index];
    destination[index] = c >= 'a' && c <= 'z' ? (char)(c - 'a' + 'A') : c;
  }
  destination[index] = '\0';
  return destination;
}

static size_t anvil_text_index(double value, size_t limit) {
  if (value != value || value <= 0.0)
    return 0;
  if (value >= (double)limit)
    return limit;
  return (size_t)value;
}

char *anvil_text_mid(const char *source, double start, double count) {
  char *destination = anvil_text_buffer();
  size_t length = strlen(source);
  size_t from = anvil_text_index(start, length);
  size_t take = anvil_text_index(count, length);
  if (take > length - from)
    take = length - from;
  memcpy(destination, source + from, take);
  destination[take] = '\0';
  return destination;
}

double anvil_text_to_number(const char *source) {
  if (!source)
    return 0.0;
  const char *cursor = source;
  while (*cursor == ' ' || *cursor == '\t')
    cursor++;
  int negative = 0;
  if (*cursor == '-' || *cursor == '+') {
    negative = *cursor == '-';
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
    double scale = 0.1;
    while (*cursor >= '0' && *cursor <= '9') {
      value += (double)(*cursor - '0') * scale;
      scale *= 0.1;
      cursor++;
      digits++;
    }
  }
  if (digits == 0)
    return 0.0;
  if (*cursor == 'e' || *cursor == 'E') {
    const char *exponent_start = cursor;
    cursor++;
    int exponent_negative = 0;
    if (*cursor == '-' || *cursor == '+') {
      exponent_negative = *cursor == '-';
      cursor++;
    }
    int exponent = 0;
    int exponent_digits = 0;
    while (*cursor >= '0' && *cursor <= '9' && exponent_digits < 1000) {
      exponent = exponent * 10 + (*cursor - '0');
      cursor++;
      exponent_digits++;
    }
    if (exponent_digits == 0) {
      cursor = exponent_start;
    } else {
      for (int i = 0; i < exponent; ++i)
        value = exponent_negative ? value / 10.0 : value * 10.0;
    }
  }
  while (*cursor == ' ' || *cursor == '\t')
    cursor++;
  if (*cursor != '\0')
    return 0.0;
  return negative ? -value : value;
}

/* ---- Input and time ----------------------------------------------------- */
static unsigned char anvil_keys[256];
static unsigned char anvil_keys_pressed[256];
static unsigned char anvil_mouse_buttons[3];
static unsigned char anvil_mouse_pressed_buttons[3];
static double anvil_mouse_x_value = -1.0, anvil_mouse_y_value = -1.0;
static double anvil_mouse_wheel_value;
static double anvil_time_seconds, anvil_delta_seconds = 1.0 / 60.0;

static int anvil_button_index(const char *button) {
  if (!button)
    return -1;
  const char *names[3] = {"left", "right", "middle"};
  for (int index = 0; index < 3; ++index) {
    const char *a = button;
    const char *b = names[index];
    int same = 1;
    while (*a && *b) {
      char ca = *a >= 'A' && *a <= 'Z' ? (char)(*a + 32) : *a;
      if (ca != *b) {
        same = 0;
        break;
      }
      a++;
      b++;
    }
    if (same && *a == '\0' && *b == '\0')
      return index;
  }
  return -1;
}

double anvil_time(void) { return anvil_time_seconds; }
double anvil_delta(void) { return anvil_delta_seconds; }
double anvil_pressed(int key) {
  return key > 0 && key < 256 ? (double)anvil_keys_pressed[key] : 0.0;
}
double anvil_held(int key) {
  return key > 0 && key < 256 ? (double)anvil_keys[key] : 0.0;
}
double anvil_mouse_x(void) { return anvil_mouse_x_value; }
double anvil_mouse_y(void) { return anvil_mouse_y_value; }
double anvil_mouse_wheel(void) { return anvil_mouse_wheel_value; }
double anvil_mouse_pressed(const char *button) {
  int index = anvil_button_index(button);
  return index >= 0 ? (double)anvil_mouse_pressed_buttons[index] : 0.0;
}
double anvil_mouse_held(const char *button) {
  int index = anvil_button_index(button);
  return index >= 0 ? (double)anvil_mouse_buttons[index] : 0.0;
}

__attribute__((export_name("anvil_key"))) void anvil_host_key(int key, int down) {
  if (key <= 0 || key > 255)
    return;
  if (down && !anvil_keys[key])
    anvil_keys_pressed[key] = 1;
  anvil_keys[key] = down != 0;
}

__attribute__((export_name("anvil_mouse"))) void anvil_host_mouse(double x,
                                                                  double y) {
  anvil_mouse_x_value = x;
  anvil_mouse_y_value = y;
}

__attribute__((export_name("anvil_mouse_button"))) void anvil_host_mouse_button(
    int button, int down) {
  if (button < 0 || button > 2)
    return;
  if (down && !anvil_mouse_buttons[button])
    anvil_mouse_pressed_buttons[button] = 1;
  anvil_mouse_buttons[button] = down != 0;
}

__attribute__((export_name("anvil_wheel"))) void anvil_host_wheel(
    double delta) {
  anvil_mouse_wheel_value += delta;
}

/* ---- Math and random ---------------------------------------------------- */
static unsigned long long anvil_rng_state = 0x9E3779B97F4A7C15ULL;

static unsigned long long anvil_random_u64(void) {
  unsigned long long x = anvil_rng_state;
  x ^= x >> 12;
  x ^= x << 25;
  x ^= x >> 27;
  anvil_rng_state = x;
  return x * 2685821657736338717ULL;
}

/* Reduce an angle to [-pi, pi] so the Taylor series stays accurate. */
static double anvil_wrap_angle(double value) {
  const double two_pi = 6.283185307179586476925286766559;
  const double inv_two_pi = 0.159154943091895335768883763373;
  double turns = value * inv_two_pi;
  turns = __builtin_trunc(turns + (turns >= 0.0 ? 0.5 : -0.5));
  return value - turns * two_pi;
}

double sin(double radians) {
  double x = anvil_wrap_angle(radians);
  double x2 = x * x;
  double term = x, sum = x;
  for (int n = 1; n <= 9; ++n) {
    term *= -x2 / ((2.0 * n) * (2.0 * n + 1.0));
    sum += term;
  }
  return sum;
}

double cos(double radians) {
  double x = anvil_wrap_angle(radians);
  double x2 = x * x;
  double term = 1.0, sum = 1.0;
  for (int n = 1; n <= 9; ++n) {
    term *= -x2 / ((2.0 * n - 1.0) * (2.0 * n));
    sum += term;
  }
  return sum;
}

/* Inclusive integer range, matching the C runtime's anvil_rnd. */
double anvil_rnd(double min_value, double max_value) {
  if (min_value > max_value) {
    double swap = min_value;
    min_value = max_value;
    max_value = swap;
  }
  long long low = (long long)ceil(min_value);
  long long high = (long long)floor(max_value);
  if (high <= low)
    return (double)low;
  unsigned long long span = (unsigned long long)(high - low) + 1ULL;
  return (double)(low + (long long)(anvil_random_u64() % span));
}

/* ---- 3D scene ------------------------------------------------------------
   A small perspective pipeline: model points are rotated, translated, put in
   camera space with the same basis and projection as the C runtime, then handed
   to the host as screen-space triangles with a depth for painter's-algorithm
   sorting. Shading is a fixed directional light so faces read as solid. */
typedef struct {
  double x, y, z;
} AnvilWasmVec3;

static int anvil_scene_is_3d;
static double anvil_camera_x, anvil_camera_y, anvil_camera_z;
static double anvil_camera_yaw, anvil_camera_pitch;
static double anvil_camera_focal = 520.0;

void anvil_set_scene3d(int enabled) {
  anvil_scene_is_3d = enabled != 0;
  anvil_host_scene_mode(anvil_scene_is_3d);
}

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
  anvil_camera_focal =
      (960.0 * 0.5) / (sin(degrees * 0.008726646259971647884) / cos(degrees * 0.008726646259971647884));
}

double anvil_camera_angle(double yaw, double pitch) {
  if (!(yaw == yaw) || !(pitch == pitch))
    return 0.0;
  if (pitch > 89.0)
    pitch = 89.0;
  if (pitch < -89.0)
    pitch = -89.0;
  anvil_camera_yaw = yaw;
  anvil_camera_pitch = pitch;
  return 1.0;
}

static AnvilWasmVec3 anvil_wasm_sub(AnvilWasmVec3 a, AnvilWasmVec3 b) {
  return (AnvilWasmVec3){a.x - b.x, a.y - b.y, a.z - b.z};
}
static double anvil_wasm_dot(AnvilWasmVec3 a, AnvilWasmVec3 b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}
static AnvilWasmVec3 anvil_wasm_cross(AnvilWasmVec3 a, AnvilWasmVec3 b) {
  return (AnvilWasmVec3){a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z,
                         a.x * b.y - a.y * b.x};
}
static AnvilWasmVec3 anvil_wasm_normalize(AnvilWasmVec3 v) {
  double length = __builtin_sqrt(anvil_wasm_dot(v, v));
  if (length < 1e-12)
    return (AnvilWasmVec3){0, 1, 0};
  return (AnvilWasmVec3){v.x / length, v.y / length, v.z / length};
}
static AnvilWasmVec3 anvil_wasm_rotate(AnvilWasmVec3 p, double rx, double ry,
                                       double rz) {
  const double d = 0.017453292519943295769;
  rx *= d;
  ry *= d;
  rz *= d;
  double c = cos(rx), s = sin(rx);
  p = (AnvilWasmVec3){p.x, p.y * c - p.z * s, p.y * s + p.z * c};
  c = cos(ry);
  s = sin(ry);
  p = (AnvilWasmVec3){p.x * c + p.z * s, p.y, -p.x * s + p.z * c};
  c = cos(rz);
  s = sin(rz);
  p = (AnvilWasmVec3){p.x * c - p.y * s, p.x * s + p.y * c, p.z};
  return p;
}

static AnvilWasmVec3 anvil_wasm_to_camera(AnvilWasmVec3 p) {
  const double radians = 0.017453292519943295769;
  double yaw = anvil_camera_yaw * radians;
  double pitch = anvil_camera_pitch * radians;
  AnvilWasmVec3 right = {cos(yaw), 0.0, sin(yaw)};
  AnvilWasmVec3 forward = {sin(yaw) * cos(pitch), sin(pitch),
                           -cos(yaw) * cos(pitch)};
  AnvilWasmVec3 up = anvil_wasm_normalize(anvil_wasm_cross(right, forward));
  AnvilWasmVec3 relative = {p.x - anvil_camera_x, p.y - anvil_camera_y,
                            p.z - anvil_camera_z};
  return (AnvilWasmVec3){anvil_wasm_dot(relative, right),
                         anvil_wasm_dot(relative, up),
                         anvil_wasm_dot(relative, forward)};
}

static int anvil_wasm_project(AnvilWasmVec3 p, double *sx, double *sy,
                              double *depth) {
  AnvilWasmVec3 camera = anvil_wasm_to_camera(p);
  if (camera.z <= 0.05)
    return 0;
  *sx = 480.0 + camera.x * anvil_camera_focal / camera.z;
  *sy = 324.0 - camera.y * anvil_camera_focal / camera.z;
  *depth = camera.z;
  return 1;
}

static void anvil_wasm_triangle(AnvilWasmVec3 a, AnvilWasmVec3 b,
                                AnvilWasmVec3 c, AnvilWasmVec3 normal,
                                int r, int g, int bl, int alpha,
                                double depth_bias, int layer) {
  if (!anvil_scene_is_3d)
    return;
  double x1, y1, d1, x2, y2, d2, x3, y3, d3;
  if (!anvil_wasm_project(a, &x1, &y1, &d1) ||
      !anvil_wasm_project(b, &x2, &y2, &d2) ||
      !anvil_wasm_project(c, &x3, &y3, &d3))
    return;
  AnvilWasmVec3 light = {-0.35, 0.8, -0.45};
  double shade = anvil_wasm_dot(anvil_wasm_normalize(normal), light);
  if (shade < 0)
    shade = -shade;
  shade = 0.45 + 0.55 * shade;
  int shaded_r = (int)(r * shade);
  int shaded_g = (int)(g * shade);
  int shaded_b = (int)(bl * shade);
  anvil_host_triangle(x1, y1, d1 + depth_bias, x2, y2, d2 + depth_bias, x3,
                      y3, d3 + depth_bias, shaded_r, shaded_g, shaded_b, alpha,
                      layer);
}

static void anvil_wasm_quad(AnvilWasmVec3 a, AnvilWasmVec3 b, AnvilWasmVec3 c,
                            AnvilWasmVec3 d, int r, int g, int bl, int alpha) {
  const double bias = 0.0;
  AnvilWasmVec3 normal =
      anvil_wasm_normalize(anvil_wasm_cross(anvil_wasm_sub(b, a),
                                            anvil_wasm_sub(c, a)));
  anvil_wasm_triangle(a, b, c, normal, r, g, bl, alpha, bias, 0);
  anvil_wasm_triangle(a, c, d, normal, r, g, bl, alpha, bias, 0);
}

static void anvil_wasm_shadow_triangle(AnvilWasmVec3 a, AnvilWasmVec3 b,
                                       AnvilWasmVec3 c);

void anvil_cube(double x, double y, double z, double size, double rx, double ry,
                double rz, int r, int g, int b, int a) {
  double half = size * 0.5;
  AnvilWasmVec3 corners[8];
  for (int index = 0; index < 8; ++index) {
    AnvilWasmVec3 local = {(index & 1) ? half : -half,
                           (index & 2) ? half : -half,
                           (index & 4) ? half : -half};
    local = anvil_wasm_rotate(local, rx, ry, rz);
    corners[index] = (AnvilWasmVec3){local.x + x, local.y + y, local.z + z};
  }
  /* Each face is two triangles; indices follow the corner bit layout. */
  anvil_wasm_quad(corners[0], corners[1], corners[3], corners[2], r, g, b, a);
  anvil_wasm_quad(corners[4], corners[6], corners[7], corners[5], r, g, b, a);
  anvil_wasm_quad(corners[0], corners[4], corners[5], corners[1], r, g, b, a);
  anvil_wasm_quad(corners[2], corners[3], corners[7], corners[6], r, g, b, a);
  anvil_wasm_quad(corners[0], corners[2], corners[6], corners[4], r, g, b, a);
  anvil_wasm_quad(corners[1], corners[5], corners[7], corners[3], r, g, b, a);
  /* One shadow for the whole cube (its bottom face), not one per face: six
     stacked translucent copies would read as solid black. */
  anvil_wasm_shadow_triangle(corners[0], corners[1], corners[5]);
  anvil_wasm_shadow_triangle(corners[0], corners[5], corners[4]);
}

void anvil_plane(double x, double y, double z, double width, double depth,
                 int r, int g, int b, int alpha) {
  double hw = width * 0.5, hd = depth * 0.5;
  AnvilWasmVec3 p0 = {x - hw, y, z - hd};
  AnvilWasmVec3 p1 = {x + hw, y, z - hd};
  AnvilWasmVec3 p2 = {x + hw, y, z + hd};
  AnvilWasmVec3 p3 = {x - hw, y, z + hd};
  anvil_wasm_quad(p0, p1, p2, p3, r, g, b, alpha);
}

void anvil_sphere(double x, double y, double z, double radius, int r, int g,
                  int b, int a) {
  const int rings = 10;
  const int segments = 16;
  for (int ring = 0; ring < rings; ++ring) {
    double phi0 = 3.14159265358979323846 * (double)ring / (double)rings;
    double phi1 = 3.14159265358979323846 * (double)(ring + 1) / (double)rings;
    for (int segment = 0; segment < segments; ++segment) {
      double theta0 = 6.283185307179586476925 * (double)segment / (double)segments;
      double theta1 =
          6.283185307179586476925 * (double)(segment + 1) / (double)segments;
      AnvilWasmVec3 quad[4];
      double phis[2] = {phi0, phi1};
      double thetas[2] = {theta0, theta1};
      for (int corner = 0; corner < 4; ++corner) {
        double phi = phis[corner >> 1];
        double theta = thetas[corner & 1];
        quad[corner] = (AnvilWasmVec3){
            x + radius * sin(phi) * cos(theta), y + radius * cos(phi),
            z + radius * sin(phi) * sin(theta)};
      }
      anvil_wasm_quad(quad[0], quad[1], quad[3], quad[2], r, g, b, a);
    }
  }
}


__attribute__((import_module("env"), import_name("music_play")))
extern int anvil_host_music_play(const short *pcm, int frames, int channels,
                                 int rate, double volume, int loop);
__attribute__((import_module("env"), import_name("music_stop")))
extern void anvil_host_music_stop(void);
__attribute__((import_module("env"), import_name("music_playing")))
extern int anvil_host_music_playing(void);
__attribute__((import_module("env"), import_name("music_volume")))
extern void anvil_host_music_volume(double volume);
__attribute__((import_module("env"), import_name("music_position")))
extern double anvil_host_music_position(void);

/* ---- Music, baked at compile time --------------------------------------
   One looping track, like the desktop runtime's streaming player, except the
   browser build carries the decoded samples in the module: a browser cannot
   stream from disk without an async fetch contract, and the music API is
   synchronous. The host owns playback position. */
static const AnvilWasmMusic *anvil_baked_music_value;
static int anvil_music_loaded;
static int anvil_music_ready;
static const char *anvil_music_error_text = "";
static double anvil_music_volume_value = 1.0;

void anvil_wasm_set_music(const AnvilWasmMusic *music) {
  anvil_baked_music_value = music;
  if (music)
    anvil_music_loaded = 1;
}

void anvil_wasm_register_music(void) __attribute__((weak));

static void anvil_music_ensure(void) {
  if (anvil_music_ready)
    return;
  anvil_music_ready = 1;
  if (anvil_wasm_register_music)
    anvil_wasm_register_music();
}

const char *anvil_music_error(void) { return anvil_music_error_text; }

double anvil_music_load(const char *path) {
  anvil_music_ensure();
  if (!anvil_baked_music_value ||
      strcmp(anvil_baked_music_value->path, path) != 0) {
    anvil_music_error_text =
        "the music was not baked into this build; only the literal "
        "music_load() path is available in the wasm backend";
    return 0.0;
  }
  anvil_music_error_text = "";
  return 1.0;
}

static double anvil_music_start(int loop) {
  if (!anvil_music_loaded || !anvil_baked_music_value)
    return 0.0;
  int voice = anvil_host_music_play(
      anvil_baked_music_value->pcm, anvil_baked_music_value->frames,
      anvil_baked_music_value->channels, anvil_baked_music_value->rate,
      anvil_music_volume_value, loop);
  if (voice <= 0)
    return 0.0;
  return 1.0;
}

double anvil_music_play(void) { return anvil_music_start(0); }
double anvil_music_play_loop(void) { return anvil_music_start(1); }

double anvil_music_stop(void) {
  anvil_host_music_stop();
  return 1.0;
}

double anvil_music_playing(void) { return (double)anvil_host_music_playing(); }

double anvil_music_volume(double volume) {
  if (!(volume == volume))
    return 0.0;
  double clamped = volume < 0.0 ? 0.0 : volume > 1.0 ? 1.0 : volume;
  anvil_music_volume_value = clamped;
  anvil_host_music_volume(clamped);
  return clamped;
}

double anvil_music_position(void) { return anvil_host_music_position(); }

double anvil_music_length(void) {
  if (!anvil_baked_music_value || anvil_baked_music_value->rate <= 0)
    return 0.0;
  return (double)anvil_baked_music_value->frames /
         (double)anvil_baked_music_value->rate;
}

/* ---- 2D physics ---------------------------------------------------------
   Circles and axis-aligned boxes on a fixed-step solver. Ported from the C
   runtime's implementation so both backends produce the same positions. */
enum {
  ANVIL_PHYSICS_BODIES = 128,
  ANVIL_PHYSICS_SOLVER_ITERATIONS = 4
};
enum { ANVIL_PHYSICS_CIRCLE, ANVIL_PHYSICS_BOX };
#define ANVIL_PHYSICS_MAX_COORDINATE 1000000000.0
#define ANVIL_PHYSICS_MAX_RADIUS 1000000.0
#define ANVIL_PHYSICS_MAX_SPEED 1000000.0

typedef struct {
  double x, y, vx, vy, force_x, force_y;
  double radius, half_width, half_height, mass, restitution, friction;
  unsigned int generation;
  int active, shape;
} AnvilPhysicsBody;

static AnvilPhysicsBody anvil_physics_bodies[ANVIL_PHYSICS_BODIES];
static int anvil_physics_active_capacity = ANVIL_PHYSICS_BODIES;
static double anvil_physics_gravity_x;
static double anvil_physics_gravity_y = -9.81;

static int anvil_wasm_finite(double value) {
  return value == value && value < 1.0e308 * 10.0 && value > -1.0e308 * 10.0;
}

static AnvilPhysicsBody *anvil_physics_body(double handle, int *slot_out) {
  const double max_handle = (double)4294967295u * ANVIL_PHYSICS_BODIES +
                            (ANVIL_PHYSICS_BODIES - 1);
  if (!anvil_wasm_finite(handle) || handle < 0.0 || handle > max_handle ||
      floor(handle) != handle)
    return NULL;
  unsigned long long encoded = (unsigned long long)handle;
  int slot = (int)(encoded % ANVIL_PHYSICS_BODIES);
  unsigned int generation = (unsigned int)(encoded / ANVIL_PHYSICS_BODIES);
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
    unsigned int generation = body->generation + 1;
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
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y) || !anvil_wasm_finite(radius) || !anvil_wasm_finite(mass) ||
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
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y) || !anvil_wasm_finite(width) || !anvil_wasm_finite(height) ||
      !anvil_wasm_finite(mass) || fabs(x) > ANVIL_PHYSICS_MAX_COORDINATE ||
      fabs(y) > ANVIL_PHYSICS_MAX_COORDINATE || width < 2.0e-6 ||
      width > 2.0 * ANVIL_PHYSICS_MAX_RADIUS || height < 2.0e-6 ||
      height > 2.0 * ANVIL_PHYSICS_MAX_RADIUS || mass < 0.0 || mass > 1.0e12 ||
      (mass > 0.0 && mass < 1.0e-6))
    return -1.0;
  return anvil_physics_allocate_body(x, y, 0.0, width * 0.5, height * 0.5,
                                     mass, ANVIL_PHYSICS_BOX);
}

double anvil_physics_capacity(double requested_capacity) {
  if (!anvil_wasm_finite(requested_capacity) || floor(requested_capacity) != requested_capacity ||
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
  if (!body || body->mass <= 0.0 || !anvil_wasm_finite(vx) || !anvil_wasm_finite(vy) ||
      fabs(vx) > ANVIL_PHYSICS_MAX_SPEED || fabs(vy) > ANVIL_PHYSICS_MAX_SPEED)
    return 0.0;
  body->vx = vx;
  body->vy = vy;
  return 1.0;
}

double anvil_body_force(double handle, double force_x, double force_y) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || body->mass <= 0.0 || !anvil_wasm_finite(force_x) || !anvil_wasm_finite(force_y) ||
      fabs(force_x) > 1.0e12 || fabs(force_y) > 1.0e12)
    return 0.0;
  double next_force_x = body->force_x + force_x;
  double next_force_y = body->force_y + force_y;
  if (!anvil_wasm_finite(next_force_x) || !anvil_wasm_finite(next_force_y) ||
      fabs(next_force_x) > 1.0e12 || fabs(next_force_y) > 1.0e12)
    return 0.0;
  body->force_x = next_force_x;
  body->force_y = next_force_y;
  return 1.0;
}

double anvil_body_restitution(double handle, double restitution) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || !anvil_wasm_finite(restitution) || restitution < 0.0 || restitution > 1.0)
    return 0.0;
  body->restitution = restitution;
  return 1.0;
}

double anvil_body_friction(double handle, double friction) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || !anvil_wasm_finite(friction) || friction < 0.0 || friction > 1.0)
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
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y) || fabs(x) > 1.0e6 || fabs(y) > 1.0e6)
    return 0.0;
  anvil_physics_gravity_x = x;
  anvil_physics_gravity_y = y;
  return 1.0;
}

double anvil_physics_step(void) {
  double dt = anvil_delta_seconds;
  if (!anvil_wasm_finite(dt) || dt <= 0.0 || dt > 0.25)
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
      if (!anvil_wasm_finite(body->x) || !anvil_wasm_finite(body->y) || !anvil_wasm_finite(body->vx) ||
          !anvil_wasm_finite(body->vy)) {
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
    if (!anvil_wasm_finite(body->x) || !anvil_wasm_finite(body->y) || !anvil_wasm_finite(body->vx) ||
        !anvil_wasm_finite(body->vy)) {
      body->x = body->y = body->vx = body->vy = 0.0;
    }
  }
  return (double)contact_count;
}

/* ---- Shadows and culling ------------------------------------------------ */
static int anvil_shadows_enabled;
static double anvil_shadow_ground_y;
static int anvil_shadow_alpha_value = 150;
static int anvil_mesh_culling_enabled = 1;
static int anvil_mesh_culled_frame;

double anvil_shadow(double on) {
  anvil_shadows_enabled = on != 0.0;
  return anvil_shadows_enabled ? 1.0 : 0.0;
}
double anvil_shadow_height(double y) {
  if (!(y == y))
    return 0.0;
  anvil_shadow_ground_y = y;
  return y;
}
double anvil_shadow_alpha(double alpha) {
  if (!(alpha == alpha))
    return 0.0;
  int applied = (int)(alpha < 0.0 ? 0.0 : alpha > 255.0 ? 255.0 : alpha);
  anvil_shadow_alpha_value = applied;
  return (double)applied;
}

static void anvil_wasm_shadow_triangle(AnvilWasmVec3 a, AnvilWasmVec3 b,
                                       AnvilWasmVec3 c) {
  if (!anvil_shadows_enabled || anvil_shadow_alpha_value <= 0)
    return;
  AnvilWasmVec3 flat_a = {a.x, anvil_shadow_ground_y + 0.002, a.z};
  AnvilWasmVec3 flat_b = {b.x, anvil_shadow_ground_y + 0.002, b.z};
  AnvilWasmVec3 flat_c = {c.x, anvil_shadow_ground_y + 0.002, c.z};
  anvil_wasm_triangle(flat_a, flat_b, flat_c, (AnvilWasmVec3){0, 1, 0}, 0, 0, 0,
                      anvil_shadow_alpha_value, 0.0, 1);
}

static int anvil_wasm_sphere_visible(double cx, double cy, double cz,
                                     double radius, double x, double y,
                                     double z, double scale, double rx,
                                     double ry, double rz) {
  if (!anvil_mesh_culling_enabled || radius <= 0.0)
    return 1;
  AnvilWasmVec3 centre = {cx * scale, cy * scale, cz * scale};
  centre = anvil_wasm_rotate(centre, rx, ry, rz);
  centre = (AnvilWasmVec3){centre.x + x, centre.y + y, centre.z + z};
  AnvilWasmVec3 camera = anvil_wasm_to_camera(centre);
  double scaled = radius * scale;
  if (camera.z + scaled <= 0.05)
    return 0;
  if (camera.z - scaled < 0.05)
    return 1;
  double projected = scaled * anvil_camera_focal / camera.z;
  double screen_x = 480.0 + camera.x * anvil_camera_focal / camera.z;
  double screen_y = 324.0 - camera.y * anvil_camera_focal / camera.z;
  if (screen_x + projected < 0.0 || screen_x - projected > 960.0)
    return 0;
  if (screen_y + projected < 0.0 || screen_y - projected > 600.0)
    return 0;
  return 1;
}

/* ---- Baked models -------------------------------------------------------
   model_draw arrays hold 12 doubles per triangle: three positions followed by
   an RGB colour. The compiler bakes them from glTF at build time, so the
   runtime only transforms and submits. */
static int anvil_mesh_drawn_frame;

double anvil_mesh_drawn(void) { return (double)anvil_mesh_drawn_frame; }
double anvil_mesh_culled(void) { return (double)anvil_mesh_culled_frame; }
double anvil_mesh_culling(double on) {
  anvil_mesh_culling_enabled = on != 0.0;
  return anvil_mesh_culling_enabled ? 1.0 : 0.0;
}

double anvil_mesh_draw(const double *data, int triangle_count, double cx,
                       double cy, double cz, double radius, double x, double y,
                       double z, double scale, double rx, double ry, double rz) {
  if (!data || triangle_count <= 0 || !(scale == scale) || scale == 0.0 ||
      !(x == x) || !(y == y) || !(z == z))
    return 0.0;
  if (!anvil_wasm_sphere_visible(cx, cy, cz, radius, x, y, z, scale, rx, ry,
                                 rz)) {
    anvil_mesh_culled_frame = 1;
    return 0.0;
  }
  anvil_mesh_culled_frame = 0;
  anvil_mesh_drawn_frame = 0;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    const double *p = data + (size_t)triangle * 12;
    AnvilWasmVec3 points[3];
    for (int vertex = 0; vertex < 3; ++vertex) {
      AnvilWasmVec3 local = {p[vertex * 3] * scale, p[vertex * 3 + 1] * scale,
                             p[vertex * 3 + 2] * scale};
      local = anvil_wasm_rotate(local, rx, ry, rz);
      points[vertex] =
          (AnvilWasmVec3){local.x + x, local.y + y, local.z + z};
    }
    int r = (int)p[9], g = (int)p[10], b = (int)p[11];
    AnvilWasmVec3 normal = anvil_wasm_normalize(
        anvil_wasm_cross(anvil_wasm_sub(points[1], points[0]),
                         anvil_wasm_sub(points[2], points[0])));
    anvil_wasm_triangle(points[0], points[1], points[2], normal, r, g, b, 255,
                        0.0, 0);
    anvil_wasm_shadow_triangle(points[0], points[1], points[2]);
    anvil_mesh_drawn_frame += 1;
  }
  return 1.0;
}

/* ---- Images, baked at compile time --------------------------------------
   The browser cannot read files synchronously, so the wasm backend bakes every
   BMP referenced by a literal image_load() into the module and registers it
   here. Drawing forwards the decoded pixels to the host, which owns the canvas
   and the scaling/rotation. */
enum {
  ANVIL_WASM_IMAGE_SLOTS = 32,
  ANVIL_WASM_IMAGE_STRIDE = 32
};

static const AnvilWasmImage *anvil_baked_images;
static int anvil_baked_image_count;
static int anvil_images_ready;
static const char *anvil_image_error_text = "";
static double anvil_wasm_image_bytes;
static double anvil_wasm_audio_bytes;

typedef struct {
  const AnvilWasmImage *source;
  unsigned int generation;
  int tint_r, tint_g, tint_b;
  int flip_x, flip_y;
  int used;
} AnvilWasmImageSlot;

static AnvilWasmImageSlot anvil_image_slots[ANVIL_WASM_IMAGE_SLOTS];

void anvil_wasm_set_images(const AnvilWasmImage *images, int count) {
  anvil_baked_images = images;
  anvil_baked_image_count = count;
}

void anvil_wasm_register_images(void) __attribute__((weak));

static void anvil_images_ensure(void) {
  if (anvil_images_ready)
    return;
  anvil_images_ready = 1;
  if (anvil_wasm_register_images)
    anvil_wasm_register_images();
}

const char *anvil_image_error(void) { return anvil_image_error_text; }

double anvil_memory_images(void) { return anvil_wasm_image_bytes; }
double anvil_memory_audio(void) { return anvil_wasm_audio_bytes; }
double anvil_memory_video(void) { return 960.0 * 600.0 * 4.0; }
double anvil_memory_total(void) {
  return anvil_memory_images() + anvil_memory_audio() + anvil_memory_video();
}

static AnvilWasmImageSlot *anvil_image_slot(double handle) {
  if (!(handle >= 1.0) || handle > 1.0e9)
    return NULL;
  int index = (int)(handle - 1.0) % ANVIL_WASM_IMAGE_STRIDE;
  unsigned int generation =
      (unsigned int)((handle - 1.0) / ANVIL_WASM_IMAGE_STRIDE) + 1;
  AnvilWasmImageSlot *slot = &anvil_image_slots[index];
  if (!slot->used || slot->generation != generation)
    return NULL;
  return slot;
}

double anvil_image_load(const char *path) {
  anvil_images_ensure();
  for (int index = 0; index < anvil_baked_image_count; ++index) {
    if (strcmp(anvil_baked_images[index].path, path) != 0)
      continue;
    for (int slot_index = 0; slot_index < ANVIL_WASM_IMAGE_SLOTS; ++slot_index) {
      AnvilWasmImageSlot *slot = &anvil_image_slots[slot_index];
      if (slot->used)
        continue;
      slot->used = 1;
      slot->source = &anvil_baked_images[index];
      slot->generation += 1;
      slot->tint_r = 255;
      slot->tint_g = 255;
      slot->tint_b = 255;
      slot->flip_x = 0;
      slot->flip_y = 0;
      anvil_wasm_image_bytes +=
          (double)slot->source->width * (double)slot->source->height * 4.0;
      anvil_image_error_text = "";
      return (double)(slot->generation - 1) * ANVIL_WASM_IMAGE_STRIDE +
             slot_index + 1;
    }
    anvil_image_error_text = "the image slots are full";
    return 0.0;
  }
  anvil_image_error_text =
      "the image was not baked into this build; only literal image_load() "
      "paths are available in the wasm backend";
  return 0.0;
}

double anvil_image_width(double handle) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  return slot ? (double)slot->source->width : 0.0;
}

double anvil_image_height(double handle) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  return slot ? (double)slot->source->height : 0.0;
}

double anvil_image_pixel(double handle, double x, double y) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot || !slot->source)
    return 0.0;
  if (!(x >= 0.0) || !(y >= 0.0) || x >= (double)slot->source->width ||
      y >= (double)slot->source->height)
    return 0.0;
  return (double)slot->source
      ->pixels[(int)y * (int)slot->source->width + (int)x];
}

double anvil_image_destroy(double handle) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot)
    return 0.0;
  anvil_wasm_image_bytes -=
      (double)slot->source->width * (double)slot->source->height * 4.0;
  slot->used = 0;
  slot->source = NULL;
  return 1.0;
}

static void anvil_image_blit(AnvilWasmImageSlot *slot, double dx, double dy,
                             double dw, double dh, double angle) {
  if (!slot)
    return;
  anvil_host_image_draw(slot->source->pixels, slot->source->width,
                        slot->source->height, dx, dy, dw, dh, angle,
                        slot->tint_r, slot->tint_g, slot->tint_b, slot->flip_x,
                        slot->flip_y);
}

double anvil_image_draw(double handle, double x, double y) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot)
    return 0.0;
  anvil_image_blit(slot, x, y, (double)slot->source->width,
                   (double)slot->source->height, 0.0);
  return 1.0;
}

double anvil_image_draw_scaled(double handle, double x, double y, double width,
                               double height) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot || !(width == width) || !(height == height) || width == 0.0 ||
      height == 0.0)
    return 0.0;
  anvil_image_blit(slot, x, y, width, height, 0.0);
  return 1.0;
}

double anvil_image_draw_rotated(double handle, double cx, double cy,
                                double degrees, double scale) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot || !(degrees == degrees) || !(scale == scale) || scale == 0.0)
    return 0.0;
  double width = (double)slot->source->width * scale;
  double height = (double)slot->source->height * scale;
  anvil_image_blit(slot, cx - width * 0.5, cy - height * 0.5, width, height,
                   degrees);
  return 1.0;
}


double anvil_image_draw_region(double handle, double sx, double sy, double sw,
                               double sh, double dx, double dy, double dw,
                               double dh) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot)
    return 0.0;
  double width = (double)slot->source->width;
  double height = (double)slot->source->height;
  if (!(sw > 0.0) || !(sh > 0.0) || !(dw == dw) || !(dh == dh) || sx < 0.0 ||
      sy < 0.0 || sx + sw > width || sy + sh > height)
    return 0.0;
  anvil_host_image_region(slot->source->pixels, slot->source->width,
                          slot->source->height, sx, sy, sw, sh, dx, dy, dw, dh,
                          slot->tint_r, slot->tint_g, slot->tint_b,
                          slot->flip_x, slot->flip_y);
  return 1.0;
}

double anvil_image_tint(double handle, double r, double g, double b) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot)
    return 0.0;
  slot->tint_r = r < 0 ? 0 : r > 255 ? 255 : (int)r;
  slot->tint_g = g < 0 ? 0 : g > 255 ? 255 : (int)g;
  slot->tint_b = b < 0 ? 0 : b > 255 ? 255 : (int)b;
  return 1.0;
}

double anvil_image_flip(double handle, double x, double y) {
  AnvilWasmImageSlot *slot = anvil_image_slot(handle);
  if (!slot)
    return 0.0;
  slot->flip_x = x != 0.0;
  slot->flip_y = y != 0.0;
  return 1.0;
}

__attribute__((import_module("env"), import_name("sound_play")))
extern int anvil_host_sound_play(const short *pcm, int frames, int channels,
                                 int rate, double volume, int loop, int group);
__attribute__((import_module("env"), import_name("sound_group_volume")))
extern void anvil_host_sound_group_volume(int group, double volume);
__attribute__((import_module("env"), import_name("sound_group_mute")))
extern void anvil_host_sound_group_mute(int group, int muted);
__attribute__((import_module("env"), import_name("sound_group_stop")))
extern int anvil_host_sound_group_stop(int group);
__attribute__((import_module("env"), import_name("sound_pan")))
extern void anvil_host_sound_pan(int voice, double pan);
__attribute__((import_module("env"), import_name("sound_pitch")))
extern void anvil_host_sound_pitch(int voice, double rate);
__attribute__((import_module("env"), import_name("sound_stop")))
extern void anvil_host_sound_stop(int voice);
__attribute__((import_module("env"), import_name("sound_stop_all")))
extern void anvil_host_sound_stop_all(void);
__attribute__((import_module("env"), import_name("sound_volume")))
extern void anvil_host_sound_volume(int voice, double volume);
__attribute__((import_module("env"), import_name("sound_active")))
extern int anvil_host_sound_active(void);

/* ---- Sounds, baked at compile time --------------------------------------
   The browser cannot stream a file synchronously, so literal sound_load()
   files are decoded while compiling and baked as int16 samples at their own
   sample rate. The host builds an AudioBuffer from them, so the browser does
   the resampling. */
enum {
  ANVIL_WASM_SOUND_SLOTS = 16,
  ANVIL_WASM_SOUND_STRIDE = 16
};

static const AnvilWasmSound *anvil_baked_sounds;
static int anvil_baked_sound_count;
static int anvil_sounds_ready;
static double anvil_wasm_sound_bytes(const AnvilWasmSound *source) {
  double rate = source->rate > 0.0 ? source->rate : 48000.0;
  return (double)source->frames * (48000.0 / rate) * 2.0 * 2.0;
}

static const char *anvil_sound_error_text = "";

typedef struct {
  const AnvilWasmSound *source;
  unsigned int generation;
  double volume;
  int group;
  int used;
} AnvilWasmSoundSlot;

/* Mirror of the host's mixer groups so group_gain can answer without a
   round trip. Group 0 is the master. */
static double anvil_group_volume[4] = {1.0, 1.0, 1.0, 1.0};
static int anvil_group_muted[4];

static AnvilWasmSoundSlot anvil_sound_slots[ANVIL_WASM_SOUND_SLOTS];

void anvil_wasm_set_sounds(const AnvilWasmSound *sounds, int count) {
  anvil_baked_sounds = sounds;
  anvil_baked_sound_count = count;
}

void anvil_wasm_register_sounds(void) __attribute__((weak));

static void anvil_sounds_ensure(void) {
  if (anvil_sounds_ready)
    return;
  anvil_sounds_ready = 1;
  if (anvil_wasm_register_sounds)
    anvil_wasm_register_sounds();
}

const char *anvil_sound_error(void) { return anvil_sound_error_text; }

static AnvilWasmSoundSlot *anvil_sound_slot(double handle) {
  if (!(handle >= 1.0) || handle > 1.0e9)
    return NULL;
  int index = (int)(handle - 1.0) % ANVIL_WASM_SOUND_STRIDE;
  unsigned int generation =
      (unsigned int)((handle - 1.0) / ANVIL_WASM_SOUND_STRIDE) + 1;
  AnvilWasmSoundSlot *slot = &anvil_sound_slots[index];
  if (!slot->used || slot->generation != generation)
    return NULL;
  return slot;
}

double anvil_sound_load(const char *path) {
  anvil_sounds_ensure();
  for (int index = 0; index < anvil_baked_sound_count; ++index) {
    if (strcmp(anvil_baked_sounds[index].path, path) != 0)
      continue;
    for (int slot_index = 0; slot_index < ANVIL_WASM_SOUND_SLOTS; ++slot_index) {
      AnvilWasmSoundSlot *slot = &anvil_sound_slots[slot_index];
      if (slot->used)
        continue;
      slot->used = 1;
      slot->source = &anvil_baked_sounds[index];
      slot->generation += 1;
      slot->volume = 1.0;
      slot->group = 1;
      anvil_wasm_audio_bytes += anvil_wasm_sound_bytes(slot->source);
      anvil_sound_error_text = "";
      return (double)(slot->generation - 1) * ANVIL_WASM_SOUND_STRIDE +
             slot_index + 1;
    }
    anvil_sound_error_text = "the sound slots are full";
    return 0.0;
  }
  anvil_sound_error_text =
      "the sound was not baked into this build; only literal sound_load() "
      "paths are available in the wasm backend";
  return 0.0;
}

double anvil_sound_start(double handle, int loop);

double anvil_sound_play(double handle) { return anvil_sound_start(handle, 0); }
double anvil_sound_play_loop(double handle) {
  return anvil_sound_start(handle, 1);
}
double anvil_sound_pan(double voice, double pan) {
  if (!(voice >= 1.0) || !(pan == pan))
    return 0.0;
  double clamped = pan < -1.0 ? -1.0 : pan > 1.0 ? 1.0 : pan;
  anvil_host_sound_pan((int)voice, clamped);
  return clamped;
}
double anvil_sound_pitch(double voice, double rate) {
  if (!(voice >= 1.0) || !(rate == rate))
    return 0.0;
  double clamped = rate < 0.25 ? 0.25 : rate > 4.0 ? 4.0 : rate;
  anvil_host_sound_pitch((int)voice, clamped);
  return clamped;
}
double anvil_sound_group(double handle, double group) {
  AnvilWasmSoundSlot *slot = anvil_sound_slot(handle);
  if (!slot || group < 1.0 || group > 3.0)
    return 0.0;
  slot->group = (int)group;
  return (double)slot->group;
}

double anvil_sound_group_volume(double group, double volume) {
  if (group < 0.0 || group > 3.0 || !(volume == volume))
    return 0.0;
  double clamped = volume < 0.0 ? 0.0 : volume > 1.0 ? 1.0 : volume;
  anvil_group_volume[(int)group] = clamped;
  anvil_host_sound_group_volume((int)group, clamped);
  return clamped;
}

double anvil_sound_group_mute(double group, double on) {
  if (group < 0.0 || group > 3.0)
    return 0.0;
  int muted = on != 0.0;
  anvil_group_muted[(int)group] = muted;
  anvil_host_sound_group_mute((int)group, muted);
  return (double)muted;
}

double anvil_sound_group_gain(double group) {
  if (group < 0.0 || group > 3.0)
    return 0.0;
  int index = (int)group;
  return anvil_group_muted[index] ? 0.0 : anvil_group_volume[index];
}

double anvil_sound_group_stop(double group) {
  if (group < 0.0 || group > 3.0)
    return 0.0;
  return (double)anvil_host_sound_group_stop((int)group);
}

double anvil_sound_duration(double handle) {
  AnvilWasmSoundSlot *slot = anvil_sound_slot(handle);
  if (!slot || slot->source->rate <= 0)
    return 0.0;
  return (double)slot->source->frames / (double)slot->source->rate;
}

double anvil_sound_start(double handle, int loop) {
  AnvilWasmSoundSlot *slot = anvil_sound_slot(handle);
  if (!slot)
    return 0.0;
  int voice = anvil_host_sound_play(slot->source->pcm, slot->source->frames,
                                    slot->source->channels,
                                    slot->source->rate, slot->volume, loop,
                                    slot->group);
  if (voice <= 0) {
    anvil_sound_error_text = "the host could not play the sound";
    return 0.0;
  }
  anvil_sound_error_text = "";
  return (double)voice;
}

double anvil_sound_stop(double voice) {
  if (!(voice >= 1.0))
    return 0.0;
  anvil_host_sound_stop((int)voice);
  return 1.0;
}

double anvil_sound_stop_all(void) {
  anvil_host_sound_stop_all();
  return 1.0;
}

double anvil_sound_volume(double voice, double volume) {
  if (!(voice >= 1.0) || !(volume == volume))
    return 0.0;
  double clamped = volume < 0.0 ? 0.0 : volume > 1.0 ? 1.0 : volume;
  anvil_host_sound_volume((int)voice, clamped);
  return clamped;
}

double anvil_sound_active(void) {
  return (double)anvil_host_sound_active();
}

double anvil_sound_destroy(double handle) {
  AnvilWasmSoundSlot *slot = anvil_sound_slot(handle);
  if (!slot)
    return 0.0;
  if (slot->source) {
    anvil_wasm_audio_bytes -= anvil_wasm_sound_bytes(slot->source);
    if (anvil_wasm_audio_bytes < 0.0) {
      anvil_wasm_audio_bytes = 0.0;
    }
  }
  slot->used = 0;
  slot->source = NULL;
  return 1.0;
}

/* ---- Noise and characters ----------------------------------------------- */
static int anvil_noise_hash(int x, int y, int z) {
  unsigned int h = (unsigned int)x * 374761393u +
                   (unsigned int)y * 668265263u +
                   (unsigned int)z * 2147483647u;
  h = (h ^ (h >> 13)) * 1274126177u;
  return (int)(h ^ (h >> 16));
}

static int anvil_noise_lattice(double value) {
  if (!(value >= -2147483648.0) || !(value < 2147483647.0)) {
    static const char message[] = "Anvil noise coordinate range error\n";
    anvil_host_write(2, message, (int)sizeof(message) - 1);
    exit(2);
  }
  return (int)floor(value);
}

static double anvil_noise_fade(double t) {
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

static double anvil_noise_grad(int hash, double x, double y, double z) {
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

static double anvil_noise_lerp(double a, double b, double t) {
  return a + t * (b - a);
}

double anvil_noise(double x, double y, double z) {
  int xi = anvil_noise_lattice(x), yi = anvil_noise_lattice(y),
      zi = anvil_noise_lattice(z);
  double xf = x - xi, yf = y - yi, zf = z - zi;
  double u = anvil_noise_fade(xf), v = anvil_noise_fade(yf),
         w = anvil_noise_fade(zf);
  double corners[8];
  for (int i = 0; i < 2; ++i)
    for (int j = 0; j < 2; ++j)
      for (int k = 0; k < 2; ++k)
        corners[i * 4 + j * 2 + k] = anvil_noise_grad(
            anvil_noise_hash(xi + i, yi + j, zi + k), xf - i, yf - j, zf - k);
  double x00 = anvil_noise_lerp(corners[0], corners[4], u);
  double x10 = anvil_noise_lerp(corners[2], corners[6], u);
  double x01 = anvil_noise_lerp(corners[1], corners[5], u);
  double x11 = anvil_noise_lerp(corners[3], corners[7], u);
  return anvil_noise_lerp(anvil_noise_lerp(x00, x10, v),
                          anvil_noise_lerp(x01, x11, v), w) *
         0.7;
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

double anvil_text_ord(const char *source) {
  return source[0] ? (double)(unsigned char)source[0] : 0.0;
}

char *anvil_text_chr(double code) {
  char *destination = anvil_text_buffer();
  if (!(code == code) || code < 0.0 || code > 255.0) {
    static const char message[] = "Anvil chr out of range\n";
    anvil_host_write(2, message, (int)sizeof(message) - 1);
    exit(1);
  }
  destination[0] = (char)(int)code;
  destination[1] = '\0';
  return destination;
}

/* ---- Text helpers ------------------------------------------------------- */
static size_t anvil_text_count(double value, size_t limit) {
  if (!(value == value) || value <= 0.0)
    return 0;
  if (value >= (double)limit)
    return limit;
  return (size_t)value;
}

char *anvil_text_lower(const char *source) {
  char *destination = anvil_text_buffer();
  size_t index = 0;
  for (; source[index] && index + 1 < ANVIL_STR_CAP; ++index) {
    char c = source[index];
    destination[index] = (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c;
  }
  destination[index] = '\0';
  return destination;
}

char *anvil_text_trim(const char *source) {
  char *destination = anvil_text_buffer();
  size_t length = strlen(source);
  size_t start = 0;
  size_t end = length;
  while (start < end && (source[start] == ' ' || source[start] == '\t'))
    start += 1;
  while (end > start && (source[end - 1] == ' ' || source[end - 1] == '\t'))
    end -= 1;
  for (size_t index = 0; index < end - start; ++index)
    destination[index] = source[start + index];
  destination[end - start] = '\0';
  return destination;
}

char *anvil_text_left(const char *source, double count) {
  char *destination = anvil_text_buffer();
  size_t length = strlen(source);
  size_t take = anvil_text_count(count, length);
  for (size_t index = 0; index < take; ++index)
    destination[index] = source[index];
  destination[take] = '\0';
  return destination;
}

char *anvil_text_right(const char *source, double count) {
  char *destination = anvil_text_buffer();
  size_t length = strlen(source);
  size_t take = anvil_text_count(count, length);
  for (size_t index = 0; index < take; ++index)
    destination[index] = source[length - take + index];
  destination[take] = '\0';
  return destination;
}

char *anvil_text_char(const char *source, double index) {
  char *destination = anvil_text_buffer();
  size_t length = strlen(source);
  if (!(index == index) || index < 0.0 || index >= (double)length) {
    destination[0] = '\0';
    return destination;
  }
  destination[0] = source[(size_t)index];
  destination[1] = '\0';
  return destination;
}

int anvil_str_contains(const char *source, const char *needle) {
  size_t needle_length = strlen(needle);
  if (needle_length == 0)
    return 1;
  for (size_t index = 0; source[index]; ++index) {
    size_t scan = 0;
    while (scan < needle_length && source[index + scan] == needle[scan])
      scan += 1;
    if (scan == needle_length)
      return 1;
  }
  return 0;
}

static void anvil_wasm_write_number_error(const char *path, int line, int index,
                                          int last) {
  char message[256];
  int at = 0;
  if (path) {
    for (const char *c = path; *c && at < 200; ++c)
      message[at++] = *c;
  } else {
    message[at++] = '?';
  }
  message[at++] = ':';
  char digits[16];
  int length = 0;
  int value = line < 0 ? -line : line;
  do {
    digits[length++] = (char)('0' + value % 10);
    value /= 10;
  } while (value > 0);
  if (line < 0)
    message[at++] = '-';
  while (length > 0)
    message[at++] = digits[--length];
  const char *middle = ": list index ";
  for (const char *c = middle; *c; ++c)
    message[at++] = *c;
  value = index < 0 ? -index : index;
  length = 0;
  do {
    digits[length++] = (char)('0' + value % 10);
    value /= 10;
  } while (value > 0);
  if (index < 0)
    message[at++] = '-';
  while (length > 0)
    message[at++] = digits[--length];
  const char *outside = " is outside 0..";
  for (const char *c = outside; *c; ++c)
    message[at++] = *c;
  value = last < 0 ? -last : last;
  length = 0;
  do {
    digits[length++] = (char)('0' + value % 10);
    value /= 10;
  } while (value > 0);
  if (last < 0)
    message[at++] = '-';
  while (length > 0)
    message[at++] = digits[--length];
  message[at++] = '\n';
  anvil_host_write(2, message, at);
}

double anvil_list_get(const double *values, int index, double count,
                      const char *path, int line) {
  if (!values || index < 0 || index >= (int)count) {
    anvil_wasm_write_number_error(path, line, index, (int)count - 1);
    exit(2);
  }
  return values[index];
}

int anvil_str_starts(const char *source, const char *prefix) {
  size_t index = 0;
  while (prefix[index]) {
    if (source[index] != prefix[index])
      return 0;
    index += 1;
  }
  return 1;
}

int anvil_str_ends(const char *source, const char *suffix) {
  size_t source_length = strlen(source);
  size_t suffix_length = strlen(suffix);
  if (suffix_length > source_length)
    return 0;
  for (size_t index = 0; index < suffix_length; ++index) {
    if (source[source_length - suffix_length + index] != suffix[index])
      return 0;
  }
  return 1;
}

/* ---- Saves --------------------------------------------------------------
   The host owns persistence (localStorage in the browser, a Map or JSON file
   under Node). Values are encoded as one type byte plus a payload: numbers as
   16 lowercase hex bytes of the IEEE-754 bit pattern, text as its UTF-8 bytes. */
enum {
  ANVIL_SAVE_TEXT_MAX = 255,
  ANVIL_SAVE_BUFFERS = 8,
  ANVIL_SAVE_SLOT_MAX = 64
};
static char anvil_save_buffers[ANVIL_SAVE_BUFFERS][ANVIL_SAVE_TEXT_MAX + 1];
static unsigned anvil_save_buffer_index;
static char anvil_project_name[64] = "Anvil_Game";
static const char *anvil_save_error_text = "";

static int anvil_slot_ok(const char *slot) {
  if (!slot)
    return 0;
  size_t length = strlen(slot);
  if (length == 0 || length > ANVIL_SAVE_SLOT_MAX)
    return 0;
  for (size_t index = 0; index < length; ++index) {
    char c = slot[index];
    int safe = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
               (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
    if (!safe)
      return 0;
  }
  return 1;
}

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
}

static int anvil_save_key(const char *slot, char *out, int capacity) {
  if (!anvil_slot_ok(slot)) {
    anvil_save_error_text = "the save slot is invalid";
    return 0;
  }
  int index = 0;
  for (const char *c = anvil_project_name; *c; ++c) {
    if (index >= capacity - 2)
      return 0;
    out[index++] = *c;
  }
  out[index++] = '/';
  for (const char *c = slot; *c; ++c) {
    if (index >= capacity - 1)
      return 0;
    out[index++] = *c;
  }
  out[index] = '\0';
  return 1;
}

static void anvil_hex16(unsigned long long value, char *out) {
  static const char digits[] = "0123456789abcdef";
  for (int index = 0; index < 16; ++index)
    out[index] = digits[(value >> (60 - 4 * index)) & 0xFu];
}

static unsigned long long anvil_unhex16(const char *text) {
  unsigned long long value = 0;
  for (int index = 0; index < 16; ++index) {
    char c = text[index];
    int digit;
    if (c >= '0' && c <= '9')
      digit = c - '0';
    else if (c >= 'a' && c <= 'f')
      digit = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F')
      digit = c - 'A' + 10;
    else
      return 0;
    value = (value << 4) | (unsigned long long)digit;
  }
  return value;
}

static int anvil_finite_bits(unsigned long long bits) {
  return ((bits >> 52) & 0x7FFULL) != 0x7FFULL;
}

const char *anvil_save_error(void) { return anvil_save_error_text; }

double anvil_save_number(const char *slot, double value) {
  char key[160];
  if (!anvil_save_key(slot, key, (int)sizeof(key)))
    return 0.0;
  union {
    double number;
    unsigned long long bits;
  } shaped;
  shaped.number = value;
  char payload[18];
  payload[0] = '1';
  anvil_hex16(shaped.bits, payload + 1);
  payload[17] = '\0';
  anvil_host_save_write(key, payload);
  anvil_save_error_text = "";
  return 1.0;
}

double anvil_load_number(const char *slot) {
  char key[160];
  if (!anvil_save_key(slot, key, (int)sizeof(key)))
    return 0.0;
  char payload[64];
  int length = anvil_host_save_read(key, payload, (int)sizeof(payload) - 1);
  if (length < 0) {
    anvil_save_error_text = "";
    return 0.0;
  }
  if (length > (int)sizeof(payload) - 1)
    length = (int)sizeof(payload) - 1;
  payload[length] = '\0';
  if (length == 0 || (payload[0] != '1' && payload[0] != '2')) {
    anvil_save_error_text = "the save is not a readable Anvil save";
    return 0.0;
  }
  if (payload[0] != '1') {
    anvil_save_error_text = "the save holds text, not a number";
    return 0.0;
  }
  if (length < 17) {
    anvil_save_error_text = "the save ended before its value did";
    return 0.0;
  }
  union {
    double number;
    unsigned long long bits;
  } shaped;
  shaped.bits = anvil_unhex16(payload + 1);
  if (!anvil_finite_bits(shaped.bits)) {
    anvil_save_error_text = "the save holds a non-finite number";
    return 0.0;
  }
  anvil_save_error_text = "";
  return shaped.number;
}

double anvil_save_text(const char *slot, const char *text) {
  const char *value = text ? text : "";
  size_t length = strlen(value);
  if (length > ANVIL_SAVE_TEXT_MAX) {
    const char *count = anvil_format_number((double)length);
    static char message[96];
    const char *prefix = "the text is ";
    const char *suffix = " bytes; the save limit is 255";
    int index = 0;
    for (const char *c = prefix; *c; ++c)
      message[index++] = *c;
    for (const char *c = count; *c; ++c)
      message[index++] = *c;
    for (const char *c = suffix; *c; ++c)
      message[index++] = *c;
    message[index] = '\0';
    anvil_save_error_text = message;
    return 0.0;
  }
  char key[160];
  if (!anvil_save_key(slot, key, (int)sizeof(key)))
    return 0.0;
  char payload[ANVIL_SAVE_TEXT_MAX + 2];
  payload[0] = '2';
  for (size_t index = 0; index <= length; ++index)
    payload[index + 1] = value[index];
  anvil_host_save_write(key, payload);
  anvil_save_error_text = "";
  return 1.0;
}

const char *anvil_load_text(const char *slot) {
  char *buffer = anvil_save_buffers[anvil_save_buffer_index &
                                    (ANVIL_SAVE_BUFFERS - 1)];
  anvil_save_buffer_index += 1;
  buffer[0] = '\0';
  char key[160];
  if (!anvil_save_key(slot, key, (int)sizeof(key)))
    return buffer;
  char payload[ANVIL_SAVE_TEXT_MAX + 8];
  int length = anvil_host_save_read(key, payload, (int)sizeof(payload) - 1);
  if (length < 0) {
    anvil_save_error_text = "";
    return buffer;
  }
  if (length > (int)sizeof(payload) - 1)
    length = (int)sizeof(payload) - 1;
  payload[length] = '\0';
  if (length == 0 || (payload[0] != '1' && payload[0] != '2')) {
    anvil_save_error_text = "the save is not a readable Anvil save";
    return buffer;
  }
  if (payload[0] != '2') {
    anvil_save_error_text = "the save holds a number, not text";
    return buffer;
  }
  int copied = length - 1;
  if (copied > ANVIL_SAVE_TEXT_MAX)
    copied = ANVIL_SAVE_TEXT_MAX;
  for (int index = 0; index < copied; ++index)
    buffer[index] = payload[index + 1];
  buffer[copied] = '\0';
  anvil_save_error_text = "";
  return buffer;
}

double anvil_save_exists(const char *slot) {
  char key[160];
  if (!anvil_save_key(slot, key, (int)sizeof(key)))
    return 0.0;
  char payload[4];
  return anvil_host_save_read(key, payload, (int)sizeof(payload)) >= 0 ? 1.0
                                                                     : 0.0;
}

double anvil_save_delete(const char *slot) {
  char key[160];
  if (!anvil_save_key(slot, key, (int)sizeof(key)))
    return 0.0;
  return anvil_host_save_delete(key) ? 1.0 : 0.0;
}

/* ---- Canvas 2D ---------------------------------------------------------- */
static int anvil_clear_r, anvil_clear_g, anvil_clear_b, anvil_clear_a;
static AnvilCallback anvil_frame_update, anvil_frame_draw;


void anvil_clear(int r, int g, int b, int a) {
  anvil_clear_r = r;
  anvil_clear_g = g;
  anvil_clear_b = b;
  anvil_clear_a = a;
}

void anvil_rect(double x, double y, double w, double h, int r, int g, int b,
                int a) {
  anvil_host_rect(x, y, w, h, r, g, b, a);
}

void anvil_circle(double x, double y, double radius, int r, int g, int b,
                  int a) {
  anvil_host_circle(x, y, radius, r, g, b, a);
}

void anvil_line(double x1, double y1, double x2, double y2, int r, int g, int b,
                int a, double thickness) {
  anvil_host_line(x1, y1, x2, y2, thickness, r, g, b, a);
}

void anvil_text(double x, double y, const char *text, int r, int g, int b,
                int a) {
  anvil_host_text(x, y, text, (int)strlen(text), r, g, b, a);
}

void anvil_trace_finish(void) {}

/* ---- Particles ---------------------------------------------------------- */
enum { ANVIL_PARTICLE_MAX = 4096 };

typedef struct {
  double x, y, vx, vy, age, life, size;
  int r, g, b, alive;
} AnvilParticle;

static AnvilParticle anvil_particles[ANVIL_PARTICLE_MAX];
static int anvil_particle_live;
static double anvil_particle_gravity_y;

double anvil_particle_emit(double x, double y, double vx, double vy,
                           double life, double size, int r, int g, int b) {
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(vx) || !anvil_wasm_finite(vy)) {
    return 0.0;
  }
  if (!(life > 0.0) || life > 600.0) {
    return 0.0;
  }
  if (!(size > 0.0) || size > 512.0) {
    return 0.0;
  }
  if (anvil_particle_live >= ANVIL_PARTICLE_MAX) {
    return 0.0;
  }
  for (int i = 0; i < ANVIL_PARTICLE_MAX; i++) {
    AnvilParticle *particle = &anvil_particles[i];
    if (particle->alive) {
      continue;
    }
    particle->x = x;
    particle->y = y;
    particle->vx = vx;
    particle->vy = vy;
    particle->age = 0.0;
    particle->life = life;
    particle->size = size;
    particle->r = r < 0 ? 0 : r > 255 ? 255 : r;
    particle->g = g < 0 ? 0 : g > 255 ? 255 : g;
    particle->b = b < 0 ? 0 : b > 255 ? 255 : b;
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
  if (!anvil_wasm_finite(gravity)) {
    return anvil_particle_gravity_y;
  }
  anvil_particle_gravity_y = gravity;
  return anvil_particle_gravity_y;
}

static void anvil_particles_update(double dt) {
  if (anvil_particle_live == 0) {
    return;
  }
  for (int i = 0; i < ANVIL_PARTICLE_MAX; i++) {
    AnvilParticle *particle = &anvil_particles[i];
    if (!particle->alive) {
      continue;
    }
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
  if (anvil_particle_live == 0) {
    return;
  }
  for (int i = 0; i < ANVIL_PARTICLE_MAX; i++) {
    AnvilParticle *particle = &anvil_particles[i];
    if (!particle->alive) {
      continue;
    }
    double fade = 1.0 - particle->age / particle->life;
    int alpha = (int)(255.0 * (fade < 0.0 ? 0.0 : fade > 1.0 ? 1.0 : fade));
    anvil_rect(particle->x - particle->size * 0.5,
               particle->y - particle->size * 0.5, particle->size,
               particle->size, particle->r, particle->g, particle->b, alpha);
  }
}

void anvil_run(AnvilCallback update, AnvilCallback draw, const char *title) {
  (void)title;
  anvil_frame_update = update;
  anvil_frame_draw = draw;
}

/* Called by the host once per animation frame; delta in milliseconds. */
__attribute__((export_name("anvil_frame"))) void anvil_frame(double delta_ms) {
  if (delta_ms < 0.0)
    delta_ms = 0.0;
  if (delta_ms > 250.0)
    delta_ms = 250.0;
  anvil_delta_seconds = delta_ms / 1000.0;
  anvil_time_seconds += anvil_delta_seconds;
  if (anvil_frame_update)
    anvil_frame_update();
  anvil_particles_update(anvil_delta_seconds);
  /* Edges last one frame, like the C runtime's first-update clearing. */
  memset(anvil_keys_pressed, 0, sizeof(anvil_keys_pressed));
  memset(anvil_mouse_pressed_buttons, 0, sizeof(anvil_mouse_pressed_buttons));
  anvil_mouse_wheel_value = 0.0;
  anvil_host_clear(anvil_clear_r, anvil_clear_g, anvil_clear_b, anvil_clear_a);
  if (anvil_frame_draw)
    anvil_frame_draw();
  anvil_particles_draw();
  anvil_host_present();
}

/* The browser composites for us, so this only records the preference. */
static double anvil_wasm_double_buffer = 1.0;

double anvil_buffer(double on) {
  double previous = anvil_wasm_double_buffer;
  anvil_wasm_double_buffer = on != 0.0 ? 1.0 : 0.0;
  return previous;
}

/* The wasm host draws through canvas calls immediately; keep the API shape. */
static double anvil_wasm_sprite_batch, anvil_wasm_sprite_depth;

double anvil_sprite_batch(double on) {
  double previous = anvil_wasm_sprite_batch;
  anvil_wasm_sprite_batch = on != 0.0 ? 1.0 : 0.0;
  return previous;
}

double anvil_sprite_depth(double depth) {
  double previous = anvil_wasm_sprite_depth;
  if (anvil_wasm_finite(depth))
    anvil_wasm_sprite_depth = depth;
  return previous;
}

double anvil_sprite_queued(void) { return 0.0; }

/* The canvas is the display surface, and reading it back synchronously is not
   possible from wasm; the compiler refuses the builtin before this point. */
double anvil_frame_capture(void) { return 0.0; }
