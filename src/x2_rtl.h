#ifndef X2_RTL_H_
#define X2_RTL_H_

#include "common_rtl.h"
#include "common_cpu_infra.h"

struct SaveLoadInfo;

/* Whole-program LLE bring-up driver. See x2_rtl.c. */
void RunOneFrameOfGame(void);
void X2DrawPpuFrame(void);

/* LLE host execution cursor (resume PC + CpuState) — not covered by
 * snes_saveload, which snapshots the unused snes->cpu. */
void X2StateSaveExtra(struct SaveLoadInfo *sli);
void X2StateLoadExtra(struct SaveLoadInfo *sli, uint32_t version);
void X2OnStateLoaded(uint32_t version);

#endif  /* X2_RTL_H_ */
