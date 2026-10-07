#pragma once

#include "mock_ara/com.hpp"

#include "vehicle_data/types.hpp"

#include <string>
#include <cstdint>
#include <utility>


namespace powertrain {


namespace methods {

} // namespace methods

namespace skeleton {
namespace methods {

} // namespace methods

class PowertrainSkeleton {
public:
    explicit PowertrainSkeleton(
        ara::core::InstanceSpecifier instance_specifier,
        ara::com::MethodCallProcessingMode mode = ara::com::MethodCallProcessingMode::kEvent)
        : instance_specifier_(std::move(instance_specifier)), mode_(mode) {}

    virtual ~PowertrainSkeleton() = default;

    // Events

    ara::com::SkeletonEvent<vehicle_data::SpeedData> VehicleSpeed;

    ara::com::SkeletonEvent<vehicle_data::CabinSensorData> CabinSensors;


    // Fields


    // Methods


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


} // namespace powertrain
