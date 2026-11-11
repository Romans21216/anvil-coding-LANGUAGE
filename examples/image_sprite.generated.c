/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_draw_ok;
static double anvil_sprite;
static double anvil_sprite_width;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_rect(80.0, 80.0, 800.0, 440.0, 29.0, 41.0, 62.0, 255.0);
    anvil_trace_finish();
    anvil_text(110.0, 110.0, "Anvil BMP sprite", 235.0, 243.0, 255.0, 255);
    anvil_draw_ok = anvil_check_number((anvil_image_draw_scaled ( anvil_sprite, 360.0, 210.0, 240.0, 240.0 )), "examples\\image_sprite.ANVL", 13);
    anvil_trace_finish();
    anvil_text_number(110.0, 540.0, "Native width: %.0f", anvil_sprite_width, 164.0, 190.0, 224.0, 255);
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(15.0, 21.0, 35.0, 255.0);
    anvil_sprite = anvil_check_number((anvil_image_load ( "examples/assets/anvil_sprite.bmp" )), "examples\\image_sprite.ANVL", 4);
    anvil_sprite_width = anvil_check_number((anvil_image_width ( anvil_sprite )), "examples\\image_sprite.ANVL", 5);
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
