// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

#include <type_traits>
#include <utility>
#include <memory>
#include <optional>
#include <mutex>
#include <condition_variable>
#include "reaktar/types.hpp"

namespace reaktar {

// SFINAE traits to detect if Derived has tagged `on(Tag, Arg)`
template <typename Derived, typename Tag, typename Arg, typename = void>
struct has_on_event : std::false_type {};

template <typename Derived, typename Tag, typename Arg>
struct has_on_event<Derived, Tag, Arg,
    std::void_t<decltype(std::declval<Derived&>().on(std::declval<Tag>(), std::declval<const Arg&>()))>>
    : std::true_type {};

template <typename Derived, typename Tag, typename Arg>
inline constexpr bool has_on_event_v = has_on_event<Derived, Tag, Arg>::value;

// strict_val prevents numeric conversions (e.g. bool -> float or uint32_t -> float)
template <typename Target>
struct strict_val {
    Target val{};
    operator Target&() & { return val; }
    operator const Target&() const& { return val; }
    operator Target&&() && { return std::move(val); }

    template <typename Other, typename = std::enable_if_t<!std::is_same_v<std::decay_t<Other>, Target>>>
    operator Other() const = delete;
    template <typename Other, typename = std::enable_if_t<!std::is_same_v<std::decay_t<Other>, Target>>>
    operator Other&() = delete;
};

// SFINAE traits to detect if Derived has direct `on(Arg)` without a tag (supports const Arg&, Arg by-value, etc.)
// Uses exact signature check to prevent implicit type conversions (e.g. uint32_t converting to float)
template <typename Derived, typename Arg>
class has_on_direct_event {
    template <typename D>
    static auto test(int) -> decltype(
        (void)(static_cast<void (D::*)(const Arg&)>(&D::on)),
        std::true_type{}
    );

    template <typename D>
    static auto test(long) -> decltype(
        (void)(static_cast<void (D::*)(Arg)>(&D::on)),
        std::true_type{}
    );

