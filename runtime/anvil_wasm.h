/* Minimal C surface for the WebAssembly (console) target.

   The Windows runtime is not usable here: no GDI, sockets or Win32. This
   header declares just what the generated C needs for the console subset the
   wasm backend accepts. Anything outside that subset is refused by the
   compiler before this header is used. */
#ifndef ANVIL_WASM_H
#define ANVIL_WASM_H

#include <stddef.h>
#include <stdarg.h>

#define ANVIL_STR_CAP 256
#define stdout ((void *)0)

extern char anvil_str_scratch[256][ANVIL_STR_CAP];

int printf(const char *format, ...);
int putchar(int character);
int fflush(void *stream);
size_t strlen(const char *text);
void *memcpy(void *dest, const void *source, size_t count);
void *memset(void *dest, int value, size_t count);
int strcmp(const char *a, const char *b);
void *calloc(size_t count, size_t size);
void *malloc(size_t size);
void free(void *pointer);
void exit(int code);

/* Wasm instructions back these, so no libm is required. */
static inline double fabs(double value) { return __builtin_fabs(value); }
static inline double floor(double value) { return __builtin_floor(value); }
static inline double ceil(double value) { return __builtin_ceil(value); }
static inline double sqrt(double value) { return __builtin_sqrt(value); }
static inline double trunc(double value) { return __builtin_trunc(value); }
static inline double round(double value) {
  double truncated = __builtin_trunc(value);
  double fraction = value - truncated;
  if (fraction >= 0.5)
    return truncated + 1.0;
  if (fraction <= -0.5)
    return truncated - 1.0;
  return truncated;
}

double anvil_divide(double numerator, double denominator, const char *path,
                    int line);
double anvil_check_number(double value, const char *path, int line);
const char *anvil_format_number(double value);
void anvil_set_fixed_hz(int hz);
void anvil_set_project(const char *name);
void anvil_net_close(void);
void anvil_frame_enter(void);
void anvil_frame_leave(void);

double anvil_array_get(const double *values, int size, double index,
                       const char *path, int line);
void anvil_array_set(double *values, int size, double index, double value,
                     const char *path, int line);

void anvil_str_set(char *dest, const char *value, const char *path, int line);
char *anvil_str_cat(char *dest, const char *a, const char *b, const char *path,
                    int line);
char *anvil_text_upper(const char *source);
char *anvil_text_mid(const char *source, double start, double count);
double anvil_text_to_number(const char *source);

/* Input and time, matching the C runtime's key codes. */
enum {
  ANVIL_KEY_ENTER = 13,
  ANVIL_KEY_ESCAPE = 27,
  ANVIL_KEY_SPACE = 32,
  ANVIL_KEY_LEFT = 37,
  ANVIL_KEY_UP = 38,
  ANVIL_KEY_RIGHT = 39,
  ANVIL_KEY_DOWN = 40,
  ANVIL_KEY_A = 'A',
  ANVIL_KEY_B = 'B',
  ANVIL_KEY_C = 'C',
  ANVIL_KEY_D = 'D',
  ANVIL_KEY_E = 'E',
  ANVIL_KEY_F = 'F',
  ANVIL_KEY_G = 'G',
  ANVIL_KEY_H = 'H',
  ANVIL_KEY_I = 'I',
  ANVIL_KEY_J = 'J',
  ANVIL_KEY_K = 'K',
  ANVIL_KEY_L = 'L',
  ANVIL_KEY_M = 'M',
  ANVIL_KEY_N = 'N',
  ANVIL_KEY_O = 'O',
  ANVIL_KEY_P = 'P',
  ANVIL_KEY_Q = 'Q',
  ANVIL_KEY_R = 'R',
  ANVIL_KEY_S = 'S',
  ANVIL_KEY_T = 'T',
  ANVIL_KEY_U = 'U',
  ANVIL_KEY_V = 'V',
  ANVIL_KEY_W = 'W',
  ANVIL_KEY_X = 'X',
  ANVIL_KEY_Y = 'Y',
  ANVIL_KEY_Z = 'Z'
};

double anvil_time(void);
double anvil_delta(void);
double anvil_pressed(int key);
double anvil_held(int key);
double anvil_mouse_x(void);
double anvil_mouse_y(void);
double anvil_mouse_pressed(const char *button);
double anvil_mouse_held(const char *button);
double anvil_mouse_wheel(void);
double sin(double radians);
double cos(double radians);
double anvil_rnd(double min_value, double max_value);

/* Saves: typed slots persisted by the host (localStorage in the browser). */
void anvil_set_project(const char *name);
double anvil_save_number(const char *slot, double value);
double anvil_load_number(const char *slot);
double anvil_save_text(const char *slot, const char *text);
const char *anvil_load_text(const char *slot);
double anvil_save_exists(const char *slot);
double anvil_save_delete(const char *slot);
const char *anvil_save_error(void);

