/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static char anvil_str_anvil_name[256];
static double anvil_main(void);

static double anvil_main(void) {
    anvil_ask("Your name? ", anvil_str_anvil_name);
    printf("%s", anvil_str_cat(anvil_str_scratch[1], anvil_str_cat(anvil_str_scratch[0], "Hello, ", anvil_str_anvil_name, "examples\\tutorial\\08_input.ANVL", 4), "!", "examples\\tutorial\\08_input.ANVL", 4));
    printf("\n");
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