    template <typename>
    static auto test(...) -> std::false_type;

public:
    static constexpr bool value = decltype(test<Derived>(0))::value;
};

template <typename Derived, typename Arg>
inline constexpr bool has_on_direct_event_v = has_on_direct_event<Derived, Arg>::value;

template <typename T>
struct is_result : std::false_type {};

template <typename T>
struct is_result<reaktar::Result<T>> : std::true_type {};

template <typename T>
inline constexpr bool is_result_v = is_result<T>::value;

template <typename T>
struct is_future : std::false_type {};

template <typename T>
struct is_future<reaktar::Future<T>> : std::true_type {};

template <typename T>
inline constexpr bool is_future_v = is_future<T>::value;

template <typename T>
struct future_traits;

template <typename T>
struct future_traits<reaktar::Future<T>> {
    using value_type = T;
};



// Helper for making future values in a vendor-adaptable way
template <typename ValType>
struct make_future_adapter {
    static reaktar::Future<ValType> make(ValType&& val) {
        reaktar::Promise<ValType> p;
        p.set_value(std::forward<ValType>(val));
        return p.get_future();
    }
    static reaktar::Future<ValType> make(const ValType& val) {
        ValType copy = val;
        return make(std::move(copy));
    }
    template <typename ResType>
    static reaktar::Future<ValType> from_result(ResType&& res) {
        reaktar::Promise<ValType> p;
        if (res.HasValue()) {
            p.set_value(std::forward<ResType>(res).Value());
        } else {
            p.SetError(std::forward<ResType>(res).Error());
        }
        return p.get_future();
    }
    static reaktar::Future<ValType> from_error(reaktar::ErrorCode err) {
        reaktar::Promise<ValType> p;
        p.SetError(std::move(err));
        return p.get_future();
    }
};

template <>
struct make_future_adapter<void> {
    static reaktar::Future<void> make() {
        reaktar::Promise<void> p;
        p.set_value();
        return p.get_future();
    }
    template <typename ResType>
    static reaktar::Future<void> from_result(ResType&& res) {
        reaktar::Promise<void> p;
        if (res.HasValue()) {
            p.set_value();
        } else {
            p.SetError(std::forward<ResType>(res).Error());
        }
        return p.get_future();
    }
    static reaktar::Future<void> from_error(reaktar::ErrorCode err) {
        reaktar::Promise<void> p;
        p.SetError(std::move(err));
        return p.get_future();
    }
};

// Helper to normalize any return type R into ExpectedType
// If user returned ExpectedType directly, pass it through.
// If ExpectedType is reaktar::Future<T>, wrap the value into Future.
// If ExpectedType has FromValue (like Result types), construct it.
template <typename ExpectedType, typename ReturnType, typename = void>
struct result_adapter {
    static ExpectedType adapt(ReturnType&& val) {
        if constexpr (std::is_same_v<std::decay_t<ReturnType>, std::decay_t<ExpectedType>>) {
            return std::forward<ReturnType>(val);
        } else if constexpr (std::is_convertible_v<ReturnType, ExpectedType>) {
            return static_cast<ExpectedType>(std::forward<ReturnType>(val));
        } else if constexpr (is_future_v<ExpectedType>) {
            using FutValType = typename future_traits<ExpectedType>::value_type;
            using DecayedRet = std::decay_t<ReturnType>;
            if constexpr (is_result_v<DecayedRet>) {
                using ResValType = typename DecayedRet::value_type;
                if constexpr (std::is_same_v<FutValType, ResValType>) {
                    return make_future_adapter<FutValType>::from_result(std::forward<ReturnType>(val));
                } else if constexpr (std::is_constructible_v<FutValType, ResValType>) {
                    if (val.HasValue()) {
                        if constexpr (std::is_void_v<ResValType>) {
                            return make_future_adapter<FutValType>::make(FutValType{});
                        } else {
                            return make_future_adapter<FutValType>::make(FutValType(val.Value()));
                        }
                    } else {
                        return make_future_adapter<FutValType>::from_error(val.Error());
                    }
                } else {
                    return make_future_adapter<FutValType>::make(FutValType{});
                }
            } else {
                using DecayedVal = std::decay_t<FutValType>;
                if constexpr (std::is_same_v<std::decay_t<ReturnType>, DecayedVal> || std::is_convertible_v<ReturnType, DecayedVal>) {
                    return make_future_adapter<DecayedVal>::make(static_cast<DecayedVal>(std::forward<ReturnType>(val)));
                } else if constexpr (std::is_constructible_v<DecayedVal, ReturnType>) {
                    return make_future_adapter<DecayedVal>::make(DecayedVal{std::forward<ReturnType>(val)});
                } else {
                    return make_future_adapter<DecayedVal>::make(DecayedVal{});
                }
            }
        } else if constexpr (is_result_v<ExpectedType>) {
            return ExpectedType::FromValue(std::forward<ReturnType>(val));
        } else {
            return ExpectedType{std::forward<ReturnType>(val)};
        }
    }
};

// Specialization when ReturnType is already ExpectedType
template <typename ExpectedType>
struct result_adapter<ExpectedType, ExpectedType, void> {
    static ExpectedType adapt(ExpectedType&& val) {
        return std::move(val);
    }
    static const ExpectedType& adapt(const ExpectedType& val) {
        return val;
    }
};

// Specialization when ExpectedType is reaktar::Result<T> and ReturnType is void
template <typename T>
struct result_adapter<reaktar::Result<T>, void, void> {
    template <typename... Ignored>
    static reaktar::Result<T> adapt(Ignored&&...) {
        if constexpr (std::is_void_v<T>) {
            return reaktar::Result<void>::FromValue();
        } else {
            return reaktar::Result<T>::FromValue(T{});
        }
    }
};

// Specialization when ExpectedType is reaktar::Future<T> and ReturnType is void
template <typename T>
struct result_adapter<reaktar::Future<T>, void, void> {
    template <typename... Ignored>
    static reaktar::Future<T> adapt(Ignored&&...) {
        if constexpr (std::is_void_v<T>) {
            return make_future_adapter<void>::make();
        } else {
            return make_future_adapter<T>::make(T{});
        }
    }
};

// Fallback specialization when ReturnType is void, ExpectedType is not void, and ExpectedType is neither Result nor Future
template <typename ExpectedType>
struct result_adapter<ExpectedType, void, std::enable_if_t<!std::is_void_v<ExpectedType> && !is_result_v<ExpectedType> && !is_future_v<ExpectedType>>> {
    template <typename... Ignored>
    static ExpectedType adapt(Ignored&&...) {
        if constexpr (std::is_default_constructible_v<ExpectedType>) {
            return ExpectedType{};
        } else {
            return ExpectedType::FromValue();
        }
    }
};

// Specialization for void expected types
template <typename ReturnType>
struct result_adapter<void, ReturnType, void> {
    static void adapt(ReturnType&&) {}
    static void adapt() {}
};

// SFINAE traits to detect if Derived has tagged method handler: `on(MethodTag, Args...)`
template <typename Derived, typename Tag, typename... Args>
class has_method_handler {
    template <typename D>
    static auto test(int) -> decltype(std::declval<D&>().on(std::declval<Tag>(), std::declval<Args>()...), std::true_type{});

