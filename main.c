#include <hal/video.h>
#include <hal/xbox.h>
#include <pbkit/pbkit.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <xboxkrnl/xboxkrnl.h>
#include <xboxrt/debug.h>

#include "net.h"
#include "dbgd.h"

/* Main program function */
void main(void)
{
    XVideoSetMode(640, 480, 32, REFRESH_DEFAULT);

    debugPrint("nxdk-rdt\n");

    //FIXME: Set up GPU
    //FIXME: pb_init
    pb_show_debug_screen();

    // Set up networking
    net_init();
    dbgd_init();

    while(1) {
        NtYieldExecution();
    }

    pb_kill();
}
