// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

#include <utility>
#include <mutex>
#include <type_traits>

namespace reaktar {

/**
 * @brief Direct execution policy (Default).
 *
 * Fully zero-cost, pass-through execution on whatever thread invokes the handler.
 * Zero size overhead, zero mutexes, zero memory allocations.
 */
class DirectExecution {
public:
    template <typename Fn>
    decltype(auto) execute(Fn&& fn) {
        if constexpr (std::is_void_v<std::invoke_result_t<Fn>>) {
            std::forward<Fn>(fn)();
        } else {
            return std::forward<Fn>(fn)();
        }
    }

    template <typename Fn>
    decltype(auto) execute(Fn&& fn) const {
        if constexpr (std::is_void_v<std::invoke_result_t<Fn>>) {
            std::forward<Fn>(fn)();
        } else {
            return std::forward<Fn>(fn)();
        }
    }

    template <typename Fn>
    void post(Fn&& fn) {
        std::forward<Fn>(fn)();
    }

    template <typename Fn>
    void post(Fn&& fn) const {
        std::forward<Fn>(fn)();
    }
};

/**
 * @brief Synchronized execution policy.
 *
 * Guarantees mutual exclusion for an Actor instance using a single non-recursive mutex.
 * All incoming events, skeleton RPCs, continuations, and sync() callback wrappers
 * are serialized to execute safely without data races.
 *
 * Zero extra OS threads, zero dynamic allocations.
 */
class SynchronizedExecution {
public:
    SynchronizedExecution() = default;
    ~SynchronizedExecution() = default;

    SynchronizedExecution(const SynchronizedExecution&) = delete;
    SynchronizedExecution& operator=(const SynchronizedExecution&) = delete;
    SynchronizedExecution(SynchronizedExecution&&) = delete;
    SynchronizedExecution& operator=(SynchronizedExecution&&) = delete;

    template <typename Fn>
    decltype(auto) execute(Fn&& fn) {
        std::lock_guard<std::mutex> lock(mutex_);
        if constexpr (std::is_void_v<std::invoke_result_t<Fn>>) {
            std::forward<Fn>(fn)();
        } else {
            return std::forward<Fn>(fn)();
        }
    }

    template <typename Fn>
    decltype(auto) execute(Fn&& fn) const {
        std::lock_guard<std::mutex> lock(mutex_);
        if constexpr (std::is_void_v<std::invoke_result_t<Fn>>) {
            std::forward<Fn>(fn)();
        } else {
            return std::forward<Fn>(fn)();
        }
    }

    template <typename Fn>
    void post(Fn&& fn) {
        std::lock_guard<std::mutex> lock(mutex_);
        std::forward<Fn>(fn)();
    }

    template <typename Fn>
    void post(Fn&& fn) const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::forward<Fn>(fn)();
    }

    std::mutex& mutex() const noexcept { return mutex_; }

private:
    mutable std::mutex mutex_{};
};

/**
 * @brief Trait to detect whether a type satisfies the Reaktar Execution Policy interface.
 */
template <typename T, typename = void>
struct is_execution_policy : std::false_type {};

template <typename T>
struct is_execution_policy<T, std::void_t<
    decltype(std::declval<T>().execute(std::declval<void(*)()>())),
    decltype(std::declval<T>().post(std::declval<void(*)()>()))
>> : std::true_type {};

template <typename T>
inline constexpr bool is_execution_policy_v = is_execution_policy<T>::value;

} // namespace reaktar