    template <typename>
    static auto test(...) -> std::false_type;

public:
    static constexpr bool value = decltype(test<Derived>(0))::value;
};

template <typename Derived, typename Tag, typename... Args>
inline constexpr bool has_method_handler_v = has_method_handler<Derived, Tag, Args...>::value;


// SFINAE traits to detect if Derived has direct method handler without tag: `on(Args...)`
template <typename Derived, typename... Args>
class has_direct_method_handler {
    template <typename D>
    static auto test(int) -> decltype(std::declval<D&>().on(std::declval<Args>()...), std::true_type{});

    template <typename>
    static auto test(...) -> std::false_type;

public:
    static constexpr bool value = decltype(test<Derived>(0))::value;
};

template <typename Derived, typename... Args>
inline constexpr bool has_direct_method_handler_v = has_direct_method_handler<Derived, Args...>::value;

// SFINAE traits to detect field setter handler: `Result<T> on_set(FieldTag, const T&)`
template <typename Derived, typename Tag, typename ValueType, typename = void>
struct has_on_field_set : std::false_type {};

template <typename Derived, typename Tag, typename ValueType>
struct has_on_field_set<Derived, Tag, ValueType,
    std::void_t<decltype(std::declval<Derived&>().on_set(std::declval<Tag>(), std::declval<const ValueType&>()))>>
    : std::true_type {};

template <typename Derived, typename Tag, typename ValueType>
inline constexpr bool has_on_field_set_v = has_on_field_set<Derived, Tag, ValueType>::value;

// SFINAE traits to detect direct field setter handler without tag: `Result<T> on_set(const T&)` or `on_set(T)`
template <typename Derived, typename ValueType>
class has_on_direct_field_set {
    template <typename D>
    static auto test(int) -> decltype(std::declval<D&>().on_set(std::declval<const ValueType&>()), std::true_type{});

    template <typename D>
    static auto test(long) -> decltype(std::declval<D&>().on_set(std::declval<ValueType>()), std::true_type{});

    template <typename>
    static auto test(...) -> std::false_type;

public:
    static constexpr bool value = decltype(test<Derived>(0))::value;
};

template <typename Derived, typename ValueType>
inline constexpr bool has_on_direct_field_set_v = has_on_direct_field_set<Derived, ValueType>::value;


/**
 * @brief Zero-overhead status for one-way / fire-and-forget dispatches (methods and events).
 *
 * Exactly 1 byte in size. Passed in a CPU register (e.g. %al / w0).
 * Completely optimized away by the compiler when unchecked.
 *
 * Supports:
 * - explicit operator bool() / ok() for `if (!emit(...))`
 * - .or_else([]() { ... }) for immediate inline fallback if proxy is missing
 * - Purposely does NOT have .then() or .get() to prevent false async assumptions.
 */
struct EmitStatus {
    bool ok_{false};

    constexpr explicit EmitStatus(bool ok = false) noexcept : ok_(ok) {}

