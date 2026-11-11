/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_box;
static double anvil_box_x;
static double anvil_box_y;
static double anvil_contacts;
static double anvil_floor;
static double anvil_ok;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    anvil_contacts = anvil_check_number((anvil_physics_step ( )), "examples\\physics_friction.ANVL", 13);
    anvil_box_x = anvil_check_number((anvil_body_x ( anvil_box )), "examples\\physics_friction.ANVL", 14);
    anvil_box_y = anvil_check_number((anvil_body_y ( anvil_box )), "examples\\physics_friction.ANVL", 15);
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_check_number(((anvil_check_number((480.0), "examples\\physics_friction.ANVL", 19) + anvil_check_number((anvil_check_number(((anvil_check_number((anvil_box_x), "examples\\physics_friction.ANVL", 19) * anvil_check_number((40.0), "examples\\physics_friction.ANVL", 19))), "examples\\physics_friction.ANVL", 19)), "examples\\physics_friction.ANVL", 19))), "examples\\physics_friction.ANVL", 19)), "examples\\physics_friction.ANVL", 19) - anvil_check_number((20.0), "examples\\physics_friction.ANVL", 19))), "examples\\physics_friction.ANVL", 19), anvil_check_number(((anvil_check_number((anvil_check_number(((anvil_check_number((300.0), "examples\\physics_friction.ANVL", 19) - anvil_check_number((anvil_check_number(((anvil_check_number((anvil_box_y), "examples\\physics_friction.ANVL", 19) * anvil_check_number((40.0), "examples\\physics_friction.ANVL", 19))), "examples\\physics_friction.ANVL", 19)), "examples\\physics_friction.ANVL", 19))), "examples\\physics_friction.ANVL", 19)), "examples\\physics_friction.ANVL", 19) - anvil_check_number((20.0), "examples\\physics_friction.ANVL", 19))), "examples\\physics_friction.ANVL", 19), 40.0, 40.0, 88.0, 164.0, 255.0, 255);
    anvil_trace_finish();
    anvil_rect(160.0, 360.0, 640.0, 40.0, 89.0, 101.0, 123.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 20.0, "2D friction demonstration", 237.0, 243.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 48.0, "Surface friction slows horizontal motion", 187.0, 202.0, 221.0, 255);
    anvil_trace_finish();
    anvil_text_number(20.0, 76.0, "Contacts: %.0f", anvil_contacts, 157.0, 199.0, 255.0, 255);
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(12.0, 17.0, 29.0, 255.0);
    anvil_floor = anvil_check_number((anvil_body_create_box ( 0.0, (-2.0), 16.0, 1.0, 0.0 )), "examples\\physics_friction.ANVL", 4);
    anvil_box = anvil_check_number((anvil_body_create_box ( (-2.0), 1.0, 1.0, 1.0, 1.0 )), "examples\\physics_friction.ANVL", 5);
    anvil_ok = anvil_check_number((anvil_body_friction ( anvil_floor, 0.9 )), "examples\\physics_friction.ANVL", 6);
    anvil_ok = anvil_check_number((anvil_body_friction ( anvil_box, 0.75 )), "examples\\physics_friction.ANVL", 7);
    anvil_ok = anvil_check_number((anvil_body_set_velocity ( anvil_box, 5.0, 0.0 )), "examples\\physics_friction.ANVL", 8);
    anvil_box_x = anvil_check_number((anvil_body_x ( anvil_box )), "examples\\physics_friction.ANVL", 9);
    anvil_box_y = anvil_check_number((anvil_body_y ( anvil_box )), "examples\\physics_friction.ANVL", 10);
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
