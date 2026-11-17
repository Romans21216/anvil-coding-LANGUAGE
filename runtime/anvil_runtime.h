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
double anvil_camera_angle(double yaw, double pitch);
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
double anvil_image_pixel(double handle, double x, double y);
double anvil_frame_capture(void);
double anvil_texture(double handle);
double anvil_buffer(double on);
double anvil_sprite_batch(double on);
double anvil_sprite_depth(double depth);
double anvil_sprite_queued(void);
double anvil_image_destroy(double handle);
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
const char *anvil_save_error(void);
void anvil_set_project(const char *name);
double anvil_save_number(const char *slot, double value);
double anvil_load_number(const char *slot);
double anvil_save_text(const char *slot, const char *text);
const char *anvil_load_text(const char *slot);
double anvil_save_exists(const char *slot);
double anvil_save_delete(const char *slot);
const char *anvil_sound_error(void);
double anvil_sound_load(const char *path);
double anvil_sound_play(double handle);
double anvil_sound_play_loop(double handle);
double anvil_sound_stop(double voice_handle);
double anvil_sound_stop_all(void);
double anvil_sound_group(double handle, double group);
double anvil_sound_group_volume(double group, double volume);
double anvil_sound_group_mute(double group, double on);
double anvil_sound_group_gain(double group);
double anvil_sound_group_stop(double group);
double anvil_music_load(const char *path);
double anvil_music_play(void);
double anvil_music_play_loop(void);
double anvil_music_stop(void);
double anvil_music_playing(void);
double anvil_music_volume(double volume);
double anvil_music_position(void);
double anvil_music_length(void);
const char *anvil_music_error(void);
double anvil_sound_volume(double voice_handle, double volume);
double anvil_sound_pan(double voice_handle, double pan);
double anvil_sound_pitch(double voice_handle, double pitch);
double anvil_sound_active(void);
double anvil_sound_duration(double handle);
double anvil_sound_rms(double handle);
double anvil_sound_destroy(double handle);
void anvil_trace_sphere(double x, double y, double z, double radius, int r,
                        int g, int b, int a);
void anvil_trace_finish(void);
int anvil_ray_backend(const char *name);
int anvil_ray_backend_available(const char *name);
void anvil_clear(int r, int g, int b, int a);
void anvil_rect(double x, double y, double w, double h, int r, int g, int b,
                int a);
double anvil_particle_emit(double x, double y, double vx, double vy,
                           double life, double size, double r, double g,
                           double b);
double anvil_particle_count(void);
double anvil_particle_clear(void);
double anvil_particle_gravity(double gravity);
void anvil_circle(double x, double y, double radius, int r, int g, int b,
                  int a);
void anvil_line(double x1, double y1, double x2, double y2, int r, int g, int b,
                int a, double thickness);
void anvil_cube(double x, double y, double z, double size, double rx, double ry,
                double rz, int r, int g, int b, int a);
double anvil_mesh_draw(const double *data, int triangle_count, double cx,
                       double cy, double cz, double radius, double x, double y,
                       double z, double scale, double rx, double ry, double rz);
double anvil_mesh_culled(void);
double anvil_mesh_drawn(void);
double anvil_mesh_culling(double on);
double anvil_shadow(double on);
double anvil_shadow_height(double y);
double anvil_shadow_alpha(double alpha);
void anvil_sphere(double x, double y, double z, double radius, int r, int g,
                  int b, int a);
void anvil_plane(double x, double y, double z, double width, double depth,
                 int r, int g, int b, int a);
void anvil_text(double x, double y, const char *text, int r, int g, int b,
                int a);
double anvil_text_width(const char *text);
void anvil_text_wrap(double x, double y, double max_width, const char *text,
                     int r, int g, int b, int a);
void anvil_text_number(double x, double y, const char *format, double value,
                       int r, int g, int b, int a);
double anvil_time(void);
double anvil_frame_tick(void);
double anvil_frame_render(void);
double anvil_frame_present(void);
double anvil_clock(void);
double anvil_delta(void);
double anvil_pressed(int key);
double anvil_held(int key);
double anvil_rnd(double min_value, double max_value);
double anvil_window_on_top(double on);
double anvil_window_fullscreen(double on);
double anvil_camera2d(double x, double y, double zoom);
void anvil_seed(unsigned long long seed);
void anvil_wait(double seconds);
void anvil_press_enter(void);
void anvil_ask(const char *prompt, char *dest);
double anvil_ask_number(const char *prompt);
#define ANVIL_STR_CAP 256
extern char anvil_str_scratch[256][ANVIL_STR_CAP];
void anvil_print_bool(double value);
const char *anvil_image_error(void);
void anvil_text_list_remove(char block[][256], int index, double count);
const char *anvil_text_list_get(const char block[][256], int index, double count, const char *path, int line);
void anvil_text_list_set(char block[][256], int index, double count, const char *value, const char *path, int line);
void anvil_str_set(char *dest, const char *value, const char *path, int line);
char *anvil_str_cat(char *dest, const char *a, const char *b,
                    const char *path, int line);
char *anvil_str_from_number(int slot, double value);
double anvil_noise(double x, double y, double z);
double anvil_fbm(double x, double y, double z, int octaves, double lacunarity,
                 double gain);
int anvil_net_host(int port);
int anvil_net_join(const char *address, int port);
int anvil_net_send(double value);
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
void anvil_frame_enter(void);
void anvil_frame_leave(void);
double anvil_list_get(const double *values, int index, double count,
                      const char *path, int line);
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

/* Resource accounting, in bytes. */
double anvil_memory_images(void);
double anvil_memory_audio(void);
double anvil_memory_video(void);
double anvil_memory_total(void);

#endif

