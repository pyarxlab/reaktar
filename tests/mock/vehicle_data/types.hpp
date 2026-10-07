#pragma once

#include "mock_ara/com.hpp"
#include <cstdint>
#include <string>

namespace vehicle_data {

struct SpeedData {
    float speed_kmh{};
    uint64_t timestamp_us{};
};

struct CabinSensorData {
    float temperature_c{};
    float humidity_pct{};
    bool passenger_detected{};
};

struct EmergencyAlert {
    uint32_t alert_id{};
    ara::core::String reason{};
};

enum class DriveMode : uint8_t {
    ECO,
    COMFORT,
    SPORT,
    EMERGENCY,
};

struct LocationPoint {
    float latitude{};
    float longitude{};
    float altitude{};
    float speed_limit_kmh{};
};

} // namespace vehicle_data
