// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// Copyright (c) 2026 Pyarx Lab. Licensed under the MIT License.
// ==============================================================================

#pragma once

/**
 * @file reaktar.hpp
 * @brief Master header for the Reaktar Reactive Actor Framework.
 */

#include "reaktar/config.hpp"
#include "reaktar/types.hpp"
#include "reaktar/traits.hpp"
#if __has_include("reaktar/tags.hpp")
#include "reaktar/tags.hpp"
#endif
#include "reaktar/proxy_slot.hpp"
#include "reaktar/actor_base.hpp"
