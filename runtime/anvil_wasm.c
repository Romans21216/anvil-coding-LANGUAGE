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
__attribute__((import_module("env"), import_name("fade")))
extern void anvil_host_fade(double alpha);
/* The page writes the label into an aria-live region, so a screen reader reads
   it without the canvas having to expose a widget tree. */
__attribute__((import_module("env"), import_name("announce")))
extern void anvil_host_announce(const char *label, int length);
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
__attribute__((import_module("env"), import_name("textured_triangle")))
extern void anvil_host_textured_triangle(
    const double *vertices, int triangle_count,
    const uint32_t *pixels, int width, int height, int layer);
__attribute__((import_module("env"), import_name("sphere_impostor_available")))
extern int anvil_host_sphere_impostor_available(void);
__attribute__((import_module("env"), import_name("sphere_impostor")))
extern void anvil_host_sphere_impostor(
    double x, double y, double z, double radius, int r, int g, int b, int a,
    double light_x, double light_y, double light_z, double focal);

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
static int anvil_wasm_ray_mesh_triangles_frame;
#define ANVIL_WASM_MODEL_TRIANGLE_BUDGET 16384
#define ANVIL_WASM_TEXTURED_MODEL_TRIANGLE_BUDGET 200000
static int anvil_wasm_textured_model_triangles_frame;
#define ANVIL_WASM_TEXTURE_RUN_BUDGET 256
static int anvil_wasm_texture_runs_frame;
static const uint32_t *anvil_wasm_last_texture_pixels;
static int anvil_wasm_last_texture_width, anvil_wasm_last_texture_height;
#define ANVIL_WASM_TEXTURE_BATCH_TRIANGLES 16384
static double anvil_wasm_texture_batch[ANVIL_WASM_TEXTURE_BATCH_TRIANGLES * 19];
static int anvil_wasm_texture_batch_count;
static int anvil_wasm_texture_batch_texture;
static double anvil_wasm_animated_textured_data[
    ANVIL_WASM_MODEL_TRIANGLE_BUDGET * 20];

static void anvil_wasm_texture_batch_flush(
    const uint32_t *const *textures, const int *texture_dimensions) {
  if (anvil_wasm_texture_batch_count <= 0)
    return;
  int texture = anvil_wasm_texture_batch_texture;
  anvil_host_textured_triangle(
      anvil_wasm_texture_batch, anvil_wasm_texture_batch_count,
      textures[texture], texture_dimensions[texture * 2],
      texture_dimensions[texture * 2 + 1], 1);
  anvil_wasm_texture_batch_count = 0;
}

static int anvil_wasm_texture_runs_preflight(
    const double *data, int triangle_count,
    const uint32_t *const *textures, const int *texture_dimensions,
    int texture_count, int *runs_out, const uint32_t **last_pixels_out,
    int *last_width_out, int *last_height_out) {
  const uint32_t *last_pixels = anvil_wasm_last_texture_pixels;
  int last_width = anvil_wasm_last_texture_width;
  int last_height = anvil_wasm_last_texture_height;
  int runs = 0;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    int texture = (int)data[(size_t)triangle * 20 + 19];
    if (texture < 0) {
      last_pixels = NULL;
      last_width = last_height = 0;
      continue;
    }
    if (texture >= texture_count || !textures[texture])
      continue;
    const uint32_t *pixels = textures[texture];
    int width = texture_dimensions[texture * 2];
    int height = texture_dimensions[texture * 2 + 1];
    if (pixels != last_pixels || width != last_width || height != last_height)
      ++runs;
    last_pixels = pixels;
    last_width = width;
    last_height = height;
  }
  if (runs > ANVIL_WASM_TEXTURE_RUN_BUDGET - anvil_wasm_texture_runs_frame)
    return 0;
  *runs_out = runs;
  *last_pixels_out = last_pixels;
  *last_width_out = last_width;
  *last_height_out = last_height;
  return 1;
}

#define ANVIL_WASM_MODEL_STATES 32
#define ANVIL_WASM_MORPH_TARGETS 8
#define ANVIL_WASM_MODEL_INSTANCES 64
#define ANVIL_WASM_INSTANCE_GENERATION_MAX 33554430
#define ANVIL_WASM_INSTANCE_HANDLE_MAX 2147483647.0
static double anvil_wasm_morph_values[ANVIL_WASM_MODEL_STATES]
                                          [ANVIL_WASM_MORPH_TARGETS];
static unsigned char anvil_wasm_morph_ready[ANVIL_WASM_MODEL_STATES];
static unsigned char anvil_wasm_morph_overridden[ANVIL_WASM_MODEL_STATES]
                                                    [ANVIL_WASM_MORPH_TARGETS];
typedef struct {
  int model_id;
  unsigned generation;
  int active, retired;
  double values[ANVIL_WASM_MORPH_TARGETS];
  unsigned char overridden[ANVIL_WASM_MORPH_TARGETS];
} AnvilWasmModelInstance;
static AnvilWasmModelInstance
    anvil_wasm_model_instances[ANVIL_WASM_MODEL_INSTANCES];
#define ANVIL_WASM_MODEL_NODES 128
static double anvil_wasm_model_times[ANVIL_WASM_MODEL_STATES];

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

static const char *anvil_current_function = "main";
static int anvil_current_source_line = 1;
#define ANVIL_WASM_SOURCE_STACK_MAX 1000
typedef struct {
  const char *function_name;
  int line;
} AnvilWasmSourceFrame;
static AnvilWasmSourceFrame
    anvil_source_stack[ANVIL_WASM_SOURCE_STACK_MAX];
static int anvil_source_stack_depth;

/* Format one dynamic numeric text label through the shared six-digit policy. */
void anvil_text_number(double x, double y, const char *prefix, double value,
                       int r, int g, int b, int a) {
  char buffer[ANVIL_STR_CAP];
  anvil_str_cat(buffer, prefix, anvil_format_number(value), NULL, 0);
  anvil_host_text(x, y, buffer, (int)strlen(buffer), r, g, b, a);
}

static void anvil_runtime_error(const char *message) {
  anvil_host_runtime_error(message, anvil_current_function,
                           anvil_current_source_line);
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
  if (anvil_frame_depth == 0) {
    anvil_wasm_ray_mesh_triangles_frame = 0;
    anvil_wasm_textured_model_triangles_frame = 0;
    anvil_wasm_texture_runs_frame = 0;
    anvil_wasm_last_texture_pixels = NULL;
    anvil_wasm_last_texture_width = 0;
    anvil_wasm_last_texture_height = 0;
  }
  anvil_frame_depth += 1;
  if (anvil_frame_depth > 1000)
    anvil_runtime_error("call depth exceeded the wasm frame budget");
}

void anvil_frame_leave(void) { anvil_frame_depth -= 1; }

/* Keep the active Anvil statement as well as the call chain so a browser trap
   can report the offending instruction line rather than only the function's
   declaration line. */
void anvil_wasm_source_line(int line) {
  if (line > 0)
    anvil_current_source_line = line;
}

void anvil_call_enter(const char *name) {
  if (anvil_source_stack_depth < ANVIL_WASM_SOURCE_STACK_MAX) {
    AnvilWasmSourceFrame *frame =
        &anvil_source_stack[anvil_source_stack_depth++];
    frame->function_name = anvil_current_function;
    frame->line = anvil_current_source_line;
  }
  anvil_current_function = name ? name : "?";
  anvil_current_source_line = 1;
}

void anvil_call_leave(void) {
  if (anvil_source_stack_depth <= 0)
    return;
  const AnvilWasmSourceFrame *frame =
      &anvil_source_stack[--anvil_source_stack_depth];
  anvil_current_function = frame->function_name;
  anvil_current_source_line = frame->line;
}

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

/* Format a number into a scratch slot so `text & number` joins work on wasm.
   The C runtime keeps this beside anvil_str_cat; the wasm shim was missing it
   entirely, so any program that joined a number to text failed to link. */
char *anvil_str_from_number(int slot, double value) {
  if (slot < 0 || slot >= 256)
    anvil_runtime_error("text slot is invalid");
  anvil_str_set(anvil_str_scratch[slot], anvil_format_number(value), NULL, 0);
  return anvil_str_scratch[slot];
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
static int anvil_mouse_has_position;
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
  anvil_mouse_has_position = 1;
}

__attribute__((export_name("anvil_mouse_button"))) void anvil_host_mouse_button(
    int button, int down) {
  if (button < 0 || button > 2)
    return;
  /* A press carries its own position, so a scripted click works without a
     preceding mousemove (the page sends one, but tests and hosts may not). */
  if (down)
    anvil_mouse_has_position = 1;
  if (down && !anvil_mouse_buttons[button])
    anvil_mouse_pressed_buttons[button] = 1;
  anvil_mouse_buttons[button] = down != 0;
}

__attribute__((export_name("anvil_wheel"))) void anvil_host_wheel(
    double delta) {
  anvil_mouse_wheel_value += delta;
}

/* The page calls this when the window loses focus. A keyup delivered to
   another window never arrives, so without this a held key or button would
   stay down and the next press would not register as a fresh press. */
