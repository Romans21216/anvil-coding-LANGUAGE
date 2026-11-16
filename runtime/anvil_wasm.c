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
