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
 * - REAKTAR_USE_AMSR: Vector AMSR / MICROSAR Adaptive (amsr::core::Future, amsr::core::Result, amsr::core::Promise)
 * - REAKTAR_USE_VES: Explicit Vector Embedded Software wrapper (ves::Future, ves::Result, ves::Promise)
 * - REAKTAR_USE_ARA: Explicit standard AUTOSAR (ara::core::Future, ara::core::Result, ara::core::Promise)
 *
 * Automatic discovery (when enabled by REAKTAR_AUTO_DISCOVER):
 * Uses standard C++17 __has_include to probe real vendor headers:
 *   1. Vector AMSR (<amsr/core/future.h> or <amsr/core/result.h>) -> defines REAKTAR_USE_AMSR
 *   2. Standard AUTOSAR fallback (<ara/core/future.h> or mock_ara) -> defines REAKTAR_USE_ARA
 *
 * Direct type aliasing is preserved so template deduction and partial
 * specializations remain non-dependent and fully deducible.
 */

// ----------------------------------------------------------------------------
// 1. Automatic Vendor Discovery: Probes headers and resolves REAKTAR_USE_*
// ----------------------------------------------------------------------------
#if !defined(REAKTAR_CUSTOM_TYPES) && \
    !defined(REAKTAR_USE_AMSR)     && \
    !defined(REAKTAR_USE_VES)      && \
    !defined(REAKTAR_USE_ARA)

    #if (defined(REAKTAR_AUTO_DISCOVER) || defined(REAKTAR_AUTO_DISCOVER_TYPES)) && defined(__has_include)
        #if __has_include(<amsr/core/future.h>) || __has_include(<amsr/core/result.h>)
            #define REAKTAR_USE_AMSR 1
        #else
            #define REAKTAR_USE_ARA 1
        #endif
    #else
        #define REAKTAR_USE_ARA 1
    #endif
#endif

// ----------------------------------------------------------------------------
// 2. Vendor Header Inclusions (when available via __has_include)
// ----------------------------------------------------------------------------
#if defined(REAKTAR_USE_AMSR)
    #if defined(__has_include)
        #if __has_include(<amsr/core/future.h>)
            #include <amsr/core/future.h>
        #endif
        #if __has_include(<amsr/core/result.h>)
            #include <amsr/core/result.h>
        #endif
        #if __has_include(<amsr/core/promise.h>)
            #include <amsr/core/promise.h>
        #endif
    #endif
#endif

// Forward-declare namespaces so namespace alias is always well-formed
#if defined(REAKTAR_USE_AMSR)
namespace amsr { namespace core {} }
#elif defined(REAKTAR_USE_VES)
namespace ves {}
#else
namespace ara { namespace core {} }
#endif

// ----------------------------------------------------------------------------
// 3. Unified Type Aliases (Zero Duplication)
// ----------------------------------------------------------------------------
namespace reaktar {

#if defined(REAKTAR_CUSTOM_TYPES)
    // Custom future/result/promise/error provided by user/project configuration
#else
    #if defined(REAKTAR_USE_AMSR)
        namespace vendor = ::amsr::core;
    #elif defined(REAKTAR_USE_VES)
        namespace vendor = ::ves;
    #else
        namespace vendor = ::ara::core;
    #endif

    template <typename T> using Future = vendor::Future<T>;
    template <typename T> using Result = vendor::Result<T>;
    template <typename T> using Promise = vendor::Promise<T>;
    using ErrorCode = vendor::ErrorCode;
    using InstanceSpecifier = vendor::InstanceSpecifier;
#endif

} // namespace reaktar
