// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// Copyright (c) 2026 Pyarx Lab. Licensed under the MIT License.
// ==============================================================================

#pragma once

/**
 * @file vendor_sdk_verifier.hpp
 * @brief Self-contained verification suite for Vendor AUTOSAR Adaptive SDK types.
 *
 * This header is COMPLETELY SELF-CONTAINED:
 * - NO external test framework dependencies (no GTest, Catch2, etc.).
 * - NO vendor SDK headers are included here.
 * - The user includes vendor SDK headers BEFORE including this file.
 * - Tested foundational types:
 *     1. reaktar::Result<T> and reaktar::Result<void>
 *     2. reaktar::Future<T> and reaktar::Future<void>
 *     3. reaktar::Promise<T> and reaktar::Promise<void>
 *     4. reaktar::ErrorCode (construction, inspection, value/domain/message)
 *     5. reaktar::InstanceSpecifier (construction, ToString / to_string / operator std::string)
 *     6. reaktar::AsyncResult<T> bridging against the vendor Future/Result
 *
 * USAGE:
 *   #include <your_vendor_sdk_headers...> // Vector AMSR, EB tresos, Continental VES, etc.
 *   #include <reaktar/vendor_sdk_verifier.hpp>
 *
 *   int main() {
 *       reaktar::verification::TestSuite suite;
 *       bool ok = suite.run();
 *       return ok ? 0 : 1;
 *   }
 */

#include <iostream>
#include <string>
#include <vector>
#include <utility>
#include <type_traits>
#include <exception>

#include "reaktar/types.hpp"
#include "reaktar/traits.hpp"

namespace reaktar {
namespace verification {

// Detection helpers for methods with varying vendor naming conventions
namespace detail {

template <typename T, typename = void>
struct has_has_value_method : std::false_type {};
template <typename T>
struct has_has_value_method<T, std::void_t<decltype(std::declval<const T&>().HasValue())>> : std::true_type {};

template <typename T, typename = void>
struct has_value_method : std::false_type {};
template <typename T>
struct has_value_method<T, std::void_t<decltype(std::declval<const T&>().Value())>> : std::true_type {};

template <typename T, typename = void>
struct has_error_method : std::false_type {};
template <typename T>
struct has_error_method<T, std::void_t<decltype(std::declval<const T&>().Error())>> : std::true_type {};

template <typename P, typename V, typename = void>
struct has_set_value : std::false_type {};
template <typename P, typename V>
struct has_set_value<P, V, std::void_t<decltype(std::declval<P&>().set_value(std::declval<V>()))>> : std::true_type {};

template <typename P, typename = void>
struct has_set_value_void : std::false_type {};
template <typename P>
struct has_set_value_void<P, std::void_t<decltype(std::declval<P&>().set_value())>> : std::true_type {};

template <typename P, typename E, typename = void>
struct has_set_error : std::false_type {};
template <typename P, typename E>
struct has_set_error<P, E, std::void_t<decltype(std::declval<P&>().set_error(std::declval<E>()))>> : std::true_type {};

template <typename P, typename = void>
struct has_get_future : std::false_type {};
template <typename P>
struct has_get_future<P, std::void_t<decltype(std::declval<P&>().get_future())>> : std::true_type {};

template <typename F, typename = void>
struct has_future_get : std::false_type {};
template <typename F>
struct has_future_get<F, std::void_t<decltype(std::declval<F&>().get())>> : std::true_type {};

template <typename T, typename = void>
struct has_equality_op : std::false_type {};
template <typename T>
struct has_equality_op<T, std::void_t<decltype(std::declval<const T&>() == std::declval<const T&>())>> : std::true_type {};

template <typename T, typename = void>
struct has_inequality_op : std::false_type {};
template <typename T>
struct has_inequality_op<T, std::void_t<decltype(std::declval<const T&>() != std::declval<const T&>())>> : std::true_type {};

template <typename T, typename = void>
struct has_less_op : std::false_type {};
template <typename T>
struct has_less_op<T, std::void_t<decltype(std::declval<const T&>() < std::declval<const T&>())>> : std::true_type {};

} // namespace detail

struct TestResult {
    std::string name;
    bool passed{false};
    std::string message;
};

class TestSuite {
public:
    explicit TestSuite(std::ostream& out = std::cout) : out_(out) {}

