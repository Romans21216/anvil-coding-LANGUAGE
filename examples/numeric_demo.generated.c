/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_final_score;
static double anvil_score;
static double anvil_add_bonus(void);
static double anvil_main(void);

static double anvil_add_bonus(void) {
    anvil_score = 12.0;
    anvil_score = anvil_check_number((anvil_score + 5.0), "examples\\numeric_demo.ANVL", 4);
    return anvil_score;
}

static double anvil_main(void) {
    anvil_final_score = anvil_add_bonus();
    if ((((double)((anvil_check_number((anvil_final_score), "examples\\numeric_demo.ANVL", 11)) >= (anvil_check_number((15.0), "examples\\numeric_demo.ANVL", 11))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        return anvil_final_score;
    } else {
        return 0.0;
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%s\n", anvil_format_number(anvil_main()));
    anvil_net_close();
    return 0;
}
