#ifndef X2_RTL_H_
#define X2_RTL_H_

#include "common_rtl.h"
#include "common_cpu_infra.h"

struct SaveLoadInfo;

/* Whole-program LLE bring-up driver. See x2_rtl.c. */
void RunOneFrameOfGame(void);
void X2DrawPpuFrame(void);

/* Per-frame 16:9 HUD anchoring. Measured slot map in
 * docs/OAM_SURVEY.md; inert unless widescreen is active AND the
 * health bar signature is present in OAM. */
void X2ConfigureWsHud(void);

/* Per-frame 16:9 BG margin fill: recomputes exact tilemap entries for the
 * widescreen gutters from the game's own layout/screen/metatile structures
 * (decoded from $00:B449; see x2_rtl.c). Self-validating against the live
 * native view; falls back to the authentic map wrap when it cannot prove
 * the scene. Kill-switch: SNESRECOMP_WS_BG_MARGINS=0. */
void X2ConfigureWsBgMargins(void);

/* LLE host execution cursor (resume PC + CpuState) — not covered by
 * snes_saveload, which snapshots the unused snes->cpu. */
void X2StateSaveExtra(struct SaveLoadInfo *sli);
void X2StateLoadExtra(struct SaveLoadInfo *sli, uint32_t version);
void X2OnStateLoaded(uint32_t version);

#endif  /* X2_RTL_H_ */