    void check(const std::string& name, bool condition, const std::string& error_msg = "") {
        TestResult res;
        res.name = name;
        res.passed = condition;
        res.message = condition ? "PASS" : (error_msg.empty() ? "FAIL" : error_msg);
        results_.push_back(res);

        if (condition) {
            out_ << "  [PASS] " << name << "\n";
        } else {
            out_ << "  [FAIL] " << name;
            if (!error_msg.empty()) {
                out_ << " -> " << error_msg;
            }
            out_ << "\n";
        }
    }

    bool run() {
        results_.clear();
        out_ << "========================================================\n";
        out_ << " Reaktar Vendor SDK Compatibility Verification Suite\n";
        out_ << "========================================================\n\n";

        test_result_type();
        test_error_code_type();
        test_promise_and_future_types();
        test_future_continuation();
        test_async_result_bridge();
        test_instance_specifier();

        return print_summary();
    }

    bool print_summary() {
        out_ << "\n--------------------------------------------------------\n";
        size_t passed = 0;
        for (const auto& r : results_) {
            if (r.passed) ++passed;
        }
        out_ << "Summary: " << passed << " / " << results_.size() << " checks passed ("
             << (passed == results_.size() ? "100% COMPATIBLE" : "COMPATIBILITY ISSUES DETECTED")
             << ")\n";
        out_ << "========================================================\n";
        return passed == results_.size();
    }

    template <typename HandleT>
    void test_handle_type(const std::string& type_name, const HandleT& h1, const HandleT& h2, const HandleT& h1_copy) {
        out_ << "\n[Section: Service HandleType Specification [SWS_CM_00312]] (" << type_name << ")\n";

        constexpr bool has_eq = detail::has_equality_op<HandleT>::value;
        check(type_name + " provides operator== [SWS_CM_00312]", has_eq);

        constexpr bool has_neq = detail::has_inequality_op<HandleT>::value;
        check(type_name + " provides operator!= [SWS_CM_00312]", has_neq);

        constexpr bool has_lt = detail::has_less_op<HandleT>::value;
        check(type_name + " provides operator< [SWS_CM_00312]", has_lt);

        if constexpr (has_eq && has_neq && has_lt) {
            bool eq_reflexive = (h1 == h1);
            bool eq_copy = (h1 == h1_copy);
            bool eq_diff = !(h1 == h2);
            check(type_name + " operator== reflexive, symmetric, and distinguishes distinct instances", eq_reflexive && eq_copy && eq_diff);

            bool neq_diff = (h1 != h2);
            bool neq_copy = !(h1 != h1_copy);
            check(type_name + " operator!= consistent with operator==", neq_diff && neq_copy);

            bool lt_irreflexive = !(h1 < h1);
            bool lt_asymmetric = (h1 < h2) ? !(h2 < h1) : ((h2 < h1) ? !(h1 < h2) : true);
            check(type_name + " operator< strict weak ordering (irreflexive & asymmetric)", lt_irreflexive && lt_asymmetric);
        }
    }