__attribute__((export_name("anvil_input_release"))) void
anvil_host_input_release(void) {
  for (int index = 0; index < 256; ++index) {
    anvil_keys[index] = 0;
    anvil_keys_pressed[index] = 0;
  }
  for (int index = 0; index < 3; ++index) {
    anvil_mouse_buttons[index] = 0;
    anvil_mouse_pressed_buttons[index] = 0;
  }
  anvil_mouse_wheel_value = 0.0;
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
/* Exact product of two doubles as an unevaluated pair (Dekker's algorithm):
   the compiler is not allowed to fuse or reassociate this, so hi + lo is the
   product before rounding. */
static void anvil_two_product(double a, double b, double *hi, double *lo) {
  const double split = 134217729.0; /* 2^27 + 1 */
  double product = a * b;
  double ca = split * a;
  double a_hi = ca - (ca - a);
  double a_lo = a - a_hi;
  double cb = split * b;
  double b_hi = cb - (cb - b);
  double b_lo = b - b_hi;
  *hi = product;
  *lo = ((a_hi * b_hi - product) + a_hi * b_lo + a_lo * b_hi) + a_lo * b_lo;
}

/* Reduce an angle to [-pi, pi]. The old version multiplied by 1/2pi, rounded
   that quotient and subtracted one rounded product, so once the turn count
   passed 2^52 the fractional turn was not representable and the phase came out
   wrong (a 2pi step is 2.4e-16 wider than its double, and that gap is
   multiplied by the turn count). This keeps 2pi as a hi/lo pair and does the
   subtraction in double-double: exact through 1e15 radians, within 1e-11 of
   libm through the 1e20 limit. Beyond 1e20 the phase cannot be recovered
   without a 2/pi table (Payne-Hanek), so the reduction returns 0 - the C
   backend uses the CRT and has no such limit. */
static double anvil_wrap_angle(double value) {
  const double two_pi_hi = 6.283185307179586;
  const double two_pi_lo = 2.4492935982947064e-16; /* 2pi - two_pi_hi */
  const double inv_two_pi = 0.15915494309189535;
  const double pi = 3.14159265358979323846;
  const double limit = 1.0e20;
  if (value != value)
    return value; /* NaN in, NaN out */
  if (value > 1.0e308 || value < -1.0e308)
    return value - value; /* infinity -> NaN, matching libm */
  if (value > limit || value < -limit)
    return 0.0; /* documented domain limit */
  double reduced = value;
  for (int pass = 0; pass < 2; ++pass) {
    double quotient = reduced * inv_two_pi;
    double turns = __builtin_trunc(quotient + (quotient >= 0.0 ? 0.5 : -0.5));
    if (turns == 0.0)
      break;
    double hi = 0.0, lo = 0.0;
    anvil_two_product(turns, two_pi_hi, &hi, &lo);
    reduced = ((reduced - hi) - lo) - turns * two_pi_lo;
  }
  for (int pass = 0; pass < 4; ++pass) {
    if (reduced > pi)
      reduced -= two_pi_hi;
    else if (reduced < -pi)
      reduced += two_pi_hi;
    else
      break;
  }
  return reduced;
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

/* Tangent has period pi. Reduce into [-pi/2, pi/2], then use the reciprocal
   identity near the poles so the denominator is evaluated close to zero,
   where the wrapped Taylor series has its best relative accuracy. */
double tan(double radians) {
  const double half_pi = 1.57079632679489661923;
  const double half_pi_lo = 6.123233995736766e-17;
  double x;
  double sign = 1.0;
  int reciprocal = 0;
  if (radians > -1.0e6 && radians < 1.0e6) {
    /* For ordinary game angles, reduce against the nearest multiple of pi/2
       using a double-double product. This retains the tiny distance to a pole
       instead of first rounding it away in a full-angle modulo operation. */
    const double inv_half_pi = 0.63661977236758134308;
    double turns = __builtin_trunc(
        radians * inv_half_pi + (radians >= 0.0 ? 0.5 : -0.5));
    double pole_hi = 0.0, pole_lo = 0.0;
    anvil_two_product(turns, half_pi, &pole_hi, &pole_lo);
    x = ((radians - pole_hi) - pole_lo) - turns * half_pi_lo;
    long long pole = (long long)turns;
    if (pole % 2 != 0) {
      reciprocal = 1;
      sign = -1.0;
    }
  } else {
    x = anvil_wrap_angle(radians);
    double magnitude = x < 0.0 ? -x : x;
    sign = x < 0.0 ? -1.0 : 1.0;
    if (magnitude > half_pi) {
      /* Keep the tiny signed distance to the pole directly. Subtracting pi
         first would round that distance away before the reciprocal step. */
      x = (half_pi - magnitude) + half_pi_lo;
      reciprocal = 1;
    } else if (magnitude > 0.78539816339744830962) {
      x = (half_pi - magnitude) + half_pi_lo;
      reciprocal = 1;
    }
  }
  double x2 = x * x;
  double sine_term = x, sine = x;
  for (int n = 1; n <= 9; ++n) {
    sine_term *= -x2 / ((2.0 * n) * (2.0 * n + 1.0));
    sine += sine_term;
  }
  double cosine_term = 1.0, cosine = 1.0;
  for (int n = 1; n <= 9; ++n) {
    cosine_term *= -x2 / ((2.0 * n - 1.0) * (2.0 * n));
    cosine += cosine_term;
  }
  return reciprocal ? sign * cosine / sine : sine / cosine;
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
static AnvilWasmVec3 anvil_wasm_light_direction = {-0.35, 0.8, 0.55};
static double anvil_wasm_light_ambient_value = 0.28;
static double anvil_wasm_light_intensity_value = 1.0;
static int anvil_wasm_finite(double value);

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

double anvil_light(double x, double y, double z) {
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || (x == 0.0 && y == 0.0 && z == 0.0))
    return 0.0;
  anvil_wasm_light_direction = (AnvilWasmVec3){x, y, z};
  return 1.0;
}

double anvil_light_ambient(double level) {
  double previous = anvil_wasm_light_ambient_value;
  if (anvil_wasm_finite(level))
    anvil_wasm_light_ambient_value =
        level < 0.0 ? 0.0 : level > 1.0 ? 1.0 : level;
  return previous;
}

double anvil_light_intensity(double level) {
  double previous = anvil_wasm_light_intensity_value;
  if (anvil_wasm_finite(level))
    anvil_wasm_light_intensity_value =
        level < 0.0 ? 0.0 : level > 2.0 ? 2.0 : level;
  return previous;
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
static AnvilWasmVec3 anvil_wasm_rotate_trig(
    AnvilWasmVec3 p, double cx, double sx, double cy, double sy, double cz,
    double sz) {
  double c = cx, s = sx;
  p = (AnvilWasmVec3){p.x, p.y * c - p.z * s, p.y * s + p.z * c};
  c = cy;
  s = sy;
  p = (AnvilWasmVec3){p.x * c + p.z * s, p.y, -p.x * s + p.z * c};
  c = cz;
  s = sz;
  p = (AnvilWasmVec3){p.x * c - p.y * s, p.x * s + p.y * c, p.z};
  return p;
}
static AnvilWasmVec3 anvil_wasm_rotate(AnvilWasmVec3 p, double rx, double ry,
                                       double rz) {
  const double d = 0.017453292519943295769;
  rx *= d;
  ry *= d;
  rz *= d;
  return anvil_wasm_rotate_trig(p, cos(rx), sin(rx), cos(ry), sin(ry),
                                cos(rz), sin(rz));
}

static void anvil_wasm_get_camera_basis(AnvilWasmVec3 *right,
                                        AnvilWasmVec3 *up,
                                        AnvilWasmVec3 *forward) {
  const double radians = 0.017453292519943295769;
  double yaw = anvil_camera_yaw * radians;
  double pitch = anvil_camera_pitch * radians;
  *right = (AnvilWasmVec3){cos(yaw), 0.0, sin(yaw)};
  *forward = (AnvilWasmVec3){sin(yaw) * cos(pitch), sin(pitch),
                             -cos(yaw) * cos(pitch)};
  *up = anvil_wasm_normalize(anvil_wasm_cross(*right, *forward));
}
static AnvilWasmVec3 anvil_wasm_to_camera_basis(
    AnvilWasmVec3 p, AnvilWasmVec3 right, AnvilWasmVec3 up,
    AnvilWasmVec3 forward) {
  AnvilWasmVec3 relative = {p.x - anvil_camera_x, p.y - anvil_camera_y,
                            p.z - anvil_camera_z};
  return (AnvilWasmVec3){anvil_wasm_dot(relative, right),
                         anvil_wasm_dot(relative, up),
                         anvil_wasm_dot(relative, forward)};
}
static AnvilWasmVec3 anvil_wasm_to_camera(AnvilWasmVec3 p) {
  AnvilWasmVec3 right, up, forward;
  anvil_wasm_get_camera_basis(&right, &up, &forward);
  return anvil_wasm_to_camera_basis(p, right, up, forward);
}

static AnvilWasmVec3 anvil_wasm_direction_to_camera(AnvilWasmVec3 direction) {
  const double radians = 0.017453292519943295769;
  double yaw = anvil_camera_yaw * radians;
  double pitch = anvil_camera_pitch * radians;
  AnvilWasmVec3 right = {cos(yaw), 0.0, sin(yaw)};
  AnvilWasmVec3 forward = {sin(yaw) * cos(pitch), sin(pitch),
                           -cos(yaw) * cos(pitch)};
  AnvilWasmVec3 up = anvil_wasm_normalize(anvil_wasm_cross(right, forward));
  return (AnvilWasmVec3){anvil_wasm_dot(direction, right),
                         anvil_wasm_dot(direction, up),
                         anvil_wasm_dot(direction, forward)};
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

#define ANVIL_WASM_MODEL_NEAR_DEPTH 0.08

static int anvil_wasm_project_model_camera(AnvilWasmVec3 camera, double *sx,
                                           double *sy, double *depth) {
  if (!anvil_wasm_finite(camera.x) || !anvil_wasm_finite(camera.y) ||
      !anvil_wasm_finite(camera.z) ||
      camera.z < ANVIL_WASM_MODEL_NEAR_DEPTH)
    return 0;
  *sx = 480.0 + camera.x * anvil_camera_focal / camera.z;
  *sy = 324.0 - camera.y * anvil_camera_focal / camera.z;
  *depth = camera.z;
  return anvil_wasm_finite(*sx) && anvil_wasm_finite(*sy);
}

static int anvil_wasm_interpolation_parameter(double a, double b,
                                              double target, double *t) {
  double aa = __builtin_fabs(a), ab = __builtin_fabs(b);
  double at = __builtin_fabs(target);
  double scale = aa > ab ? aa : ab;
  if (at > scale) scale = at;
  if (!t || !anvil_wasm_finite(scale) || scale == 0.0)
    return 0;
  double scaled_a = a / scale;
  double denominator = b / scale - scaled_a;
  if (denominator == 0.0 || !anvil_wasm_finite(denominator))
    return 0;
  *t = (target / scale - scaled_a) / denominator;
  return anvil_wasm_finite(*t) && *t >= 0.0 && *t <= 1.0;
}

static double anvil_wasm_lerp_stable(double a, double b, double t) {
  return a * (1.0 - t) + b * t;
}

typedef struct {
  AnvilWasmVec3 camera;
  double u;
  double v;
} AnvilWasmTexturedVertex;

static int anvil_wasm_clip_textured_triangle(
    const AnvilWasmTexturedVertex input[3],
    AnvilWasmTexturedVertex output[4]) {
  int count = 0;
  AnvilWasmTexturedVertex previous = input[2];
  if (!anvil_wasm_finite(previous.camera.x) ||
      !anvil_wasm_finite(previous.camera.y) ||
      !anvil_wasm_finite(previous.camera.z) ||
      !anvil_wasm_finite(previous.u) || !anvil_wasm_finite(previous.v))
    return 0;
  int previous_inside = previous.camera.z >= ANVIL_WASM_MODEL_NEAR_DEPTH;
  for (int i = 0; i < 3; ++i) {
    AnvilWasmTexturedVertex current = input[i];
    if (!anvil_wasm_finite(current.camera.x) ||
        !anvil_wasm_finite(current.camera.y) ||
        !anvil_wasm_finite(current.camera.z) ||
        !anvil_wasm_finite(current.u) || !anvil_wasm_finite(current.v))
      return 0;
    int current_inside = current.camera.z >= ANVIL_WASM_MODEL_NEAR_DEPTH;
    if (current_inside != previous_inside) {
      double t;
      if (!anvil_wasm_interpolation_parameter(
              previous.camera.z, current.camera.z,
              ANVIL_WASM_MODEL_NEAR_DEPTH, &t) ||
          count >= 4)
        return 0;
      output[count++] = (AnvilWasmTexturedVertex){
          {anvil_wasm_lerp_stable(previous.camera.x, current.camera.x, t),
           anvil_wasm_lerp_stable(previous.camera.y, current.camera.y, t),
           ANVIL_WASM_MODEL_NEAR_DEPTH},
          anvil_wasm_lerp_stable(previous.u, current.u, t),
          anvil_wasm_lerp_stable(previous.v, current.v, t)};
    }
    if (current_inside) {
      if (count >= 4)
        return 0;
      output[count++] = current;
    }
    previous = current;
    previous_inside = current_inside;
  }
  return count;
}

static void anvil_wasm_triangle(AnvilWasmVec3 a, AnvilWasmVec3 b,
                                AnvilWasmVec3 c, AnvilWasmVec3 normal,
                                int r, int g, int bl, int alpha, int two_sided,
                                double depth_bias, int layer) {
  if (!anvil_scene_is_3d)
    return;
  double x1, y1, d1, x2, y2, d2, x3, y3, d3;
  if (!anvil_wasm_project(a, &x1, &y1, &d1) ||
      !anvil_wasm_project(b, &x2, &y2, &d2) ||
      !anvil_wasm_project(c, &x3, &y3, &d3))
    return;
  AnvilWasmVec3 light =
      anvil_wasm_normalize(anvil_wasm_light_direction);
  double facing = anvil_wasm_dot(anvil_wasm_normalize(normal), light);
  if (two_sided && facing < 0.0)
    facing = -facing;
  if (!(facing > 0.0))
    facing = 0.0;
  double shade = anvil_wasm_light_ambient_value +
                 (1.0 - anvil_wasm_light_ambient_value) *
                     anvil_wasm_light_intensity_value * facing;
  if (shade < 0.0)
    shade = 0.0;
  if (shade > 1.0)
    shade = 1.0;
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
  anvil_wasm_triangle(a, b, c, normal, r, g, bl, alpha, 0, bias, 0);
  anvil_wasm_triangle(a, c, d, normal, r, g, bl, alpha, 0, bias, 0);
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
  /* Match the outward winding of anvil_cube so one-sided lighting agrees. */
  anvil_wasm_quad(corners[0], corners[4], corners[6], corners[2], r, g, b, a);
  anvil_wasm_quad(corners[1], corners[3], corners[7], corners[5], r, g, b, a);
  anvil_wasm_quad(corners[0], corners[1], corners[5], corners[4], r, g, b, a);
  anvil_wasm_quad(corners[2], corners[6], corners[7], corners[3], r, g, b, a);
  anvil_wasm_quad(corners[0], corners[2], corners[3], corners[1], r, g, b, a);
  anvil_wasm_quad(corners[4], corners[5], corners[7], corners[6], r, g, b, a);
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

/* ---- Ray-traced spheres -------------------------------------------------
   The C runtime traces these against a per-frame BVH: a Lambert term from a
   fixed light, a Blinn-Phong highlight at exponent 28, and sphere-on-sphere
   shadows, all resolved per pixel. A WebGL page has no per-pixel tracer, so
   the browser build tessellates the sphere and evaluates the same shading
   model at each triangle's centroid. The light, the brightness curve and the
   highlight exponent are the C runtime's; silhouette edges and cast-shadow
   edges are polygons instead of exact curves, which is the honest difference
   between the two backends here.

   Spheres queue until the frame ends, because a sphere drawn first still has
   to be shadowed by one drawn later - the C tracer works that way too, since
   it runs after the frame's own draws. */
#define ANVIL_WASM_TRACE_MAX 32
#define ANVIL_WASM_TRACE_TRIANGLE_BUDGET 16384
typedef struct {
  AnvilWasmVec3 center;
  double radius;
  int r, g, b, a;
} AnvilWasmTraceSphere;
static AnvilWasmTraceSphere anvil_wasm_trace_spheres[ANVIL_WASM_TRACE_MAX];
static int anvil_wasm_trace_count;

void anvil_trace_sphere(double x, double y, double z, double radius, int r,
                        int g, int b, int a) {
  if (!(radius > 0.0) || anvil_wasm_trace_count >= ANVIL_WASM_TRACE_MAX)
    return;
  AnvilWasmTraceSphere *sphere =
      &anvil_wasm_trace_spheres[anvil_wasm_trace_count++];
  sphere->center = (AnvilWasmVec3){x, y, z};
  sphere->radius = radius;
  sphere->r = r;
  sphere->g = g;
  sphere->b = b;
  sphere->a = a;
}

/* Nearest positive root, or -1. Same epsilon and same "inside the sphere"
   fallback as the C tracer, so a camera inside a sphere still shades. */
static double anvil_wasm_ray_hit(AnvilWasmVec3 origin, AnvilWasmVec3 direction,
                                 AnvilWasmVec3 center, double radius) {
  AnvilWasmVec3 offset = anvil_wasm_sub(origin, center);
  double half_b = anvil_wasm_dot(offset, direction);
  double c = anvil_wasm_dot(offset, offset) - radius * radius;
  double discriminant = half_b * half_b - c;
  if (discriminant < 0.0)
    return -1.0;
  double root = __builtin_sqrt(discriminant);
  double t = -half_b - root;
  if (t <= 0.001)
    t = -half_b + root;
  return t <= 0.001 ? -1.0 : t;
}

static int anvil_wasm_trace_shadowed(AnvilWasmVec3 origin, AnvilWasmVec3 light) {
  for (int index = 0; index < anvil_wasm_trace_count; ++index) {
    const AnvilWasmTraceSphere *sphere = &anvil_wasm_trace_spheres[index];
    if (anvil_wasm_ray_hit(origin, light, sphere->center, sphere->radius) > 0.0)
      return 1;
  }
  return 0;
}

static int anvil_wasm_channel(double value) {
  if (!(value > 0.0))
    return 0;
  return value > 255.0 ? 255 : (int)value;
}

/* x^28 by squaring; the freestanding runtime carries no pow(). */
static double anvil_wasm_pow28(double base) {
  if (!(base > 0.0))
    return 0.0;
  double x2 = base * base, x4 = x2 * x2, x8 = x4 * x4, x16 = x8 * x8;
  return x16 * x8 * x4;
}

/* `point` must be on the sphere, not the triangle's centroid: a centroid sits
   slightly inside the surface, so the shadow ray would start inside the sphere
   and the sphere would shadow itself - every triangle came out at the 0.13
   shadowed brightness before this was split out. */
static void anvil_wasm_trace_shade(AnvilWasmVec3 point, AnvilWasmVec3 normal,
                                   const AnvilWasmTraceSphere *sphere,
                                   AnvilWasmVec3 light, AnvilWasmVec3 view,
                                   int *red, int *green, int *blue) {
  double diffuse = anvil_wasm_dot(normal, light);
  if (diffuse < 0.0)
    diffuse = 0.0;
  int shadowed = 0;
  if (diffuse > 0.0) {
    AnvilWasmVec3 origin = {point.x + normal.x * 0.002,
                            point.y + normal.y * 0.002,
                            point.z + normal.z * 0.002};
    shadowed = anvil_wasm_trace_shadowed(origin, light);
  }
  double brightness = shadowed ? 0.13 : 0.16 + 0.78 * diffuse;
  AnvilWasmVec3 halfway = anvil_wasm_normalize(
      (AnvilWasmVec3){light.x + view.x, light.y + view.y, light.z + view.z});
  double specular = anvil_wasm_pow28(anvil_wasm_dot(normal, halfway)) * 0.22;
  *red = anvil_wasm_channel(sphere->r * brightness + 255.0 * specular);
  *green = anvil_wasm_channel(sphere->g * brightness + 255.0 * specular);
  *blue = anvil_wasm_channel(sphere->b * brightness + 255.0 * specular);
}

static void anvil_wasm_triangle_flat(AnvilWasmVec3 a, AnvilWasmVec3 b,
                                     AnvilWasmVec3 c, int red, int green,
                                     int blue, int alpha) {
  double x1, y1, d1, x2, y2, d2, x3, y3, d3;
  if (!anvil_wasm_project(a, &x1, &y1, &d1) ||
      !anvil_wasm_project(b, &x2, &y2, &d2) ||
      !anvil_wasm_project(c, &x3, &y3, &d3))
    return;
  anvil_host_triangle(x1, y1, d1, x2, y2, d2, x3, y3, d3, red, green, blue,
                      alpha, 0);
}

void anvil_wasm_trace_flush(void) {
  if (anvil_wasm_trace_count == 0)
    return;
  if (!anvil_scene_is_3d) {
    anvil_wasm_trace_count = 0;
    return;
  }
  const double pi = 3.14159265358979323846;
  const double tau = 6.283185307179586476925;
  const AnvilWasmVec3 light =
      anvil_wasm_normalize((AnvilWasmVec3){-0.4, 0.75, 0.55});
  if (anvil_host_sphere_impostor_available()) {
    AnvilWasmVec3 camera_light = anvil_wasm_direction_to_camera(light);
    for (int index = 0; index < anvil_wasm_trace_count; ++index) {
      const AnvilWasmTraceSphere *sphere = &anvil_wasm_trace_spheres[index];
      AnvilWasmVec3 center = anvil_wasm_to_camera(sphere->center);
      if (center.z + sphere->radius <= 0.05)
        continue;
      anvil_host_sphere_impostor(
          center.x, center.y, center.z, sphere->radius, sphere->r, sphere->g,
          sphere->b, sphere->a, camera_light.x, camera_light.y,
          camera_light.z, anvil_camera_focal);
    }
    anvil_wasm_trace_count = 0;
    return;
  }
  const AnvilWasmVec3 eye = {anvil_camera_x, anvil_camera_y, anvil_camera_z};
  int remaining_budget = ANVIL_WASM_TRACE_TRIANGLE_BUDGET;
  for (int index = 0; index < anvil_wasm_trace_count; ++index) {
    const AnvilWasmTraceSphere *sphere = &anvil_wasm_trace_spheres[index];
    AnvilWasmVec3 camera_center = anvil_wasm_to_camera(sphere->center);
    double nearest_z = camera_center.z - sphere->radius;
    if (nearest_z < 0.05)
      nearest_z = 0.05;
    double projected_radius = sphere->radius * anvil_camera_focal / nearest_z;
    if (projected_radius < 0.5)
      projected_radius = 0.5;
    /* For small angular steps, sagitta is approximately R*angle^2/2.
       A 0.5 px silhouette error therefore gives this angular step without
       requiring libm acos in the freestanding wasm runtime. */
    double half_angle = 1.0 / __builtin_sqrt(projected_radius);
    int rings = (int)(pi / (2.0 * half_angle) + 0.999999);
    int segments = (int)(pi / half_angle + 0.999999);
    if (rings < 6)
      rings = 6;
    if (rings > 36)
      rings = 36;
    if (segments < 8)
      segments = 8;
    if (segments > 54)
      segments = 54;
    int remaining_spheres = anvil_wasm_trace_count - index;
    int sphere_budget = remaining_budget / remaining_spheres;
    while (rings * segments * 2 > sphere_budget &&
           (rings > 4 || segments > 8)) {
      double ring_ratio = (double)rings / 36.0;
      double segment_ratio = (double)segments / 54.0;
      if (rings > 4 && (segments <= 8 || ring_ratio >= segment_ratio))
        rings--;
      else if (segments > 8)
        segments--;
    }
    int sphere_triangles = rings * segments * 2;
    if (sphere_triangles > sphere_budget) {
      anvil_wasm_trace_count = 0;
      return;
    }
    remaining_budget -= sphere_triangles;
    for (int ring = 0; ring < rings; ++ring) {
      double phi0 = pi * (double)ring / (double)rings;
      double phi1 = pi * (double)(ring + 1) / (double)rings;
      for (int segment = 0; segment < segments; ++segment) {
        double theta0 = tau * (double)segment / (double)segments;
        double theta1 = tau * (double)(segment + 1) / (double)segments;
        double phis[2] = {phi0, phi1};
        double thetas[2] = {theta0, theta1};
        AnvilWasmVec3 quad[4];
        for (int corner = 0; corner < 4; ++corner) {
          double phi = phis[corner >> 1];
          double theta = thetas[corner & 1];
          quad[corner] =
              (AnvilWasmVec3){sphere->center.x + sphere->radius * sin(phi) * cos(theta),
                              sphere->center.y + sphere->radius * cos(phi),
                              sphere->center.z + sphere->radius * sin(phi) * sin(theta)};
        }
        AnvilWasmVec3 triangles[2][3] = {{quad[0], quad[1], quad[3]},
                                         {quad[0], quad[3], quad[2]}};
        for (int tri = 0; tri < 2; ++tri) {
          AnvilWasmVec3 center = {
              (triangles[tri][0].x + triangles[tri][1].x + triangles[tri][2].x) / 3.0,
              (triangles[tri][0].y + triangles[tri][1].y + triangles[tri][2].y) / 3.0,
              (triangles[tri][0].z + triangles[tri][1].z + triangles[tri][2].z) / 3.0};
          AnvilWasmVec3 outward =
              anvil_wasm_normalize(anvil_wasm_sub(center, sphere->center));
          AnvilWasmVec3 sight = anvil_wasm_normalize(anvil_wasm_sub(eye, center));
          /* Back faces would only be overdrawn; skipping them halves the op
             stream and keeps the painter's sort from flickering. */
          if (anvil_wasm_dot(outward, sight) <= 0.0)
            continue;
          AnvilWasmVec3 surface = {sphere->center.x + outward.x * sphere->radius,
                                   sphere->center.y + outward.y * sphere->radius,
                                   sphere->center.z + outward.z * sphere->radius};
          int red, green, blue;
          anvil_wasm_trace_shade(surface, outward, sphere, light, sight, &red,
                                 &green, &blue);
          anvil_wasm_triangle_flat(triangles[tri][0], triangles[tri][1],
                                   triangles[tri][2], red, green, blue, sphere->a);
        }
      }
    }
  }
  anvil_wasm_trace_count = 0;
}


__attribute__((import_module("env"), import_name("music_play")))
extern int anvil_host_music_play(const short *pcm, int frames, int channels,
                                 int rate, double volume, int loop);
__attribute__((import_module("env"), import_name("music_stream")))
extern int anvil_host_music_stream(const char *url, double duration,
                                   double volume, int loop);
__attribute__((import_module("env"), import_name("music_stop")))
extern void anvil_host_music_stop(void);
__attribute__((import_module("env"), import_name("music_playing")))
extern int anvil_host_music_playing(void);
__attribute__((import_module("env"), import_name("music_volume")))
extern void anvil_host_music_volume(double volume);
__attribute__((import_module("env"), import_name("music_position")))
extern double anvil_host_music_position(void);

/* ---- Music, streamed by the browser or played by the Node test host -------
   Browser builds publish one WAV beside the HTML host and use an
   HTMLMediaElement so samples are fetched and decoded incrementally. */
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
  if (anvil_baked_music_value->stream_url)
    return anvil_host_music_stream(anvil_baked_music_value->stream_url,
                                   anvil_baked_music_value->duration,
                                   anvil_music_volume_value, loop) > 0
               ? 1.0
               : 0.0;
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
  if (anvil_baked_music_value && anvil_baked_music_value->stream_url)
    return anvil_baked_music_value->duration;
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
                      anvil_shadow_alpha_value, 0, 0.0, 1);
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
  double scaled = radius * fabs(scale);
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
  if (!data || triangle_count <= 0 ||
      triangle_count > ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                           anvil_wasm_ray_mesh_triangles_frame ||
      !anvil_wasm_finite(cx) || !anvil_wasm_finite(cy) ||
      !anvil_wasm_finite(cz) || !anvil_wasm_finite(radius) || radius < 0.0 ||
      !anvil_wasm_finite(scale) || scale == 0.0 || !anvil_wasm_finite(x) ||
      !anvil_wasm_finite(y) || !anvil_wasm_finite(z) ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz))
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
                        1, 0.0, 0);
    anvil_wasm_shadow_triangle(points[0], points[1], points[2]);
    anvil_mesh_drawn_frame += 1;
  }
  anvil_wasm_ray_mesh_triangles_frame += triangle_count;
  return 1.0;
}

