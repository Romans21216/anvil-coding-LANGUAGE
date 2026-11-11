/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_offset;
static double anvil_panel_x;
static double anvil_paused;
static double anvil_pointer_x;
static double anvil_pointer_y;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    anvil_pointer_x = anvil_check_number((anvil_mouse_x ( )), "examples\\native_2d.ANVL", 13);
    anvil_pointer_y = anvil_check_number((anvil_mouse_y ( )), "examples\\native_2d.ANVL", 14);
    if ((((double)((anvil_check_number((anvil_check_number((anvil_mouse_held ( "left" )), "examples\\native_2d.ANVL", 15)), "examples\\native_2d.ANVL", 15)) && (anvil_check_number(((((double)((anvil_check_number((anvil_pointer_x), "examples\\native_2d.ANVL", 15)) >= (anvil_check_number((0.0), "examples\\native_2d.ANVL", 15))) == 1.0) ? 1.0 : 0.0)), "examples\\native_2d.ANVL", 15))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_panel_x = anvil_check_number(((anvil_check_number((anvil_pointer_x), "examples\\native_2d.ANVL", 16) - anvil_check_number((250.0), "examples\\native_2d.ANVL", 16))), "examples\\native_2d.ANVL", 16);
    }
    anvil_panel_x = anvil_check_number((anvil_panel_x + anvil_check_number(((anvil_check_number((anvil_check_number((anvil_mouse_wheel ( )), "examples\\native_2d.ANVL", 18)), "examples\\native_2d.ANVL", 18) * anvil_check_number((30.0), "examples\\native_2d.ANVL", 18))), "examples\\native_2d.ANVL", 18)), "examples\\native_2d.ANVL", 18);
    if (anvil_check_number((anvil_mouse_pressed ( "right" )), "examples\\native_2d.ANVL", 19) != 0.0) {
        anvil_paused = anvil_check_number(((anvil_check_number((1.0), "examples\\native_2d.ANVL", 20) - anvil_check_number((anvil_paused), "examples\\native_2d.ANVL", 20))), "examples\\native_2d.ANVL", 20);
    }
    if (anvil_check_number((anvil_mouse_pressed ( "middle" )), "examples\\native_2d.ANVL", 22) != 0.0) {
        anvil_panel_x = 40.0;
        anvil_offset = 0.0;
    }
    if (anvil_check_number((anvil_held ( ANVIL_KEY_LEFT )), "examples\\native_2d.ANVL", 26) != 0.0) {
        anvil_panel_x = anvil_check_number((anvil_panel_x - anvil_check_number(((anvil_check_number((180.0), "examples\\native_2d.ANVL", 27) * anvil_check_number((anvil_check_number((anvil_delta ( )), "examples\\native_2d.ANVL", 27)), "examples\\native_2d.ANVL", 27))), "examples\\native_2d.ANVL", 27)), "examples\\native_2d.ANVL", 27);
    }
    if (anvil_check_number((anvil_held ( ANVIL_KEY_RIGHT )), "examples\\native_2d.ANVL", 29) != 0.0) {
        anvil_panel_x = anvil_check_number((anvil_panel_x + anvil_check_number(((anvil_check_number((180.0), "examples\\native_2d.ANVL", 30) * anvil_check_number((anvil_check_number((anvil_delta ( )), "examples\\native_2d.ANVL", 30)), "examples\\native_2d.ANVL", 30))), "examples\\native_2d.ANVL", 30)), "examples\\native_2d.ANVL", 30);
    }
    if (anvil_check_number((anvil_pressed ( ANVIL_KEY_SPACE )), "examples\\native_2d.ANVL", 32) != 0.0) {
        anvil_paused = anvil_check_number(((anvil_check_number((1.0), "examples\\native_2d.ANVL", 33) - anvil_check_number((anvil_paused), "examples\\native_2d.ANVL", 33))), "examples\\native_2d.ANVL", 33);
    }
    if (anvil_check_number((anvil_pressed ( ANVIL_KEY_R )), "examples\\native_2d.ANVL", 35) != 0.0) {
        anvil_panel_x = 40.0;
        anvil_offset = 0.0;
    }
    if ((((double)((anvil_check_number((anvil_paused), "examples\\native_2d.ANVL", 39)) == (anvil_check_number((0.0), "examples\\native_2d.ANVL", 39))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_offset = anvil_check_number((anvil_offset + anvil_check_number(((anvil_check_number((80.0), "examples\\native_2d.ANVL", 40) * anvil_check_number((anvil_check_number((anvil_delta ( )), "examples\\native_2d.ANVL", 40)), "examples\\native_2d.ANVL", 40))), "examples\\native_2d.ANVL", 40)), "examples\\native_2d.ANVL", 40);
    }
    if ((((double)((anvil_check_number((anvil_offset), "examples\\native_2d.ANVL", 42)) > (anvil_check_number((440.0), "examples\\native_2d.ANVL", 42))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_offset = 0.0;
    }
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_rect(anvil_panel_x, 40.0, 500.0, 260.0, 35.0, 60.0, 90.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "examples\\native_2d.ANVL", 49) + anvil_check_number((24.0), "examples\\native_2d.ANVL", 49))), "examples\\native_2d.ANVL", 49), 64.0, 180.0, 180.0, 88.0, 164.0, 255.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "examples\\native_2d.ANVL", 50) + anvil_check_number((228.0), "examples\\native_2d.ANVL", 50))), "examples\\native_2d.ANVL", 50), 64.0, 248.0, 72.0, 172.0, 106.0, 255.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "examples\\native_2d.ANVL", 51) + anvil_check_number((228.0), "examples\\native_2d.ANVL", 51))), "examples\\native_2d.ANVL", 51), 160.0, 248.0, 84.0, 93.0, 223.0, 199.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "examples\\native_2d.ANVL", 52) + anvil_check_number((anvil_offset), "examples\\native_2d.ANVL", 52))), "examples\\native_2d.ANVL", 52), 276.0, 30.0, 8.0, 255.0, 210.0, 90.0, 255);
    if ((((double)((anvil_check_number((anvil_pointer_x), "examples\\native_2d.ANVL", 53)) >= (anvil_check_number((0.0), "examples\\native_2d.ANVL", 53))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_trace_finish();
        anvil_rect(anvil_check_number(((anvil_check_number((anvil_pointer_x), "examples\\native_2d.ANVL", 54) - anvil_check_number((3.0), "examples\\native_2d.ANVL", 54))), "examples\\native_2d.ANVL", 54), anvil_check_number(((anvil_check_number((anvil_pointer_y), "examples\\native_2d.ANVL", 54) - anvil_check_number((3.0), "examples\\native_2d.ANVL", 54))), "examples\\native_2d.ANVL", 54), 6.0, 6.0, 255.0, 255.0, 255.0, 255);
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(11.0, 16.0, 27.0, 255.0);
    anvil_panel_x = 40.0;
    anvil_offset = 0.0;
    anvil_paused = 0.0;
    anvil_pointer_x = (-1.0);
    anvil_pointer_y = (-1.0);
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
