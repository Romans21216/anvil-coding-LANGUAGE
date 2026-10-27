/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>

static double anvil_final_score;
static double anvil_score;
static double anvil_add_bonus(void);
static double anvil_main(void);

static double anvil_add_bonus(void) {
    anvil_score = 12.0;
    anvil_score += 5.0;
    return anvil_score;
}

static double anvil_main(void) {
    anvil_final_score = anvil_add_bonus();
    if ((anvil_final_score >= 15.0) != 0.0) {
        return anvil_final_score;
    } else {
        return 0.0;
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%.15g\n", anvil_main());
    anvil_net_close();
    return 0;
}

