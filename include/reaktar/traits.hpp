// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// Copyright (c) 2026 Pyarx Lab. Licensed under the MIT License.
// ==============================================================================

#pragma once

#include <type_traits>
#include <utility>
#include <memory>
#include <functional>
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
        using ResType = reaktar::Result<ValType>;
        reaktar::Promise<ValType> p;
        p.set_value(ResType::FromValue(std::forward<ValType>(val)));
        return p.get_future();
    }
    static reaktar::Future<ValType> make(const ValType& val) {
        ValType copy = val;
        return make(std::move(copy));
    }
    template <typename ResType>
    static reaktar::Future<ValType> from_result(ResType&& res) {
        reaktar::Promise<ValType> p;
        p.set_value(std::forward<ResType>(res));
        return p.get_future();
    }
    static reaktar::Future<ValType> from_error(reaktar::ErrorCode err) {
        reaktar::Promise<ValType> p;
        p.set_error(std::move(err));
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
        p.set_value(std::forward<ResType>(res));
        return p.get_future();
    }
    static reaktar::Future<void> from_error(reaktar::ErrorCode err) {
        reaktar::Promise<void> p;
        p.set_error(std::move(err));
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
 * @brief Ergonomic Async Result continuation wrapper.
 * Returned when emitting an RPC request.
 * - Wraps vendor Future directly with zero heap allocations and zero mutex locks.
 * - Relies on AUTOSAR Adaptive's threading and continuation model.
 * - Allows .then([this](T val) { ... }) with unwrapped value
 * - Allows .or_else([this](ErrorCode err) { ... })
 * - Allows .get() for synchronous blocking wait
 * - Can be safely discarded for fire-and-forget
 */
template <typename T>
class AsyncContinuation;

template <typename T>
class AsyncResult {
    friend class AsyncContinuation<T>;
private:
    reaktar::Future<T> future_{};
    bool is_valid_{false};
    bool dispatched_{false};
    std::function<void(T)> on_success_{};
    std::function<void(reaktar::ErrorCode)> on_error_{};
    std::function<void()> on_error_void_{};

    template <typename Callback>
    void set_then(Callback&& cb) {
        if (!is_valid_) return;
        on_success_ = std::forward<Callback>(cb);
    }

    template <typename ErrorCallback>
    void set_or_else(ErrorCallback&& cb) {
        if (!is_valid_) {
            if constexpr (std::is_invocable_v<ErrorCallback, reaktar::ErrorCode>) {
                cb(reaktar::ErrorCode{});
            } else {
                cb();
            }
            return;
        }
        if constexpr (std::is_invocable_v<ErrorCallback, reaktar::ErrorCode>) {
            on_error_ = std::forward<ErrorCallback>(cb);
        } else {
            on_error_void_ = [c = std::forward<ErrorCallback>(cb)]() mutable { c(); };
        }
    }

    void dispatch() {
        if (!is_valid_ || dispatched_) return;
        if (!on_success_ && !on_error_ && !on_error_void_) return;
        dispatched_ = true;
        future_.then([s = std::move(on_success_),
                      e = std::move(on_error_),
                      ev = std::move(on_error_void_)](reaktar::Future<T> f) mutable {
            auto res = f.get();
            if (res.HasValue()) {
                if constexpr (!std::is_void_v<T>) {
                    if (s) s(res.Value());
                } else {
                    if (s) s();
                }
            } else {
                if (e) e(res.Error());
                else if (ev) ev();
            }
        });
    }

public:
    AsyncResult() noexcept : is_valid_(false) {}

    explicit AsyncResult(reaktar::Future<T> future)
        : future_(std::move(future)), is_valid_(true) {}

    ~AsyncResult() {
        dispatch();
    }

    AsyncResult(AsyncResult&& other) noexcept
        : future_(std::move(other.future_)),
          is_valid_(other.is_valid_),
          dispatched_(other.dispatched_),
          on_success_(std::move(other.on_success_)),
          on_error_(std::move(other.on_error_)),
          on_error_void_(std::move(other.on_error_void_)) {
        other.is_valid_ = false;
        other.dispatched_ = true;
    }

    AsyncResult& operator=(AsyncResult&& other) noexcept {
        if (this != &other) {
            dispatch();
            future_ = std::move(other.future_);
            is_valid_ = other.is_valid_;
            dispatched_ = other.dispatched_;
            on_success_ = std::move(other.on_success_);
            on_error_ = std::move(other.on_error_);
            on_error_void_ = std::move(other.on_error_void_);
            other.is_valid_ = false;
            other.dispatched_ = true;
        }
        return *this;
    }

    AsyncResult(const AsyncResult&) = delete;
    AsyncResult& operator=(const AsyncResult&) = delete;

    static AsyncResult<T> Failed() noexcept {
        return AsyncResult<T>{};
    }

    explicit operator bool() const noexcept { return is_valid_; }
    bool ok() const noexcept { return is_valid_; }

    template <typename Callback>
    AsyncContinuation<T> then(Callback&& cb) {
        set_then(std::forward<Callback>(cb));
        return AsyncContinuation<T>(this);
    }

    template <typename ErrorCallback>
    AsyncContinuation<T> or_else(ErrorCallback&& cb) {
        set_or_else(std::forward<ErrorCallback>(cb));
        return AsyncContinuation<T>(this);
    }

    T get() {
        if (!is_valid_) return T{};
        if (dispatched_) return T{};
        auto res = future_.get();
        if (res.HasValue()) {
            return res.Value();
        }
        return T{};
    }

    reaktar::Future<T>& raw_future() noexcept {
        return future_;
    }
};

template <typename T>
class AsyncContinuation {
private:
    AsyncResult<T>* parent_{nullptr};
public:
    explicit AsyncContinuation(AsyncResult<T>* parent) noexcept : parent_(parent) {}
    ~AsyncContinuation() {
        if (parent_) parent_->dispatch();
    }
    AsyncContinuation(AsyncContinuation&& o) noexcept : parent_(o.parent_) {
        o.parent_ = nullptr;
    }
    AsyncContinuation& operator=(AsyncContinuation&& o) noexcept {
        if (this != &o) {
            if (parent_) parent_->dispatch();
            parent_ = o.parent_;
            o.parent_ = nullptr;
        }
        return *this;
    }
    AsyncContinuation(const AsyncContinuation&) = delete;
    AsyncContinuation& operator=(const AsyncContinuation&) = delete;

    template <typename Callback>
    AsyncContinuation& then(Callback&& cb) {
        if (parent_) parent_->set_then(std::forward<Callback>(cb));
        return *this;
    }

    template <typename ErrorCallback>
    AsyncContinuation& or_else(ErrorCallback&& cb) {
        if (parent_) parent_->set_or_else(std::forward<ErrorCallback>(cb));
        return *this;
    }

    explicit operator bool() const noexcept { return parent_ ? bool(*parent_) : false; }
    bool ok() const noexcept { return parent_ ? parent_->ok() : false; }

    T get() {
        if (parent_) {
            parent_->dispatch();
            return parent_->get();
        }
        return T{};
    }

    reaktar::Future<T>& raw_future() noexcept {
        static reaktar::Future<T> s_empty{};
        return parent_ ? parent_->raw_future() : s_empty;
    }
};

// AsyncResult specialization for void RPC methods
template <>
class AsyncContinuation<void>;

template <>
class AsyncResult<void> {
    friend class AsyncContinuation<void>;
private:
    reaktar::Future<void> future_{};
    bool is_valid_{false};
    bool dispatched_{false};
    std::function<void()> on_success_{};
    std::function<void(reaktar::ErrorCode)> on_error_{};
    std::function<void()> on_error_void_{};

    template <typename Callback>
    void set_then(Callback&& cb) {
        if (!is_valid_) return;
        on_success_ = std::forward<Callback>(cb);
    }

    template <typename ErrorCallback>
    void set_or_else(ErrorCallback&& cb) {
        if (!is_valid_) {
            if constexpr (std::is_invocable_v<ErrorCallback, reaktar::ErrorCode>) {
                cb(reaktar::ErrorCode{});
            } else {
                cb();
            }
            return;
        }
        if constexpr (std::is_invocable_v<ErrorCallback, reaktar::ErrorCode>) {
            on_error_ = std::forward<ErrorCallback>(cb);
        } else {
            on_error_void_ = [c = std::forward<ErrorCallback>(cb)]() mutable { c(); };
        }
    }

    void dispatch() {
        if (!is_valid_ || dispatched_) return;
        if (!on_success_ && !on_error_ && !on_error_void_) return;
        dispatched_ = true;
        future_.then([s = std::move(on_success_),
                      e = std::move(on_error_),
                      ev = std::move(on_error_void_)](reaktar::Future<void> f) mutable {
            auto res = f.get();
            if (res.HasValue()) {
                if (s) s();
            } else {
                if (e) e(res.Error());
                else if (ev) ev();
            }
        });
    }

public:
    AsyncResult() noexcept : is_valid_(false) {}

    explicit AsyncResult(reaktar::Future<void> future)
        : future_(std::move(future)), is_valid_(true) {}

    ~AsyncResult() {
        dispatch();
    }

    AsyncResult(AsyncResult&& other) noexcept
        : future_(std::move(other.future_)),
          is_valid_(other.is_valid_),
          dispatched_(other.dispatched_),
          on_success_(std::move(other.on_success_)),
          on_error_(std::move(other.on_error_)),
          on_error_void_(std::move(other.on_error_void_)) {
        other.is_valid_ = false;
        other.dispatched_ = true;
    }

    AsyncResult& operator=(AsyncResult&& other) noexcept {
        if (this != &other) {
            dispatch();
            future_ = std::move(other.future_);
            is_valid_ = other.is_valid_;
            dispatched_ = other.dispatched_;
            on_success_ = std::move(other.on_success_);
            on_error_ = std::move(other.on_error_);
            on_error_void_ = std::move(other.on_error_void_);
            other.is_valid_ = false;
            other.dispatched_ = true;
        }
        return *this;
    }

    AsyncResult(const AsyncResult&) = delete;
    AsyncResult& operator=(const AsyncResult&) = delete;

    static AsyncResult<void> Failed() noexcept {
        return AsyncResult<void>{};
    }

    explicit operator bool() const noexcept { return is_valid_; }
    bool ok() const noexcept { return is_valid_; }

    template <typename Callback>
    AsyncContinuation<void> then(Callback&& cb);

    template <typename ErrorCallback>
    AsyncContinuation<void> or_else(ErrorCallback&& cb);

    void get() {
        if (!is_valid_) return;
        if (dispatched_) return;
        future_.get();
    }

    reaktar::Future<void>& raw_future() noexcept {
        return future_;
    }
};

template <>
class AsyncContinuation<void> {
private:
    AsyncResult<void>* parent_{nullptr};
public:
    explicit AsyncContinuation(AsyncResult<void>* parent) noexcept : parent_(parent) {}
    ~AsyncContinuation() {
        if (parent_) parent_->dispatch();
    }
    AsyncContinuation(AsyncContinuation&& o) noexcept : parent_(o.parent_) {
        o.parent_ = nullptr;
    }
    AsyncContinuation& operator=(AsyncContinuation&& o) noexcept {
        if (this != &o) {
            if (parent_) parent_->dispatch();
            parent_ = o.parent_;
            o.parent_ = nullptr;
        }
        return *this;
    }
    AsyncContinuation(const AsyncContinuation&) = delete;
    AsyncContinuation& operator=(const AsyncContinuation&) = delete;

    template <typename Callback>
    AsyncContinuation& then(Callback&& cb) {
        if (parent_) parent_->set_then(std::forward<Callback>(cb));
        return *this;
    }

    template <typename ErrorCallback>
    AsyncContinuation& or_else(ErrorCallback&& cb) {
        if (parent_) parent_->set_or_else(std::forward<ErrorCallback>(cb));
        return *this;
    }

    explicit operator bool() const noexcept { return parent_ ? bool(*parent_) : false; }
    bool ok() const noexcept { return parent_ ? parent_->ok() : false; }

    void get() {
        if (parent_) {
            parent_->dispatch();
            parent_->get();
        }
    }

    reaktar::Future<void>& raw_future() noexcept {
        static reaktar::Future<void> s_empty{};
        return parent_ ? parent_->raw_future() : s_empty;
    }
};

template <typename Callback>
inline AsyncContinuation<void> AsyncResult<void>::then(Callback&& cb) {
    set_then(std::forward<Callback>(cb));
    return AsyncContinuation<void>(this);
}

template <typename ErrorCallback>
inline AsyncContinuation<void> AsyncResult<void>::or_else(ErrorCallback&& cb) {
    set_or_else(std::forward<ErrorCallback>(cb));
    return AsyncContinuation<void>(this);
}

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

enum class StrictValidation {
    kEnabled,
    kDisabled
};

// Signature descriptor
template <typename... Args>
struct sig {};

// Check if a signature exists in LegalSigs
template <typename Candidate, typename LegalSigsTuple>
struct is_legal_signature;

template <typename... CandidateArgs, typename... LegalSigs>
struct is_legal_signature<sig<CandidateArgs...>, std::tuple<LegalSigs...>> {
    static constexpr bool value = (std::is_same_v<sig<std::decay_t<CandidateArgs>...>, LegalSigs> || ...);
};

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
};

