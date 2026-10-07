#pragma once

#include "mock_ara/com.hpp"

#include "vehicle_data/types.hpp"

#include <string>
#include <cstdint>
#include <utility>


namespace infotainment {

namespace geo {

namespace navigation {


namespace methods {

namespace SetDestination {
    struct Tag {};

struct Output {

    bool Result{};


    Output() = default;

    explicit Output(bool v) : Result(std::move(v)) {}
    Output(const ara::core::Result<bool>& res) : Result(res.Value()) {}
    operator bool() const { return Result; }

};

} // namespace SetDestination

} // namespace methods

namespace skeleton {
namespace methods {


namespace SetDestination {
    using Output = ::infotainment::geo::navigation::methods::SetDestination::Output;
} // namespace SetDestination


} // namespace methods

class NavigationSkeleton {
public:
    explicit NavigationSkeleton(
        ara::core::InstanceSpecifier instance_specifier,
        ara::com::MethodCallProcessingMode mode = ara::com::MethodCallProcessingMode::kEvent)
        : instance_specifier_(std::move(instance_specifier)), mode_(mode) {}

    virtual ~NavigationSkeleton() = default;

    // Events

    ara::com::SkeletonEvent<vehicle_data::LocationPoint> CurrentLocation;


    // Fields


    // Methods


    virtual ara::core::Future<methods::SetDestination::Output> SetDestination(const float& latitude, const float& longitude, const uint32_t& priority) = 0;



    void OfferService() { offered_ = true; }
    void StopOfferService() { offered_ = false; }
    bool IsOffered() const { return offered_; }
    ara::com::MethodCallProcessingMode GetMethodCallProcessingMode() const noexcept { return mode_; }

private:
    ara::core::InstanceSpecifier instance_specifier_;
    [[maybe_unused]] ara::com::MethodCallProcessingMode mode_;
    bool offered_{false};
};

} // namespace skeleton


} // namespace navigation

} // namespace geo

} // namespace infotainment
