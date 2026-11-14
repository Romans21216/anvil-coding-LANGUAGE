/* Generated from Anvil source. The .ANVL source remains the program. */
/* builtins used: ray_backend, ray_backend_available */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static double anvil_bvh_selected;
static double anvil_dxr_available;
static double anvil_embree_available;
static double anvil_main(void);

static double anvil_main(void) {
    return anvil_check_number(((anvil_check_number((anvil_check_number(((anvil_check_number((anvil_bvh_selected), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 7) + anvil_check_number((anvil_dxr_available), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 7))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 7)), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 7) + anvil_check_number((anvil_embree_available), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 7))), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 7);
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_bvh_selected = anvil_check_number((anvil_ray_backend ( "bvh" )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 2);
    anvil_dxr_available = anvil_check_number((anvil_ray_backend_available ( "dxr" )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 3);
    anvil_embree_available = anvil_check_number((anvil_ray_backend_available ( "embree" )), "C:\\Users\\power\\Documents\\buld\\os\\toolchain\\anvil\\examples\\ray_backends.ANVL", 4);
    printf("%s\n", anvil_format_number(anvil_main()));
    anvil_net_close();
    return 0;
}