// Universal probe type that converts to anything
struct universal_probe {
    template <typename T>
    operator T() const;
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

template <typename App, typename LegalSigsTuple, typename... Ts>
struct illegal_combo_checker_2arg {
    template <typename T1>
    static constexpr bool check_row() {
        return (check_pair_rogue<App, LegalSigsTuple, T1, Ts>() || ...);
    }

    static constexpr bool value = (check_row<Ts>() || ...);
};

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

template <typename App, typename LegalSigsTuple, typename... Ts>
struct illegal_combo_checker_3arg {
    template <typename T1, typename T2>
    static constexpr bool check_plane() {
        return (check_triplet_rogue<App, LegalSigsTuple, T1, T2, Ts>() || ...);
    }

    template <typename T1>
    static constexpr bool check_row() {
        return (check_plane<T1, Ts>() || ...);
    }

    static constexpr bool value = (check_row<Ts>() || ...);
};

// SFINAE detector for rogue / orphan on(...) declarations
template <typename App, typename LegalSigsTuple, typename... LegalTypes>
class rogue_handler_detector {
    using Bad = illegal_probe<LegalTypes...>;
    using Any = universal_probe;

    // Test 1: Single argument on(Bad) - catches rogue event/field types, primitives, typos
    template <typename A>
    static auto test_1arg(int) -> decltype(std::declval<A&>().on(std::declval<Bad>()), std::true_type{});
    template <typename>
    static auto test_1arg(...) -> std::false_type;