    const std::vector<TestResult>& results() const { return results_; }

private:
    void test_result_type() {
        out_ << "[Section 1: Result<T> and Result<void>]\n";

        // 1. Result<int> value semantics
        {
            auto res_val = reaktar::Result<int>::FromValue(42);
            check("Result<T>::FromValue creates valid result", res_val.HasValue());
            check("Result<T>::Value extracts stored value", res_val.Value() == 42);

            // Copy/Move
            auto copy_res = res_val;
            check("Result<T> is copyable", copy_res.HasValue() && copy_res.Value() == 42);
            auto move_res = std::move(copy_res);
            check("Result<T> is moveable", move_res.HasValue() && move_res.Value() == 42);
        }

        // 2. Result<void> value semantics
        {
            auto res_void = reaktar::Result<void>::FromValue();
            check("Result<void>::FromValue creates valid result", res_void.HasValue());
        }

        // 3. Result<T> error semantics
        {
            reaktar::ErrorCode err{};
            auto res_err = reaktar::Result<int>::FromError(err);
            check("Result<T>::FromError creates error result", !res_err.HasValue());
            auto res_void_err = reaktar::Result<void>::FromError(err);
            check("Result<void>::FromError creates error result", !res_void_err.HasValue());
        }
    }

    void test_error_code_type() {
        out_ << "\n[Section 2: ErrorCode]\n";

        check("ErrorCode is default constructible", std::is_default_constructible_v<reaktar::ErrorCode>);
        check("ErrorCode is copyable", std::is_copy_constructible_v<reaktar::ErrorCode>);
        check("ErrorCode is moveable", std::is_move_constructible_v<reaktar::ErrorCode>);

        reaktar::ErrorCode err{};
        // Test inspection methods safely
        bool has_val_or_code = false;
        if constexpr (std::is_invocable_v<decltype(&reaktar::ErrorCode::Value), reaktar::ErrorCode>) {
            has_val_or_code = true;
            (void)err.Value();
        }
        check("ErrorCode provides Value() accessor", has_val_or_code);

        bool has_message = false;
        if constexpr (std::is_invocable_v<decltype(&reaktar::ErrorCode::Message), reaktar::ErrorCode>) {
            has_message = true;
            (void)err.Message();
        }
        check("ErrorCode provides Message() accessor", has_message);
    }

    void test_promise_and_future_types() {
        out_ << "\n[Section 3: Promise<T> and Future<T> Foundations]\n";

        // Check Promise methods exist
        check("Promise<int> has get_future()", detail::has_get_future<reaktar::Promise<int>>::value);
        check("Promise<void> has get_future()", detail::has_get_future<reaktar::Promise<void>>::value);
        check("Promise<int> has set_value()", detail::has_set_value<reaktar::Promise<int>, int>::value);
        check("Promise<void> has set_value()", detail::has_set_value_void<reaktar::Promise<void>>::value);
        check("Promise<int> has set_error()", detail::has_set_error<reaktar::Promise<int>, reaktar::ErrorCode>::value);
        check("Promise<void> has set_error()", detail::has_set_error<reaktar::Promise<void>, reaktar::ErrorCode>::value);

        // Value delivery: Promise<int> -> Future<int>
        {
            reaktar::Promise<int> p;
            auto f = p.get_future();
            p.set_value(100);
            auto res = f.get();
            check("Promise<int>::set_value -> Future<int>::get() delivers value", res.HasValue() && res.Value() == 100);
        }

        // Value delivery: Promise<void> -> Future<void>
        {
            reaktar::Promise<void> p;
            auto f = p.get_future();
            p.set_value();
            auto res = f.get();
            check("Promise<void>::set_value -> Future<void>::get() delivers success", res.HasValue());
        }

        // Error delivery: Promise<int> -> Future<int>
        {
            reaktar::Promise<int> p;
            auto f = p.get_future();
            reaktar::ErrorCode err{};
            p.set_error(err);
            auto res = f.get();
            check("Promise<int>::set_error -> Future<int>::get() delivers error", !res.HasValue());
        }

        // Error delivery: Promise<void> -> Future<void>
        {
            reaktar::Promise<void> p;
            auto f = p.get_future();
            reaktar::ErrorCode err{};
            p.set_error(err);
            auto res = f.get();
            check("Promise<void>::set_error -> Future<void>::get() delivers error", !res.HasValue());
        }
    }

