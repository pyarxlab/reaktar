// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// Copyright (c) 2026 Pyarx Lab. Licensed under the MIT License.
// ==============================================================================

#pragma once

#include <cstddef>
#include <chrono>
#include <mutex>
#include <condition_variable>

namespace reaktar {

/**
 * @brief Zero-overhead readiness synchronization tracker for Actors consuming N proxies.
 *
 * For N > 0, tracks resolution of consumed proxies with wait/notify semantics.
 * Specialised for N == 0 so that no mutex or condition variable exists in memory.
 */
template <size_t ConsumedProxyCount>
class ReadinessTracker {
public:
    template <typename Predicate>
    bool is_ready(Predicate&& pred) const noexcept {
        return pred();
    }

    template <typename Predicate>
    bool wait_until_ready(Predicate&& pred) {
        if (pred()) {
            return true;
        }
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, pred);
        return true;
    }

    template <typename Predicate, typename Rep, typename Period>
    bool wait_until_ready(Predicate&& pred, const std::chrono::duration<Rep, Period>& timeout) {
        if (pred()) {
            return true;
        }
        std::unique_lock<std::mutex> lock(mutex_);
        return cv_.wait_for(lock, timeout, pred);
    }

    void notify_resolved() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
        }
        cv_.notify_all();
    }

private:
    mutable std::mutex mutex_{};
    std::condition_variable cv_{};
};

/**
 * @brief Specialisation for Actors consuming 0 proxies.
 * Completely zero-cost: zero size overhead, zero mutex/cv, fully inlined.
 */
template <>
class ReadinessTracker<0> {
public:
    template <typename Predicate>
    constexpr bool is_ready(Predicate&&) const noexcept {
        return true;
    }

    template <typename Predicate>
    constexpr bool wait_until_ready(Predicate&&) const noexcept {
        return true;
    }

    template <typename Predicate, typename Rep, typename Period>
    constexpr bool wait_until_ready(Predicate&&, const std::chrono::duration<Rep, Period>&) const noexcept {
        return true;
    }

    constexpr void notify_resolved() const noexcept {}
};

} // namespace reaktar
