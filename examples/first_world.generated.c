/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>

static double anvil_score;
static double anvil_spin;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    anvil_spin = (anvil_spin + anvil_delta ( ));
    if (anvil_pressed ( ANVIL_KEY_SPACE ) != 0.0) {
        anvil_score += 1.0;
    }
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_plane(0.0, (-1.0), 0.0, 12.0, 12.0, 33.0, 47.0, 64.0, 255);
    anvil_trace_finish();
    anvil_cube(0.0, 0.0, 0.0, 1.8, 0.0, anvil_spin, 0.0, 88.0, 164.0, 255.0, 255);
    anvil_trace_finish();
    anvil_sphere(2.0, 0.2, 0.0, 0.7, 255.0, 157.0, 91.0, 255);
    anvil_trace_sphere((-2.0), 0.15, 0.0, 0.85, 172.0, 106.0, 255.0, 255);
    anvil_trace_sphere((-3.25), 0.85, (-0.7), 0.42, 93.0, 223.0, 199.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 24.0, "Anvil Engine", 237.0, 243.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text_number(20.0, 52.0, "Space presses: %.0f", anvil_score, 157.0, 199.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 80.0, "WASD move | arrows look | Q/E rise", 187.0, 202.0, 221.0, 255);
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(1);
    anvil_camera_perspective(0.0, 3.0, 8.0);
    anvil_camera_fov(70.0);
    anvil_camera_control(4.0, 80.0);
    anvil_clear(11.0, 16.0, 27.0, 255.0);
    anvil_spin = 0.0;
    anvil_score = 0.0;
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}

