#pragma once

#include <functional>
#include <vector>
#include <memory>
#include <utility>
#include <future>
#include <string>
#include <map>
#include <array>

namespace ara {
namespace core {

// AUTOSAR Adaptive Platform Standard Core Types (SWS Core Types)
using String = std::string;
template <typename T> using Vector = std::vector<T>;
template <typename K, typename V> using Map = std::map<K, V>;
template <typename T, std::size_t N> using Array = std::array<T, N>;

class ErrorDomain {
public:
    using IdType = uint64_t;
    using CodeType = int32_t;

    constexpr explicit ErrorDomain(IdType id) noexcept : id_(id) {}
    virtual ~ErrorDomain() = default;

    virtual const char* Name() const noexcept = 0;
    virtual const char* Message(CodeType code) const noexcept = 0;

    constexpr IdType Id() const noexcept { return id_; }
private:
    IdType id_;
};

class ErrorCode {
public:
    using CodeType = ErrorDomain::CodeType;

    constexpr ErrorCode() noexcept : code_(0), domain_(nullptr) {}
    constexpr ErrorCode(CodeType code, const ErrorDomain& domain) noexcept
        : code_(code), domain_(&domain) {}

    constexpr CodeType Value() const noexcept { return code_; }
    constexpr const ErrorDomain* Domain() const noexcept { return domain_; }
    const char* Message() const noexcept {
        return domain_ ? domain_->Message(code_) : "Unknown error";
    }

    constexpr bool operator==(const ErrorCode& other) const noexcept {
        return code_ == other.code_ && domain_ == other.domain_;
    }
    constexpr bool operator!=(const ErrorCode& other) const noexcept {
        return !(*this == other);
    }

private:
    CodeType code_{0};
    const ErrorDomain* domain_{nullptr};
};

enum class CoreErrc : ErrorDomain::CodeType {
    kInvalidArgument = 1,
    kInvalidMetaModelArguments = 2,
    kInvalidMetaModelPath = 3,
    kDiscoveryError = 4,
    kServiceNotAvailable = 5
};

class CoreErrorDomain : public ErrorDomain {
public:
    constexpr CoreErrorDomain() noexcept : ErrorDomain(0x8000000000000014ULL) {}
    const char* Name() const noexcept override { return "Core"; }
    const char* Message(CodeType code) const noexcept override {
        switch (static_cast<CoreErrc>(code)) {
            case CoreErrc::kInvalidArgument: return "Invalid argument";
            case CoreErrc::kDiscoveryError: return "Discovery error";
            case CoreErrc::kServiceNotAvailable: return "Service not available";
            default: return "Core error";
        }
    }
};

inline const ErrorDomain& GetCoreErrorDomain() noexcept {
    static const CoreErrorDomain domain;
    return domain;
}

inline ErrorCode MakeErrorCode(CoreErrc code) noexcept {
    return ErrorCode(static_cast<ErrorDomain::CodeType>(code), GetCoreErrorDomain());
}

template <typename T>
class Result {
public:
    using value_type = T;

    Result() = delete;
    Result(const T& val) : val_(val), has_val_(true) {}
    Result(T&& val) : val_(std::move(val)), has_val_(true) {}
    Result(ErrorCode err) : err_(std::move(err)), has_val_(false) {}
    
    static Result FromValue(T val) { return Result(std::move(val)); }
    static Result FromError(ErrorCode err) { return Result(std::move(err)); }

    bool HasValue() const { return has_val_; }
    const T& Value() const { return val_; }
    T& Value() { return val_; }
    const ErrorCode& Error() const { return err_; }
private:
    T val_{};
    ErrorCode err_{};
    bool has_val_{false};
};

template <>
class Result<void> {
public:
    using value_type = void;

    Result() : has_val_(true) {}
    explicit Result(ErrorCode err) : err_(std::move(err)), has_val_(false) {}

    static Result FromValue() { return Result(); }
    static Result FromError(ErrorCode err) { return Result(std::move(err)); }

    bool HasValue() const { return has_val_; }
    const ErrorCode& Error() const { return err_; }
private:
    ErrorCode err_{};
    bool has_val_{true};
};

template <typename T>
class Promise;

// ara::core::Future matching AUTOSAR Adaptive specification with .then()
template <typename T>
class Future {
public:
    Future() = default;
    explicit Future(std::future<Result<T>> fut) : fut_(std::move(fut)) {}

