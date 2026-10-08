// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

#include <cstdint>
#include <string_view>
#include <type_traits>

namespace reaktar {

/**
 * @brief Directionality/Role of an AUTOSAR Port Prototype.
 */
enum class PortKind : uint8_t {
    Required, ///< R-Port: Consumes/requires an AUTOSAR service (Proxy)
    Provided  ///< P-Port: Provides/offers an AUTOSAR service (Skeleton)
};

/**
 * @brief Tag type indicating an R-Port (Required / Proxy).
 */
struct RequiredPortTag {
    static constexpr PortKind kind = PortKind::Required;
};

/**
 * @brief Tag type indicating a P-Port (Provided / Skeleton).
 */
struct ProvidedPortTag {
    static constexpr PortKind kind = PortKind::Provided;
};

/**
 * @brief Compile-time trait to detect if a type is a generated ReaktAR Port Tag.
 */
template <typename T, typename = void>
struct is_port : std::false_type {};

template <typename T>
struct is_port<T, std::void_t<decltype(T::kind)>> : std::true_type {};

template <typename T>
inline constexpr bool is_port_v = is_port<T>::value;

/**
 * @brief Compile-time trait checking if a Port is an R-Port (Required / Proxy).
 */
template <typename T>
inline constexpr bool is_required_port_v = (is_port_v<T> && T::kind == PortKind::Required);

/**
 * @brief Compile-time trait checking if a Port is a P-Port (Provided / Skeleton).
 */
template <typename T>
inline constexpr bool is_provided_port_v = (is_port_v<T> && T::kind == PortKind::Provided);

} // namespace reaktar