    constexpr explicit operator bool() const noexcept { return ok_; }
    constexpr bool ok() const noexcept { return ok_; }

    template <typename ErrorCallback>
    void or_else(ErrorCallback&& cb) const {
        if (!ok_) {
            std::forward<ErrorCallback>(cb)();
        }
    }
};

/**
 * @brief Zero-overhead, zero-heap Async Result wrapper for AUTOSAR Adaptive RPC invocations.
 *
 * - Wraps vendor Future directly with zero heap allocations, zero std::function, zero mutex locks.
 * - Supports explicit operator bool() / ok() for `if (!emit(...))` synchronous check.
 * - `.then(fn)`: Direct pass-through to vanilla AUTOSAR Future::then(fn) (receives Future<T> / Result<T>).
 * - `.on_success(fn)`: Syntactic sugar that automatically unwraps Result and invokes fn(val) on success only.
 * - `.on_failure(fn)`: Syntactic sugar that invokes fn(ErrorCode) on failure or when proxy is missing.
 * - Non-chainable / terminal to completely eliminate type erasure and expression template overhead.
 */
template <typename T>
class AsyncResult {
private:
    reaktar::Future<T> future_{};
    bool is_valid_{false};

public:
    AsyncResult() noexcept : is_valid_(false) {}

    explicit AsyncResult(reaktar::Future<T> future)
        : future_(std::move(future)), is_valid_(true) {}

    ~AsyncResult() = default;

    AsyncResult(AsyncResult&& other) noexcept
        : future_(std::move(other.future_)),
          is_valid_(other.is_valid_) {
        other.is_valid_ = false;
    }

    AsyncResult& operator=(AsyncResult&& other) noexcept {
        if (this != &other) {
            future_ = std::move(other.future_);
            is_valid_ = other.is_valid_;
            other.is_valid_ = false;
        }
        return *this;
    }

    AsyncResult(const AsyncResult&) = delete;
    AsyncResult& operator=(const AsyncResult&) = delete;

    static AsyncResult<T> Failed() noexcept {
        return AsyncResult<T>{};
    }

    constexpr explicit operator bool() const noexcept { return is_valid_; }
    constexpr bool ok() const noexcept { return is_valid_; }

    /**
     * @brief Vanilla AUTOSAR Future pass-through.
     * Passes the callback directly into the vendor future without storage or intermediate wrappers.
     */
    template <typename Callback>
    auto then(Callback&& cb) {
        if (!is_valid_) {
            using RetType = decltype(std::declval<reaktar::Future<T>&>().then(std::forward<Callback>(cb)));
            if constexpr (!std::is_void_v<RetType>) {
                return RetType{};
            } else {
                return;
            }
        }
        return future_.then(std::forward<Callback>(cb));
    }

    /**
     * @brief Sugar for handling only success (unwrapped T or void).
     */
    template <typename Callback>
    void on_success(Callback&& cb) {
        if (!is_valid_) return;
        future_.then([c = std::forward<Callback>(cb)](reaktar::Future<T> f) mutable {
            auto res = f.GetResult();
            if (res.HasValue()) {
                if constexpr (std::is_void_v<T>) {
                    c();
                } else {
                    c(res.Value());
                }
            }
        });
    }

    /**
     * @brief Sugar for handling only failure (passes ErrorCode, or default/optional if invocable).
     */
    template <typename ErrorCallback>
    void on_failure(ErrorCallback&& cb) {
        if (!is_valid_) {
            if constexpr (std::is_invocable_v<ErrorCallback>) {
                std::forward<ErrorCallback>(cb)();
            } else if constexpr (std::is_invocable_v<ErrorCallback, std::optional<reaktar::ErrorCode>>) {
                std::forward<ErrorCallback>(cb)(std::nullopt);
            }
            return;
        }
        future_.then([c = std::forward<ErrorCallback>(cb)](reaktar::Future<T> f) mutable {
            auto res = f.GetResult();
            if (!res.HasValue()) {
                if constexpr (std::is_invocable_v<ErrorCallback>) {
                    c();
                } else if constexpr (std::is_invocable_v<ErrorCallback, std::optional<reaktar::ErrorCode>>) {
                    c(res.Error());
                } else if constexpr (std::is_invocable_v<ErrorCallback, reaktar::ErrorCode>) {
                    c(res.Error());
                }
            }
        });
    }

