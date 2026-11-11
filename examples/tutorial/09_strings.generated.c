/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static char anvil_str_anvil_word[256];
static double anvil_main(void);

static double anvil_main(void) {
    anvil_str_set(anvil_str_anvil_word, "  Beginner  ", "examples\\tutorial\\09_strings.ANVL", 3);
    printf("%s", anvil_str_cat(anvil_str_scratch[1], anvil_str_cat(anvil_str_scratch[0], "[", anvil_text_trim ( anvil_str_anvil_word ), "examples\\tutorial\\09_strings.ANVL", 4), "]", "examples\\tutorial\\09_strings.ANVL", 4));
    printf("\n");
    printf("%s", anvil_text_left ( "Anvil", 3.0 ));
    printf("\n");
    printf("%s", anvil_text_right ( "Anvil", 3.0 ));
    printf("\n");
    printf("%s", anvil_text_mid ( "Anvil", 2.0, 2.0 ));
    printf("\n");
    printf("%s", anvil_text_char ( "Anvil", 0.0 ));
    printf("\n");
    printf("%.15g", anvil_check_number(((anvil_check_number((anvil_check_number((anvil_text_to_number ( "42" )), "examples\\tutorial\\09_strings.ANVL", 9)), "examples\\tutorial\\09_strings.ANVL", 9) + anvil_check_number((8.0), "examples\\tutorial\\09_strings.ANVL", 9))), "examples\\tutorial\\09_strings.ANVL", 9));
    printf("\n");
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    (void)anvil_main();
    anvil_net_close();
    return 0;
}