/* Textured baked models use 20 doubles per triangle: three position/UV pairs,
   RGB tint, alpha, and a texture table index. Pixel arrays are embedded in the
   module and consumed by the browser host during frame presentation. */
double anvil_mesh_draw_textured(
    const double *data, int triangle_count, const uint32_t *const *textures,
    const int *texture_dimensions, int texture_count, double cx, double cy,
    double cz, double radius, double x, double y, double z, double scale,
    double rx, double ry, double rz) {
  if (!data || !textures || !texture_dimensions || triangle_count <= 0 ||
      texture_count <= 0 || triangle_count > ANVIL_WASM_TEXTURED_MODEL_TRIANGLE_BUDGET -
          anvil_wasm_textured_model_triangles_frame ||
      !anvil_wasm_finite(cx) || !anvil_wasm_finite(cy) ||
      !anvil_wasm_finite(cz) || !anvil_wasm_finite(radius) || radius < 0.0 ||
      !anvil_wasm_finite(scale) || scale == 0.0 || !anvil_wasm_finite(x) ||
      !anvil_wasm_finite(y) || !anvil_wasm_finite(z) ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz)) return 0.0;
  if (!anvil_wasm_sphere_visible(cx, cy, cz, radius, x, y, z, scale, rx, ry,
                                 rz)) {
    anvil_mesh_culled_frame = 1;
    return 0.0;
  }
  anvil_mesh_culled_frame = 0;
  anvil_mesh_drawn_frame = 0;
  const double radians = 0.017453292519943295769;
  double rx_radians = rx * radians, ry_radians = ry * radians;
  double rz_radians = rz * radians;
  double cos_rx = cos(rx_radians), sin_rx = sin(rx_radians);
  double cos_ry = cos(ry_radians), sin_ry = sin(ry_radians);
  double cos_rz = cos(rz_radians), sin_rz = sin(rz_radians);
  AnvilWasmVec3 camera_right, camera_up, camera_forward;
  anvil_wasm_get_camera_basis(&camera_right, &camera_up, &camera_forward);
  int texture_runs = 0, last_width = 0, last_height = 0;
  const uint32_t *last_pixels = NULL;
  if (!anvil_wasm_texture_runs_preflight(
          data, triangle_count, textures, texture_dimensions, texture_count,
          &texture_runs, &last_pixels, &last_width, &last_height))
    return 0.0;
  anvil_wasm_texture_batch_count = 0;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    const double *p = data + (size_t)triangle * 20;
    AnvilWasmVec3 world[3];
    AnvilWasmTexturedVertex camera[3];
    for (int vertex = 0; vertex < 3; ++vertex) {
      AnvilWasmVec3 local = {p[vertex * 5] * scale,
                             p[vertex * 5 + 1] * scale,
                             p[vertex * 5 + 2] * scale};
      local = anvil_wasm_rotate_trig(local, cos_rx, sin_rx, cos_ry, sin_ry,
                                     cos_rz, sin_rz);
      world[vertex] = (AnvilWasmVec3){local.x + x, local.y + y, local.z + z};
      camera[vertex] = (AnvilWasmTexturedVertex){
          anvil_wasm_to_camera_basis(world[vertex], camera_right, camera_up,
                                     camera_forward), p[vertex * 5 + 3],
          p[vertex * 5 + 4]};
    }
    AnvilWasmTexturedVertex clipped[4];
    int clipped_count =
        anvil_wasm_clip_textured_triangle(camera, clipped);
    if (clipped_count < 3)
      continue;
    double projected[4][3];
    int projectable = 1;
    for (int vertex = 0; vertex < clipped_count; ++vertex) {
      if (!anvil_wasm_project_model_camera(
              clipped[vertex].camera, &projected[vertex][0],
              &projected[vertex][1], &projected[vertex][2])) {
        projectable = 0;
        break;
      }
    }
    if (!projectable)
      continue;
    AnvilWasmVec3 normal = anvil_wasm_normalize(
        anvil_wasm_cross(anvil_wasm_sub(world[1], world[0]),
                         anvil_wasm_sub(world[2], world[0])));
    double facing = anvil_wasm_dot(
        normal, anvil_wasm_normalize(anvil_wasm_light_direction));
    if (facing < 0.0) facing = -facing;
    double shade = anvil_wasm_light_ambient_value +
        (1.0 - anvil_wasm_light_ambient_value) *
        anvil_wasm_light_intensity_value * facing;
    if (shade < 0.0) shade = 0.0;
    if (shade > 1.0) shade = 1.0;
    int texture = (int)p[19];
    if (texture < 0) {
      anvil_wasm_texture_batch_flush(textures, texture_dimensions);
      double alpha = p[18];
      if (alpha < 0.0) alpha = 0.0;
      if (alpha > 255.0) alpha = 255.0;
      anvil_wasm_triangle(world[0], world[1], world[2], normal,
                          (int)p[15], (int)p[16], (int)p[17], (int)alpha, 1,
                          0.0, 1);
      anvil_mesh_drawn_frame += 1;
      continue;
    }
    if (texture >= texture_count || !textures[texture]) continue;
    if (anvil_wasm_texture_batch_count &&
        texture != anvil_wasm_texture_batch_texture) {
      anvil_wasm_texture_batch_flush(textures, texture_dimensions);
    }
    anvil_wasm_texture_batch_texture = texture;
    double alpha = p[18];
    if (alpha < 0.0) alpha = 0.0;
    if (alpha > 255.0) alpha = 255.0;
    for (int vertex = 1; vertex + 1 < clipped_count; ++vertex) {
      const int fan[3] = {0, vertex, vertex + 1};
      if (anvil_wasm_texture_batch_count >= ANVIL_WASM_TEXTURE_BATCH_TRIANGLES)
        anvil_wasm_texture_batch_flush(textures, texture_dimensions);
      double *batch = anvil_wasm_texture_batch +
          (size_t)anvil_wasm_texture_batch_count * 19;
      for (int corner = 0; corner < 3; ++corner) {
        int source = fan[corner];
        batch[corner * 5] = projected[source][0];
        batch[corner * 5 + 1] = projected[source][1];
        batch[corner * 5 + 2] = projected[source][2];
        batch[corner * 5 + 3] = clipped[source].u;
        batch[corner * 5 + 4] = clipped[source].v;
      }
      batch[15] = p[15] * shade;
      batch[16] = p[16] * shade;
      batch[17] = p[17] * shade;
      batch[18] = alpha;
      anvil_wasm_texture_batch_count++;
      anvil_mesh_drawn_frame += 1;
    }
  }
  anvil_wasm_texture_batch_flush(textures, texture_dimensions);
  anvil_wasm_textured_model_triangles_frame += triangle_count;
  anvil_wasm_texture_runs_frame += texture_runs;
  anvil_wasm_last_texture_pixels = last_pixels;
  anvil_wasm_last_texture_width = last_width;
  anvil_wasm_last_texture_height = last_height;
  return 1.0;
}

