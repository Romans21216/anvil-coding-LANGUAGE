/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_n;
static double anvil_main(void);

static double anvil_main(void) {
    double anvil_main__index = 0.0;
    double anvil_main__repeat3 = 0.0;
    {
        const double _anvil_for_start_anvil_main_3 = 1.0;
        const double _anvil_for_end_anvil_main_3 = 3.0;
        const double _anvil_for_step_anvil_main_3 = 1.0;
        anvil_main__repeat3 = _anvil_for_start_anvil_main_3;
        if (_anvil_for_step_anvil_main_3 != 0.0) {
            while (((_anvil_for_step_anvil_main_3 > 0.0 && anvil_main__repeat3 <= _anvil_for_end_anvil_main_3) || (_anvil_for_step_anvil_main_3 < 0.0 && anvil_main__repeat3 >= _anvil_for_end_anvil_main_3))) {
                printf("%s", "hip");
                printf("\n");
                anvil_main__repeat3 = anvil_check_number((anvil_main__repeat3 + _anvil_for_step_anvil_main_3), "examples\\tutorial\\05_loops.ANVL", 3);
            }
        }
    }
    {
        const double _anvil_for_start_anvil_main_6 = 1.0;
        const double _anvil_for_end_anvil_main_6 = 3.0;
        const double _anvil_for_step_anvil_main_6 = 1.0;
        anvil_main__index = _anvil_for_start_anvil_main_6;
        if (_anvil_for_step_anvil_main_6 != 0.0) {
            while (((_anvil_for_step_anvil_main_6 > 0.0 && anvil_main__index <= _anvil_for_end_anvil_main_6) || (_anvil_for_step_anvil_main_6 < 0.0 && anvil_main__index >= _anvil_for_end_anvil_main_6))) {
                printf("%s", anvil_str_cat(anvil_str_scratch[0], "count ", anvil_str_from_number(1, anvil_check_number((anvil_main__index), "examples\\tutorial\\05_loops.ANVL", 7)), "examples\\tutorial\\05_loops.ANVL", 7));
                printf("\n");
                anvil_main__index = anvil_check_number((anvil_main__index + _anvil_for_step_anvil_main_6), "examples\\tutorial\\05_loops.ANVL", 6);
            }
        }
    }
    anvil_n = 3.0;
    while ((((double)((anvil_check_number((anvil_n), "examples\\tutorial\\05_loops.ANVL", 10)) > (anvil_check_number((0.0), "examples\\tutorial\\05_loops.ANVL", 10))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        printf("%.15g", anvil_n);
        printf("\n");
        anvil_n = anvil_check_number((anvil_n + (-1.0)), "examples\\tutorial\\05_loops.ANVL", 12);
    }
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