    Result<T> get() {
        return fut_.get();
    }

    template <typename F>
    void then(F&& func) {
        auto res = fut_.get();
        std::promise<Result<T>> p;
        p.set_value(res);
        func(Future<T>(p.get_future()));
    }

private:
    std::future<Result<T>> fut_;
};

template <typename T>
class Promise {
public:
    Promise() = default;
    void set_value(Result<T> res) { prom_.set_value(std::move(res)); }
    void set_value(const T& val) { prom_.set_value(Result<T>::FromValue(val)); }
    void set_error(ErrorCode err) { prom_.set_value(Result<T>::FromError(std::move(err))); }
    Future<T> get_future() { return Future<T>(prom_.get_future()); }
private:
    std::promise<Result<T>> prom_;
};

template <>
class Promise<void> {
public:
    Promise() = default;
    void set_value(Result<void> res) { prom_.set_value(std::move(res)); }
    void set_value() { prom_.set_value(Result<void>::FromValue()); }
    void set_error(ErrorCode err) { prom_.set_value(Result<void>::FromError(std::move(err))); }
    Future<void> get_future() { return Future<void>(prom_.get_future()); }
private:
    std::promise<Result<void>> prom_;
};

template <typename T>
inline Future<std::decay_t<T>> MakeFuture(T&& val) {
    Promise<std::decay_t<T>> p;
    p.set_value(Result<std::decay_t<T>>::FromValue(std::forward<T>(val)));
    return p.get_future();
}

template <typename T>
inline Future<T> MakeFuture(ErrorCode err) {
    Promise<T> p;
    p.set_error(std::move(err));
    return p.get_future();
}

inline Future<void> MakeFuture() {
    Promise<void> p;
    p.set_value(Result<void>::FromValue());
    return p.get_future();
}

class InstanceSpecifier {
public:
    explicit InstanceSpecifier(std::string path) : path_(std::move(path)) {}
    const std::string& ToString() const { return path_; }
    bool operator==(const InstanceSpecifier& other) const { return path_ == other.path_; }
    bool operator<(const InstanceSpecifier& other) const { return path_ < other.path_; }
private:
    std::string path_;
};

} // namespace core

namespace com {

class FindServiceHandle {
public:
    FindServiceHandle() = delete;
    explicit FindServiceHandle(uint64_t id) : id_(id) {}
    uint64_t id() const { return id_; }
    bool operator==(const FindServiceHandle& other) const { return id_ == other.id_; }
private:
    uint64_t id_{0};
};

enum class MethodCallProcessingMode {
    kPoll,
    kEvent,
    kEventSingleThread
};

struct ServiceHandleType {
    ara::core::InstanceSpecifier instance_specifier{""};
    uint32_t instance_id{0};

    bool operator==(const ServiceHandleType& other) const noexcept {
        return instance_specifier == other.instance_specifier && instance_id == other.instance_id;
    }
    bool operator!=(const ServiceHandleType& other) const noexcept {
        return !(*this == other);
    }
    bool operator<(const ServiceHandleType& other) const noexcept {
        if (instance_specifier == other.instance_specifier) {
            return instance_id < other.instance_id;
        }
        return instance_specifier < other.instance_specifier;
    }
};

template <typename HandleType = ServiceHandleType>
using ServiceHandleContainer = std::vector<HandleType>;

template <typename ProxyClass>
using FindServiceHandler = std::function<void(ServiceHandleContainer<ServiceHandleType>, FindServiceHandle)>;

namespace detail {
    inline uint64_t next_find_handle_id() {
        static uint64_t counter = 1;
        return counter++;
    }
} // namespace detail

// Mock SamplePtr wrapping const data
template <typename T>
class SamplePtr {
public:
    SamplePtr(std::shared_ptr<const T> ptr) : ptr_(std::move(ptr)) {}
    const T& operator*() const { return *ptr_; }
    const T* operator->() const { return ptr_.get(); }
    const T* Get() const { return ptr_.get(); }
private:
    std::shared_ptr<const T> ptr_;
};

// Mock Skeleton Event (Publisher)
template <typename SampleType>
class SkeletonEvent {
public:
    using ReceiverCallback = std::function<void(SamplePtr<SampleType>)>;

