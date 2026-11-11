/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_age;
static double anvil_main(void);

static double anvil_main(void) {
    anvil_age = 15.0;
    if ((((double)((anvil_check_number((anvil_age), "examples\\tutorial\\04_decisions.ANVL", 4)) >= (anvil_check_number((18.0), "examples\\tutorial\\04_decisions.ANVL", 4))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        printf("%s", "adult");
        printf("\n");
    } else {
        if ((((double)((anvil_check_number((anvil_age), "examples\\tutorial\\04_decisions.ANVL", 6)) >= (anvil_check_number((13.0), "examples\\tutorial\\04_decisions.ANVL", 6))) == 1.0) ? 1.0 : 0.0) != 0.0) {
            printf("%s", "teen");
            printf("\n");
        } else {
            printf("%s", "child");
            printf("\n");
        }
    }
    if (((double)(!(anvil_check_number(((((double)((anvil_check_number((anvil_age), "examples\\tutorial\\04_decisions.ANVL", 11)) == (anvil_check_number((15.0), "examples\\tutorial\\04_decisions.ANVL", 11))) == 1.0) ? 1.0 : 0.0)), "examples\\tutorial\\04_decisions.ANVL", 11)))) != 0.0) {
        printf("%s", "unexpected");
        printf("\n");
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
