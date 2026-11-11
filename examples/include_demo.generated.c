/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_main(void);
static double anvil_scale_value(double anvil_scale_value__value, double anvil_scale_value__factor);
static double anvil_optional_pointer_x(void);
static double anvil_clamp_value(double anvil_clamp_value__value, double anvil_clamp_value__minimum, double anvil_clamp_value__maximum);

static double anvil_main(void) {
    return anvil_clamp_value(anvil_scale_value(7.0, 3.0), 0.0, 20.0);
}

static double anvil_scale_value(double anvil_scale_value__value, double anvil_scale_value__factor) {
    return anvil_check_number(((anvil_check_number((anvil_scale_value__value), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\lib\\numbers.ANVL", 3) * anvil_check_number((anvil_scale_value__factor), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\lib\\numbers.ANVL", 3))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\lib\\numbers.ANVL", 3);
}

static double anvil_optional_pointer_x(void) {
    return anvil_check_number((anvil_mouse_x ( )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\lib\\numbers.ANVL", 8);
}

static double anvil_clamp_value(double anvil_clamp_value__value, double anvil_clamp_value__minimum, double anvil_clamp_value__maximum) {
    return anvil_check_number((fmin ( anvil_check_number((fmax ( anvil_clamp_value__value, anvil_clamp_value__minimum )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\lib\\clamp.ANVL", 3), anvil_clamp_value__maximum )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\lib\\clamp.ANVL", 3);
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%s\n", anvil_format_number(anvil_main()));
    anvil_net_close();
    return 0;
}
