/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_total;
static double anvil_scores[3];
static double anvil_main(void);

static double anvil_main(void) {
    double anvil_main__index = 0.0;
    {
        const double _anvil_array_index_anvil_main_5 = 0.0;
        const double _anvil_array_value_anvil_main_5 = 10.0;
        anvil_array_set(anvil_scores, 3, _anvil_array_index_anvil_main_5, _anvil_array_value_anvil_main_5, "examples\\tutorial\\07_arrays.ANVL", 5);
    }
    {
        const double _anvil_array_index_anvil_main_6 = 1.0;
        const double _anvil_array_value_anvil_main_6 = 20.0;
        anvil_array_set(anvil_scores, 3, _anvil_array_index_anvil_main_6, _anvil_array_value_anvil_main_6, "examples\\tutorial\\07_arrays.ANVL", 6);
    }
    {
        const double _anvil_array_index_anvil_main_7 = 2.0;
        const double _anvil_array_value_anvil_main_7 = 30.0;
        anvil_array_set(anvil_scores, 3, _anvil_array_index_anvil_main_7, _anvil_array_value_anvil_main_7, "examples\\tutorial\\07_arrays.ANVL", 7);
    }
    anvil_total = 0.0;
    {
        const double _anvil_for_start_anvil_main_9 = 0.0;
        const double _anvil_for_end_anvil_main_9 = 2.0;
        const double _anvil_for_step_anvil_main_9 = 1.0;
        anvil_main__index = _anvil_for_start_anvil_main_9;
        if (_anvil_for_step_anvil_main_9 != 0.0) {
            while (((_anvil_for_step_anvil_main_9 > 0.0 && anvil_main__index <= _anvil_for_end_anvil_main_9) || (_anvil_for_step_anvil_main_9 < 0.0 && anvil_main__index >= _anvil_for_end_anvil_main_9))) {
                anvil_total = anvil_check_number((anvil_total + anvil_array_get(anvil_scores, 3, anvil_main__index, "examples\\tutorial\\07_arrays.ANVL", 10)), "examples\\tutorial\\07_arrays.ANVL", 10);
                anvil_main__index = anvil_check_number((anvil_main__index + _anvil_for_step_anvil_main_9), "examples\\tutorial\\07_arrays.ANVL", 9);
            }
        }
    }
    printf("%s", anvil_str_cat(anvil_str_scratch[0], "Total: ", anvil_str_from_number(1, anvil_check_number((anvil_total), "examples\\tutorial\\07_arrays.ANVL", 12)), "examples\\tutorial\\07_arrays.ANVL", 12));
    printf("\n");
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
