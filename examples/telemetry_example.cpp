// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#include "generated_framework/telemetry_example.hpp"

void run_telemetry_example() {
    reaktar::TelemetryExample telemetry_app;
    telemetry_app.demonstrate_all_emits();
}
