#pragma once

#include "mock_ara/com.hpp"

#include "vehicle_data/types.hpp"

#include "powertrain/powertrain_skeleton.h"
#include <string>
#include <cstdint>
#include <map>
#include <functional>


namespace powertrain {


namespace proxy {

class PowertrainProxy {
public:
    using HandleType = ara::com::ServiceHandleType;

    PowertrainProxy() = default;
    explicit PowertrainProxy(const HandleType& handle) : handle_(handle) {}

    // Events

    ara::com::ProxyEvent<vehicle_data::SpeedData> VehicleSpeed;

    ara::com::ProxyEvent<vehicle_data::CabinSensorData> CabinSensors;


    // Fields


    // Methods


    static ara::com::FindServiceHandle StartFindService(
        ara::com::FindServiceHandler<PowertrainProxy> handler,
        ara::core::InstanceSpecifier instance_specifier)
    {
        ara::com::FindServiceHandle find_handle(ara::com::detail::next_find_handle_id());
        active_find_handlers()[find_handle.id()] = handler;
        ara::com::ServiceHandleContainer<HandleType> handles;
        handles.push_back(HandleType{instance_specifier, 1});
        handler(handles, find_handle);
        return find_handle;
    }

    static void StopFindService(ara::com::FindServiceHandle handle) {
        active_find_handlers().erase(handle.id());
    }

    /// Simulation / Test-Bench helper: trigger service availability update across active find handlers
    static void TriggerFindService(const ara::com::ServiceHandleContainer<HandleType>& handles) {
        for (const auto& kv : active_find_handlers()) {
            kv.second(handles, ara::com::FindServiceHandle(kv.first));
        }
    }

    /// Simulation / Test-Bench helper: simulate service going offline (empty container)
    static void TriggerFindServiceEmpty() {
        TriggerFindService({});
    }

    const HandleType& GetHandle() const { return handle_; }

private:
    HandleType handle_{};

    static std::map<uint64_t, ara::com::FindServiceHandler<PowertrainProxy>>& active_find_handlers() {
        static std::map<uint64_t, ara::com::FindServiceHandler<PowertrainProxy>> handlers;
        return handlers;
    }
};

} // namespace proxy


} // namespace powertrain
