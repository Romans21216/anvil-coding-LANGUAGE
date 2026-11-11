/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_terrain_seed;
static double anvil_terrain[64];
static double anvil_regenerate(void);
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_regenerate(void) {
    double anvil_regenerate__i = 0.0;
    double anvil_regenerate__offset = 0.0;
    anvil_seed((unsigned long long)(anvil_terrain_seed));
    anvil_regenerate__offset = anvil_check_number((anvil_rnd ( (-1000.0), 1000.0 )), "examples\\native_procedural.ANVL", 10);
    {
        const double _anvil_for_start_anvil_regenerate_11 = 0.0;
        const double _anvil_for_end_anvil_regenerate_11 = 63.0;
        const double _anvil_for_step_anvil_regenerate_11 = 1.0;
        anvil_regenerate__i = _anvil_for_start_anvil_regenerate_11;
        if (_anvil_for_step_anvil_regenerate_11 != 0.0) {
            while (((_anvil_for_step_anvil_regenerate_11 > 0.0 && anvil_regenerate__i <= _anvil_for_end_anvil_regenerate_11) || (_anvil_for_step_anvil_regenerate_11 < 0.0 && anvil_regenerate__i >= _anvil_for_end_anvil_regenerate_11))) {
                {
                    const double _anvil_array_index_anvil_regenerate_12 = anvil_regenerate__i;
                    const double _anvil_array_value_anvil_regenerate_12 = anvil_check_number(((anvil_check_number((220.0), "examples\\native_procedural.ANVL", 12) + anvil_check_number((anvil_check_number(((anvil_check_number((anvil_check_number((anvil_fbm ( anvil_check_number(((anvil_check_number((anvil_divide(anvil_check_number((anvil_regenerate__i), "examples\\native_procedural.ANVL", 12), 12.0, "examples\\native_procedural.ANVL", 12)), "examples\\native_procedural.ANVL", 12) + anvil_check_number((anvil_regenerate__offset), "examples\\native_procedural.ANVL", 12))), "examples\\native_procedural.ANVL", 12), 0.2, 0.3, 5.0, 2.0, 0.5 )), "examples\\native_procedural.ANVL", 12)), "examples\\native_procedural.ANVL", 12) * anvil_check_number((240.0), "examples\\native_procedural.ANVL", 12))), "examples\\native_procedural.ANVL", 12)), "examples\\native_procedural.ANVL", 12))), "examples\\native_procedural.ANVL", 12);
                    anvil_array_set(anvil_terrain, 64, _anvil_array_index_anvil_regenerate_12, _anvil_array_value_anvil_regenerate_12, "examples\\native_procedural.ANVL", 12);
                }
                anvil_regenerate__i = anvil_check_number((anvil_regenerate__i + _anvil_for_step_anvil_regenerate_11), "examples\\native_procedural.ANVL", 11);
            }
        }
    }
    return 0.0;
}

static double anvil_update(void) {
    if ((((double)((anvil_check_number((anvil_check_number((anvil_pressed ( ANVIL_KEY_SPACE )), "examples\\native_procedural.ANVL", 17)), "examples\\native_procedural.ANVL", 17)) || (anvil_check_number((anvil_check_number((anvil_mouse_pressed ( "left" )), "examples\\native_procedural.ANVL", 17)), "examples\\native_procedural.ANVL", 17))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_terrain_seed = anvil_check_number((anvil_terrain_seed + 1.0), "examples\\native_procedural.ANVL", 18);
        (void)anvil_regenerate();
    }
    return 0.0;
}

static double anvil_draw(void) {
    double anvil_draw__height = 0.0;
    double anvil_draw__i = 0.0;
    {
        const double _anvil_for_start_anvil_draw_24 = 0.0;
        const double _anvil_for_end_anvil_draw_24 = 63.0;
        const double _anvil_for_step_anvil_draw_24 = 1.0;
        anvil_draw__i = _anvil_for_start_anvil_draw_24;
        if (_anvil_for_step_anvil_draw_24 != 0.0) {
            while (((_anvil_for_step_anvil_draw_24 > 0.0 && anvil_draw__i <= _anvil_for_end_anvil_draw_24) || (_anvil_for_step_anvil_draw_24 < 0.0 && anvil_draw__i >= _anvil_for_end_anvil_draw_24))) {
                anvil_draw__height = anvil_array_get(anvil_terrain, 64, anvil_draw__i, "examples\\native_procedural.ANVL", 25);
                anvil_trace_finish();
                anvil_rect(anvil_check_number(((anvil_check_number((anvil_draw__i), "examples\\native_procedural.ANVL", 26) * anvil_check_number((14.0), "examples\\native_procedural.ANVL", 26))), "examples\\native_procedural.ANVL", 26), anvil_draw__height, 14.0, anvil_check_number((fmax ( 0.0, anvil_check_number(((anvil_check_number((600.0), "examples\\native_procedural.ANVL", 26) - anvil_check_number((anvil_draw__height), "examples\\native_procedural.ANVL", 26))), "examples\\native_procedural.ANVL", 26) )), "examples\\native_procedural.ANVL", 26), 60.0, 145.0, 110.0, 255);
                anvil_trace_finish();
                anvil_rect(anvil_check_number(((anvil_check_number((anvil_draw__i), "examples\\native_procedural.ANVL", 27) * anvil_check_number((14.0), "examples\\native_procedural.ANVL", 27))), "examples\\native_procedural.ANVL", 27), anvil_draw__height, 14.0, 5.0, 115.0, 220.0, 150.0, 255);
                anvil_draw__i = anvil_check_number((anvil_draw__i + _anvil_for_step_anvil_draw_24), "examples\\native_procedural.ANVL", 24);
            }
        }
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(11.0, 16.0, 27.0, 255.0);
    anvil_terrain_seed = 42.0;
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}