    void Send(const SampleType& data) {
        auto sharedData = std::make_shared<const SampleType>(data);
        for (auto& cb : subscribers_) {
            if (cb) cb(SamplePtr<SampleType>(sharedData));
        }
    }

    void Connect(ReceiverCallback cb) {
        subscribers_.push_back(std::move(cb));
    }

private:
    std::vector<ReceiverCallback> subscribers_;
};

// Mock Proxy Event (Subscriber)
template <typename SampleType>
class ProxyEvent {
public:
    using ReceiveHandler = std::function<void()>;

    void Subscribe(size_t /*maxSampleCount*/) {
        is_subscribed_ = true;
    }

    void Unsubscribe() {
        is_subscribed_ = false;
    }

    bool IsSubscribed() const {
        return is_subscribed_;
    }

    void SetReceiveHandler(ReceiveHandler handler) {
        receive_handler_ = std::move(handler);
    }

    void OnDataArrived(SamplePtr<SampleType> sample) {
        if (!is_subscribed_) return;
        {
            std::lock_guard<std::mutex> lock(samples_mutex_);
            pending_samples_.push_back(sample);
        }
        if (receive_handler_) {
            receive_handler_();
        }
    }

    template <typename F>
    size_t GetNewSamples(F&& receiver) {
        std::vector<SamplePtr<SampleType>> samples;
        {
            std::lock_guard<std::mutex> lock(samples_mutex_);
            samples = std::move(pending_samples_);
            pending_samples_.clear();
        }
        size_t count = 0;
        for (auto& s : samples) {
            receiver(s);
            ++count;
        }
        return count;
    }

private:
    bool is_subscribed_{false};
    ReceiveHandler receive_handler_;
    std::mutex samples_mutex_;
    std::vector<SamplePtr<SampleType>> pending_samples_;
};

// Mock Skeleton Field (Getter, Setter, Notifier)
template <typename FieldType>
class SkeletonField : public SkeletonEvent<FieldType> {
public:
    using SetHandler = std::function<ara::core::Result<FieldType>(const FieldType&)>;
    using GetHandler = std::function<ara::core::Result<FieldType>()>;

    void Update(const FieldType& data) {
        current_val_ = data;
        this->Send(data);
    }

    void RegisterSetHandler(SetHandler handler) {
        set_handler_ = std::move(handler);
    }

    void RegisterGetHandler(GetHandler handler) {
        get_handler_ = std::move(handler);
    }

    ara::core::Result<FieldType> InvokeSet(const FieldType& val) {
        if (set_handler_) {
            auto res = set_handler_(val);
            if (res.HasValue()) {
                current_val_ = res.Value();
                this->Send(current_val_);
            }
            return res;
        }
        current_val_ = val;
        this->Send(current_val_);
        return ara::core::Result<FieldType>::FromValue(val);
    }

    ara::core::Result<FieldType> InvokeGet() {
        if (get_handler_) return get_handler_();
        return ara::core::Result<FieldType>::FromValue(current_val_);
    }

private:
    FieldType current_val_{};
    SetHandler set_handler_;
    GetHandler get_handler_;
};

// Mock Proxy Field (Getter, Setter, Notifier)
template <typename FieldType>
class ProxyField : public ProxyEvent<FieldType> {
public:
    void Wire(SkeletonField<FieldType>& skel_field) {
        skel_field_ = &skel_field;
        skel_field_->Connect([this](SamplePtr<FieldType> s) {
            this->OnDataArrived(s);
        });
    }

    ara::core::Future<FieldType> Get() {
        ara::core::Promise<FieldType> p;
        if (skel_field_) {
            p.set_value(skel_field_->InvokeGet());
        } else {
            p.set_value(ara::core::Result<FieldType>::FromValue(FieldType{}));
        }
        return p.get_future();
    }

    ara::core::Future<FieldType> Set(const FieldType& val) {
        ara::core::Promise<FieldType> p;
        if (skel_field_) {
            p.set_value(skel_field_->InvokeSet(val));
        } else {
            p.set_value(ara::core::Result<FieldType>::FromValue(val));
        }
        return p.get_future();
    }

private:
    SkeletonField<FieldType>* skel_field_{nullptr};
};

} // namespace com
} // namespace ara
