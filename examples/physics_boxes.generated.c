/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_ball;
static double anvil_ball_x;
static double anvil_ball_y;
static double anvil_box;
static double anvil_box_x;
static double anvil_box_y;
static double anvil_contact_count;
static double anvil_floor;
static double anvil_ok;
static double anvil_pool_capacity;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    if (anvil_check_number((anvil_held ( ANVIL_KEY_LEFT )), "examples\\physics_boxes.ANVL", 18) != 0.0) {
        anvil_ok = anvil_check_number((anvil_body_force ( anvil_box, (-8.0), 0.0 )), "examples\\physics_boxes.ANVL", 19);
    }
    if (anvil_check_number((anvil_held ( ANVIL_KEY_RIGHT )), "examples\\physics_boxes.ANVL", 21) != 0.0) {
        anvil_ok = anvil_check_number((anvil_body_force ( anvil_box, 8.0, 0.0 )), "examples\\physics_boxes.ANVL", 22);
    }
    anvil_contact_count = anvil_check_number((anvil_physics_step ( )), "examples\\physics_boxes.ANVL", 24);
    anvil_box_x = anvil_check_number((anvil_body_x ( anvil_box )), "examples\\physics_boxes.ANVL", 25);
    anvil_box_y = anvil_check_number((anvil_body_y ( anvil_box )), "examples\\physics_boxes.ANVL", 26);
    anvil_ball_x = anvil_check_number((anvil_body_x ( anvil_ball )), "examples\\physics_boxes.ANVL", 27);
    anvil_ball_y = anvil_check_number((anvil_body_y ( anvil_ball )), "examples\\physics_boxes.ANVL", 28);
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_rect(anvil_check_number(((anvil_check_number((anvil_check_number(((anvil_check_number((480.0), "examples\\physics_boxes.ANVL", 32) + anvil_check_number((anvil_check_number(((anvil_check_number((anvil_box_x), "examples\\physics_boxes.ANVL", 32) * anvil_check_number((48.0), "examples\\physics_boxes.ANVL", 32))), "examples\\physics_boxes.ANVL", 32)), "examples\\physics_boxes.ANVL", 32))), "examples\\physics_boxes.ANVL", 32)), "examples\\physics_boxes.ANVL", 32) - anvil_check_number((24.0), "examples\\physics_boxes.ANVL", 32))), "examples\\physics_boxes.ANVL", 32), anvil_check_number(((anvil_check_number((anvil_check_number(((anvil_check_number((300.0), "examples\\physics_boxes.ANVL", 32) - anvil_check_number((anvil_check_number(((anvil_check_number((anvil_box_y), "examples\\physics_boxes.ANVL", 32) * anvil_check_number((48.0), "examples\\physics_boxes.ANVL", 32))), "examples\\physics_boxes.ANVL", 32)), "examples\\physics_boxes.ANVL", 32))), "examples\\physics_boxes.ANVL", 32)), "examples\\physics_boxes.ANVL", 32) - anvil_check_number((24.0), "examples\\physics_boxes.ANVL", 32))), "examples\\physics_boxes.ANVL", 32), 48.0, 48.0, 88.0, 164.0, 255.0, 255);
    anvil_trace_finish();
    anvil_circle(anvil_check_number(((anvil_check_number((480.0), "examples\\physics_boxes.ANVL", 33) + anvil_check_number((anvil_check_number(((anvil_check_number((anvil_ball_x), "examples\\physics_boxes.ANVL", 33) * anvil_check_number((48.0), "examples\\physics_boxes.ANVL", 33))), "examples\\physics_boxes.ANVL", 33)), "examples\\physics_boxes.ANVL", 33))), "examples\\physics_boxes.ANVL", 33), anvil_check_number(((anvil_check_number((300.0), "examples\\physics_boxes.ANVL", 33) - anvil_check_number((anvil_check_number(((anvil_check_number((anvil_ball_y), "examples\\physics_boxes.ANVL", 33) * anvil_check_number((48.0), "examples\\physics_boxes.ANVL", 33))), "examples\\physics_boxes.ANVL", 33)), "examples\\physics_boxes.ANVL", 33))), "examples\\physics_boxes.ANVL", 33), 24.0, 172.0, 106.0, 255.0, 255);
    anvil_trace_finish();
    anvil_rect(192.0, 372.0, 576.0, 48.0, 89.0, 101.0, 123.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 20.0, "2D box and circle physics", 237.0, 243.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 48.0, "Hold left/right to push the box", 187.0, 202.0, 221.0, 255);
    anvil_trace_finish();
    anvil_text_number(20.0, 76.0, "Contacts: %.0f", anvil_contact_count, 157.0, 199.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text_number(20.0, 104.0, "Physics body slots: %.0f", anvil_pool_capacity, 157.0, 199.0, 255.0, 255);
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(12.0, 17.0, 29.0, 255.0);
    anvil_pool_capacity = anvil_check_number((anvil_physics_capacity ( 32.0 )), "examples\\physics_boxes.ANVL", 4);
    anvil_floor = anvil_check_number((anvil_body_create_box ( 0.0, (-2.0), 12.0, 1.0, 0.0 )), "examples\\physics_boxes.ANVL", 6);
    anvil_box = anvil_check_number((anvil_body_create_box ( (-1.0), 2.0, 1.0, 1.0, 1.0 )), "examples\\physics_boxes.ANVL", 7);
    anvil_ball = anvil_check_number((anvil_body_create ( 1.0, 3.0, 0.5, 1.0 )), "examples\\physics_boxes.ANVL", 8);
    anvil_ok = anvil_check_number((anvil_body_restitution ( anvil_box, 0.35 )), "examples\\physics_boxes.ANVL", 9);
    anvil_ok = anvil_check_number((anvil_body_restitution ( anvil_ball, 0.5 )), "examples\\physics_boxes.ANVL", 10);
    anvil_box_x = anvil_check_number((anvil_body_x ( anvil_box )), "examples\\physics_boxes.ANVL", 11);
    anvil_box_y = anvil_check_number((anvil_body_y ( anvil_box )), "examples\\physics_boxes.ANVL", 12);
    anvil_ball_x = anvil_check_number((anvil_body_x ( anvil_ball )), "examples\\physics_boxes.ANVL", 13);
    anvil_ball_y = anvil_check_number((anvil_body_y ( anvil_ball )), "examples\\physics_boxes.ANVL", 14);
    anvil_contact_count = 0.0;
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
