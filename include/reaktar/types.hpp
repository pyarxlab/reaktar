// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

#include "reaktar/config.hpp"

/**
 * @file types.hpp
 * @brief Vendor-configurable type mappings for Reaktar.
 *
 * Explicit configuration always trumps automatic discovery:
 * - REAKTAR_CUSTOM_TYPES: Custom future/result/promise provided by user/project configuration
 * - REAKTAR_USE_VES: Vector Embedded Software (ves::Future, ves::Result, ves::Promise)
 * - REAKTAR_USE_AMSR: Vector AMSR (amsr::core::Future, amsr::core::Result, amsr::core::Promise)
 * - REAKTAR_USE_ARA: Explicit standard AUTOSAR (ara::core::Future, ara::core::Result, ara::core::Promise)
 *
 * Automatic discovery (when enabled by REAKTAR_AUTO_DISCOVER):
 * Uses standard C++17 __has_include to probe vendor include paths:
 *   1. VES  (<ves/Future.h> or <ves/types.hpp>)
 *   2. AMSR (<amsr/core/future.h> or <amsr/core/result.h>)
 *   3. Standard ARA fallback (<ara/core/future.h> or ara::core mock)
 *
 * Direct type aliasing is preserved so template deduction and partial
 * specializations remain non-dependent and fully deducible.
 */

namespace reaktar {

#if defined(REAKTAR_CUSTOM_TYPES)
    // Custom future/result/promise/error provided by user/project configuration
#elif defined(REAKTAR_USE_VES)
    template <typename T> using Future = ::ves::Future<T>;
    template <typename T> using Result = ::ves::Result<T>;
    template <typename T> using Promise = ::ves::Promise<T>;
    using ErrorCode = ::ves::ErrorCode;
    using InstanceSpecifier = ::ves::InstanceSpecifier;
#elif defined(REAKTAR_USE_AMSR)
    template <typename T> using Future = ::amsr::core::Future<T>;
    template <typename T> using Result = ::amsr::core::Result<T>;
    template <typename T> using Promise = ::amsr::core::Promise<T>;
    using ErrorCode = ::amsr::core::ErrorCode;
    using InstanceSpecifier = ::amsr::core::InstanceSpecifier;
#elif defined(REAKTAR_USE_ARA)
    template <typename T> using Future = ::ara::core::Future<T>;
    template <typename T> using Result = ::ara::core::Result<T>;
    template <typename T> using Promise = ::ara::core::Promise<T>;
    using ErrorCode = ::ara::core::ErrorCode;
    using InstanceSpecifier = ::ara::core::InstanceSpecifier;
#elif defined(REAKTAR_AUTO_DISCOVER) || defined(REAKTAR_AUTO_DISCOVER_TYPES)
    #if defined(__has_include)
        #if __has_include(<ves/Future.h>) || __has_include(<ves/types.hpp>)
            template <typename T> using Future = ::ves::Future<T>;
            template <typename T> using Result = ::ves::Result<T>;
            template <typename T> using Promise = ::ves::Promise<T>;
            using ErrorCode = ::ves::ErrorCode;
            using InstanceSpecifier = ::ves::InstanceSpecifier;
        #elif __has_include(<amsr/core/future.h>) || __has_include(<amsr/core/result.h>)
            template <typename T> using Future = ::amsr::core::Future<T>;
            template <typename T> using Result = ::amsr::core::Result<T>;
            template <typename T> using Promise = ::amsr::core::Promise<T>;
            using ErrorCode = ::amsr::core::ErrorCode;
            using InstanceSpecifier = ::amsr::core::InstanceSpecifier;
        #else
            // Fallback: standard ara::core
            template <typename T> using Future = ::ara::core::Future<T>;
            template <typename T> using Result = ::ara::core::Result<T>;
            template <typename T> using Promise = ::ara::core::Promise<T>;
            using ErrorCode = ::ara::core::ErrorCode;
            using InstanceSpecifier = ::ara::core::InstanceSpecifier;
        #endif
    #else
        template <typename T> using Future = ::ara::core::Future<T>;
        template <typename T> using Result = ::ara::core::Result<T>;
        template <typename T> using Promise = ::ara::core::Promise<T>;
        using ErrorCode = ::ara::core::ErrorCode;
        using InstanceSpecifier = ::ara::core::InstanceSpecifier;
    #endif
#else
    // Default: Safe, standard AUTOSAR Adaptive (ara::core)
    template <typename T> using Future = ::ara::core::Future<T>;
    template <typename T> using Result = ::ara::core::Result<T>;
    template <typename T> using Promise = ::ara::core::Promise<T>;
    using ErrorCode = ::ara::core::ErrorCode;
    using InstanceSpecifier = ::ara::core::InstanceSpecifier;
#endif

} // namespace reaktar
