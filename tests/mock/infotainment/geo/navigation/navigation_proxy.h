#pragma once

#include "mock_ara/com.hpp"

#include "vehicle_data/types.hpp"

#include "infotainment/geo/navigation/navigation_skeleton.h"
#include <string>
#include <cstdint>
#include <map>
#include <functional>


namespace infotainment {

namespace geo {

namespace navigation {


namespace proxy {

class NavigationProxy {
public:
    using HandleType = ara::com::ServiceHandleType;

    NavigationProxy() = default;
    explicit NavigationProxy(const HandleType& handle) : handle_(handle) {}

    // Events

    ara::com::ProxyEvent<vehicle_data::LocationPoint> CurrentLocation;


    // Fields


    // Methods


    std::function<ara::core::Future<methods::SetDestination::Output>(const float&, const float&, const uint32_t&)> skel_set_destination_{nullptr};

    template <typename F>
    void set_mock_set_destination(F&& f) {
        skel_set_destination_ = [fn = std::forward<F>(f)](const float& latitude, const float& longitude, const uint32_t& priority) -> ara::core::Future<methods::SetDestination::Output> {
            using Ret = decltype(fn(latitude, longitude, priority));
            if constexpr (std::is_same_v<std::decay_t<Ret>, ara::core::Future<methods::SetDestination::Output>>) {
                return fn(latitude, longitude, priority);
            } else {
                return ara::core::MakeFuture<methods::SetDestination::Output>(methods::SetDestination::Output(fn(latitude, longitude, priority)));
            }
        };
    }

    ara::core::Future<methods::SetDestination::Output> SetDestination(const float& latitude, const float& longitude, const uint32_t& priority) {
        if (skel_set_destination_) {
            return skel_set_destination_(latitude, longitude, priority);
        }
        return ara::core::MakeFuture<methods::SetDestination::Output>(methods::SetDestination::Output{});
    }



    static ara::com::FindServiceHandle StartFindService(
        ara::com::FindServiceHandler<NavigationProxy> handler,
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

    static std::map<uint64_t, ara::com::FindServiceHandler<NavigationProxy>>& active_find_handlers() {
        static std::map<uint64_t, ara::com::FindServiceHandler<NavigationProxy>> handlers;
        return handlers;
    }
};

} // namespace proxy


} // namespace navigation

} // namespace geo

} // namespace infotainment