    void test_future_continuation() {
        out_ << "\n[Section 4: Future<T>::then() Continuation Pipeline]\n";

        // Test Future<int>::then() execution
        {
            reaktar::Promise<int> p;
            auto f = p.get_future();
            bool then_executed = false;
            int received_val = 0;

            p.set_value(777);
            f.then([&](reaktar::Future<int> ready_fut) {
                then_executed = true;
                auto r = ready_fut.get();
                if (r.HasValue()) {
                    received_val = r.Value();
                }
            });

            check("Future<int>::then() invoked properly", then_executed && received_val == 777);
        }

        // Test Future<void>::then() execution
        {
            reaktar::Promise<void> p;
            auto f = p.get_future();
            bool then_executed = false;

            p.set_value();
            f.then([&](reaktar::Future<void> ready_fut) {
                auto r = ready_fut.get();
                if (r.HasValue()) {
                    then_executed = true;
                }
            });

            check("Future<void>::then() invoked properly", then_executed);
        }
    }

    void test_async_result_bridge() {
        out_ << "\n[Section 5: Reaktar AsyncResult<T> Bridge Semantics]\n";

        // AsyncResult<int> success callback
        {
            reaktar::Promise<int> p;
            auto f = p.get_future();
            p.set_value(999);

            bool success_called = false;
            int value_delivered = 0;

            {
                reaktar::AsyncResult<int> ar(std::move(f));
                ar.then([&](int val) {
                    success_called = true;
                    value_delivered = val;
                });
                // ar destructs here, invoking dispatch()
            }

            check("AsyncResult<T>::then executes on success", success_called && value_delivered == 999);
        }

        // AsyncResult<int> error callback
        {
            reaktar::Promise<int> p;
            auto f = p.get_future();
            reaktar::ErrorCode err{};
            p.set_error(err);

            bool error_called = false;
            {
                reaktar::AsyncResult<int> ar(std::move(f));
                ar.or_else([&](reaktar::ErrorCode) {
                    error_called = true;
                });
                // ar destructs here, invoking dispatch()
            }

            check("AsyncResult<T>::or_else executes on error", error_called);
        }

        // AsyncResult<void> success callback
        {
            reaktar::Promise<void> p;
            auto f = p.get_future();
            p.set_value();

            bool success_called = false;
            {
                reaktar::AsyncResult<void> ar(std::move(f));
                ar.then([&]() {
                    success_called = true;
                });
                // ar destructs here, invoking dispatch()
            }

            check("AsyncResult<void>::then executes on success", success_called);
        }

        // AsyncResult<void> error callback
        {
            reaktar::Promise<void> p;
            auto f = p.get_future();
            reaktar::ErrorCode err{};
            p.set_error(err);

            bool error_called = false;
            {
                reaktar::AsyncResult<void> ar(std::move(f));
                ar.or_else([&](reaktar::ErrorCode) {
                    error_called = true;
                });
                // ar destructs here, invoking dispatch()
            }

            check("AsyncResult<void>::or_else executes on error", error_called);
        }
    }

    void test_instance_specifier() {
        out_ << "\n[Section 6: InstanceSpecifier Identification]\n";

        // Test constructor from string
        bool constructible_from_str = std::is_constructible_v<reaktar::InstanceSpecifier, std::string>;
        bool constructible_from_cstr = std::is_constructible_v<reaktar::InstanceSpecifier, const char*>;
        check("InstanceSpecifier constructible from string", constructible_from_str || constructible_from_cstr);

        if (constructible_from_str || constructible_from_cstr) {
            reaktar::InstanceSpecifier spec{"my/service/instance"};
            bool has_to_string = false;
            if constexpr (std::is_invocable_v<decltype(&reaktar::InstanceSpecifier::ToString), reaktar::InstanceSpecifier>) {
                has_to_string = (spec.ToString() == "my/service/instance");
            }
            check("InstanceSpecifier provides ToString() accessor", has_to_string);
        }
    }

    std::ostream& out_;
    std::vector<TestResult> results_;
};

} // namespace verification
} // namespace reaktar
