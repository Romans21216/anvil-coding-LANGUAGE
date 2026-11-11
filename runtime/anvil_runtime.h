#ifndef ANVIL_RUNTIME_H
#define ANVIL_RUNTIME_H

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#else
#error The first native Anvil runtime target is Windows.
#endif

typedef double (*AnvilCallback)(void);

enum {
  ANVIL_KEY_SPACE = VK_SPACE,
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
  ANVIL_KEY_Z = 'Z',
  ANVIL_KEY_UP = VK_UP,
  ANVIL_KEY_DOWN = VK_DOWN,
  ANVIL_KEY_LEFT = VK_LEFT,
  ANVIL_KEY_RIGHT = VK_RIGHT,
  ANVIL_KEY_ENTER = VK_RETURN,
  ANVIL_KEY_ESCAPE = VK_ESCAPE
};

void anvil_run(AnvilCallback update, AnvilCallback draw, const char *title);
double anvil_divide(double numerator, double denominator, const char *path,
                    int line);
double anvil_check_number(double value, const char *path, int line);
double anvil_zero_clean(double value);
const char *anvil_format_number(double value);
void anvil_set_fixed_hz(int hz);
void anvil_set_scene3d(int enabled);
void anvil_camera_perspective(double x, double y, double z);
void anvil_camera_fov(double degrees);
void anvil_camera_control(double speed, double turn_degrees_per_second);
double anvil_mouse_x(void);
double anvil_mouse_y(void);
double anvil_mouse_pressed(const char *button);
double anvil_mouse_held(const char *button);
double anvil_mouse_wheel(void);
double anvil_image_load(const char *path);
double anvil_image_width(double handle);
double anvil_image_height(double handle);
double anvil_image_destroy(double handle);
double anvil_image_draw(double handle, double x, double y);
double anvil_image_draw_scaled(double handle, double x, double y, double width,
                               double height);
void anvil_trace_sphere(double x, double y, double z, double radius, int r,
                        int g, int b, int a);
void anvil_trace_finish(void);
int anvil_ray_backend(const char *name);
int anvil_ray_backend_available(const char *name);
void anvil_clear(int r, int g, int b, int a);
void anvil_rect(double x, double y, double w, double h, int r, int g, int b,
                int a);
void anvil_circle(double x, double y, double radius, int r, int g, int b,
                  int a);
void anvil_line(double x1, double y1, double x2, double y2, int r, int g, int b,
                int a, double thickness);
void anvil_cube(double x, double y, double z, double size, double rx, double ry,
                double rz, int r, int g, int b, int a);
void anvil_sphere(double x, double y, double z, double radius, int r, int g,
                  int b, int a);
void anvil_plane(double x, double y, double z, double width, double depth,
                 int r, int g, int b, int a);
void anvil_text(double x, double y, const char *text, int r, int g, int b,
                int a);
void anvil_text_number(double x, double y, const char *format, double value,
                       int r, int g, int b, int a);
double anvil_time(void);
double anvil_delta(void);
double anvil_pressed(int key);
double anvil_held(int key);
double anvil_rnd(double min_value, double max_value);
void anvil_seed(unsigned long long seed);
void anvil_wait(double seconds);
void anvil_press_enter(void);
void anvil_ask(const char *prompt, char *dest);
double anvil_ask_number(const char *prompt);
#define ANVIL_STR_CAP 256
extern char anvil_str_scratch[256][ANVIL_STR_CAP];
void anvil_str_set(char *dest, const char *value, const char *path, int line);
char *anvil_str_cat(char *dest, const char *a, const char *b,
                    const char *path, int line);
char *anvil_str_from_number(int slot, double value);
double anvil_noise(double x, double y, double z);
double anvil_fbm(double x, double y, double z, int octaves, double lacunarity,
                 double gain);
int anvil_net_host(int port);
int anvil_net_join(const char *address, int port);
void anvil_net_send(double value);
double anvil_net_receive(void);
void anvil_net_close(void);
double anvil_body_create(double x, double y, double radius, double mass);
double anvil_body_create_box(double x, double y, double width, double height,
                             double mass);
double anvil_physics_capacity(double requested_capacity);
double anvil_body_destroy(double handle);
double anvil_body_active(double handle);
double anvil_body_x(double handle);
double anvil_body_y(double handle);
double anvil_body_vx(double handle);
double anvil_body_vy(double handle);
double anvil_body_set_velocity(double handle, double vx, double vy);
double anvil_body_force(double handle, double fx, double fy);
double anvil_body_restitution(double handle, double restitution);
double anvil_body_friction(double handle, double friction);
double anvil_body_collision(double first, double second);
double anvil_physics_gravity(double x, double y);
double anvil_physics_step(void);
double anvil_array_get(const double *values, int size, double index,
                       const char *source, int line);
void anvil_array_set(double *values, int size, double index, double value,
                     const char *source, int line);
char *anvil_text_upper(const char *source);
char *anvil_text_lower(const char *source);
char *anvil_text_chr(double code);
double anvil_text_ord(const char *source);
char *anvil_text_trim(const char *source);
double anvil_text_to_number(const char *source);
char *anvil_text_char(const char *source, double index);
int anvil_str_contains(const char *source, const char *needle);
char *anvil_text_mid(const char *source, double start, double count);
char *anvil_text_left(const char *source, double count);
char *anvil_text_right(const char *source, double count);
int anvil_str_starts(const char *source, const char *prefix);
int anvil_str_ends(const char *source, const char *suffix);

#endif

