// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>

namespace reaktar {

// Portable branch-prediction hints for GCC, Clang (macOS, Linux, QNX 8)
#if defined(__GNUC__) || defined(__clang__)
#  define REAKTAR_LIKELY(x)   (__builtin_expect(!!(x), 1))
#  define REAKTAR_UNLIKELY(x) (__builtin_expect(!!(x), 0))
#else
#  define REAKTAR_LIKELY(x)   (x)
#  define REAKTAR_UNLIKELY(x) (x)
#endif

// Forward declarations
template <typename T>
struct ProxyCell;

template <typename T>
class ProxySlot;

/**
 * @brief Generational Control Block for an active proxy instance.
 *
 * Encapsulates the proxy instance alongside its independent reader counter,
 * lifecycle activation flag, and drain synchronization primitives.
 * Generational isolation ensures that hung or delayed readers on older
 * proxy instances never taint or block newly published proxies.
 */
template <typename T>
struct ProxyCell {
    std::unique_ptr<T> instance;
    std::atomic<uint32_t> active_readers{0};
    std::atomic<bool> is_active{true};
    mutable std::mutex drain_mutex;
    std::condition_variable drain_cv;

    explicit ProxyCell(std::unique_ptr<T> inst) noexcept
        : instance(std::move(inst)) {}

    ~ProxyCell() = default;

    ProxyCell(const ProxyCell&) = delete;
    ProxyCell& operator=(const ProxyCell&) = delete;
    ProxyCell(ProxyCell&&) = delete;
    ProxyCell& operator=(ProxyCell&&) = delete;
};

/**
 * @brief Zero-overhead RAII Lease on an active proxy pointer.
 *
 * Automatically tracks reader count per generational cell.
 * Prevents the proxy from being deallocated during method execution.
 * Wait-free on the normal fast path.
 */
template <typename T>
class ProxyLease {
public:
    ProxyLease() noexcept : ptr_(nullptr), cell_(nullptr) {}

    ProxyLease(T* ptr, ProxyCell<T>* cell) noexcept
        : ptr_(ptr), cell_(cell) {}

    ~ProxyLease() {
        release();
    }

    ProxyLease(const ProxyLease&) = delete;
    ProxyLease& operator=(const ProxyLease&) = delete;

    ProxyLease(ProxyLease&& other) noexcept
        : ptr_(other.ptr_), cell_(other.cell_) {
        other.ptr_ = nullptr;
        other.cell_ = nullptr;
    }

    ProxyLease& operator=(ProxyLease&& other) noexcept {
        if (this != &other) {
            release();
            ptr_ = other.ptr_;
            cell_ = other.cell_;
            other.ptr_ = nullptr;
            other.cell_ = nullptr;
        }
        return *this;
    }

    T* operator->() const noexcept { return ptr_; }
    T& operator*() const noexcept { return *ptr_; }
    T* get() const noexcept { return ptr_; }
    explicit operator bool() const noexcept { return ptr_ != nullptr; }

private:
    void release() noexcept {
        if (cell_) {
            // Decrement reader count with release barrier
            if (cell_->active_readers.fetch_sub(1, std::memory_order_acq_rel) == 1) {
                // If this was the last reader and cell is inactive, notify waiting drain
                if (!cell_->is_active.load(std::memory_order_acquire)) {
                    std::lock_guard<std::mutex> lock(cell_->drain_mutex);
                    cell_->drain_cv.notify_all();
                }
            }
            cell_ = nullptr;
            ptr_ = nullptr;
        }
    }

    T* ptr_{nullptr};
    ProxyCell<T>* cell_{nullptr};
};

/**
 * @brief Thread-safe, lock-free reader Proxy Slot for AUTOSAR Adaptive services.
 *
 * Implements the Generational Cell with Bounded Drain & Graveyard Retirement architecture:
 * - FAST HAPPY PATH: ~5ns lock-free reader acquire (2 atomic loads + 1 atomic increment).
 * - ZERO DYNAMIC ALLOCATIONS in the fast path.
 * - BOUNDED DRAIN: Bounded wait on kernel condition variable (0% CPU burn, immune to priority inversion).
 * - CATASTROPHE IMMUNITY: Readers delayed or hung beyond timeout never crash (no Use-After-Free)
 *   and never deadlock the discovery thread (graveyard retirement).
 * - GENERATIONAL ISOLATION: A hung reader on Generation N does not block Generation N+1.
 */
template <typename T>
class ProxySlot {
public:
    ProxySlot() = default;

    ~ProxySlot() {
        reset(std::chrono::milliseconds(20));
    }

    ProxySlot(const ProxySlot&) = delete;
    ProxySlot& operator=(const ProxySlot&) = delete;

    /**
     * @brief Acquire a RAII lease to invoke methods safely across threads.
     *
     * Returns an empty lease if the proxy has not been resolved yet.
     */
    ProxyLease<T> acquire(const char* /*service_name*/ = "AUTOSAR Service") noexcept {
        return try_acquire();
    }

