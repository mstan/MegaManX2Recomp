/* Mega Man X2 identity/adaptation layer for the shared X2/X3 desktop host. */
#define MMX_RTL_HEADER "x2_rtl.h"
#define MMX_DISPLAY_HEADER "x2_display.h"
#define MMX_SPC_HEADER "x2_spc_player.h"

#define MMX_WINDOW_TITLE "Mega Man X2 (Recompiled)"
#define MMX_GAME_NAME "Mega Man X2"
#define MMX_GAME_REGION "(USA)"
#define MMX_LAUNCHER_TITLE "Mega Man X2 \xE2\x80\x94 Launcher"
#define MMX_ROM_CRC32 0x947B0355u
#define MMX_ROM_SHA256_BYTES \
  0xf3,0x24,0x67,0x55,0xf6,0x08,0xa1,0xe1, \
  0xdc,0x9c,0x84,0x8b,0x61,0xda,0x3b,0x82, \
  0x4c,0x78,0x53,0xb2,0x9b,0x3b,0xe4,0x0d, \
  0xf6,0xfc,0x7f,0x27,0x93,0xa8,0x87,0xed
#define MMX_ROM_SHA256_HEX \
  "f3246755f608a1e1dc9c848b61da3b824c7853b29b3be40df6fc7f2793a887ed"
#define MMX_MOD_GAME_ID "megaman-x2-us"
#define MMX_DEBUG_PORT 4383
#define MMX_HAS_BG3_SUB_OVERLAY 1
#define MMX_WIDESCREEN_STATUS_LINES \
  "# is native 4:3. The built-in Mods package owns normal activation;\n" \
  "# broad stage-by-stage widescreen validation is still in progress.\n" \
  "# See docs/WIDESCREEN.md for surveyed systems and remaining work.\n"

#define MmxDisplayViewport X2DisplayViewport
#define MmxDisplay_ComputeFrameWidth X2Display_ComputeFrameWidth
#define MmxDisplay_ComputeViewport X2Display_ComputeViewport
#define MmxDisplay_GetWindowBaseWidth X2Display_GetWindowBaseWidth
#define MmxDisplay_GetWindowBaseHeight X2Display_GetWindowBaseHeight
#define MmxDisplay_SetWidescreenEnabled X2Display_SetWidescreenEnabled
#define MmxDisplay_IsWidescreenEnabled X2Display_IsWidescreenEnabled
#define MmxDisplay_IsWidescreenActive X2Display_IsWidescreenActive
#define MmxDisplay_GetCurrentFrameWidth X2Display_GetCurrentFrameWidth
#define MmxConfigureWsHud X2ConfigureWsHud
#define MmxConfigureWsBgMargins X2ConfigureWsBgMargins
#define kMmxGameInfo kX2GameInfo

#include "desktop/mmx23_host_main.inc"
