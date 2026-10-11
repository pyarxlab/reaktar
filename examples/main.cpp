// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#include <iostream>

void run_vehicle_supervisor_example();
void run_cockpit_domain_example();
void run_telemetry_example();

int main() {
    std::cout << "=== Reaktar Reference Example Applications ===\n";

    // 1. VehicleSupervisorExample
    run_vehicle_supervisor_example();

    // 2. CockpitDomainExample
    run_cockpit_domain_example();

    // 3. TelemetryExample
    run_telemetry_example();

    std::cout << "=== All Example Applications Completed Successfully ===\n";
    return 0;
}
