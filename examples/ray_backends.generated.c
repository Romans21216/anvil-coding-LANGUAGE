/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static double anvil_bvh_selected;
static double anvil_dxr_available;
static double anvil_embree_available;
static double anvil_main(void);

static double anvil_main(void) {
    return ((anvil_bvh_selected + anvil_dxr_available) + anvil_embree_available);
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_bvh_selected = anvil_ray_backend ( "bvh" );
    anvil_dxr_available = anvil_ray_backend_available ( "dxr" );
    anvil_embree_available = anvil_ray_backend_available ( "embree" );
    printf("%.15g\n", anvil_main());
    anvil_net_close();
    return 0;
}
