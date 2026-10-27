/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>

static double anvil_double(double anvil_double__value);
static double anvil_add_and_double(double anvil_add_and_double__left, double anvil_add_and_double__right);
static double anvil_main(void);

static double anvil_double(double anvil_double__value) {
    return (anvil_double__value * 2.0);
}

static double anvil_add_and_double(double anvil_add_and_double__left, double anvil_add_and_double__right) {
    return (anvil_double(anvil_add_and_double__left) + anvil_add_and_double__right);
}

static double anvil_main(void) {
    double anvil_main__result = 0.0;
    anvil_main__result = anvil_add_and_double(4.0, 5.0);
    return anvil_main__result;
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%.15g\n", anvil_main());
    anvil_net_close();
    return 0;
}

