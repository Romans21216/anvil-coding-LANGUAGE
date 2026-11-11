/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_contact_count;
static double anvil_force_result;
static double anvil_player;
static double anvil_player_bounce;
static double anvil_player_x;
static double anvil_player_y;
static double anvil_target;
static double anvil_target_bounce;
static double anvil_target_x;
static double anvil_target_y;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    if (anvil_check_number((anvil_held ( ANVIL_KEY_LEFT )), "examples\\physics.ANVL", 15) != 0.0) {
        anvil_force_result = anvil_check_number((anvil_body_force ( anvil_player, (-8.0), 0.0 )), "examples\\physics.ANVL", 16);
    }
    if (anvil_check_number((anvil_held ( ANVIL_KEY_RIGHT )), "examples\\physics.ANVL", 18) != 0.0) {
        anvil_force_result = anvil_check_number((anvil_body_force ( anvil_player, 8.0, 0.0 )), "examples\\physics.ANVL", 19);
    }
    anvil_contact_count = anvil_check_number((anvil_physics_step ( )), "examples\\physics.ANVL", 21);
    anvil_player_x = anvil_check_number((anvil_body_x ( anvil_player )), "examples\\physics.ANVL", 22);
    anvil_player_y = anvil_check_number((anvil_body_y ( anvil_player )), "examples\\physics.ANVL", 23);
    anvil_target_x = anvil_check_number((anvil_body_x ( anvil_target )), "examples\\physics.ANVL", 24);
    anvil_target_y = anvil_check_number((anvil_body_y ( anvil_target )), "examples\\physics.ANVL", 25);
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_circle(anvil_check_number(((anvil_check_number((480.0), "examples\\physics.ANVL", 29) + anvil_check_number((anvil_check_number(((anvil_check_number((anvil_player_x), "examples\\physics.ANVL", 29) * anvil_check_number((64.0), "examples\\physics.ANVL", 29))), "examples\\physics.ANVL", 29)), "examples\\physics.ANVL", 29))), "examples\\physics.ANVL", 29), anvil_check_number(((anvil_check_number((300.0), "examples\\physics.ANVL", 29) - anvil_check_number((anvil_check_number(((anvil_check_number((anvil_player_y), "examples\\physics.ANVL", 29) * anvil_check_number((64.0), "examples\\physics.ANVL", 29))), "examples\\physics.ANVL", 29)), "examples\\physics.ANVL", 29))), "examples\\physics.ANVL", 29), 32.0, 88.0, 164.0, 255.0, 255);
    anvil_trace_finish();
    anvil_circle(anvil_check_number(((anvil_check_number((480.0), "examples\\physics.ANVL", 30) + anvil_check_number((anvil_check_number(((anvil_check_number((anvil_target_x), "examples\\physics.ANVL", 30) * anvil_check_number((64.0), "examples\\physics.ANVL", 30))), "examples\\physics.ANVL", 30)), "examples\\physics.ANVL", 30))), "examples\\physics.ANVL", 30), anvil_check_number(((anvil_check_number((300.0), "examples\\physics.ANVL", 30) - anvil_check_number((anvil_check_number(((anvil_check_number((anvil_target_y), "examples\\physics.ANVL", 30) * anvil_check_number((64.0), "examples\\physics.ANVL", 30))), "examples\\physics.ANVL", 30)), "examples\\physics.ANVL", 30))), "examples\\physics.ANVL", 30), 48.0, 172.0, 106.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 20.0, "2D circle physics", 237.0, 243.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text(20.0, 48.0, "Hold left/right to push the blue body", 187.0, 202.0, 221.0, 255);
    anvil_trace_finish();
    anvil_text_number(20.0, 76.0, "Contacts: %.0f", anvil_contact_count, 157.0, 199.0, 255.0, 255);
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(12.0, 17.0, 29.0, 255.0);
    anvil_player = anvil_check_number((anvil_body_create ( (-1.0), 2.0, 0.5, 1.0 )), "examples\\physics.ANVL", 5);
    anvil_target = anvil_check_number((anvil_body_create ( 1.0, 0.0, 0.75, 2.0 )), "examples\\physics.ANVL", 6);
    anvil_player_bounce = anvil_check_number((anvil_body_restitution ( anvil_player, 0.65 )), "examples\\physics.ANVL", 7);
    anvil_target_bounce = anvil_check_number((anvil_body_restitution ( anvil_target, 0.65 )), "examples\\physics.ANVL", 8);
    anvil_player_x = anvil_check_number((anvil_body_x ( anvil_player )), "examples\\physics.ANVL", 9);
    anvil_player_y = anvil_check_number((anvil_body_y ( anvil_player )), "examples\\physics.ANVL", 10);
    anvil_target_x = anvil_check_number((anvil_body_x ( anvil_target )), "examples\\physics.ANVL", 11);
    anvil_target_y = anvil_check_number((anvil_body_y ( anvil_target )), "examples\\physics.ANVL", 12);
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
