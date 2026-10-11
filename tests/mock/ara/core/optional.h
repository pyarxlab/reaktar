#pragma once

#include <optional>

namespace ara {
namespace core {

template <typename T>
using Optional = std::optional<T>;

using nullopt_t = std::nullopt_t;
inline constexpr std::nullopt_t nullopt{std::nullopt};

} // namespace core
} // namespace ara
