#pragma once

#include <map>

namespace ara {
namespace core {

template <typename K, typename V, typename Compare = std::less<K>, typename Alloc = std::allocator<std::pair<const K, V>>>
using Map = std::map<K, V, Compare, Alloc>;

} // namespace core
} // namespace ara
