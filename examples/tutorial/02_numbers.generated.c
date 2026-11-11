/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_score;
static double anvil_main(void);

static double anvil_main(void) {
    anvil_score = 10.0;
    anvil_score = anvil_check_number((anvil_score + 5.0), "examples\\tutorial\\02_numbers.ANVL", 4);
    printf("%s", anvil_str_cat(anvil_str_scratch[0], "Score: ", anvil_str_from_number(1, anvil_check_number((anvil_score), "examples\\tutorial\\02_numbers.ANVL", 5)), "examples\\tutorial\\02_numbers.ANVL", 5));
    printf("\n");
    printf("%.15g", anvil_check_number(((anvil_check_number((3.0), "examples\\tutorial\\02_numbers.ANVL", 6) + anvil_check_number((anvil_check_number(((anvil_check_number((4.0), "examples\\tutorial\\02_numbers.ANVL", 6) * anvil_check_number((2.0), "examples\\tutorial\\02_numbers.ANVL", 6))), "examples\\tutorial\\02_numbers.ANVL", 6)), "examples\\tutorial\\02_numbers.ANVL", 6))), "examples\\tutorial\\02_numbers.ANVL", 6));
    printf("\n");
    printf("%.15g", anvil_check_number(((anvil_check_number((anvil_check_number(((anvil_check_number((3.0), "examples\\tutorial\\02_numbers.ANVL", 7) + anvil_check_number((4.0), "examples\\tutorial\\02_numbers.ANVL", 7))), "examples\\tutorial\\02_numbers.ANVL", 7)), "examples\\tutorial\\02_numbers.ANVL", 7) * anvil_check_number((2.0), "examples\\tutorial\\02_numbers.ANVL", 7))), "examples\\tutorial\\02_numbers.ANVL", 7));
    printf("\n");
    printf("%.15g", anvil_check_number((fmod(anvil_check_number((7.0), "examples\\tutorial\\02_numbers.ANVL", 8), anvil_check_number((3.0), "examples\\tutorial\\02_numbers.ANVL", 8))), "examples\\tutorial\\02_numbers.ANVL", 8));
    printf("\n");
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
