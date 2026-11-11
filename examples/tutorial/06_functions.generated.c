/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_double(double anvil_double__value);
static double anvil_main(void);

static double anvil_double(double anvil_double__value) {
    return anvil_check_number(((anvil_check_number((anvil_double__value), "examples\\tutorial\\06_functions.ANVL", 3) * anvil_check_number((2.0), "examples\\tutorial\\06_functions.ANVL", 3))), "examples\\tutorial\\06_functions.ANVL", 3);
}

static double anvil_main(void) {
    printf("%.15g", anvil_double(21.0));
    printf("\n");
    printf("%.15g", anvil_double(3.5));
    printf("\n");
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