double anvil_trace_mesh(const double *data, int triangle_count, double cx,
                        double cy, double cz, double radius, double x,
                        double y, double z, double scale, double rx,
                        double ry, double rz) {
  if (!anvil_scene_is_3d || !data || triangle_count <= 0 ||
      triangle_count > ANVIL_WASM_MODEL_TRIANGLE_BUDGET ||
      !anvil_wasm_finite(cx) || !anvil_wasm_finite(cy) ||
      !anvil_wasm_finite(cz) || !anvil_wasm_finite(radius) || radius < 0.0 ||
      !anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || !anvil_wasm_finite(scale) || scale == 0.0 ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz))
    return 0.0;
  if (!anvil_wasm_sphere_visible(cx, cy, cz, radius, x, y, z, scale, rx, ry,
                                 rz)) {
    anvil_mesh_culled_frame = 1;
    return 1.0;
  }
  if (triangle_count > ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                           anvil_wasm_ray_mesh_triangles_frame)
    return 0.0;
  if (!anvil_mesh_draw(data, triangle_count, cx, cy, cz, radius, x, y, z,
                       scale, rx, ry, rz))
    return 0.0;
  return 1.0;
}

double anvil_trace_mesh_textured(
    const double *data, const double *textured_data,
    const uint32_t *const *textures, const int *texture_dimensions,
    int texture_count, int triangle_count, double cx, double cy, double cz,
    double radius, double x, double y, double z, double scale, double rx,
    double ry, double rz) {
  if (!anvil_scene_is_3d || !data || !textured_data || !textures ||
      !texture_dimensions || triangle_count <= 0 ||
      triangle_count > ANVIL_WASM_MODEL_TRIANGLE_BUDGET || texture_count <= 0 ||
      !anvil_wasm_finite(cx) || !anvil_wasm_finite(cy) ||
      !anvil_wasm_finite(cz) || !anvil_wasm_finite(radius) || radius < 0.0 ||
      !anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || !anvil_wasm_finite(scale) || scale == 0.0 ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz))
    return 0.0;
  if (!anvil_wasm_sphere_visible(cx, cy, cz, radius, x, y, z, scale, rx, ry,
                                 rz)) {
    anvil_mesh_culled_frame = 1;
    return 1.0;
  }
  if (triangle_count > ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                           anvil_wasm_ray_mesh_triangles_frame)
    return 0.0;
  if (!anvil_mesh_draw_textured(
          textured_data, triangle_count, textures, texture_dimensions,
          texture_count, cx, cy, cz, radius, x, y, z, scale, rx, ry, rz))
    return 0.0;
  anvil_wasm_ray_mesh_triangles_frame += triangle_count;
  return 1.0;
}

const double *anvil_model_morph_weights(int id, const double *defaults,
                                        int count) {
  if (id < 0 || id >= ANVIL_WASM_MODEL_STATES || !defaults || count <= 0 ||
      count > ANVIL_WASM_MORPH_TARGETS)
    return defaults;
  if (!anvil_wasm_morph_ready[id]) {
    for (int target = 0; target < ANVIL_WASM_MORPH_TARGETS; ++target)
      anvil_wasm_morph_values[id][target] =
          target < count ? defaults[target] : 0.0;
    anvil_wasm_morph_ready[id] = 1;
  }
  return anvil_wasm_morph_values[id];
}

double anvil_model_morph(int id, int index, double weight,
                         const double *defaults, int count) {
  if (id < 0 || id >= ANVIL_WASM_MODEL_STATES || index < 0 ||
      index >= ANVIL_WASM_MORPH_TARGETS || !anvil_wasm_finite(weight) ||
      !defaults || count <= 0 || count > ANVIL_WASM_MORPH_TARGETS)
    return 0.0;
  anvil_model_morph_weights(id, defaults, count);
  double previous = anvil_wasm_morph_values[id][index];
  anvil_wasm_morph_values[id][index] =
      weight < 0.0 ? 0.0 : weight > 1.0 ? 1.0 : weight;
  anvil_wasm_morph_overridden[id][index] = 1;
  return previous;
}

static AnvilWasmModelInstance *anvil_wasm_instance_lookup(double handle,
                                                           int model_id) {
  if (!anvil_wasm_finite(handle) || handle < 1.0 ||
      handle > ANVIL_WASM_INSTANCE_HANDLE_MAX ||
      (double)(int)handle != handle)
    return NULL;
  unsigned token = (unsigned)handle - 1u;
  unsigned slot = token % ANVIL_WASM_MODEL_INSTANCES;
  unsigned generation = token / ANVIL_WASM_MODEL_INSTANCES;
  AnvilWasmModelInstance *instance = &anvil_wasm_model_instances[slot];
  return instance->active && instance->generation == generation &&
                 instance->model_id == model_id
             ? instance
             : NULL;
}

