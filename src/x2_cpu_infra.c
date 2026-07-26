#include "common_cpu_infra.h"
#include "x2_rtl.h"

/* .title drives coverage-artifact naming (tier2_<title>_*.json) — keep it
 * unique per ROM so sibling Mega Man X ports never collide. */
const RtlGameInfo kX2GameInfo = {
  .title = "x2",
  .initialize = NULL,
  .run_frame = &RunOneFrameOfGame,
  .draw_ppu_frame = &X2DrawPpuFrame,
  .save_name_prefix = "save",
  .state_save_extra = &X2StateSaveExtra,
  .state_load_extra = &X2StateLoadExtra,
  .on_state_loaded = &X2OnStateLoaded,
};
