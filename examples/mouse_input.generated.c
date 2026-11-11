/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_clicks;
static double anvil_cursor_x;
static double anvil_cursor_y;
static double anvil_wheel;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    anvil_cursor_x = anvil_check_number((anvil_mouse_x ( )), "examples\\mouse_input.ANVL", 11);
    anvil_cursor_y = anvil_check_number((anvil_mouse_y ( )), "examples\\mouse_input.ANVL", 12);
    if (anvil_check_number((anvil_mouse_pressed ( "left" )), "examples\\mouse_input.ANVL", 13) != 0.0) {
        anvil_clicks = anvil_check_number((anvil_clicks + 1.0), "examples\\mouse_input.ANVL", 14);
    }
    anvil_wheel = anvil_check_number((anvil_wheel + anvil_check_number((anvil_mouse_wheel ( )), "examples\\mouse_input.ANVL", 16)), "examples\\mouse_input.ANVL", 16);
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_text_number(24.0, 32.0, "Click count: %.0f", anvil_clicks, 235.0, 242.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text_number(24.0, 60.0, "Wheel detents: %.0f", anvil_wheel, 156.0, 195.0, 255.0, 255);
    if ((((double)((anvil_check_number(((((double)((anvil_check_number((anvil_cursor_x), "examples\\mouse_input.ANVL", 22)) >= (anvil_check_number((0.0), "examples\\mouse_input.ANVL", 22))) == 1.0) ? 1.0 : 0.0)), "examples\\mouse_input.ANVL", 22)) && (anvil_check_number(((((double)((anvil_check_number((anvil_cursor_y), "examples\\mouse_input.ANVL", 22)) >= (anvil_check_number((0.0), "examples\\mouse_input.ANVL", 22))) == 1.0) ? 1.0 : 0.0)), "examples\\mouse_input.ANVL", 22))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_trace_finish();
        anvil_circle(anvil_cursor_x, anvil_cursor_y, 10.0, 96.0, 212.0, 164.0, 200.0);
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(12.0, 17.0, 29.0, 255.0);
    anvil_cursor_x = (-1.0);
    anvil_cursor_y = (-1.0);
    anvil_clicks = 0.0;
    anvil_wheel = 0.0;
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