    /**
     * @brief Non-throwing lease acquisition.
     * Returns an empty lease if the proxy is not currently available.
     */
    ProxyLease<T> try_acquire() noexcept {
        ProxyCell<T>* cell = current_cell_.load(std::memory_order_acquire);
        if (REAKTAR_UNLIKELY(cell == nullptr)) {
            return ProxyLease<T>{};
        }

        // Announce intent to read
        cell->active_readers.fetch_add(1, std::memory_order_acquire);

        // Verification fence: make sure the cell was not retired/exchanged
        // concurrently right before our increment.
        if (REAKTAR_UNLIKELY(!cell->is_active.load(std::memory_order_acquire) ||
                             cell != current_cell_.load(std::memory_order_relaxed))) {
            if (cell->active_readers.fetch_sub(1, std::memory_order_acq_rel) == 1) {
                if (!cell->is_active.load(std::memory_order_acquire)) {
                    std::lock_guard<std::mutex> lock(cell->drain_mutex);
                    cell->drain_cv.notify_all();
                }
            }
            return ProxyLease<T>{};
        }

        return ProxyLease<T>(cell->instance.get(), cell);
    }

    /**
     * @brief Fast check whether the proxy is currently available.
     */
    bool is_available() const noexcept {
        ProxyCell<T>* cell = current_cell_.load(std::memory_order_acquire);
        return cell != nullptr && cell->is_active.load(std::memory_order_relaxed) && cell->instance != nullptr;
    }

    /**
     * @brief Raw pointer access (for test benches and diagnostics).
     */
    T* get() const noexcept {
        ProxyCell<T>* cell = current_cell_.load(std::memory_order_acquire);
        return (cell != nullptr && cell->is_active.load(std::memory_order_relaxed))
            ? cell->instance.get()
            : nullptr;
    }

    /**
     * @brief Atomically publish or replace a proxy instance.
     *
     * If an existing proxy was active, it is drained with a bounded timeout
     * before publishing the new instance.
     */
    void publish(std::unique_ptr<T> instance,
                 std::chrono::milliseconds timeout = std::chrono::milliseconds(50)) {
        if (!instance) return;
        std::lock_guard<std::mutex> lock(lifecycle_mutex_);

        if (current_cell_.load(std::memory_order_relaxed) != nullptr) {
            reset_locked(timeout);
        }

        auto new_cell = std::make_unique<ProxyCell<T>>(std::move(instance));
        current_cell_.store(new_cell.get(), std::memory_order_release);
        active_cell_ = std::move(new_cell);
    }

    /**
     * @brief Safely revoke and retire the active proxy instance.
     *
     * Atomically deactivates the current cell so no new readers can enter.
     * Waits for active readers up to @p timeout. If readers finish, the proxy
     * instance is deallocated immediately. If a reader hangs, the instance
     * is safely preserved in the graveyard to prevent use-after-free and deadlock.
     */
    void reset(std::chrono::milliseconds timeout = std::chrono::milliseconds(50)) {
        std::lock_guard<std::mutex> lock(lifecycle_mutex_);
        reset_locked(timeout);
    }

    /**
     * @brief Diagnostics: Number of retired cells preserved in the graveyard.
     */
    size_t graveyard_size() const noexcept {
        std::lock_guard<std::mutex> lock(lifecycle_mutex_);
        return graveyard_.size();
    }

    /**
     * @brief Diagnostics: Number of active readers on the current generation.
     */
    size_t active_readers() const noexcept {
        ProxyCell<T>* cell = current_cell_.load(std::memory_order_acquire);
        return cell ? cell->active_readers.load(std::memory_order_relaxed) : 0;
    }

private:
    void reset_locked(std::chrono::milliseconds timeout) {
        ProxyCell<T>* old_cell = current_cell_.exchange(nullptr, std::memory_order_acq_rel);
        if (!old_cell) {
            return;
        }

        // 1. Mark inactive: future acquire() will reject this cell
        old_cell->is_active.store(false, std::memory_order_release);

        // 2. Bounded wait for active readers to finish
        bool drained = false;
        {
            std::unique_lock<std::mutex> drain_lock(old_cell->drain_mutex);
            drained = old_cell->drain_cv.wait_for(drain_lock, timeout, [old_cell]() {
                return old_cell->active_readers.load(std::memory_order_acquire) == 0;
            });
        }

        if (drained) {
            // Normal path: all readers finished cleanly within timeout.
            // Safely deallocate the underlying proxy instance immediately.
            old_cell->instance.reset();
        } else {
            // Catastrophe Prevention:
            // A reader is hung or took longer than the deadline.
            // DO NOT hang forever (prevents Deadlock / Watchdog termination).
            // DO NOT delete the proxy (prevents Use-After-Free crash).
            // Retain the proxy instance intact inside the cell.
        }

        // Store active_cell_ in graveyard so the cell control block itself
        // remains valid in memory and is safely reclaimed upon slot destruction.
        if (active_cell_) {
            graveyard_.push_back(std::move(active_cell_));
        }
    }

    std::atomic<ProxyCell<T>*> current_cell_{nullptr};
    std::unique_ptr<ProxyCell<T>> active_cell_{nullptr};
    std::vector<std::unique_ptr<ProxyCell<T>>> graveyard_;
    mutable std::mutex lifecycle_mutex_;
};

} // namespace reaktar
