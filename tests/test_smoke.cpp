// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// Smoke Test Suite: Core Primitives & Application Deriving from Generated Actor
// ==============================================================================

#include <iostream>
#include <thread>
#include <chrono>
#include <atomic>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>

#include "mock_ara/com.hpp"
#include "reaktar.hpp"
#include "generated_framework/telemetry_actor.hpp"
#include "generated_framework/telemetry_test_bench.hpp"
#include "generated_framework/vehicle_supervisor_actor.hpp"
#include "generated_framework/vehicle_supervisor_test_bench.hpp"

// -----------------------------------------------------------------------------
// Compile-time trait verification probe
// -----------------------------------------------------------------------------
struct SampleEvent {
    int id;
};

struct SampleTag {};

class TestActor {
public:
    bool event_received{false};

    void on(const SampleEvent& ev) {
        if (ev.id == 42) {
            event_received = true;
        }
    }

    void on(SampleTag, int val) {
        (void)val;
    }
};

// -----------------------------------------------------------------------------
// Applications deriving directly from code-generated actors
// -----------------------------------------------------------------------------
class TelemetrySmokeApp : public reaktar::generated::TelemetryActor<TelemetrySmokeApp> {
public:
    void send_alert(uint16_t code, const std::string& msg) {
        emit(vehicle_data::EmergencyAlert{code, msg});
    }
};

class SupervisorSmokeApp : public reaktar::generated::VehicleSupervisorActor<SupervisorSmokeApp> {
public:
    bool speed_received{false};
    bool alert_emitted{false};

    // Consumed event handler
    void on(const vehicle_data::SpeedData& speed) {
        speed_received = true;
        if (speed.speed_kmh > 15.0f) {
            emit(true); // Emits LockDoors RPC to BodyControl proxy
        }
        if (speed.speed_kmh > 180.0f) {
            emit(vehicle_data::EmergencyAlert{1001, "Overspeed safety trigger"});
            alert_emitted = true;
        }
    }

    // Method handler with bare tag TriggerDiagnostic
    bool on(TriggerDiagnostic, uint32_t code) {
        return (code != 0xDEAD);
    }
};

// -----------------------------------------------------------------------------
// Main Test Runner
// -----------------------------------------------------------------------------
int main() {
    std::cout << "[Smoke Test] Verifying ReaktAR core primitives & generated actor app...\n";

    // 1. EmitStatus verification
    std::cout << "  - Verifying EmitStatus... ";
    static_assert(sizeof(reaktar::EmitStatus) == 1, "EmitStatus must be 1 byte!");
    reaktar::EmitStatus success{true};
    assert(success);
    assert(success.ok());

    reaktar::EmitStatus failure{false};
    assert(!failure);
    assert(!failure.ok());

    bool or_else_called = false;
    failure.or_else([&]() {
        or_else_called = true;
    });
    assert(or_else_called);
    std::cout << "PASSED\n";

    // 2. ReadinessTracker<0> (Zero-overhead specialization)
    std::cout << "  - Verifying ReadinessTracker<0>... ";
    reaktar::ReadinessTracker<0> tracker0;
    static_assert(sizeof(tracker0) == 1, "ReadinessTracker<0> must have empty-class size (1 byte)!");
    assert(tracker0.is_ready([]() { return false; }) == true);
    assert(tracker0.wait_until_ready([]() { return false; }) == true);
    assert(tracker0.wait_until_ready([]() { return false; }, std::chrono::milliseconds(10)) == true);
    tracker0.notify_resolved();
    std::cout << "PASSED\n";

    // 3. ReadinessTracker<1> (Synchronization)
    std::cout << "  - Verifying ReadinessTracker<1>... ";
    reaktar::ReadinessTracker<1> tracker1;
    std::atomic<bool> service_ready{false};

    assert(!tracker1.is_ready([&]() { return service_ready.load(); }));

    std::thread resolver([&]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        service_ready.store(true);
        tracker1.notify_resolved();
    });

    bool wait_res = tracker1.wait_until_ready([&]() { return service_ready.load(); }, std::chrono::milliseconds(500));
    assert(wait_res);
    assert(tracker1.is_ready([&]() { return service_ready.load(); }));
    resolver.join();
    std::cout << "PASSED\n";

    // 4. Compile-time trait detection
    std::cout << "  - Verifying compile-time traits... ";
    static_assert(reaktar::has_on_direct_event_v<TestActor, SampleEvent>, "has_on_direct_event_v must detect on(SampleEvent)");
    static_assert(!reaktar::has_on_direct_event_v<TestActor, double>, "has_on_direct_event_v must reject unhandled types");
    static_assert(reaktar::has_on_event_v<TestActor, SampleTag, int>, "has_on_event_v must detect on(SampleTag, int)");
    std::cout << "PASSED\n";

    // 5. ProxySlot basic lifecycle
    std::cout << "  - Verifying ProxySlot basic lifecycle... ";
    struct MockService {
        int ping() { return 123; }
    };
    reaktar::ProxySlot<MockService> slot;
    assert(!slot.is_available());
    auto empty_lease = slot.acquire();
    assert(!empty_lease);

    slot.publish(std::make_unique<MockService>());
    assert(slot.is_available());
    auto active_lease = slot.acquire();
    assert(active_lease);
    assert(active_lease->ping() == 123);
    slot.reset();
    assert(!slot.is_available());
    std::cout << "PASSED\n";

    // 6. App deriving from generated TelemetryActor
    std::cout << "  - Verifying app deriving from generated TelemetryActor... ";
    {
        reaktar::testing::TelemetryTestBench<TelemetrySmokeApp> bench;
        bench.app().send_alert(999, "Telemetry Smoke Alert");
        assert(bench.emergencyalert_count() == 1);
        auto alert = bench.last_emitted<vehicle_supervisor::events::EmergencyAlert>();
        assert(alert.has_value());
        assert(alert->alert_id == 999);
        assert(alert->reason == "Telemetry Smoke Alert");
    }
    std::cout << "PASSED\n";

    // 7. App deriving from generated VehicleSupervisorActor
    std::cout << "  - Verifying app deriving from generated VehicleSupervisorActor... ";
    {
        reaktar::testing::VehicleSupervisorTestBench<SupervisorSmokeApp> bench;
        bool rpc_called = false;
        bench.mock_rpc<reaktar::tags::body_control::methods::LockDoors>([&](bool lock) {
            rpc_called = true;
            assert(lock == true);
            return ara::core::Result<bool>::FromValue(true);
        });

        bench.inject(vehicle_data::SpeedData{195.0f, 100});
        assert(bench.app().speed_received);
        assert(bench.app().alert_emitted);
        assert(rpc_called);
        assert(bench.emitted_count<vehicle_supervisor::events::EmergencyAlert>() == 1);
        auto alert = bench.last_emitted<vehicle_supervisor::events::EmergencyAlert>();
        assert(alert.has_value());
        assert(alert->alert_id == 1001);
    }
    std::cout << "PASSED\n";

    std::cout << "[Smoke Test] All core primitives and generated actor applications verified successfully!\n";
    return 0;
}
