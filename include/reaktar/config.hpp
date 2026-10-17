// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

/**
 * @file config.hpp
 * @brief Reaktar distribution configuration and compile-time defaults.
 *
 * Vendor Type Selection:
 * By default, this distribution ships with automatic discovery enabled.
 * Integrators or projects can override this default by defining any of the
 * following macros prior to including Reaktar headers or via compiler flags (-D):
 *   - REAKTAR_CUSTOM_TYPES     : User provides custom Future, Result, and Promise
 *   - REAKTAR_USE_VES          : Target ves:: namespace toolchain
 *   - REAKTAR_USE_AMSR         : Target amsr::core:: namespace toolchain
 *   - REAKTAR_USE_ARA          : Explicitly use standard AUTOSAR Adaptive (ara::core::)
 *   - REAKTAR_NO_AUTO_DISCOVER : Disable auto-discovery and fall back directly to ara::core::
 */

#if !defined(REAKTAR_CUSTOM_TYPES)     && \
    !defined(REAKTAR_USE_VES)          && \
    !defined(REAKTAR_USE_AMSR)         && \
    !defined(REAKTAR_USE_ARA)          && \
    !defined(REAKTAR_NO_AUTO_DISCOVER) && \
    !defined(REAKTAR_AUTO_DISCOVER)
    #define REAKTAR_AUTO_DISCOVER 1
#endif

// ============================================================================
// Compile-time Strict Validation Configuration
// ============================================================================

/**
 * Compile-time Strict Validation Control:
 *
 * Can be enabled or disabled via build system flags (-D):
 *   -DREAKTAR_STRICT_VALIDATION=1 (or bare -DREAKTAR_STRICT_VALIDATION)
 *   -DREAKTAR_ENABLE_STRICT_VALIDATION
 *   -DREAKTAR_DISABLE_STRICT_VALIDATION
 *
 * Never overrides flags supplied by the build system.
 * Defaults to 0 (disabled) for maximum compilation speed during development.
 */
#ifndef REAKTAR_STRICT_VALIDATION
#  if defined(REAKTAR_DISABLE_STRICT_VALIDATION)
#    define REAKTAR_STRICT_VALIDATION 0
#  elif defined(REAKTAR_ENABLE_STRICT_VALIDATION)
#    define REAKTAR_STRICT_VALIDATION 1
#  else
#    define REAKTAR_STRICT_VALIDATION 0
#  endif
#endif

// ============================================================================
// Compile-time Ambiguity Validation Control (Nuclear Bypass)
// ============================================================================

/**
 * Ambiguity Validation Control:
 *
 * When REAKTAR_DISABLE_AMBIGUITY_VALIDATION (or REAKTAR_DISABLE_DISAMBIGUATION_VALIDATION) is defined:
 * Compile-time static assertions checking handler collisions, ambiguous direct/port
 * handlers, and conflicting handlers are completely bypassed, trusting developer intent.
 *
 * UNDEFINED by default (ambiguity validation is active).
 */
#ifndef REAKTAR_AMBIGUITY_VALIDATION
#  if defined(REAKTAR_DISABLE_AMBIGUITY_VALIDATION) || defined(REAKTAR_DISABLE_DISAMBIGUATION_VALIDATION)
#    define REAKTAR_AMBIGUITY_VALIDATION 0
#  else
#    define REAKTAR_AMBIGUITY_VALIDATION 1
#  endif
#endif

namespace reaktar {

inline constexpr bool strict_validation_enabled = (REAKTAR_STRICT_VALIDATION != 0);
inline constexpr bool ambiguity_validation_enabled = (REAKTAR_AMBIGUITY_VALIDATION != 0);

} // namespace reaktar


