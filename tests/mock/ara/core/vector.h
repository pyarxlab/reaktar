#pragma once

#include <vector>

namespace ara {
namespace core {

template <typename T, typename Alloc = std::allocator<T>>
using Vector = std::vector<T, Alloc>;

} // namespace core
} // namespace ara
