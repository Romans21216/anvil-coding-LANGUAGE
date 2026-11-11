/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_flag;
static double anvil_is_even(double anvil_is_even__n);
static double anvil_main(void);

static double anvil_is_even(double anvil_is_even__n) {
    if ((((double)((anvil_check_number((anvil_check_number((fmod(anvil_check_number((anvil_is_even__n), "examples\\tutorial\\10_program.ANVL", 4), anvil_check_number((2.0), "examples\\tutorial\\10_program.ANVL", 4))), "examples\\tutorial\\10_program.ANVL", 4)), "examples\\tutorial\\10_program.ANVL", 4)) == (anvil_check_number((0.0), "examples\\tutorial\\10_program.ANVL", 4))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        return 1.0;
    }
    return 0.0;
}

static double anvil_main(void) {
    double anvil_main__index = 0.0;
    {
        const double _anvil_for_start_anvil_main_11 = 1.0;
        const double _anvil_for_end_anvil_main_11 = 4.0;
        const double _anvil_for_step_anvil_main_11 = 1.0;
        anvil_main__index = _anvil_for_start_anvil_main_11;
        if (_anvil_for_step_anvil_main_11 != 0.0) {
            while (((_anvil_for_step_anvil_main_11 > 0.0 && anvil_main__index <= _anvil_for_end_anvil_main_11) || (_anvil_for_step_anvil_main_11 < 0.0 && anvil_main__index >= _anvil_for_end_anvil_main_11))) {
                anvil_flag = anvil_is_even(anvil_main__index);
                if ((((double)((anvil_check_number((anvil_flag), "examples\\tutorial\\10_program.ANVL", 13)) == (anvil_check_number((1.0), "examples\\tutorial\\10_program.ANVL", 13))) == 1.0) ? 1.0 : 0.0) != 0.0) {
                    printf("%s", anvil_str_cat(anvil_str_scratch[0], anvil_str_from_number(0, anvil_check_number((anvil_main__index), "examples\\tutorial\\10_program.ANVL", 14)), " is even", "examples\\tutorial\\10_program.ANVL", 14));
                    printf("\n");
                } else {
                    printf("%s", anvil_str_cat(anvil_str_scratch[0], anvil_str_from_number(0, anvil_check_number((anvil_main__index), "examples\\tutorial\\10_program.ANVL", 16)), " is odd", "examples\\tutorial\\10_program.ANVL", 16));
                    printf("\n");
                }
                anvil_main__index = anvil_check_number((anvil_main__index + _anvil_for_step_anvil_main_11), "examples\\tutorial\\10_program.ANVL", 11);
            }
        }
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
