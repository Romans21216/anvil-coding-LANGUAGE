/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_double(double anvil_double__value);
static double anvil_add_and_double(double anvil_add_and_double__left, double anvil_add_and_double__right);
static double anvil_main(void);

static double anvil_double(double anvil_double__value) {
    return anvil_check_number(((anvil_check_number((anvil_double__value), "examples\\functions.ANVL", 3) * anvil_check_number((2.0), "examples\\functions.ANVL", 3))), "examples\\functions.ANVL", 3);
}

static double anvil_add_and_double(double anvil_add_and_double__left, double anvil_add_and_double__right) {
    return anvil_check_number(((anvil_check_number((anvil_double(anvil_add_and_double__left)), "examples\\functions.ANVL", 7) + anvil_check_number((anvil_add_and_double__right), "examples\\functions.ANVL", 7))), "examples\\functions.ANVL", 7);
}

static double anvil_main(void) {
    double anvil_main__result = 0.0;
    anvil_main__result = anvil_add_and_double(4.0, 5.0);
    return anvil_main__result;
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%s\n", anvil_format_number(anvil_main()));
    anvil_net_close();
    return 0;
}