double anvil_model_instance_create(int model_id, int morph_count) {
  if (model_id < 0 || model_id >= ANVIL_WASM_MODEL_STATES || morph_count <= 0 ||
      morph_count > ANVIL_WASM_MORPH_TARGETS)
    return 0.0;
  for (unsigned slot = 0; slot < ANVIL_WASM_MODEL_INSTANCES; ++slot) {
    AnvilWasmModelInstance *instance = &anvil_wasm_model_instances[slot];
    if (instance->active || instance->retired)
      continue;
    double handle = (double)instance->generation *
                        ANVIL_WASM_MODEL_INSTANCES +
                    slot + 1.0;
    if (handle > ANVIL_WASM_INSTANCE_HANDLE_MAX) {
      instance->retired = 1;
      continue;
    }
    instance->active = 1;
    instance->model_id = model_id;
    for (int i = 0; i < ANVIL_WASM_MORPH_TARGETS; ++i) {
      instance->values[i] = 0.0;
      instance->overridden[i] = 0;
    }
    return handle;
  }
  return 0.0;
}

double anvil_model_instance_destroy(double handle, int model_id) {
  AnvilWasmModelInstance *instance = anvil_wasm_instance_lookup(handle, model_id);
  if (!instance)
    return 0.0;
  instance->active = 0;
  instance->model_id = -1;
  if (instance->generation >= ANVIL_WASM_INSTANCE_GENERATION_MAX)
    instance->retired = 1;
  else
    instance->generation++;
  return 1.0;
}

int anvil_model_instance_valid(double handle, int model_id) {
  return anvil_wasm_instance_lookup(handle, model_id) != NULL;
}

const double *anvil_model_instance_morph_weights(double handle, int model_id,
                                                  const double *defaults,
                                                  int morph_count) {
  AnvilWasmModelInstance *instance = anvil_wasm_instance_lookup(handle, model_id);
  return instance && defaults && morph_count > 0 &&
                 morph_count <= ANVIL_WASM_MORPH_TARGETS
             ? instance->values
             : defaults;
}

double anvil_model_instance_morph(double handle, int model_id, double index,
                                  double weight, const double *defaults,
                                  int morph_count) {
  AnvilWasmModelInstance *instance = anvil_wasm_instance_lookup(handle, model_id);
  if (!instance || !defaults || !anvil_wasm_finite(index) || index < 0.0 ||
      index >= morph_count || (double)(int)index != index ||
      morph_count <= 0 || morph_count > ANVIL_WASM_MORPH_TARGETS ||
      !anvil_wasm_finite(weight))
    return 0.0;
  int target = (int)index;
  double previous = instance->overridden[target]
                        ? instance->values[target]
                        : defaults[target];
  instance->values[target] = weight < 0.0 ? 0.0 : weight > 1.0 ? 1.0 : weight;
  instance->overridden[target] = 1;
  return previous;
}

static AnvilWasmModelInstance *anvil_wasm_instance_from_state_id(int id) {
  if (id >= 0)
    return NULL;
  unsigned token = (unsigned)(-id) - 1u;
  unsigned slot = token % ANVIL_WASM_MODEL_INSTANCES;
  unsigned generation = token / ANVIL_WASM_MODEL_INSTANCES;
  AnvilWasmModelInstance *instance = &anvil_wasm_model_instances[slot];
  return instance->active && instance->generation == generation ? instance
                                                                 : NULL;
}

static void anvil_wasm_morph_group_weights(
    int model_id, const double *defaults, const double *current_weights,
    int morph_count, double *weights) {
  AnvilWasmModelInstance *instance =
      anvil_wasm_instance_from_state_id(model_id);
  for (int target = 0; target < morph_count; ++target)
    weights[target] = instance
                          ? (instance->overridden[target]
                                 ? current_weights[target]
                                 : defaults[target])
                          : (model_id >= 0 &&
                                     model_id < ANVIL_WASM_MODEL_STATES &&
                                     anvil_wasm_morph_overridden[model_id][target]
                                 ? current_weights[target]
                                 : defaults[target]);
}

static int anvil_wasm_morph_group_visible(const double *envelope_bounds,
                                          double x, double y, double z,
                                          double scale, double rx, double ry,
                                          double rz) {
  if (!anvil_mesh_culling_enabled || anvil_shadows_enabled)
    return 1;
  return anvil_wasm_sphere_visible(envelope_bounds[0], envelope_bounds[1],
                                   envelope_bounds[2], envelope_bounds[3], x,
                                   y, z, scale, rx, ry, rz);
}

double anvil_trace_mesh_morphed_groups(
    const double *data, int triangle_count, const double *morph_deltas,
    const int *groups, int group_count, const double *group_bounds,
    const double *group_defaults,
    const double *current_weights, int model_id, int morph_count, double cx,
    double cy, double cz, double radius, double x, double y, double z,
    double scale, double rx, double ry, double rz) {
  if (!anvil_scene_is_3d || !data || !morph_deltas || !groups ||
      !group_bounds || !group_defaults || !current_weights || triangle_count <= 0 ||
      group_count <= 0 || morph_count <= 0 ||
      morph_count > ANVIL_WASM_MORPH_TARGETS ||
      !anvil_wasm_finite(cx) || !anvil_wasm_finite(cy) ||
      !anvil_wasm_finite(cz) || !anvil_wasm_finite(radius) || radius < 0.0 ||
      !anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || !anvil_wasm_finite(scale) || scale == 0.0 ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz))
    return 0.0;
  int active_triangles = 0;
  int visible_triangles = 0;
  for (int group = 0; group < group_count; ++group) {
    int first = groups[group * 2];
    int count = groups[group * 2 + 1];
    if (first < 0 || count < 0 || first > triangle_count ||
        count > triangle_count - first)
      return 0.0;
    const double *bounds = group_bounds + (size_t)group * 4;
    for (int field = 0; field < 4; ++field)
      if (!anvil_wasm_finite(bounds[field]))
        return 0.0;
    if (bounds[3] < 0.0)
      return 0.0;
    const double *defaults =
        group_defaults + (size_t)group * (size_t)morph_count;
    for (int target = 0; target < morph_count; ++target) {
      if (!anvil_wasm_finite(defaults[target]) ||
          !anvil_wasm_finite(current_weights[target]))
        return 0.0;
    }
    if (count > 0) {
      const double *deltas =
          morph_deltas + (size_t)first * 9 * (size_t)morph_count;
      size_t values = (size_t)count * 9 * (size_t)morph_count;
      for (size_t value = 0; value < values; ++value) {
        if (!anvil_wasm_finite(deltas[value]))
          return 0.0;
      }
      active_triangles += count;
    }
  }
  for (int group = 0; group < group_count; ++group) {
    int count = groups[group * 2 + 1];
    if (count <= 0)
      continue;
    const double *bounds = group_bounds + (size_t)group * 4;
    if (anvil_wasm_morph_group_visible(bounds, x, y, z, scale, rx, ry, rz))
      visible_triangles += count;
  }
  if (active_triangles <= 0)
    return 0.0;
  if (visible_triangles <= 0) {
    anvil_mesh_culled_frame = 1;
    return 1.0;
  }
  anvil_mesh_culled_frame = 0;
  if (visible_triangles > ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                              anvil_wasm_ray_mesh_triangles_frame)
    return 0.0;

  anvil_mesh_drawn_frame = 0;
  double weights[ANVIL_WASM_MORPH_TARGETS];
  for (int group = 0; group < group_count; ++group) {
    int first = groups[group * 2];
    int count = groups[group * 2 + 1];
    if (count <= 0)
      continue;
    const double *defaults =
        group_defaults + (size_t)group * (size_t)morph_count;
    const double *bounds = group_bounds + (size_t)group * 4;
    anvil_wasm_morph_group_weights(model_id, defaults, current_weights,
                                   morph_count, weights);
    if (!anvil_wasm_morph_group_visible(bounds, x, y, z, scale, rx, ry, rz))
      continue;
    for (int triangle = first; triangle < first + count; ++triangle) {
      const double *source = data + (size_t)triangle * 12;
      AnvilWasmVec3 points[3];
      for (int vertex = 0; vertex < 3; ++vertex) {
        size_t vertex_index = (size_t)triangle * 3 + (size_t)vertex;
        const double *deltas =
            morph_deltas + vertex_index * (size_t)morph_count * 3;
        AnvilWasmVec3 local = {source[vertex * 3], source[vertex * 3 + 1],
                               source[vertex * 3 + 2]};
        for (int target = 0; target < morph_count; ++target) {
          local.x += deltas[target * 3] * weights[target];
          local.y += deltas[target * 3 + 1] * weights[target];
          local.z += deltas[target * 3 + 2] * weights[target];
        }
        local = (AnvilWasmVec3){local.x * scale, local.y * scale,
                                local.z * scale};
        local = anvil_wasm_rotate(local, rx, ry, rz);
        points[vertex] =
            (AnvilWasmVec3){local.x + x, local.y + y, local.z + z};
      }
      int red = (int)source[9], green = (int)source[10], blue = (int)source[11];
      AnvilWasmVec3 normal = anvil_wasm_normalize(
          anvil_wasm_cross(anvil_wasm_sub(points[1], points[0]),
                           anvil_wasm_sub(points[2], points[0])));
      anvil_wasm_triangle(points[0], points[1], points[2], normal, red, green,
                          blue, 255, 1, 0.0, 0);
      anvil_wasm_shadow_triangle(points[0], points[1], points[2]);
      anvil_mesh_drawn_frame += 1;
    }
  }
  anvil_wasm_ray_mesh_triangles_frame += visible_triangles;
  return 1.0;
}

double anvil_mesh_draw_morphed_groups(
    const double *data, int triangle_count, const double *morph_deltas,
    const int *groups, int group_count, const double *group_bounds,
    const double *group_defaults,
    const double *current_weights, int model_id, int morph_count, double x,
    double y, double z, double scale, double rx, double ry, double rz) {
  if (!data || !morph_deltas || !groups || !group_bounds || !group_defaults ||
      !current_weights || triangle_count <= 0 || group_count <= 0 ||
      morph_count <= 0 || morph_count > ANVIL_WASM_MORPH_TARGETS ||
      !anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || !anvil_wasm_finite(scale) || scale == 0.0 ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz))
    return 0.0;
  size_t active_triangles = 0;
  size_t visible_triangles = 0;
  for (int group = 0; group < group_count; ++group) {
    int first = groups[group * 2];
    int count = groups[group * 2 + 1];
    if (first < 0 || count < 0 || first > triangle_count ||
        count > triangle_count - first)
      return 0.0;
    const double *bounds = group_bounds + (size_t)group * 4;
    for (int field = 0; field < 4; ++field)
      if (!anvil_wasm_finite(bounds[field]))
        return 0.0;
    if (bounds[3] < 0.0)
      return 0.0;
    active_triangles += (size_t)count;
    const double *defaults =
        group_defaults + (size_t)group * (size_t)morph_count;
    for (int target = 0; target < morph_count; ++target) {
      if (!anvil_wasm_finite(defaults[target]) ||
          !anvil_wasm_finite(current_weights[target]))
        return 0.0;
    }
    if (count > 0) {
      const double *deltas =
          morph_deltas + (size_t)first * 9 * (size_t)morph_count;
      size_t values = (size_t)count * 9 * (size_t)morph_count;
      for (size_t value = 0; value < values; ++value) {
        if (!anvil_wasm_finite(deltas[value]))
          return 0.0;
      }
    }
  }
  if (active_triangles == 0)
    return 0.0;

  for (int group = 0; group < group_count; ++group) {
    int count = groups[group * 2 + 1];
    if (count <= 0)
      continue;
    const double *bounds = group_bounds + (size_t)group * 4;
    if (anvil_wasm_morph_group_visible(bounds, x, y, z, scale, rx, ry, rz))
      visible_triangles += (size_t)count;
  }

  if (visible_triangles == 0) {
    anvil_mesh_culled_frame = 1;
    anvil_mesh_drawn_frame = 0;
    return 0.0;
  }
  anvil_mesh_culled_frame = 0;
  if (visible_triangles > (size_t)(ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                                   anvil_wasm_ray_mesh_triangles_frame))
    return 0.0;

  anvil_mesh_drawn_frame = 0;
  double weights[ANVIL_WASM_MORPH_TARGETS];
  for (int group = 0; group < group_count; ++group) {
    int first = groups[group * 2];
    int count = groups[group * 2 + 1];
    if (count <= 0)
      continue;
    const double *defaults =
        group_defaults + (size_t)group * (size_t)morph_count;
    const double *bounds = group_bounds + (size_t)group * 4;
    anvil_wasm_morph_group_weights(model_id, defaults, current_weights,
                                   morph_count, weights);
    if (!anvil_wasm_morph_group_visible(bounds, x, y, z, scale, rx, ry, rz))
      continue;
    for (int triangle = first; triangle < first + count; ++triangle) {
      const double *source = data + (size_t)triangle * 12;
      AnvilWasmVec3 points[3];
      for (int vertex = 0; vertex < 3; ++vertex) {
        size_t vertex_index = (size_t)triangle * 3 + (size_t)vertex;
        const double *deltas =
            morph_deltas + vertex_index * (size_t)morph_count * 3;
        AnvilWasmVec3 local = {source[vertex * 3], source[vertex * 3 + 1],
                               source[vertex * 3 + 2]};
        for (int target = 0; target < morph_count; ++target) {
          local.x += deltas[target * 3] * weights[target];
          local.y += deltas[target * 3 + 1] * weights[target];
          local.z += deltas[target * 3 + 2] * weights[target];
        }
        local = (AnvilWasmVec3){local.x * scale, local.y * scale,
                                local.z * scale};
        local = anvil_wasm_rotate(local, rx, ry, rz);
        points[vertex] =
            (AnvilWasmVec3){local.x + x, local.y + y, local.z + z};
      }
      int red = (int)source[9], green = (int)source[10], blue = (int)source[11];
      AnvilWasmVec3 normal = anvil_wasm_normalize(
          anvil_wasm_cross(anvil_wasm_sub(points[1], points[0]),
                           anvil_wasm_sub(points[2], points[0])));
      anvil_wasm_triangle(points[0], points[1], points[2], normal, red, green,
                          blue, 255, 1, 0.0, 0);
      anvil_wasm_shadow_triangle(points[0], points[1], points[2]);
      anvil_mesh_drawn_frame += 1;
    }
  }
  anvil_wasm_ray_mesh_triangles_frame += (int)visible_triangles;
  return 1.0;
}

