#pragma once

#include "mock_ara/com.hpp"

#include "body_control/bodycontrol_skeleton.h"
#include <string>
#include <cstdint>
#include <map>
#include <functional>


namespace body_control {


namespace proxy {

class BodyControlProxy {
public:
    using HandleType = ara::com::ServiceHandleType;

    BodyControlProxy() = default;
    explicit BodyControlProxy(const HandleType& handle) : handle_(handle) {}

    // Events


    // Fields

    ara::com::ProxyField<float> TargetCabinTemperature;

    ara::com::ProxyField<uint32_t> RainSensorLevel;

    ara::com::ProxyField<uint32_t> OutsideAirQuality;

    ara::com::ProxyField<uint32_t> WindowPosition;


    // Methods


    std::function<ara::core::Future<methods::LockDoors::Output>(const bool&)> skel_lock_doors_{nullptr};

    template <typename F>
    void set_mock_lock_doors(F&& f) {
        skel_lock_doors_ = [fn = std::forward<F>(f)](const bool& lock) -> ara::core::Future<methods::LockDoors::Output> {
            using Ret = decltype(fn(lock));
            if constexpr (std::is_same_v<std::decay_t<Ret>, ara::core::Future<methods::LockDoors::Output>>) {
                return fn(lock);
            } else {
                return ara::core::MakeFuture<methods::LockDoors::Output>(methods::LockDoors::Output(fn(lock)));
            }
        };
    }

    ara::core::Future<methods::LockDoors::Output> LockDoors(const bool& lock) {
        if (skel_lock_doors_) {
            return skel_lock_doors_(lock);
        }
        return ara::core::MakeFuture<methods::LockDoors::Output>(methods::LockDoors::Output{});
    }



    std::function<void(const uint32_t&, const uint32_t&)> skel_flash_lights_{nullptr};

    void FlashLights(const uint32_t& duration_ms, const uint32_t& count) {
        if (skel_flash_lights_) {
            skel_flash_lights_(duration_ms, count);
        }
    }



    static ara::com::FindServiceHandle StartFindService(
        ara::com::FindServiceHandler<BodyControlProxy> handler,
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

    static std::map<uint64_t, ara::com::FindServiceHandler<BodyControlProxy>>& active_find_handlers() {
        static std::map<uint64_t, ara::com::FindServiceHandler<BodyControlProxy>> handlers;
        return handlers;
    }
};

} // namespace proxy


} // namespace body_control
