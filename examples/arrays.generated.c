/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>

static double anvil_scores[4];
static double anvil_main(void);

static double anvil_main(void) {
    double anvil_main__index = 0.0;
    {
        const double _anvil_for_start_anvil_main_4 = 0.0;
        const double _anvil_for_end_anvil_main_4 = 3.0;
        const double _anvil_for_step_anvil_main_4 = 1.0;
        anvil_main__index = _anvil_for_start_anvil_main_4;
        if (_anvil_for_step_anvil_main_4 != 0.0) {
            for (; ((_anvil_for_step_anvil_main_4 > 0.0 && anvil_main__index <= _anvil_for_end_anvil_main_4) || (_anvil_for_step_anvil_main_4 < 0.0 && anvil_main__index >= _anvil_for_end_anvil_main_4)); anvil_main__index += _anvil_for_step_anvil_main_4) {
                {
                    const double _anvil_array_index_anvil_main_5 = anvil_main__index;
                    const double _anvil_array_value_anvil_main_5 = (anvil_main__index * 10.0);
                    anvil_array_set(anvil_scores, 4, _anvil_array_index_anvil_main_5, _anvil_array_value_anvil_main_5, "examples\\arrays.ANVL", 5);
                }
            }
        }
    }
    return (anvil_array_get(anvil_scores, 4, 2.0, "examples\\arrays.ANVL", 7) + anvil_array_get(anvil_scores, 4, 3.0, "examples\\arrays.ANVL", 7));
}

int main(void) {
    anvil_set_fixed_hz(60);
    printf("%.15g\n", anvil_main());
    anvil_net_close();
    return 0;
}