double anvil_model_animate(int id, double seconds) {
  if (id < 0 || id >= ANVIL_WASM_MODEL_STATES ||
      !anvil_wasm_finite(seconds))
    return 0.0;
  anvil_wasm_model_times[id] = seconds;
  return seconds;
}

double anvil_model_clock(int id) {
  return id >= 0 && id < ANVIL_WASM_MODEL_STATES
             ? anvil_wasm_model_times[id]
             : 0.0;
}

static double anvil_wasm_model_local_t[ANVIL_WASM_MODEL_NODES][3];
static double anvil_wasm_model_local_r[ANVIL_WASM_MODEL_NODES][4];
static double anvil_wasm_model_local_s[ANVIL_WASM_MODEL_NODES][3];
static double anvil_wasm_model_world[ANVIL_WASM_MODEL_NODES][16];
static int anvil_wasm_model_resolving[ANVIL_WASM_MODEL_NODES];

static void anvil_wasm_mat_trs(const double *translation,
                               const double *rotation, const double *scale,
                               double *matrix) {
  double x = rotation[0], y = rotation[1], z = rotation[2], w = rotation[3];
  matrix[0] = (1.0 - 2.0 * (y * y + z * z)) * scale[0];
  matrix[1] = (2.0 * (x * y + z * w)) * scale[0];
  matrix[2] = (2.0 * (x * z - y * w)) * scale[0];
  matrix[3] = 0.0;
  matrix[4] = (2.0 * (x * y - z * w)) * scale[1];
  matrix[5] = (1.0 - 2.0 * (x * x + z * z)) * scale[1];
  matrix[6] = (2.0 * (y * z + x * w)) * scale[1];
  matrix[7] = 0.0;
  matrix[8] = (2.0 * (x * z + y * w)) * scale[2];
  matrix[9] = (2.0 * (y * z - x * w)) * scale[2];
  matrix[10] = (1.0 - 2.0 * (x * x + y * y)) * scale[2];
  matrix[11] = 0.0;
  matrix[12] = translation[0];
  matrix[13] = translation[1];
  matrix[14] = translation[2];
  matrix[15] = 1.0;
}

static void anvil_wasm_mat_mul(const double *a, const double *b, double *out) {
  for (int column = 0; column < 4; ++column)
    for (int row = 0; row < 4; ++row)
      out[column * 4 + row] =
          a[row] * b[column * 4] + a[4 + row] * b[column * 4 + 1] +
          a[8 + row] * b[column * 4 + 2] +
          a[12 + row] * b[column * 4 + 3];
}

static void anvil_wasm_mat_point(const double *matrix, double x, double y,
                                 double z, double *out) {
  out[0] = matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12];
  out[1] = matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13];
  out[2] = matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14];
}

static double anvil_wasm_acos(double value) {
  const double pi = 3.14159265358979323846;
  double magnitude = fabs(value);
  if (magnitude > 1.0)
    magnitude = 1.0;
  double result =
      (((-0.0187293 * magnitude + 0.0742610) * magnitude - 0.2121144) *
       magnitude + 1.5707288) *
      sqrt(1.0 - magnitude);
  return value < 0.0 ? pi - result : result;
}

static void anvil_wasm_slerp(const double *a, const double *b, double amount,
                             double *out) {
  double dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  double sign = 1.0;
  if (dot < 0.0) {
    sign = -1.0;
    dot = -dot;
  }
  if (dot > 0.9995) {
    for (int i = 0; i < 4; ++i)
      out[i] = a[i] + (sign * b[i] - a[i]) * amount;
  } else {
    double theta = anvil_wasm_acos(dot);
    double sin_theta = sin(theta);
    double weight_a = sin((1.0 - amount) * theta) / sin_theta;
    double weight_b = sin(amount * theta) / sin_theta;
    for (int i = 0; i < 4; ++i)
      out[i] = a[i] * weight_a + sign * b[i] * weight_b;
  }
  double norm = out[0] * out[0] + out[1] * out[1] + out[2] * out[2] +
                out[3] * out[3];
  if (norm > 0.0) {
    norm = sqrt(norm);
    for (int i = 0; i < 4; ++i)
      out[i] /= norm;
  }
}

static void anvil_wasm_track_sample(const double *times, const double *values,
                                    int first_time, int first_value, int count,
                                    int path, int interpolation, double time,
                                    double *out) {
  int width = path == 1 ? 4 : 3;
  const double *row;
  if (time <= times[first_time]) {
    row = values + first_value;
  } else if (time >= times[first_time + count - 1]) {
    row = values + first_value + (size_t)(count - 1) * (size_t)width;
  } else {
    int index = 0;
    while (index + 2 < count && times[first_time + index + 1] <= time)
      ++index;
    if (interpolation == 1) {
      row = values + first_value + (size_t)index * (size_t)width;
    } else {
      double t0 = times[first_time + index];
      double t1 = times[first_time + index + 1];
      double amount = t1 > t0 ? (time - t0) / (t1 - t0) : 0.0;
      const double *left = values + first_value + (size_t)index * (size_t)width;
      const double *right = left + width;
      if (path == 1) {
        anvil_wasm_slerp(left, right, amount, out);
        return;
      }
      for (int i = 0; i < width; ++i)
        out[i] = left[i] + (right[i] - left[i]) * amount;
      return;
    }
  }
  for (int i = 0; i < width; ++i)
    out[i] = row[i];
}

static void anvil_wasm_model_resolve(int index, const int *parents,
                                     int depth) {
  if (anvil_wasm_model_resolving[index] == 2)
    return;
  if (anvil_wasm_model_resolving[index] == 1 || depth > 64) {
    anvil_wasm_mat_trs(anvil_wasm_model_local_t[index],
                       anvil_wasm_model_local_r[index],
                       anvil_wasm_model_local_s[index],
                       anvil_wasm_model_world[index]);
    anvil_wasm_model_resolving[index] = 2;
    return;
  }
  anvil_wasm_model_resolving[index] = 1;
  double local[16];
  anvil_wasm_mat_trs(anvil_wasm_model_local_t[index],
                     anvil_wasm_model_local_r[index],
                     anvil_wasm_model_local_s[index], local);
  int parent = parents[index];
  if (parent >= 0 && parent != index) {
    if (parent >= ANVIL_WASM_MODEL_NODES) {
      anvil_wasm_model_resolving[index] = 0;
      return;
    }
    anvil_wasm_model_resolve(parent, parents, depth + 1);
    anvil_wasm_mat_mul(anvil_wasm_model_world[parent], local,
                       anvil_wasm_model_world[index]);
  } else {
    for (int i = 0; i < 16; ++i)
      anvil_wasm_model_world[index][i] = local[i];
  }
  anvil_wasm_model_resolving[index] = 2;
}

static double anvil_wasm_positive_remainder(double value, double period) {
  if (value < period)
    return value;
  double multiple = period;
  while (multiple <= value * 0.5 && multiple <= 8.988465674311579e307)
    multiple *= 2.0;
  while (multiple >= period) {
    if (value >= multiple)
      value -= multiple;
    multiple *= 0.5;
  }
  return value;
}

static int anvil_wasm_model_pose(const double *nodes, int node_count,
                                 const int *parents, const double *times,
                                 const double *values, const int *tracks,
                                 int track_count, double clip_length,
                                 double clip_time) {
  if (!nodes || !parents || !times || !values || !tracks || node_count <= 0 ||
      node_count > ANVIL_WASM_MODEL_NODES || track_count < 0 ||
      (track_count > 0 && (!times || !values || !tracks)) ||
      !anvil_wasm_finite(clip_length) || !anvil_wasm_finite(clip_time))
    return 0;
  for (int node = 0; node < node_count; ++node) {
    for (int i = 0; i < 3; ++i) {
      anvil_wasm_model_local_t[node][i] = nodes[node * 10 + i];
      anvil_wasm_model_local_r[node][i] = nodes[node * 10 + 3 + i];
      anvil_wasm_model_local_s[node][i] = nodes[node * 10 + 7 + i];
    }
    anvil_wasm_model_local_r[node][3] = nodes[node * 10 + 6];
  }
  double time = 0.0;
  if (clip_length > 0.0) {
    double magnitude = fabs(clip_time);
    time = anvil_wasm_positive_remainder(magnitude, clip_length);
    if (clip_time < 0.0 && time > 0.0)
      time = clip_length - time;
  }
  for (int i = 0; i < track_count; ++i) {
    const int *track = tracks + i * 6;
    int node = track[0];
    int path = track[1];
    int interpolation = track[2];
    int first_time = track[3];
    int first_value = track[4];
    int count = track[5];
    if (node < 0 || node >= node_count || path < 0 || path > 2 ||
        (interpolation != 0 && interpolation != 1) || first_time < 0 ||
        first_value < 0 || count <= 0)
      return 0;
    double sampled[4] = {0.0, 0.0, 0.0, 0.0};
    anvil_wasm_track_sample(times, values, first_time, first_value, count,
                            path, interpolation, time, sampled);
    if (path == 0)
      for (int k = 0; k < 3; ++k)
        anvil_wasm_model_local_t[node][k] = sampled[k];
    else if (path == 2)
      for (int k = 0; k < 3; ++k)
        anvil_wasm_model_local_s[node][k] = sampled[k];
    else
      for (int k = 0; k < 4; ++k)
        anvil_wasm_model_local_r[node][k] = sampled[k];
  }
  for (int node = 0; node < node_count; ++node) {
    anvil_wasm_model_resolving[node] = 0;
    anvil_wasm_model_resolve(node, parents, 0);
    if (anvil_wasm_model_resolving[node] != 2)
      return 0;
  }
  return 1;
}

