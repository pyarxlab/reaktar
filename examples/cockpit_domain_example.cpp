// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#include "generated_framework/cockpit_domain_example.hpp"

void run_cockpit_domain_example() {
    reaktar::CockpitDomainExample cockpit_app;
    cockpit_app.demonstrate_all_emits();
}
