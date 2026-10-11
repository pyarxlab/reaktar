// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#include "generated_framework/multi_port_radar_example.hpp"

void run_multi_port_radar_example() {
    reaktar::MultiPortRadarExample radar_app;
    radar_app.demonstrate_all_emits();
}
