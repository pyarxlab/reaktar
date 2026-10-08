// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

/**
 * @file reaktar.hpp
 * @brief Master header for the Reaktar Reactive Actor Framework.
 */

#include "reaktar/config.hpp"
#include "reaktar/traits.hpp"
#include "reaktar/types.hpp"
#if __has_include("reaktar/tags.hpp")
#include "reaktar/tags.hpp"
#endif
#include "reaktar/actor_base.hpp"
#include "reaktar/port.hpp"
#include "reaktar/execution_policy.hpp"
#include "reaktar/proxy_slot.hpp"