    T get() {
        if (!is_valid_) {
            if constexpr (!std::is_void_v<T>) {
                return T{};
            } else {
                return;
            }
        }
        auto res = future_.GetResult();
        if constexpr (!std::is_void_v<T>) {
            if (res.HasValue()) {
                return res.Value();
            }
            return T{};
        }
    }

    reaktar::Future<T>& raw_future() noexcept {
        return future_;
    }
};

// C++17 Deduction Guide for AsyncResult
template <typename T>
AsyncResult(reaktar::Future<T>) -> AsyncResult<T>;

template <typename T>
auto make_async_result(reaktar::Future<T> future) {
    return AsyncResult<T>(std::move(future));
}

// ============================================================================
// Compile-time Rogue / Orphan Handler Detection
// ============================================================================

// Signature descriptor
template <typename... Args>
struct sig {};

template <typename Sig>
struct decay_sig;

template <typename... Args>
struct decay_sig<sig<Args...>> {
    using type = sig<std::decay_t<Args>...>;
};

// Check if a signature exists in LegalSigs
template <typename Candidate, typename LegalSigsTuple>
struct is_legal_signature;

template <typename... CandidateArgs, typename... LegalSigs>
struct is_legal_signature<sig<CandidateArgs...>, std::tuple<LegalSigs...>> {
    static constexpr bool value = (std::is_same_v<
        sig<std::decay_t<CandidateArgs>...>,
        typename decay_sig<LegalSigs>::type
    > || ...);
};

// Check if a call signature or arguments are legal for an actor or signature tuple
template <typename SigsOrActor, typename... Args>
struct is_legal_call {
private:
    template <typename T, typename = void>
    struct extract_sigs {
        using type = T;
    };
    template <typename T>
    struct extract_sigs<T, std::void_t<typename T::legal_signatures>> {
        using type = typename T::legal_signatures;
    };
    using Sigs = typename extract_sigs<SigsOrActor>::type;
public:
    static constexpr bool value = is_legal_signature<sig<std::decay_t<Args>...>, Sigs>::value;
};

template <typename SigsOrActor, typename... Args>
inline constexpr bool is_legal_call_v = is_legal_call<SigsOrActor, Args...>::value;

template <typename SigsOrActor, typename... Args>
inline constexpr bool is_legal_signature_v = is_legal_call<SigsOrActor, Args...>::value;

// Check if LegalSigs has any signature with arity N
template <std::size_t N, typename LegalSigsTuple>
struct has_signature_with_arity;

template <std::size_t N, typename... LegalSigs>
struct has_signature_with_arity<N, std::tuple<LegalSigs...>> {
    template <typename S>
    struct sig_size;
    template <typename... Args>
    struct sig_size<sig<Args...>> : std::integral_constant<std::size_t, sizeof...(Args)> {};

    static constexpr bool value = ((sig_size<LegalSigs>::value == N) || ...);
};

// Probe type that converts to ANY type T except the whitelisted legal types
template <typename... LegalTypes>
struct illegal_probe {
    template <typename T,
              typename = std::enable_if_t<(!std::is_same_v<std::decay_t<T>, LegalTypes> && ...)>>
    operator T() const;

    template <typename T,
              typename = std::enable_if_t<(!std::is_same_v<std::decay_t<T>, LegalTypes> && ...)>>
    operator T&();
};

// Universal probe type that converts to anything
struct universal_probe {
    template <typename T>
    operator T() const;

