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
static inline double round(double value) { return __builtin_round(value); }

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

/* Canvas 2D surface: every call is forwarded to the host. */
typedef double (*AnvilCallback)(void);
void anvil_set_scene3d(int enabled);
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
