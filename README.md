# Reaktar

A lightweight, message-driven actor framework for **AUTOSAR Adaptive Platform (`ara::com` / `ara::core`)**.

Part of the **[Pyarx](https://github.com/pyarxlab)** project.

---

## Why Reaktar?

Writing software for AUTOSAR Adaptive usually involves an enormous amount of boilerplate:
- Searching for service handles (`FindService`, `ServiceHandleContainer`).
- Subscribing to proxy events and configuring receive handlers.
- Providing skeleton implementations and managing service offering states (`OfferService`).
- Remembering vendor-specific future types (`ara::core::Future`, `amsr::core::Future`, etc.).
- Coordinating asynchronous RPC calls across different service instances.
- Managing multi-port topologies and fan-in routing.

In typical codebases, this plumbing dwarfs the actual vehicle logic and makes testing painful.

**Reaktar replaces that ceremony with three declarative primitives: `on`, `emit`, and `read`.**

Instead of wiring skeletons and proxies manually, your application declares what it reacts to (`on`), what it produces (`emit`), and what it queries (`read`). Reaktar inspects your AUTOSAR ARXML model and handles all discovery, subscription, dispatching, thread-safety, and lifecycle management behind the scenes.

---

## What It Looks Like

```cpp
#include "generated_framework/vehicle_supervisor_actor.hpp"

class VehicleSupervisorApp : public reaktar::generated::VehicleSupervisorActor<VehicleSupervisorApp> {
public:
    // 1. Inbound Event: React to vehicle speed updates (supports automatic fan-in across ports)
    void on(const vehicle_data::SpeedData& speed) {
        if (speed.speed_kmh > 15.0f && !doors_locked_) {
            // Outbound RPC: Request door lock via BodyControl proxy port
            if (emit<ports::BodyControl>(true).get()) {
                doors_locked_ = true;
            }
        }

        // Outbound Event: Publish an emergency alert
        if (speed.speed_kmh > 180.0f) {
            emit(vehicle_data::EmergencyAlert{1001, "Critical overspeed intervention"});
        }
    }

    // 2. Inbound RPC Method: Respond to diagnostic trigger
    bool on(TriggerDiagnostic, uint32_t code) {
        return (code != 0xDEAD);
    }

    // 3. Inbound Field Setter: Unified on(...) handler with direct or ara::core::Result return
    vehicle_data::DriveMode on(CurrentDriveMode, const vehicle_data::DriveMode& requested_mode) {
        if (doors_locked_ && requested_mode == vehicle_data::DriveMode::SPORT) {
            return requested_mode;
        }
        return vehicle_data::DriveMode::COMFORT;
    }

    // 4. Inbound Field Notifier: React to consumed proxy field changes
    void on(OutsideAirQuality, uint32_t aqi) {
        current_aqi_ = aqi;
    }

    // 5. Inbound Field Getter Query: Asynchronously read proxy fields
    void check_climate() {
        // Query by Tag, Port, or Type:
        // - By tag:  read<TargetCabinTemperature>()
        // - By port: read<ports::BodyControl>()
        // - By type: read<float>()
        auto target_temp = read<TargetCabinTemperature>();
        if (target_temp.valid() && target_temp.get() > 25.0f) {
            // Adjust cooling or notify supervisor
        }
    }

    // 6. Dynamic Port Lifecycle: Phased control for safe degradation or boot orchestration
    void handle_fault_condition() {
        if (is_ready<ports::Supervisor>()) {
            close_port<ports::Supervisor>(); // Revoke service offering
        }
    }

private:
    bool doors_locked_{false};
    uint32_t current_aqi_{0};
};
```

---

## Core Capabilities

### 1. Three-Verb Reactive Model: `on(...)`, `emit(...)`, and `read(...)`
- **`on(...)` handles all incoming interactions**:
  - Consumed Events: `void on(const EventType&)` or `void on(ports::PortName, const EventType&)`
  - Consumed Field Notifiers: `void on(FieldTag, const ValueType&)` or `void on(ports::PortName, const ValueType&)`
  - Offered RPC Methods: `RetType on(MethodTag, Args...)` or `RetType on(ports::PortName, Args...)`
  - Offered Field Setters: `ValueType on(FieldTag, const ValueType&)` or `ara::core::Result<ValueType> on(...)`
- **`emit(...)` handles all outgoing interactions**:
  - Published Events: `emit(event_data)` or `emit<ports::PortName>(event_data)`
  - Client RPC Invocations: `emit(arg1, arg2)` or `emit<ports::PortName>(arg1, arg2)`
  - Offered Field Updates: `emit(FieldTag, value)` or `emit<ports::PortName>(FieldTag, value)`
- **`read(...)` handles all field getter queries**:
  - Query by Field Tag: `read<TargetCabinTemperature>()` or `read(TargetCabinTemperature{})`
  - Query by Port & Field Tag: `read<ports::BodyControl::TargetCabinTemperature>()` or `read<ports::BodyControl, TargetCabinTemperature>()` or `read(ports::BodyControl{}, TargetCabinTemperature{})`
  - Query by Port: `read<ports::BodyControl>()` (disambiguated automatically when the port has exactly one readable field)
  - Query by Return Type: `read<float>()` (disambiguated automatically when exactly one readable field across all consumed ports returns that type)
  - Compile-Time Safety: Calling `read(...)` on a field without an ARXML getter (`has_getter == false`) or with ambiguous routing results in an immediate, descriptive compile-time `static_assert`.
  - Safe Proxy Leasing: Integrated with RAII `ProxySlot` leases; returns an invalid `AsyncResult` if the proxy is unavailable or disconnected.

### 2. Multi-Port Routing, Disambiguation & Fan-In
- **Automatic Fan-In**: When multiple required ports supply the same event or field notifier type, a single `on(const Payload&)` handler automatically fans in across all of them without boilerplate.
- **Port Tag Specificity**: If explicit routing is needed, tag your handler with `ports::PortName` (e.g., `void on(ports::RadarFront, const Detection&)`).
- **Compile-Time Safety**: Ambiguous calls across multiple ports are caught at compile time with clear `static_assert` messages.

### 3. Dynamic Port Lifecycle Control
- Manage ports individually at runtime directly from actor methods:
  - `open_port<ports::PortName>()`: Open proxy resolution or offer skeleton service.
  - `close_port<ports::PortName>()`: Suspend proxy subscriptions or revoke service offering.
  - `is_ready<ports::PortName>()`: Non-blocking check of port availability.
  - `wait_until_ready()`: Synchronous/asynchronous barrier for actor readiness.

### 4. Pluggable Execution Policies
Actors can specify their dispatch execution policy:
- `reaktar::DirectExecution`: Zero-overhead, synchronous direct dispatch in the caller/callback thread.
- `reaktar::QueuedExecution`: Asynchronous message queue with thread-safe actor mailbox processing.
- `reaktar::ThreadPerServiceExecution`: Dedicated worker thread per AUTOSAR service port.

### 5. Selective Subscriptions
If an actor does not define an `on(...)` handler for a specific event or field notifier, Reaktar never calls `Subscribe()`. No wasted bus traffic, serialization overhead, or CPU wakeups.

### 6. Turnkey Offline Unit Testing (`<Actor>TestBench`)
Every generated actor comes with a companion test bench for 100% deterministic, offline testing without running daemons, brokers, or IPC stacks:
- `inject_event(...)`: Simulate incoming proxy events.
- `inject_field_notify(...)`: Simulate proxy field value notifications.
- `set_field<Tag>(value)` / `set_field<PortTag, Tag>(value)`: Set mock skeleton field values for proxy `read(...)` queries and getters.
- `intercept_emit(...)`: Verify outbound events and RPC requests.
- `mock_rpc_response(...)`: Mock client RPC responses.
- `InvokeGet()` / `InvokeSet()`: Directly test skeleton field getters and setters.

### 7. Zero-Copy JSON Telemetry & Serialization
Built-in lightweight JSON support (`reaktar/json.hpp`) allows effortless telemetry serialization, state inspection, and debugging of AUTOSAR structures.

---

## Quick Start

### 1. Prerequisites & Setup

Reaktar requires **C++17** and **Python 3.10+** (for code generation).

```bash
# Verify Python version and install dependencies
make bootstrap
```

### 2. Generate and Build

```bash
# Generate C++ actors and test benches from your ARXML model
make generate

# Build targets in Release mode
make build

# Run test suites via CTest
make test

# Package core framework and generated headers into a redistributable archive (dist/)
make package
```

---

## Project Structure

```text
arxml/                  # AUTOSAR ARXML system model
include/
  reaktar.hpp           # Master umbrella header
  reaktar/
    actor_base.hpp      # Base actor class and CRTP lifecycle hooks
    config.hpp          # Compile-time switches and platform feature flags
    execution_policy.hpp# DirectExecution, QueuedExecution, ThreadPerServiceExecution
    json.hpp            # Lightweight JSON serialization & telemetry
    port.hpp            # PortDirection and port routing tags
    proxy_slot.hpp      # Safe proxy lifecycle, states, and reconnection management
    tags.hpp            # Static compile-time method and field identifier tags
    thread_safety.hpp   # Clang -Wthread-safety annotations & locking primitives
    traits.hpp          # SFINAE and C++17 type inspection traits
    vendor.hpp          # Vendor SDK type mappings (Future, Result, Promise, ErrorCode)
  generated_framework/  # Generated Actor bases & Test Benches from ARXML
scripts/
  generate_actor.py     # Code generator (ARXML -> Actor & TestBench)
  templates/            # Jinja2 code generation templates
    actor/
      actor_base.jinja
      inbound_read.jinja
      outbound_emit.jinja
      proxy_wiring.jinja
      skeleton_adapter.jinja
  package_reaktar.py    # Bundler for redistributable framework packages
tests/
  test_smoke.cpp        # Smoke tests for core primitives and generated actors
  mock/                 # Mock AUTOSAR Adaptive environment (ara::com / ara::core)
```

---

## Packaging

To package only the core Reaktar library and generated headers into a clean redistributable tarball (without tests or mock files):

```bash
make package

# Or specify a custom ARXML model and output directory:
python3 scripts/package_reaktar.py path/to/model.arxml -o dist/
```

---

## License

MIT License. Copyright (c) 2026 Pyarx Lab. See [LICENSE](LICENSE) for details.

### Trademarks & Disclaimers

All product names, trademarks, and registered trademarks mentioned in this repository are the property of their respective owners. Company, product, and service names are used solely for identification and compatibility purposes, and do not imply any affiliation or endorsement.