    template <typename T>
    operator T&();
};

// Domain partitioning: distinguish tag types (empty structs) from payload types
template <typename T>
struct is_tag_type : std::bool_constant<std::is_empty_v<T> && !std::is_arithmetic_v<T> && !std::is_enum_v<T>> {};

template <typename T>
inline constexpr bool is_tag_type_v = is_tag_type<T>::value;

template <typename... Ts>
struct type_list {};

template <typename List, typename T>
struct list_append;

template <typename... Ts, typename T>
struct list_append<type_list<Ts...>, T> {
    using type = type_list<Ts..., T>;
};

template <typename InList, typename FilterList = type_list<>, typename RestList = type_list<>>
struct partition_tags;

template <typename FilterList, typename RestList>
struct partition_tags<type_list<>, FilterList, RestList> {
    using tags = FilterList;
    using payloads = RestList;
};

template <typename Head, typename... Tail, typename FilterList, typename RestList>
struct partition_tags<type_list<Head, Tail...>, FilterList, RestList> {
private:
    using next_tags = std::conditional_t<
        is_tag_type_v<Head>,
        typename list_append<FilterList, Head>::type,
        FilterList>;
    using next_payloads = std::conditional_t<
        !is_tag_type_v<Head>,
        typename list_append<RestList, Head>::type,
        RestList>;
public:
    using tags = typename partition_tags<type_list<Tail...>, next_tags, next_payloads>::tags;
    using payloads = typename partition_tags<type_list<Tail...>, next_tags, next_payloads>::payloads;
};

// SFINAE test for 1 argument with strict values
template <typename App, typename T, typename = void>
struct is_callable_1arg : std::false_type {};

template <typename App, typename T>
struct is_callable_1arg<App, T,
    std::void_t<decltype(std::declval<App&>().on(std::declval<strict_val<T>&>()))>>
    : std::true_type {};

template <typename App, typename LegalSigsTuple, typename T>
constexpr bool check_single_rogue() {
    if constexpr (is_callable_1arg<App, T>::value) {
        return !is_legal_signature<sig<T>, LegalSigsTuple>::value;
    }
    return false;
}

template <typename App, typename LegalSigsTuple, typename... Ts>
struct illegal_combo_checker_1arg {
    static constexpr bool value = (check_single_rogue<App, LegalSigsTuple, Ts>() || ...);
};

// SFINAE test for 2 arguments with strict values
template <typename App, typename T1, typename T2, typename = void>
struct is_callable_2arg : std::false_type {};

template <typename App, typename T1, typename T2>
struct is_callable_2arg<App, T1, T2,
    std::void_t<decltype(std::declval<App&>().on(std::declval<strict_val<T1>&>(), std::declval<strict_val<T2>&>()))>>
    : std::true_type {};

template <typename App, typename LegalSigsTuple, typename T1, typename T2>
constexpr bool check_pair_rogue() {
    if constexpr (is_callable_2arg<App, T1, T2>::value) {
        return !is_legal_signature<sig<T1, T2>, LegalSigsTuple>::value;
    }
    return false;
}

template <typename App, typename Tag, typename = void>
struct has_arg2_tag_handler : std::false_type {};

template <typename App, typename Tag>
struct has_arg2_tag_handler<App, Tag,
    std::void_t<decltype(std::declval<App&>().on(std::declval<universal_probe>(), std::declval<strict_val<Tag>&>()))>>
    : std::true_type {};

template <typename App, typename LegalSigsTuple, typename TagList, typename PayloadList>
struct illegal_combo_checker_2arg_partitioned;

template <typename App, typename LegalSigsTuple, typename... Tags, typename... Payloads>
struct illegal_combo_checker_2arg_partitioned<App, LegalSigsTuple, type_list<Tags...>, type_list<Payloads...>> {
    static constexpr bool has_arg2_tag = (has_arg2_tag_handler<App, Tags>::value || ...);

    template <typename Tag>
    static constexpr bool check_tag_row() {
        return (check_pair_rogue<App, LegalSigsTuple, Tag, Payloads>() || ...);
    }
    static constexpr bool has_bad_tag_payload = (check_tag_row<Tags>() || ...);

    template <typename P1>
    static constexpr bool check_payload_row() {
        return (check_pair_rogue<App, LegalSigsTuple, P1, Payloads>() || ...);
    }
    static constexpr bool has_bad_payload_payload = (check_payload_row<Payloads>() || ...);