double anvil_mesh_draw_skinned(
    const double *data, int triangle_count, const double *nodes, int node_count,
    const int *parents, const int *joint_nodes, int joint_count,
    const double *bind, const double *times, const double *values,
    const int *tracks, int track_count, double clip_length, double clip_time,
    const double *textured_data, const uint32_t *const *textures,
    const int *texture_dimensions, int texture_count, double x, double y,
    double z, double scale, double rx, double ry, double rz) {
  if (!anvil_scene_is_3d || !data || !nodes || !parents || !joint_nodes ||
      !bind || triangle_count <= 0 ||
      triangle_count > ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                           anvil_wasm_ray_mesh_triangles_frame ||
      node_count <= 0 || node_count > ANVIL_WASM_MODEL_NODES ||
      joint_count <= 0 || joint_count > 64 || track_count < 0 ||
      !anvil_wasm_finite(clip_length) || !anvil_wasm_finite(clip_time) ||
      !anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || !anvil_wasm_finite(scale) || scale == 0.0 ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz) ||
      (track_count > 0 && (!times || !values || !tracks)) ||
      (textured_data && (!textures || !texture_dimensions || texture_count <= 0)) ||
      (textured_data && triangle_count >
          ANVIL_WASM_TEXTURED_MODEL_TRIANGLE_BUDGET -
              anvil_wasm_textured_model_triangles_frame))
    return 0.0;
  for (int node = 0; node < node_count; ++node) {
    if (parents[node] < -1 || parents[node] >= node_count)
      return 0.0;
    for (int field = 0; field < 10; ++field)
      if (!anvil_wasm_finite(nodes[node * 10 + field]))
        return 0.0;
  }
  for (int joint = 0; joint < joint_count; ++joint) {
    if (joint_nodes[joint] < 0 || joint_nodes[joint] >= node_count)
      return 0.0;
    for (int element = 0; element < 16; ++element)
      if (!anvil_wasm_finite(bind[joint * 16 + element]))
        return 0.0;
  }
  size_t value_count = (size_t)triangle_count * 42;
  for (size_t index = 0; index < value_count; ++index)
    if (!anvil_wasm_finite(data[index]))
      return 0.0;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    const double *source = data + (size_t)triangle * 42;
    for (int corner = 0; corner < 3; ++corner) {
      const double *vertex = source + corner * 14;
      for (int influence = 0; influence < 4; ++influence) {
        double joint = vertex[6 + influence];
        double weight = vertex[10 + influence];
        if (joint < 0.0 || joint >= joint_count || joint != (int)joint ||
            weight < 0.0)
          return 0.0;
      }
    }
  }
  if (!anvil_wasm_model_pose(nodes, node_count, parents, times, values, tracks,
                             track_count, clip_length, clip_time))
    return 0.0;

  double joint_matrices[64][16];
  for (int joint = 0; joint < joint_count; ++joint)
    anvil_wasm_mat_mul(anvil_wasm_model_world[joint_nodes[joint]],
                       bind + joint * 16, joint_matrices[joint]);

  anvil_mesh_culled_frame = 0;
  anvil_mesh_drawn_frame = 0;
  for (int triangle = 0; triangle < triangle_count; ++triangle) {
    const double *source = data + (size_t)triangle * 42;
    AnvilWasmVec3 points[3];
    for (int corner = 0; corner < 3; ++corner) {
      const double *vertex = source + corner * 14;
      double px = 0.0, py = 0.0, pz = 0.0, carried = 0.0;
      for (int influence = 0; influence < 4; ++influence) {
        int joint = (int)vertex[6 + influence];
        double weight = vertex[10 + influence];
        if (weight <= 0.0)
          continue;
        double transformed[3];
        anvil_wasm_mat_point(joint_matrices[joint], vertex[0], vertex[1],
                             vertex[2], transformed);
        px += transformed[0] * weight;
        py += transformed[1] * weight;
        pz += transformed[2] * weight;
        carried += weight;
      }
      if (carried <= 0.0) {
        px = vertex[0];
        py = vertex[1];
        pz = vertex[2];
      }
      if (textured_data) {
        const double *texture = textured_data + (size_t)triangle * 20;
        double *posed = anvil_wasm_animated_textured_data +
                        (size_t)triangle * 20;
        posed[corner * 5] = px;
        posed[corner * 5 + 1] = py;
        posed[corner * 5 + 2] = pz;
        posed[corner * 5 + 3] = texture[corner * 5 + 3];
        posed[corner * 5 + 4] = texture[corner * 5 + 4];
        if (corner == 2) {
          posed[15] = texture[15]; posed[16] = texture[16];
          posed[17] = texture[17]; posed[18] = texture[18];
          posed[19] = texture[19];
        }
      }
      AnvilWasmVec3 local = {px * scale, py * scale, pz * scale};
      local = anvil_wasm_rotate(local, rx, ry, rz);
      points[corner] =
          (AnvilWasmVec3){x + local.x, y + local.y, z + local.z};
    }
    AnvilWasmVec3 normal = anvil_wasm_normalize(
        anvil_wasm_cross(anvil_wasm_sub(points[1], points[0]),
                         anvil_wasm_sub(points[2], points[0])));
    if (textured_data)
      continue;
    anvil_wasm_triangle(points[0], points[1], points[2], normal,
                        (int)source[3], (int)source[4], (int)source[5], 255, 1,
                        0.0, 0);
  }
  if (textured_data &&
      !anvil_mesh_draw_textured(
          anvil_wasm_animated_textured_data, triangle_count, textures,
          texture_dimensions, texture_count, 0.0, 0.0, 0.0, 1.0e100,
          x, y, z, scale, rx, ry, rz))
    return 0.0;
  anvil_mesh_drawn_frame = triangle_count;
  anvil_wasm_ray_mesh_triangles_frame += triangle_count;
  return 1.0;
}

static double anvil_wasm_submit_animated_groups(
    const double *data, int triangle_count, const double *nodes, int node_count,
    const int *parents, const int *groups, int group_count, const double *times,
    const double *values, const int *tracks, int track_count, double clip_length,
    double clip_time, const double *morph_deltas,
    const double *group_defaults, const double *morph_weights, int model_id,
    int morph_count, const double *textured_data,
    const uint32_t *const *textures, const int *texture_dimensions,
    int texture_count, double x, double y, double z, double scale, double rx,
    double ry, double rz) {
  if (!anvil_scene_is_3d || !data || !groups || triangle_count <= 0 ||
      group_count <= 0 || morph_count < 0 ||
      morph_count > ANVIL_WASM_MORPH_TARGETS ||
      (morph_count > 0 &&
       (!morph_deltas || !group_defaults || !morph_weights)) ||
      (textured_data && (!textures || !texture_dimensions || texture_count <= 0)) ||
      !anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(z) || !anvil_wasm_finite(scale) || scale == 0.0 ||
      !anvil_wasm_finite(rx) || !anvil_wasm_finite(ry) ||
      !anvil_wasm_finite(rz))
    return 0.0;
  size_t active_triangles = 0;
  for (int group = 0; group < group_count; ++group) {
    const int *entry = groups + (size_t)group * 3;
    int node = entry[0], first = entry[1], count = entry[2];
    if (node < 0 || node >= node_count || first < 0 || count < 0 ||
        first > triangle_count || count > triangle_count - first)
      return 0.0;
    if (morph_count > 0) {
      const double *defaults =
          group_defaults + (size_t)group * (size_t)morph_count;
      for (int target = 0; target < morph_count; ++target) {
        if (!anvil_wasm_finite(defaults[target]) ||
            !anvil_wasm_finite(morph_weights[target]))
          return 0.0;
      }
    }
    active_triangles += (size_t)count;
  }
  if (active_triangles == 0 ||
      active_triangles >
          (size_t)(ANVIL_WASM_MODEL_TRIANGLE_BUDGET -
                   anvil_wasm_ray_mesh_triangles_frame))
    return 0.0;
  if (textured_data && active_triangles != (size_t)triangle_count)
    return 0.0;
  if (textured_data &&
      triangle_count > ANVIL_WASM_TEXTURED_MODEL_TRIANGLE_BUDGET -
                           anvil_wasm_textured_model_triangles_frame)
    return 0.0;
  if (!anvil_wasm_model_pose(nodes, node_count, parents, times, values, tracks,
                             track_count, clip_length, clip_time))
    return 0.0;

  anvil_mesh_culled_frame = 0;
  anvil_mesh_drawn_frame = 0;
  double weights[ANVIL_WASM_MORPH_TARGETS];
  for (int group = 0; group < group_count; ++group) {
    const int *entry = groups + (size_t)group * 3;
    int node = entry[0], first = entry[1], count = entry[2];
    if (count <= 0)
      continue;
    if (morph_count > 0) {
      const double *defaults =
          group_defaults + (size_t)group * (size_t)morph_count;
      for (int target = 0; target < morph_count; ++target)
        weights[target] =
            model_id >= 0 && model_id < ANVIL_WASM_MODEL_STATES &&
                    anvil_wasm_morph_overridden[model_id][target]
                ? morph_weights[target]
                : defaults[target];
    }
    const double *matrix = anvil_wasm_model_world[node];
    for (int triangle = first; triangle < first + count; ++triangle) {
      const double *source = data + (size_t)triangle * 12;
      AnvilWasmVec3 points[3];
      for (int vertex = 0; vertex < 3; ++vertex) {
        double position[3];
        double px = source[vertex * 3];
        double py = source[vertex * 3 + 1];
        double pz = source[vertex * 3 + 2];
        if (morph_count > 0) {
          size_t vertex_index = (size_t)triangle * 3 + (size_t)vertex;
          for (int target = 0; target < morph_count; ++target) {
            const double *delta =
                morph_deltas +
                (vertex_index * (size_t)morph_count + (size_t)target) * 3;
            px += delta[0] * weights[target];
            py += delta[1] * weights[target];
            pz += delta[2] * weights[target];
          }
        }
        anvil_wasm_mat_point(matrix, px, py, pz, position);
        if (textured_data) {
          const double *texture = textured_data + (size_t)triangle * 20;
          double *posed = anvil_wasm_animated_textured_data +
                          (size_t)triangle * 20;
          posed[vertex * 5] = position[0];
          posed[vertex * 5 + 1] = position[1];
          posed[vertex * 5 + 2] = position[2];
          posed[vertex * 5 + 3] = texture[vertex * 5 + 3];
          posed[vertex * 5 + 4] = texture[vertex * 5 + 4];
          if (vertex == 2) {
            posed[15] = texture[15]; posed[16] = texture[16];
            posed[17] = texture[17]; posed[18] = texture[18];
            posed[19] = texture[19];
          }
        }
        AnvilWasmVec3 local = {position[0] * scale, position[1] * scale,
                               position[2] * scale};
        local = anvil_wasm_rotate(local, rx, ry, rz);
        points[vertex] =
            (AnvilWasmVec3){x + local.x, y + local.y, z + local.z};
      }
      if (textured_data)
        continue;
      int red = (int)source[9], green = (int)source[10], blue = (int)source[11];
      AnvilWasmVec3 normal = anvil_wasm_normalize(
          anvil_wasm_cross(anvil_wasm_sub(points[1], points[0]),
                           anvil_wasm_sub(points[2], points[0])));
      anvil_wasm_triangle(points[0], points[1], points[2], normal, red, green,
                          blue, 255, 1, 0.0, 0);
      anvil_wasm_shadow_triangle(points[0], points[1], points[2]);
      anvil_mesh_drawn_frame += 1;
    }
  }
  if (textured_data &&
      !anvil_mesh_draw_textured(
          anvil_wasm_animated_textured_data, triangle_count, textures,
          texture_dimensions, texture_count, 0.0, 0.0, 0.0, 1.0e100,
          x, y, z, scale, rx, ry, rz))
    return 0.0;
  if (textured_data)
    anvil_mesh_drawn_frame = (int)active_triangles;
  anvil_wasm_ray_mesh_triangles_frame += (int)active_triangles;
  return 1.0;
}

double anvil_mesh_draw_animated(
    const double *data, int triangle_count, const double *nodes, int node_count,
    const int *parents, const int *groups, int group_count, const double *times,
    const double *values, const int *tracks, int track_count, double clip_length,
    double clip_time, const double *morph_deltas,
    const double *group_defaults, const double *morph_weights, int model_id,
    int morph_count, const double *textured_data,
    const uint32_t *const *textures, const int *texture_dimensions,
    int texture_count, double x, double y, double z, double scale, double rx,
    double ry, double rz) {
  return anvil_wasm_submit_animated_groups(
      data, triangle_count, nodes, node_count, parents, groups, group_count,
      times, values, tracks, track_count, clip_length, clip_time, morph_deltas,
      group_defaults, morph_weights, model_id, morph_count, textured_data,
      textures, texture_dimensions, texture_count, x, y, z, scale, rx, ry, rz);
}

