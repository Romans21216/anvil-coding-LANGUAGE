/* Generated from Anvil source. The .ANVL source remains the program. */
/* builtins used: delta, held, mouse_held, mouse_pressed, mouse_wheel, mouse_x, mouse_y, pressed */
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
    anvil_pointer_x = anvil_check_number((anvil_mouse_x ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 13);
    anvil_pointer_y = anvil_check_number((anvil_mouse_y ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 14);
    if ((((double)((anvil_check_number((anvil_check_number((anvil_mouse_held ( "left" )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 15)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 15)) && (anvil_check_number(((((double)((anvil_check_number((anvil_pointer_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 15)) >= (anvil_check_number((0.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 15))) == 1.0) ? 1.0 : 0.0)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 15))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_panel_x = anvil_check_number(((anvil_check_number((anvil_pointer_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 16) - anvil_check_number((250.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 16))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 16);
    }
    anvil_panel_x = anvil_check_number((anvil_panel_x + anvil_check_number(((anvil_check_number((anvil_check_number((anvil_mouse_wheel ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 18)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 18) * anvil_check_number((30.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 18))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 18)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 18);
    if (anvil_check_number((anvil_mouse_pressed ( "right" )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 19) != 0.0) {
        anvil_paused = anvil_check_number(((anvil_check_number((1.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 20) - anvil_check_number((anvil_paused), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 20))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 20);
    }
    if (anvil_check_number((anvil_mouse_pressed ( "middle" )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 22) != 0.0) {
        anvil_panel_x = 40.0;
        anvil_offset = 0.0;
    }
    if (anvil_check_number((anvil_held ( ANVIL_KEY_LEFT )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 26) != 0.0) {
        anvil_panel_x = anvil_check_number((anvil_panel_x - anvil_check_number(((anvil_check_number((180.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 27) * anvil_check_number((anvil_check_number((anvil_delta ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 27)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 27))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 27)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 27);
    }
    if (anvil_check_number((anvil_held ( ANVIL_KEY_RIGHT )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 29) != 0.0) {
        anvil_panel_x = anvil_check_number((anvil_panel_x + anvil_check_number(((anvil_check_number((180.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 30) * anvil_check_number((anvil_check_number((anvil_delta ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 30)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 30))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 30)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 30);
    }
    if (anvil_check_number((anvil_pressed ( ANVIL_KEY_SPACE )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 32) != 0.0) {
        anvil_paused = anvil_check_number(((anvil_check_number((1.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 33) - anvil_check_number((anvil_paused), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 33))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 33);
    }
    if (anvil_check_number((anvil_pressed ( ANVIL_KEY_R )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 35) != 0.0) {
        anvil_panel_x = 40.0;
        anvil_offset = 0.0;
    }
    if ((((double)((anvil_check_number((anvil_paused), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 39)) == (anvil_check_number((0.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 39))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_offset = anvil_check_number((anvil_offset + anvil_check_number(((anvil_check_number((80.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 40) * anvil_check_number((anvil_check_number((anvil_delta ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 40)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 40))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 40)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 40);
    }
    if ((((double)((anvil_check_number((anvil_offset), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 42)) > (anvil_check_number((440.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 42))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_offset = 0.0;
    }
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_rect(anvil_panel_x, 40.0, 500.0, 260.0, 35.0, 60.0, 90.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 49) + anvil_check_number((24.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 49))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 49), 64.0, 180.0, 180.0, 88.0, 164.0, 255.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 50) + anvil_check_number((228.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 50))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 50), 64.0, 248.0, 72.0, 172.0, 106.0, 255.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 51) + anvil_check_number((228.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 51))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 51), 160.0, 248.0, 84.0, 93.0, 223.0, 199.0, 255);
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_panel_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 52) + anvil_check_number((anvil_offset), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 52))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 52), 276.0, 30.0, 8.0, 255.0, 210.0, 90.0, 255);
    if ((((double)((anvil_check_number((anvil_pointer_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 53)) >= (anvil_check_number((0.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 53))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_trace_finish();
        anvil_rect(anvil_check_number(((anvil_check_number((anvil_pointer_x), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 54) - anvil_check_number((3.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 54))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 54), anvil_check_number(((anvil_check_number((anvil_pointer_y), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 54) - anvil_check_number((3.0), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 54))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\native_2d.ANVL", 54), 6.0, 6.0, 255.0, 255.0, 255.0, 255);
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