/* Text helpers, matching the C runtime's clamped slice semantics. */
char *anvil_text_lower(const char *source);
char *anvil_text_trim(const char *source);
char *anvil_text_left(const char *source, double count);
char *anvil_text_right(const char *source, double count);
char *anvil_text_char(const char *source, double index);
int anvil_str_contains(const char *source, const char *needle);
int anvil_str_starts(const char *source, const char *prefix);
int anvil_str_ends(const char *source, const char *suffix);

/* Perlin-style noise and character conversion, matching the C runtime. */
double anvil_noise(double x, double y, double z);
double anvil_fbm(double x, double y, double z, int octaves, double lacunarity,
                 double gain);
double anvil_text_ord(const char *source);
char *anvil_text_chr(double code);

/* Images are baked into the module by the compiler. */
typedef struct {
  const char *path;
  int width, height;
  const unsigned int *pixels; /* 0xAARRGGBB */
} AnvilWasmImage;

void anvil_wasm_set_images(const AnvilWasmImage *images, int count);
double anvil_image_load(const char *path);
double anvil_image_width(double handle);
double anvil_image_height(double handle);
double anvil_image_draw(double handle, double x, double y);
double anvil_image_draw_scaled(double handle, double x, double y, double width,
                               double height);
double anvil_image_draw_rotated(double handle, double cx, double cy,
                                double degrees, double scale);
double anvil_image_draw_region(double handle, double sx, double sy, double sw,
                               double sh, double dx, double dy, double dw,
                               double dh);
double anvil_image_tint(double handle, double r, double g, double b);
double anvil_image_flip(double handle, double x, double y);
double anvil_image_destroy(double handle);
const char *anvil_image_error(void);

/* Sounds are baked into the module by the compiler. */
typedef struct {
  const char *path;
  int channels, rate, frames;
  const short *pcm;
} AnvilWasmSound;

void anvil_wasm_set_sounds(const AnvilWasmSound *sounds, int count);
double anvil_sound_load(const char *path);
double anvil_sound_play(double handle);
double anvil_sound_play_loop(double handle);
double anvil_sound_pan(double voice, double pan);
double anvil_sound_pitch(double voice, double rate);
double anvil_sound_duration(double handle);
double anvil_sound_group(double handle, double group);
double anvil_sound_group_volume(double group, double volume);
double anvil_sound_group_mute(double group, double on);
double anvil_sound_group_gain(double group);
double anvil_sound_group_stop(double group);
double anvil_sound_stop(double voice);
double anvil_sound_stop_all(void);
double anvil_sound_volume(double voice, double volume);
double anvil_sound_active(void);
double anvil_sound_destroy(double handle);
const char *anvil_sound_error(void);

/* One music track, baked into the module by the compiler. */
typedef struct {
  const char *path;
  int channels, rate, frames;
  const short *pcm;
} AnvilWasmMusic;

void anvil_wasm_set_music(const AnvilWasmMusic *music);
double anvil_music_load(const char *path);
double anvil_music_play(void);
double anvil_music_play_loop(void);
double anvil_music_stop(void);
double anvil_music_playing(void);
double anvil_music_volume(double volume);
double anvil_music_position(void);
double anvil_music_length(void);
const char *anvil_music_error(void);

/* Canvas 2D surface: every call is forwarded to the host. */
typedef double (*AnvilCallback)(void);
void anvil_set_scene3d(int enabled);
void anvil_camera_perspective(double x, double y, double z);
void anvil_camera_fov(double degrees);
double anvil_camera_angle(double yaw, double pitch);
void anvil_cube(double x, double y, double z, double size, double rx, double ry,
                double rz, int r, int g, int b, int a);
void anvil_plane(double x, double y, double z, double width, double depth,
                 int r, int g, int b, int a);
void anvil_sphere(double x, double y, double z, double radius, int r, int g,
                  int b, int a);
double anvil_mesh_draw(const double *data, int triangle_count, double cx,
                       double cy, double cz, double radius, double x, double y,
                       double z, double scale, double rx, double ry, double rz);
double anvil_mesh_drawn(void);
double anvil_mesh_culled(void);
double anvil_mesh_culling(double on);
double anvil_shadow(double on);
double anvil_shadow_height(double y);
double anvil_shadow_alpha(double alpha);
void anvil_clear(int r, int g, int b, int a);
void anvil_rect(double x, double y, double w, double h, int r, int g, int b,
                int a);
void anvil_circle(double x, double y, double radius, int r, int g, int b,
                  int a);
void anvil_line(double x1, double y1, double x2, double y2, int r, int g, int b,
                int a, double thickness);
void anvil_text(double x, double y, const char *text, int r, int g, int b,
                int a);
void anvil_trace_finish(void);
void anvil_run(AnvilCallback update, AnvilCallback draw, const char *title);

#endif