    // Test 2: Two arguments with rogue type: on(Bad, Any), on(Any, Bad)
    template <typename A>
    static auto test_2arg_bad1(int) -> decltype(std::declval<A&>().on(std::declval<Bad>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_2arg_bad1(...) -> std::false_type;

    template <typename A>
    static auto test_2arg_bad2(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Bad>()), std::true_type{});
    template <typename>
    static auto test_2arg_bad2(...) -> std::false_type;

    // Test 3: Three arguments with rogue type: on(Bad, Any, Any), on(Any, Bad, Any), on(Any, Any, Bad)
    template <typename A>
    static auto test_3arg_bad1(int) -> decltype(std::declval<A&>().on(std::declval<Bad>(), std::declval<Any>(), std::declval<Any>()), std::true_type{});
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

    // Test 3b: Any 3-argument handler
    template <typename A>
    static auto test_3arg_any(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Any>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_3arg_any(...) -> std::false_type;

    // Test 4: Four arguments (any 4-arg on(...) handler)
    template <typename A>
    static auto test_4arg_bad(int) -> decltype(std::declval<A&>().on(std::declval<Any>(), std::declval<Any>(), std::declval<Any>(), std::declval<Any>()), std::true_type{});
    template <typename>
    static auto test_4arg_bad(...) -> std::false_type;

public:
    static constexpr bool has_rogue = decltype(test_1arg<App>(0))::value ||
                                      decltype(test_2arg_bad1<App>(0))::value ||
                                      decltype(test_2arg_bad2<App>(0))::value ||
                                      decltype(test_3arg_bad1<App>(0))::value ||
                                      decltype(test_3arg_bad2<App>(0))::value ||
                                      decltype(test_3arg_bad3<App>(0))::value ||
                                      (!has_signature_with_arity<3, LegalSigsTuple>::value && decltype(test_3arg_any<App>(0))::value) ||
                                      decltype(test_4arg_bad<App>(0))::value ||
                                      illegal_combo_checker_2arg<App, LegalSigsTuple, LegalTypes...>::value ||
                                      illegal_combo_checker_3arg<App, LegalSigsTuple, LegalTypes...>::value;
};

template <typename App, typename LegalSigsTuple, typename... LegalTypes>
inline constexpr bool has_rogue_handler_v = rogue_handler_detector<App, LegalSigsTuple, LegalTypes...>::has_rogue;

} // namespace reaktar


