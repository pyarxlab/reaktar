#pragma once

#include <array>
#include <cstddef>

namespace ara {
namespace core {

template <typename T, std::size_t N>
using Array = std::array<T, N>;

} // namespace core
} // namespace ara