    static constexpr bool value = has_arg2_tag || has_bad_tag_payload || has_bad_payload_payload;
};

template <typename App, typename LegalSigsTuple, typename... Ts>
struct fast_combo_checker_2arg {
    static constexpr bool value = []() constexpr {
        if constexpr (!has_signature_with_arity<2, LegalSigsTuple>::value) {
            return false;
        } else {
            using P = partition_tags<type_list<Ts...>>;
            return illegal_combo_checker_2arg_partitioned<
                App, LegalSigsTuple, typename P::tags, typename P::payloads>::value;
        }
    }();
};

template <typename App, typename LegalSigsTuple, typename... Ts>
using illegal_combo_checker_2arg = fast_combo_checker_2arg<App, LegalSigsTuple, Ts...>;

// SFINAE test for 3 arguments with strict values
template <typename App, typename T1, typename T2, typename T3, typename = void>
struct is_callable_3arg : std::false_type {};

template <typename App, typename T1, typename T2, typename T3>
struct is_callable_3arg<App, T1, T2, T3,
    std::void_t<decltype(std::declval<App&>().on(std::declval<strict_val<T1>&>(), std::declval<strict_val<T2>&>(), std::declval<strict_val<T3>&>()))>>
    : std::true_type {};

template <typename App, typename LegalSigsTuple, typename T1, typename T2, typename T3>
constexpr bool check_triplet_rogue() {
    if constexpr (is_callable_3arg<App, T1, T2, T3>::value) {
        return !is_legal_signature<sig<T1, T2, T3>, LegalSigsTuple>::value;
    }
    return false;
}

template <typename App, typename Tag, typename = void>
struct has_arg2_tag_handler_3arg : std::false_type {};

template <typename App, typename Tag>
struct has_arg2_tag_handler_3arg<App, Tag,
    std::void_t<decltype(
        std::declval<App&>().on(std::declval<universal_probe>(), std::declval<strict_val<Tag>&>(), std::declval<universal_probe>())
    )>>
    : std::true_type {};

template <typename App, typename Tag, typename = void>
struct has_arg3_tag_handler_3arg : std::false_type {};

template <typename App, typename Tag>
struct has_arg3_tag_handler_3arg<App, Tag,
    std::void_t<decltype(
        std::declval<App&>().on(std::declval<universal_probe>(), std::declval<universal_probe>(), std::declval<strict_val<Tag>&>())
    )>>
    : std::true_type {};

template <typename App, typename LegalSigsTuple, typename AllTypesList, typename TagList, typename PayloadList>
struct illegal_combo_checker_3arg_partitioned;

template <typename App, typename LegalSigsTuple, typename... AllTypes, typename... Tags, typename... Payloads>
struct illegal_combo_checker_3arg_partitioned<App, LegalSigsTuple, type_list<AllTypes...>, type_list<Tags...>, type_list<Payloads...>> {
    static constexpr bool has_bad_tag_pos = (has_arg2_tag_handler_3arg<App, Tags>::value || ...) ||
                                            (has_arg3_tag_handler_3arg<App, Tags>::value || ...);

    template <typename T1, typename P2>
    static constexpr bool check_col() {
        return (check_triplet_rogue<App, LegalSigsTuple, T1, P2, Payloads>() || ...);
    }
    template <typename T1>
    static constexpr bool check_plane() {
        return (check_col<T1, Payloads>() || ...);
    }
    static constexpr bool has_bad_triplets = (check_plane<AllTypes>() || ...);

    static constexpr bool value = has_bad_tag_pos || has_bad_triplets;
};

template <typename App, typename LegalSigsTuple, typename... Ts>
struct fast_combo_checker_3arg {
    static constexpr bool value = []() constexpr {
        if constexpr (!has_signature_with_arity<3, LegalSigsTuple>::value) {
            return false;
        } else {
            using P = partition_tags<type_list<Ts...>>;
            return illegal_combo_checker_3arg_partitioned<
                App, LegalSigsTuple, type_list<Ts...>, typename P::tags, typename P::payloads>::value;
        }
    }();
};

template <typename App, typename LegalSigsTuple, typename... Ts>
using illegal_combo_checker_3arg = fast_combo_checker_3arg<App, LegalSigsTuple, Ts...>;

// SFINAE detector for rogue / orphan on(...) declarations
template <typename App, typename LegalSigsTuple, typename... LegalTypes>
class rogue_handler_detector {
    using Bad = illegal_probe<LegalTypes...>;
    using Any = universal_probe;

