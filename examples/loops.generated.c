/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_sum_range(double anvil_sum_range__first, double anvil_sum_range__last, double anvil_sum_range__step);
static double anvil_sum_to(double anvil_sum_to__limit);
static double anvil_main(void);

static double anvil_sum_range(double anvil_sum_range__first, double anvil_sum_range__last, double anvil_sum_range__step) {
    double anvil_sum_range__index = 0.0;
    double anvil_sum_range__total = 0.0;
    anvil_sum_range__total = 0.0;
    {
        const double _anvil_for_start_anvil_sum_range_4 = anvil_sum_range__first;
        const double _anvil_for_end_anvil_sum_range_4 = anvil_sum_range__last;
        const double _anvil_for_step_anvil_sum_range_4 = anvil_sum_range__step;
        anvil_sum_range__index = _anvil_for_start_anvil_sum_range_4;
        if (_anvil_for_step_anvil_sum_range_4 != 0.0) {
            while (((_anvil_for_step_anvil_sum_range_4 > 0.0 && anvil_sum_range__index <= _anvil_for_end_anvil_sum_range_4) || (_anvil_for_step_anvil_sum_range_4 < 0.0 && anvil_sum_range__index >= _anvil_for_end_anvil_sum_range_4))) {
                anvil_sum_range__total = anvil_check_number((anvil_sum_range__total + anvil_sum_range__index), "examples\\loops.ANVL", 5);
                anvil_sum_range__index = anvil_check_number((anvil_sum_range__index + _anvil_for_step_anvil_sum_range_4), "examples\\loops.ANVL", 4);
            }
        }
    }
    return anvil_sum_range__total;
}

static double anvil_sum_to(double anvil_sum_to__limit) {
    double anvil_sum_to__index = 0.0;
    double anvil_sum_to__total = 0.0;
    anvil_sum_to__index = 1.0;
    anvil_sum_to__total = 0.0;
    while ((((double)((anvil_check_number((anvil_sum_to__index), "examples\\loops.ANVL", 14)) <= (anvil_check_number((anvil_sum_to__limit), "examples\\loops.ANVL", 14))) == 1.0) ? 1.0 : 0.0) != 0.0) {
        anvil_sum_to__total = anvil_check_number((anvil_sum_to__total + anvil_sum_to__index), "examples\\loops.ANVL", 15);
        anvil_sum_to__index = anvil_check_number((anvil_sum_to__index + 1.0), "examples\\loops.ANVL", 16);
    }
    return anvil_sum_to__total;
}

static double anvil_main(void) {
    return anvil_sum_range(1.0, 5.0, 1.0);
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%s\n", anvil_format_number(anvil_main()));
    anvil_net_close();
    return 0;
}
