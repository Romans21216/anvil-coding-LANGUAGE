/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>

static double anvil_sum_offset(double anvil_sum_offset__offset);
static double anvil_main(void);

static double anvil_sum_offset(double anvil_sum_offset__offset) {
    double anvil_sum_offset__index = 0.0;
    double anvil_sum_offset__values[3] = {0};
    {
        const double _anvil_for_start_anvil_sum_offset_3 = 0.0;
        const double _anvil_for_end_anvil_sum_offset_3 = 2.0;
        const double _anvil_for_step_anvil_sum_offset_3 = 1.0;
        anvil_sum_offset__index = _anvil_for_start_anvil_sum_offset_3;
        if (_anvil_for_step_anvil_sum_offset_3 != 0.0) {
            for (; ((_anvil_for_step_anvil_sum_offset_3 > 0.0 && anvil_sum_offset__index <= _anvil_for_end_anvil_sum_offset_3) || (_anvil_for_step_anvil_sum_offset_3 < 0.0 && anvil_sum_offset__index >= _anvil_for_end_anvil_sum_offset_3)); anvil_sum_offset__index += _anvil_for_step_anvil_sum_offset_3) {
                {
                    const double _anvil_array_index_anvil_sum_offset_4 = anvil_sum_offset__index;
                    const double _anvil_array_value_anvil_sum_offset_4 = (anvil_sum_offset__offset + anvil_sum_offset__index);
                    anvil_array_set(anvil_sum_offset__values, 3, _anvil_array_index_anvil_sum_offset_4, _anvil_array_value_anvil_sum_offset_4, "examples\\local_arrays.ANVL", 4);
                }
            }
        }
    }
    return ((anvil_array_get(anvil_sum_offset__values, 3, 0.0, "examples\\local_arrays.ANVL", 6) + anvil_array_get(anvil_sum_offset__values, 3, 1.0, "examples\\local_arrays.ANVL", 6)) + anvil_array_get(anvil_sum_offset__values, 3, 2.0, "examples\\local_arrays.ANVL", 6));
}

static double anvil_main(void) {
    return (anvil_sum_offset(2.0) + anvil_sum_offset(5.0));
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%.15g\n", anvil_main());
    anvil_net_close();
    return 0;
}