    // Test 1: Single argument on(Bad) - catches rogue event/field types, primitives, typos
    template <typename A>
    static auto test_1arg_bad(int) -> decltype(std::declval<A&>().on(std::declval<Bad>()), std::true_type{});
    template <typename>
    static auto test_1arg_bad(...) -> std::false_type;

    // Test 2: Two arguments with rogue type: on(Bad, Any), on(Any, Bad)
    template <typename A>
    static auto test_2arg_bad1(int) -> decltype(std::declval<A&>().on(std::declval<Bad>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_2arg_bad1(...) -> std::false_type;

    template <typename A>
    static auto test_2arg_bad2(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Bad>()), std::true_type{});
    template <typename>
    static auto test_2arg_bad2(...) -> std::false_type;

    // Test 2b: Any 2-argument handler (used when actor has zero legal 2-arg signatures)
    template <typename A>
    static auto test_2arg_any(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_2arg_any(...) -> std::false_type;

    // Test 3: Three arguments with rogue type: on(Bad, Any, Any), on(Any, Bad, Any), on(Any, Any, Bad)
    template <typename A>
    static auto test_3arg_bad1(int) -> decltype(std::declval<A&>().on(std::declval<Bad>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_3arg_bad1(...) -> std::false_type;

    template <typename A>
    static auto test_3arg_bad2(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Bad>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_3arg_bad2(...) -> std::false_type;

    template <typename A>
    static auto test_3arg_bad3(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Any>(), std::declval<Bad>()), std::true_type{});
    template <typename>
    static auto test_3arg_bad3(...) -> std::false_type;

    // Test 3b: Any 3-argument handler (used when actor has zero legal 3-arg signatures)
    template <typename A>
    static auto test_3arg_any(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Any>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_3arg_any(...) -> std::false_type;

    // Test 4: Four arguments (any 4-arg on(...) handler)
    template <typename A>
    static auto test_4arg_bad(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Any>(), std::declval<Any>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_4arg_bad(...) -> std::false_type;

    static constexpr bool check_rogue() {
        if (decltype(test_1arg_bad<App>(0))::value) return true;
        if (illegal_combo_checker_1arg<App, LegalSigsTuple, LegalTypes...>::value) return true;

        if constexpr (!has_signature_with_arity<2, LegalSigsTuple>::value) {
            if (decltype(test_2arg_any<App>(0))::value) return true;
        } else {
            if (decltype(test_2arg_bad1<App>(0))::value) return true;
            if (decltype(test_2arg_bad2<App>(0))::value) return true;
            if (fast_combo_checker_2arg<App, LegalSigsTuple, LegalTypes...>::value) return true;
        }

        if constexpr (!has_signature_with_arity<3, LegalSigsTuple>::value) {
            if (decltype(test_3arg_any<App>(0))::value) return true;
        } else {
            if (decltype(test_3arg_bad1<App>(0))::value) return true;
            if (decltype(test_3arg_bad2<App>(0))::value) return true;
            if (decltype(test_3arg_bad3<App>(0))::value) return true;
            if (fast_combo_checker_3arg<App, LegalSigsTuple, LegalTypes...>::value) return true;
        }

        if constexpr (!has_signature_with_arity<4, LegalSigsTuple>::value) {
            if (decltype(test_4arg_bad<App>(0))::value) return true;
        }

        return false;
    }

public:
    static constexpr bool has_rogue = check_rogue();
};

template <typename App, typename LegalSigsTuple, typename... LegalTypes>
inline constexpr bool has_rogue_handler_v = rogue_handler_detector<App, LegalSigsTuple, LegalTypes...>::has_rogue;

} // namespace reaktar