double anvil_trace_mesh_animated(
    const double *data, int triangle_count, const double *nodes, int node_count,
    const int *parents, const int *groups, int group_count, const double *times,
    const double *values, const int *tracks, int track_count, double clip_length,
    double clip_time, const double *morph_deltas,
    const double *group_defaults, const double *morph_weights, int model_id,
    int morph_count, const double *textured_data,
    const uint32_t *const *textures, const int *texture_dimensions,
    int texture_count, double x, double y, double z, double scale, double rx,
    double ry, double rz) {
  return anvil_wasm_submit_animated_groups(
      data, triangle_count, nodes, node_count, parents, groups, group_count,
      times, values, tracks, track_count, clip_length, clip_time, morph_deltas,
      group_defaults, morph_weights, model_id, morph_count, textured_data,
      textures, texture_dimensions, texture_count, x, y, z, scale, rx, ry, rz);
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
/* The page owns the canvas; the module holds no pixel memory, so both
   video counters are zero here and memory_total() covers images and audio. */
double anvil_memory_video(void) { return 0.0; }
double anvil_memory_gpu(void) { return 0.0; }
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

/* The browser backend bakes every literal load at compile time, so there is no
   call site to remember: memory_report() does not exist here and the extra
   arguments are accepted only to keep the shared C generator's calls linking. */
double anvil_image_load_site(const char *path, const char *file, int line) {
  (void)file;
  (void)line;
  return anvil_image_load(path);
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

double anvil_sound_load_site(const char *path, const char *file, int line) {
  (void)file;
  (void)line;
  return anvil_sound_load(path);
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
  if (!(code == code) || code < 0.0 || code > 255.0)
    anvil_runtime_error("Anvil chr out of range");
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

/* The version lives under one reserved key beside the slots. Slot names cannot
   start with a dot, so ".version" is not reachable as a slot. */
static int anvil_save_version_key(char *out, int capacity) {
  int index = 0;
  for (const char *c = anvil_project_name; *c; ++c) {
    if (index >= capacity - 12)
      return 0;
    out[index++] = *c;
  }
  const char *suffix = "/.version";
  for (const char *c = suffix; *c; ++c)
    out[index++] = *c;
  out[index] = '\0';
  return 1;
}

double anvil_save_version(void) {
  char key[160];
  if (!anvil_save_version_key(key, (int)sizeof(key))) {
    anvil_save_error_text = "the save folder is too long";
    return 0.0;
  }
  char payload[32];
  int length = anvil_host_save_read(key, payload, (int)sizeof(payload) - 1);
  if (length < 0) {
    anvil_save_error_text = ""; /* no version yet is a first run */
    return 0.0;
  }
  if (length > (int)sizeof(payload) - 1)
    length = (int)sizeof(payload) - 1;
  payload[length] = '\0';
  double value = 0.0;
  int digits = 0;
  for (int i = 0; i < length; ++i) {
    char c = payload[i];
    if (c < '0' || c > '9') {
      anvil_save_error_text = "the save version file is not readable";
      return 0.0;
    }
    value = value * 10.0 + (double)(c - '0');
    if (value > 1000000.0) {
      anvil_save_error_text = "the save version file is not readable";
      return 0.0;
    }
    ++digits;
  }
  if (!digits) {
    anvil_save_error_text = "the save version file is not readable";
    return 0.0;
  }
  anvil_save_error_text = "";
  return value;
}

double anvil_save_set_version(double version) {
  double previous = anvil_save_version();
  if (!anvil_wasm_finite(version) || version < 0.0 || version > 1000000.0 ||
      floor(version) != version) {
    anvil_save_error_text =
        "the save version must be a whole number from 0 to 1000000";
    return previous;
  }
  char key[160];
  if (!anvil_save_version_key(key, (int)sizeof(key))) {
    anvil_save_error_text = "the save folder is too long";
    return previous;
  }
  char reversed[16];
  int count = 0;
  unsigned long long whole = (unsigned long long)version;
  if (whole == 0)
    reversed[count++] = '0';
  while (whole) {
    reversed[count++] = (char)('0' + (int)(whole % 10));
    whole /= 10;
  }
  char payload[24];
  int index = 0;
  while (count)
    payload[index++] = reversed[--count];
  payload[index] = '\0';
  anvil_host_save_write(key, payload);
  anvil_save_error_text = "";
  return previous;
}

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
  if (length > 0 && payload[0] > '2') {
    anvil_save_error_text = "the save was written by a newer Anvil version";
    return 0.0;
  }
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
  if (length > 0 && payload[0] > '2') {
    anvil_save_error_text = "the save was written by a newer Anvil version";
    return buffer;
  }
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
/* Screen fade: the same 0..255 black overlay as the C runtime, applied by the
   host after the frame's own draws and before the present. */
static double anvil_screen_fade_value;
static double anvil_screen_fade_target;
static double anvil_screen_fade_speed;
static int anvil_screen_fade_active;

double anvil_screen_fade(double alpha) {
  double previous = anvil_screen_fade_value;
  if (alpha == alpha && alpha > -1.0e308 && alpha < 1.0e308) {
    anvil_screen_fade_value =
        alpha < 0.0 ? 0.0 : alpha > 255.0 ? 255.0 : alpha;
    anvil_screen_fade_active = 0;
  }
  return previous;
}

double anvil_screen_fade_to(double target, double seconds) {
  double previous = anvil_screen_fade_value;
  if (!(target == target) || target > 1.0e308 || target < -1.0e308)
    return previous;
  double clamped = target < 0.0 ? 0.0 : target > 255.0 ? 255.0 : target;
  if (!(seconds > 0.0) || seconds > 1.0e308) {
    anvil_screen_fade_value = clamped;
    anvil_screen_fade_active = 0;
    return previous;
  }
  anvil_screen_fade_target = clamped;
  double distance = clamped - anvil_screen_fade_value;
  anvil_screen_fade_speed = (distance < 0.0 ? -distance : distance) / seconds;
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

/* ---- Scene manager -------------------------------------------------------
   Same timeline as the C runtime: fade out, swap the scene name inside the
   black hold, fade back in. */

enum { ANVIL_SCENE_NAME_MAX = 64 };

/* Distinct names from the accessor functions: C has one namespace. */
static char anvil_scene_current[ANVIL_SCENE_NAME_MAX];
static char anvil_scene_pending[ANVIL_SCENE_NAME_MAX];
static double anvil_scene_elapsed;
static double anvil_scene_total;
static int anvil_scene_switching;
static int anvil_scene_swapped;

double anvil_scene_change(const char *name, double seconds) {
  const char *text = name ? name : "";
  size_t length = strlen(text);
  if (!length || length >= ANVIL_SCENE_NAME_MAX)
    return 0.0;
  if (anvil_scene_switching)
    return 0.0;
  if (!anvil_wasm_finite(seconds) || seconds <= 0.0) {
    memcpy(anvil_scene_current, text, length + 1);
    anvil_scene_pending[0] = '\0';
    anvil_scene_switching = 0;
    anvil_scene_swapped = 1;
    return 1.0;
  }
  memcpy(anvil_scene_pending, text, length + 1);
  anvil_scene_elapsed = 0.0;
  anvil_scene_total = seconds;
  anvil_scene_switching = 1;
  anvil_screen_fade_active = 0;
  anvil_screen_fade_value = 0.0;
  return 1.0;
}

const char *anvil_scene_name(void) { return anvil_scene_current; }
const char *anvil_scene_target(void) { return anvil_scene_pending; }
double anvil_scene_changing(void) { return (double)anvil_scene_switching; }
double anvil_scene_changed(void) { return (double)anvil_scene_swapped; }

double anvil_scene_progress(void) {
  if (!anvil_scene_switching || !(anvil_scene_total > 0.0))
    return 1.0;
  double progress = anvil_scene_elapsed / anvil_scene_total;
  return progress < 0.0 ? 0.0 : progress > 1.0 ? 1.0 : progress;
}

static void anvil_scene_update(double seconds) {
  if (!anvil_scene_switching)
    return;
  anvil_scene_elapsed += seconds > 0.0 ? seconds : 0.0;
  double progress = anvil_scene_elapsed / anvil_scene_total;
  if (progress >= 0.5 && anvil_scene_pending[0]) {
    memcpy(anvil_scene_current, anvil_scene_pending, sizeof(anvil_scene_current));
    anvil_scene_pending[0] = '\0';
    anvil_scene_swapped = 1;
  }
  double alpha;
  if (progress < 0.45)
    alpha = 255.0 * (progress / 0.45);
  else if (progress < 0.55)
    alpha = 255.0;
  else
    alpha = 255.0 * (1.0 - (progress - 0.55) / 0.45);
  anvil_screen_fade_active = 0;
  anvil_screen_fade_value = alpha < 0.0 ? 0.0 : alpha > 255.0 ? 255.0 : alpha;
  if (progress >= 1.0) {
    anvil_scene_switching = 0;
    anvil_screen_fade_value = 0.0;
  }
}

/* ---- UI focus and accessible labels -------------------------------------
   Same registry as the C runtime. There is no window manager here, so the
   announcement goes through the host's aria-live region instead of an MSAA
   child window. */

enum { ANVIL_FOCUS_REGIONS = 64, ANVIL_FOCUS_LABEL_MAX = 96 };

typedef struct {
  int used;
  double x, y, width, height;
  char label[ANVIL_FOCUS_LABEL_MAX];
} AnvilFocusRegion;

static AnvilFocusRegion anvil_focus_regions[ANVIL_FOCUS_REGIONS];
static int anvil_focus_count;
static int anvil_focus_current;
static int anvil_focus_activated;
static int anvil_focus_accessible;
static int anvil_focus_announced;

static AnvilFocusRegion *anvil_focus_region(double handle) {
  if (!anvil_wasm_finite(handle) || handle < 1.0 ||
      handle > (double)ANVIL_FOCUS_REGIONS || floor(handle) != handle)
    return 0;
  AnvilFocusRegion *region = &anvil_focus_regions[(int)handle - 1];
  return region->used ? region : 0;
}

double anvil_ui_focus_add(double x, double y, double width, double height,
                          const char *label) {
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y) ||
      !anvil_wasm_finite(width) || !anvil_wasm_finite(height))
    return 0.0;
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
  if (length >= ANVIL_FOCUS_LABEL_MAX)
    return 0.0;
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
  return anvil_focus_region((double)anvil_focus_current) != 0
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

double anvil_ui_focus_at(double x, double y) {
  if (!anvil_wasm_finite(x) || !anvil_wasm_finite(y))
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

double anvil_ui_accessible(double on) {
  if (on == 0.0) {
    anvil_focus_accessible = 0;
    anvil_focus_announced = 0;
    return 0.0;
  }
  anvil_focus_accessible = 1;
  anvil_focus_announced = 0;
  return 1.0;
}

static void anvil_focus_frame(void) {
  anvil_focus_activated = 0;
  if (!anvil_focus_count) {
    anvil_focus_current = 0;
    return;
  }
  if (anvil_mouse_pressed_buttons[0] && anvil_mouse_has_position) {
    double hit = anvil_ui_focus_at(anvil_mouse_x_value, anvil_mouse_y_value);
    if (hit != 0.0) {
      anvil_focus_current = (int)hit;
      anvil_focus_activated = (int)hit;
    }
  }
  if (!anvil_focus_activated && anvil_focus_current &&
      (anvil_keys_pressed[13] || anvil_keys_pressed[32]))
    anvil_focus_activated = anvil_focus_current;
  if (anvil_focus_accessible && anvil_focus_current != anvil_focus_announced) {
    anvil_focus_announced = anvil_focus_current;
    const AnvilFocusRegion *region =
        anvil_focus_region((double)anvil_focus_current);
    if (region)
      anvil_host_announce(region->label, (int)strlen(region->label));
  }
}

__attribute__((export_name("anvil_frame"))) void anvil_frame(double delta_ms) {
  if (delta_ms < 0.0)
    delta_ms = 0.0;
  if (delta_ms > 250.0)
    delta_ms = 250.0;
  anvil_delta_seconds = delta_ms / 1000.0;
  anvil_time_seconds += anvil_delta_seconds;
  anvil_screen_fade_advance(anvil_delta_seconds);
  anvil_scene_swapped = 0;
  anvil_focus_frame();
  if (anvil_frame_update)
    anvil_frame_update();
  anvil_scene_update(anvil_delta_seconds);
  anvil_particles_update(anvil_delta_seconds);
  /* Edges last one frame, like the C runtime's first-update clearing. */
  memset(anvil_keys_pressed, 0, sizeof(anvil_keys_pressed));
  memset(anvil_mouse_pressed_buttons, 0, sizeof(anvil_mouse_pressed_buttons));
  anvil_mouse_wheel_value = 0.0;
  anvil_host_clear(anvil_clear_r, anvil_clear_g, anvil_clear_b, anvil_clear_a);
  if (anvil_frame_draw)
    anvil_frame_draw();
  anvil_particles_draw();
  /* Ray-traced spheres last, in the same batch, so they depth-sort against the
     frame's own geometry and against each other. */
  anvil_wasm_trace_flush();
  /* Only when a fade is active, so an ordinary frame's op stream is unchanged. */
  if (anvil_screen_fade_value > 0.0)
    anvil_host_fade(anvil_screen_fade_value);
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
