cmake_minimum_required(VERSION 3.20)
project(MegaManX2SNESRecomp C CXX)
set(CMAKE_C_STANDARD 11)

file(READ "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" _version)
string(STRIP "${_version}" GAME_RELEASE_VERSION)
set(SNESRECOMP_BUILD_VERSION "" CACHE STRING "Build stamp (empty: Release uses VERSION, otherwise dev)")
if(SNESRECOMP_BUILD_VERSION STREQUAL "")
    set(SNESRECOMP_BUILD_VERSION "$<IF:$<CONFIG:Release>,${GAME_RELEASE_VERSION},dev>")
endif()
set(SNESRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/snesrecomp" CACHE PATH "snesrecomp checkout")
set(RECOMP_UI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/recomp-ui" CACHE PATH "recomp-ui checkout")
set(SNESRECOMP_ENABLE_MODS ON CACHE BOOL "Shared mod package runtime" FORCE)
include(${SNESRECOMP_ROOT}/runner/runner.cmake)

add_executable(MegaManX2SNESRecomp
    ${SNESRECOMP_RUNNER_SOURCES}
    src/main.c src/gen_stubs.c src/x2_display.c src/x2_cpu_infra.c
    src/x2_rtl.c src/x2_spc_player.c src/mods/x2_widescreen_plugin.c)
target_include_directories(MegaManX2SNESRecomp PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/recomp ${SNESRECOMP_RUNNER_INCLUDE_DIRS})
target_compile_definitions(MegaManX2SNESRecomp PRIVATE
    SMW_DISABLE_LM=1 SYSTEM_VOLUME_MIXER_AVAILABLE=0
    SNESRECOMP_TRACE=$<BOOL:${SNESRECOMP_ENABLE_TRACE}> SNESRECOMP_REVERSE_DEBUG=0)
set_property(SOURCE src/main.c APPEND PROPERTY COMPILE_DEFINITIONS
    SNESRECOMP_BUILD_VERSION="${SNESRECOMP_BUILD_VERSION}")
if(NOT MSVC)
    target_compile_options(MegaManX2SNESRecomp PRIVATE
        $<$<COMPILE_LANGUAGE:C>:-Wno-implicit-function-declaration>)
endif()
target_link_libraries(MegaManX2SNESRecomp PRIVATE ${SNESRECOMP_RUNNER_LIBRARIES})
snesrecomp_target_sdl(MegaManX2SNESRecomp)
snesrecomp_target_fiber_compat(MegaManX2SNESRecomp)
snesrecomp_target_desktop_host(MegaManX2SNESRecomp TIER2)
snesrecomp_target_generated_code(MegaManX2SNESRecomp ${CMAKE_CURRENT_SOURCE_DIR}/src/gen)
snesrecomp_target_mod_catalog(MegaManX2SNESRecomp ${CMAKE_CURRENT_SOURCE_DIR}/mods/preloaded)

include(${RECOMP_UI_ROOT}/recomp_ui.cmake)
recomp_target_launcher_ui(MegaManX2SNESRecomp CONSOLE snes
    BOXART ${CMAKE_CURRENT_SOURCE_DIR}/recomp/launcher/boxart.tga)

include(${SNESRECOMP_ROOT}/runner/cmake/mmx_state_tests.cmake)
snesrecomp_target_mmx_state_tests(MegaManX2SNESRecomp ${CMAKE_CURRENT_SOURCE_DIR}/src/main.c)
