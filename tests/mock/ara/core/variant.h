#pragma once

#include <cstddef>
#include <utility>
#include <variant>

namespace ara {
namespace core {

template <typename... Ts>
using Variant = std::variant<Ts...>;

using monostate = std::monostate;

template <typename Visitor, typename... Variants>
constexpr decltype(auto) visit(Visitor&& vis, Variants&&... vars) {
    return std::visit(std::forward<Visitor>(vis), std::forward<Variants>(vars)...);
}

template <typename T, typename... Ts>
constexpr bool holds_alternative(const Variant<Ts...>& v) noexcept {
    return std::holds_alternative<T>(v);
}

template <typename T, typename... Ts>
constexpr T& get(Variant<Ts...>& v) {
    return std::get<T>(v);
}

template <typename T, typename... Ts>
constexpr const T& get(const Variant<Ts...>& v) {
    return std::get<T>(v);
}

template <std::size_t I, typename... Ts>
constexpr auto& get(Variant<Ts...>& v) {
    return std::get<I>(v);
}

template <std::size_t I, typename... Ts>
constexpr const auto& get(const Variant<Ts...>& v) {
    return std::get<I>(v);
}

} // namespace core
} // namespace ara
