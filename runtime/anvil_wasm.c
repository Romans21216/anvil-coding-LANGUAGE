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
void anvil_set_project(const char *name) { (void)name; }
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
    if (same && *a == ' ' && *b == ' ')
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

/* ---- Canvas 2D ---------------------------------------------------------- */
static int anvil_clear_r, anvil_clear_g, anvil_clear_b, anvil_clear_a;
static AnvilCallback anvil_frame_update, anvil_frame_draw;

void anvil_set_scene3d(int enabled) { (void)enabled; }

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
  /* Edges last one frame, like the C runtime's first-update clearing. */
  memset(anvil_keys_pressed, 0, sizeof(anvil_keys_pressed));
  memset(anvil_mouse_pressed_buttons, 0, sizeof(anvil_mouse_pressed_buttons));
  anvil_mouse_wheel_value = 0.0;
  anvil_host_clear(anvil_clear_r, anvil_clear_g, anvil_clear_b, anvil_clear_a);
  if (anvil_frame_draw)
    anvil_frame_draw();
  anvil_host_present();
}
