// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

/**
 * @file thread_safety.hpp
 * @brief Thread safety capability and analysis annotations for ReaktAR.
 *
 * Implements Clang Thread Safety Analysis macros (GUARDED_BY, REQUIRES, etc.)
 * for compile-time verification of lock invariants and data race prevention.
 *
 * Portability:
 * These attributes are Clang-specific. When compiling with other standard toolchains
 * (e.g. GCC), all annotations expand to empty tokens.
 */

#if defined(__clang__)
#  define REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(x) __attribute__((x))
#else
#  define REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(x)
#endif

// Document that a data member is protected by the given capability/mutex
#define REAKTAR_GUARDED_BY(x) \
  REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(guarded_by(x))

// Document that a pointer's pointee is protected by the given capability/mutex
#define REAKTAR_PT_GUARDED_BY(x) \
  REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(pt_guarded_by(x))

// Document that calling a function requires holding the given capability/mutex
#define REAKTAR_REQUIRES(...) \
  REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(requires_capability(__VA_ARGS__))

// Document that a function must NOT be called with the given capability/mutex held (deadlock prevention)
#define REAKTAR_EXCLUDES(...) \
  REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(locks_excluded(__VA_ARGS__))

// Document that thread safety analysis should be disabled for a specific function
#define REAKTAR_NO_THREAD_SAFETY_ANALYSIS \
  REAKTAR_THREAD_ANNOTATION_ATTRIBUTE__(no_thread_safety_analysis)
