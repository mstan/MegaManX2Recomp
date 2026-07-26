#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Host-only display controls. These never modify emulated SNES state. */
void X2Display_SetWidescreenEnabled(bool enabled);
bool X2Display_IsWidescreenEnabled(void);
bool X2Display_IsWidescreenActive(void);
int X2Display_GetCurrentFrameWidth(void);

typedef struct X2DisplayViewport {
  int x, y, width, height;
} X2DisplayViewport;

/* Pure geometry: SNES active pixels have a 7:6 horizontal pixel aspect. */
int X2Display_ComputeFrameWidth(int drawable_width, int drawable_height,
                                 bool widescreen);
void X2Display_ComputePresentationSize(int frame_width, int frame_height,
                                        int *width, int *height);
void X2Display_ComputeViewport(int source_width, int source_height,
                                int drawable_width, int drawable_height,
                                bool ignore_aspect, bool integer_scale,
                                X2DisplayViewport *viewport);
int X2Display_GetWindowBaseWidth(int frame_width);
int X2Display_GetWindowBaseHeight(void);

/* Reattach a streamed PPU tilemap's 8-bit phase to MMX's full world camera. */
int X2Display_ExpandStageScroll(uint16_t camera, uint16_t ppu_scroll);

#ifdef __cplusplus
}
#endif
