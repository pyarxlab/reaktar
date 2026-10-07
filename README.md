# Reaktar

A lightweight, message-driven actor model for **AUTOSAR Adaptive Platform (`ara::com` / `ara::core`)**.

Part of the **[Pyarx](https://github.com/pyarxlab)** project.

---

## Why Reaktar?

Writing software for AUTOSAR Adaptive usually involves an enormous amount of boilerplate:
- Searching for service handles (`FindService`, `ServiceHandleContainer`).
- Subscribing to proxy events and configuring receive handlers.
- Providing skeleton implementations and managing service offering states (`OfferService`).
- Remembering vendor-specific future types (`ara::core::Future`, `amsr::core::Future`, etc.).
- Coordinating asynchronous RPC calls across different service instances.

In typical codebases, this plumbing dwarfs the actual vehicle logic and makes testing painful.

**Reaktar replaces that ceremony with two concepts: `on` and `emit`.**

Instead of wiring skeletons and proxies manually, your application declares what it reacts to (`on`) and what it produces (`emit`). Reaktar inspects your AUTOSAR ARXML model and handles all the discovery, subscription, dispatching, and lifecycle management behind the scenes.

---

## What It Looks Like

```cpp
#include "generated_framework/vehicle_supervisor_actor.hpp"

class VehicleSupervisorApp : public reaktar::generated::VehicleSupervisorActor<VehicleSupervisorApp> {
public:
    // 1. Inbound Event: React to vehicle speed updates
    void on(const vehicle_data::SpeedData& speed) {
        // Outbound RPC: If speed exceeds 15 km/h, auto-lock doors
        if (speed.speed_kmh > 15.0f && !doors_locked_) {
            if (emit(true).get()) {
                doors_locked_ = true;
            }
        }

        // Outbound Event: Publish an emergency alert if overspeed
        if (speed.speed_kmh > 180.0f) {
            emit(vehicle_data::EmergencyAlert{1001, "Critical overspeed intervention"});
            emit(uint32_t{500}, uint32_t{3}); // FlashLights(500ms, 3 times)
        }
    }

    // 2. Inbound RPC Method: Respond to diagnostic trigger
    bool on(TriggerDiagnostic, uint32_t code) {
        return (code != 0xDEAD);
    }

    // 3. Inbound Field Setter: Validate requested drive mode
    ara::core::Result<vehicle_data::DriveMode> on_set(
        CurrentDriveMode, 
        const vehicle_data::DriveMode& requested_mode) 
    {
        if (doors_locked_ && requested_mode == vehicle_data::DriveMode::SPORT) {
            return ara::core::Result<vehicle_data::DriveMode>::FromValue(requested_mode);
        }
        return ara::core::Result<vehicle_data::DriveMode>::FromValue(vehicle_data::DriveMode::COMFORT);
    }

private:
    bool doors_locked_{false};
};
```

---

## Key Benefits

- **Clear two-verb model**: You only write `on(...)` to handle incoming messages (events, RPC calls, field updates) and `emit(...)` to send outbound messages.
- **Selective subscriptions**: If an application does not implement an `on(...)` handler for a specific event or field, Reaktar never calls `Subscribe()`. No wasted bus traffic or CPU wakeups.
- **Direct ARXML derivation**: Generated code matches your actual ARXML architecture using [pyarx](https://github.com/pyarxlab). No manual interface mapping.
- **Zero lock-in**: Works on standard AUTOSAR Adaptive stacks (Vector DaVinci Adaptive, EB corbos, ETAS RTA-VRTE, Apex.AI, etc.).
- **Turnkey unit testing**: Every generated actor includes a companion test bench that lets you inject events, intercept emitted data, and mock RPC responses without running real daemons or IPC infrastructure.

---

## Quick Start

### 1. Prerequisites & Setup

Reaktar requires C++17 and Python 3.10+ (for generator tooling).

```bash
# Install Python dependencies (pyarxlab, Jinja2)
pip install -r requirements.txt
```

### 2. Generate and Build

```bash
# Generate C++ actors and test benches from your ARXML
make generate

# Build targets
make build

# Run smoke tests
make test

# Package framework and generated headers into a redistributable archive (dist/)
make package
```

---

## Project Structure

```text
arxml/                  # AUTOSAR ARXML system model
include/
  reaktar.hpp           # Master umbrella header
  reaktar/              # Core header-only primitives, proxy slots, traits, and types
  generated_framework/  # Generated Actor bases & Test Benches from ARXML
scripts/
  generate_actor.py     # Code generator (ARXML -> Actor & TestBench)
  templates/            # Jinja2 code generation templates
  package_reactar.py    # Bundler for redistributable framework packages
tests/
  test_smoke.cpp        # Smoke tests for core primitives and generated actors
  mock/                 # Mock AUTOSAR Adaptive environment for testing
```

---

## Packaging

To package only the core Reaktar library and generated headers into a clean redistributable tarball (without tests or mock files):

```bash
make package
# Or with a custom ARXML model:
python3 scripts/package_reactar.py path/to/model.arxml -o dist/
```

---

## License

MIT License. Copyright (c) 2026 Pyarx Lab. See [LICENSE](LICENSE) for details.
