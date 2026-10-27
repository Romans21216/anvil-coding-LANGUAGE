/* Generated from Anvil source. The .ANVL source remains the program. */
#include "anvil_runtime.h"
#include <math.h>
#include <stdio.h>

static double anvil_local_count;
static double anvil_peer_count;
static double anvil_update(void);
static double anvil_draw(void);

static double anvil_update(void) {
    if (anvil_pressed ( ANVIL_KEY_SPACE ) != 0.0) {
        anvil_local_count += 1.0;
    }
    anvil_net_send(anvil_local_count);
    anvil_peer_count = anvil_net_receive ( );
    return 0.0;
}

static double anvil_draw(void) {
    anvil_trace_finish();
    anvil_text(24.0, 24.0, "Anvil LAN client", 235.0, 241.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text_number(24.0, 60.0, "Local count: %.0f", anvil_local_count, 100.0, 190.0, 255.0, 255);
    anvil_trace_finish();
    anvil_text_number(24.0, 96.0, "Host count: %.0f", anvil_peer_count, 255.0, 175.0, 110.0, 255);
    return 0.0;
}

int main(void) {
    anvil_set_fixed_hz(60);
    anvil_set_scene3d(0);
    anvil_clear(13.0, 19.0, 31.0, 255.0);
    (void)anvil_net_join("127.0.0.1", 7777);
    anvil_local_count = 0.0;
    anvil_peer_count = 0.0;
    anvil_run(anvil_update, anvil_draw, "Anvil Game");
    anvil_net_close();
    return 0;
}

