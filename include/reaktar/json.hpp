// ==============================================================================
// Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
// Part of the Pyarx project: https://github.com/pyarxlab/reaktar
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Pyarx Lab
// ==============================================================================

#pragma once

#include <charconv>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ostream>
#include <array>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <variant>
#include <vector>

namespace reaktar::json {

// ==============================================================================
// Sink Abstraction
// ==============================================================================

// StringSink: Appends directly into a std::string buffer
class StringSink {
public:
    explicit StringSink(std::string& str) noexcept : str_(str) {}

    void write(char c) {
        str_.push_back(c);
    }

    void write(std::string_view sv) {
        str_.append(sv.data(), sv.size());
    }

    void write_int(int64_t v) {
        str_.append(std::to_string(v));
    }

    void write_uint(uint64_t v) {
        str_.append(std::to_string(v));
    }

    void write_float(double v) {
        str_.append(std::to_string(v));
    }

    void write_bool(bool v) {
        str_.append(v ? "true" : "false");
    }

    std::string& target() noexcept { return str_; }

private:
    std::string& str_;
};

// StreamSink: Streams directly into std::ostream or ara::log::LogStream
template <typename Stream>
class StreamSink {
public:
    explicit StreamSink(Stream& stream) noexcept : stream_(stream) {}

    void write(char c) {
        stream_ << c;
    }

    void write(std::string_view sv) {
        stream_ << sv;
    }

    void write_int(int64_t v) {
        stream_ << v;
    }

    void write_uint(uint64_t v) {
        stream_ << v;
    }

    void write_float(double v) {
        stream_ << v;
    }

    void write_bool(bool v) {
        stream_ << (v ? "true" : "false");
    }

    Stream& target() noexcept { return stream_; }

private:
    Stream& stream_;
};

// NullSink: Zero-overhead no-op sink for discarding logs or compile-time silencing
class NullSink {
public:
    void write([[maybe_unused]] char c) noexcept {}
    void write([[maybe_unused]] std::string_view sv) noexcept {}
    void write_int([[maybe_unused]] int64_t v) noexcept {}
    void write_uint([[maybe_unused]] uint64_t v) noexcept {}
    void write_float([[maybe_unused]] double v) noexcept {}
    void write_bool([[maybe_unused]] bool v) noexcept {}
};

// FixedBufferSink: Zero-allocation, stack-bounded buffer sink using fast <charconv>
template <size_t Capacity>
class FixedBufferSink {
public:
    FixedBufferSink() noexcept {
        buffer_[0] = '\0';
    }

    void write(char c) noexcept {
        if (size_ < Capacity - 1) {
            buffer_[size_++] = c;
            buffer_[size_] = '\0';
        } else {
            truncated_ = true;
        }
    }

    void write(std::string_view sv) noexcept {
        size_t to_copy = (size_ + sv.size() < Capacity) ? sv.size() : (Capacity - 1 > size_ ? Capacity - 1 - size_ : 0);
        if (to_copy < sv.size()) {
            truncated_ = true;
        }
        if (to_copy > 0) {
            std::memcpy(buffer_ + size_, sv.data(), to_copy);
            size_ += to_copy;
            buffer_[size_] = '\0';
        }
    }

    void write_int(int64_t v) noexcept {
        if (size_ >= Capacity - 1) {
            truncated_ = true;
            return;
        }
        auto [ptr, ec] = std::to_chars(buffer_ + size_, buffer_ + (Capacity - 1), v);
        if (ec == std::errc{}) {
            size_ = static_cast<size_t>(ptr - buffer_);
            buffer_[size_] = '\0';
        } else {
            truncated_ = true;
        }
    }

    void write_uint(uint64_t v) noexcept {
        if (size_ >= Capacity - 1) {
            truncated_ = true;
            return;
        }
        auto [ptr, ec] = std::to_chars(buffer_ + size_, buffer_ + (Capacity - 1), v);
        if (ec == std::errc{}) {
            size_ = static_cast<size_t>(ptr - buffer_);
            buffer_[size_] = '\0';
        } else {
            truncated_ = true;
        }
    }

    void write_float(double v) noexcept {
        if (size_ >= Capacity - 1) {
            truncated_ = true;
            return;
        }
        auto [ptr, ec] = std::to_chars(buffer_ + size_, buffer_ + (Capacity - 1), v);
        if (ec == std::errc{}) {
            size_ = static_cast<size_t>(ptr - buffer_);
            buffer_[size_] = '\0';
        } else {
            truncated_ = true;
        }
    }

    void write_bool(bool v) noexcept {
        write(v ? std::string_view("true") : std::string_view("false"));
    }

    [[nodiscard]] std::string_view view() const noexcept {
        return std::string_view(buffer_, size_);
    }

    [[nodiscard]] const char* c_str() const noexcept {
        return buffer_;
    }

    [[nodiscard]] size_t size() const noexcept {
        return size_;
    }

    [[nodiscard]] bool truncated() const noexcept {
        return truncated_;
    }

    void reset() noexcept {
        size_ = 0;
        truncated_ = false;
        buffer_[0] = '\0';
    }

private:
    char buffer_[Capacity];
    size_t size_{0};
    bool truncated_{false};
};

// ==============================================================================
// Serialization Declarations
// ==============================================================================

// Primary customization point template for user / actor types
template <typename T, typename Enable = void>
struct ActorJsonWriter;

// Forward declaration of sink-based serialization: write_json(sink, val)
template <typename Sink, typename T>
void write_json(Sink& sink, const T& val);

// Buffer-appending overload: write_json(std::string& out, val)
template <typename T>
inline void write_json(std::string& out, const T& val) {
    StringSink sink(out);
    write_json(sink, val);
}

// Buffer-appending overload: to_json(std::string& out, val)
template <typename T>
inline void to_json(std::string& out, const T& val) {
    write_json(out, val);
}

// High-level serialization returning std::string: to_json(val)
template <typename T>
inline std::string to_json(const T& val) {
    std::string out;
    write_json(out, val);
    return out;
}

// String escaping helper
template <typename Sink>
inline void escape_json_string(Sink& sink, std::string_view s) {
    sink.write('"');
    for (char c : s) {
        switch (c) {
            case '"':  sink.write("\\\""); break;
            case '\\': sink.write("\\\\"); break;
            case '\b': sink.write("\\b"); break;
            case '\f': sink.write("\\f"); break;
            case '\n': sink.write("\\n"); break;
            case '\r': sink.write("\\r"); break;
            case '\t': sink.write("\\t"); break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned char>(c));
                    sink.write(std::string_view(buf));
                } else {
                    sink.write(c);
                }
                break;
        }
    }
    sink.write('"');
}

// Legacy string escaping helper for backwards compatibility
inline void escape_json_string(std::string& out, std::string_view s) {
    StringSink sink(out);
    escape_json_string(sink, s);
}

// ==============================================================================
// Type Trait Detectors
// ==============================================================================

// String-like detector (for custom types like ara::core::String)
template <typename T, typename = void>
struct is_custom_string_like : std::false_type {};

template <typename T>
struct is_custom_string_like<T, std::void_t<
    decltype(std::declval<const T&>().data()),
    decltype(std::declval<const T&>().size()),
    typename T::value_type
>> : std::integral_constant<bool,
    (std::is_same_v<typename T::value_type, char> || std::is_same_v<typename T::value_type, const char>) &&
    !std::is_same_v<std::decay_t<T>, std::string> &&
    !std::is_same_v<std::decay_t<T>, std::string_view>
> {};

// Map container detector
template <typename Map, typename = void>
struct is_map_container : std::false_type {};

template <typename T>
struct is_map_container<T, std::void_t<
    typename T::key_type,
    typename T::mapped_type,
    typename T::value_type,
    decltype(std::declval<const T&>().begin()),
    decltype(std::declval<const T&>().end())
>> : std::true_type {};

// Sequence container detector (for std::vector, ara::core::Vector, std::array, ara::core::Array, etc.)
template <typename T, typename = void>
struct is_sequence_container : std::false_type {};

template <typename T>
struct is_sequence_container<T, std::void_t<
    typename T::value_type,
    decltype(std::declval<const T&>().begin()),
    decltype(std::declval<const T&>().end()),
    decltype(std::declval<const T&>().size())
>> : std::integral_constant<bool,
    !is_map_container<T>::value &&
    !std::is_same_v<std::decay_t<T>, std::string> &&
    !std::is_same_v<std::decay_t<T>, std::string_view> &&
    !is_custom_string_like<T>::value
> {};

// Optional-like detector (for std::optional, ara::core::Optional, etc.)
template <typename T>
struct is_std_optional : std::false_type {};

template <typename T>
struct is_std_optional<std::optional<T>> : std::true_type {};

template <typename T, typename = void>
struct is_optional_like : std::false_type {};

template <typename T>
struct is_optional_like<T, std::void_t<
    decltype(std::declval<const T&>().has_value()),
    decltype(*std::declval<const T&>())
>> : std::true_type {};


namespace detail {

    // Primary fallback dispatcher for user and actor data types
    template <typename T, typename Enable = void>
    struct JsonWriter {
        template <typename Sink>
        static void write(Sink& sink, const T& val) {
            ActorJsonWriter<T>::write(sink, val);
        }
    };

    // bool
    template <>
    struct JsonWriter<bool> {
        template <typename Sink>
        static void write(Sink& sink, bool v) {
            sink.write_bool(v);
        }
    };

    // uint8_t / int8_t formatted as integers
    template <>
    struct JsonWriter<uint8_t> {
        template <typename Sink>
        static void write(Sink& sink, uint8_t v) {
            sink.write_uint(static_cast<uint64_t>(v));
        }
    };

    template <>
    struct JsonWriter<int8_t> {
        template <typename Sink>
        static void write(Sink& sink, int8_t v) {
            sink.write_int(static_cast<int64_t>(v));
        }
    };

    // Other integral types
    template <typename T>
    struct JsonWriter<T, std::enable_if_t<
        std::is_integral_v<T> &&
        !std::is_same_v<T, bool> &&
        !std::is_same_v<T, uint8_t> &&
        !std::is_same_v<T, int8_t>
    >> {
        template <typename Sink>
        static void write(Sink& sink, T v) {
            if constexpr (std::is_signed_v<T>) {
                sink.write_int(static_cast<int64_t>(v));
            } else {
                sink.write_uint(static_cast<uint64_t>(v));
            }
        }
    };

    // Floating-point types
    template <typename T>
    struct JsonWriter<T, std::enable_if_t<std::is_floating_point_v<T>>> {
        template <typename Sink>
        static void write(Sink& sink, T v) {
            sink.write_float(static_cast<double>(v));
        }
    };

    // std::string
    template <>
    struct JsonWriter<std::string> {
        template <typename Sink>
        static void write(Sink& sink, const std::string& v) {
            escape_json_string(sink, v);
        }
    };

    // std::string_view
    template <>
    struct JsonWriter<std::string_view> {
        template <typename Sink>
        static void write(Sink& sink, std::string_view v) {
            escape_json_string(sink, v);
        }
    };

    // const char*
    template <>
    struct JsonWriter<const char*> {
        template <typename Sink>
        static void write(Sink& sink, const char* v) {
            if (v == nullptr) {
                sink.write("null");
            } else {
                escape_json_string(sink, v);
            }
        }
    };

    // char*
    template <>
    struct JsonWriter<char*> {
        template <typename Sink>
        static void write(Sink& sink, const char* v) {
            if (v == nullptr) {
                sink.write("null");
            } else {
                escape_json_string(sink, v);
            }
        }
    };

    template <size_t N>
    struct JsonWriter<char[N]> {
        template <typename Sink>
        static void write(Sink& sink, const char* v) {
            escape_json_string(sink, v);
        }
    };

    template <size_t N>
    struct JsonWriter<const char[N]> {
        template <typename Sink>
        static void write(Sink& sink, const char* v) {
            escape_json_string(sink, v);
        }
    };

    // Custom string-like types (e.g. ara::core::String)
    template <typename T>
    struct JsonWriter<T, std::enable_if_t<is_custom_string_like<T>::value>> {
        template <typename Sink>
        static void write(Sink& sink, const T& v) {
            escape_json_string(sink, std::string_view(v.data(), v.size()));
        }
    };

    // Sequence containers: std::vector, std::array, ara::core::Vector, ara::core::Array, etc.
    template <typename C>
    struct JsonWriter<C, std::enable_if_t<is_sequence_container<C>::value>> {
        template <typename Sink>
        static void write(Sink& sink, const C& container) {
            sink.write('[');
            bool first = true;
            for (const auto& item : container) {
                if (!first) {
                    sink.write(',');
                }
                first = false;
                write_json(sink, item);
            }
            sink.write(']');
        }
    };

    // std::pair<T1, T2>
    template <typename T1, typename T2>
    struct JsonWriter<std::pair<T1, T2>> {
        template <typename Sink>
        static void write(Sink& sink, const std::pair<T1, T2>& p) {
            sink.write("{\"first\":");
            write_json(sink, p.first);
            sink.write(",\"second\":");
            write_json(sink, p.second);
            sink.write('}');
        }
    };

    // std::optional<T>
    template <typename T>
    struct JsonWriter<std::optional<T>> {
        template <typename Sink>
        static void write(Sink& sink, const std::optional<T>& opt) {
            if (opt.has_value()) {
                write_json(sink, *opt);
            } else {
                sink.write("null");
            }
        }
    };

    // Generic Optional-like fallback (e.g. ara::core::Optional when not an alias of std::optional)
    template <typename Opt>
    struct JsonWriter<Opt, std::enable_if_t<is_optional_like<Opt>::value && !is_std_optional<Opt>::value>> {
        template <typename Sink>
        static void write(Sink& sink, const Opt& opt) {
            if (opt.has_value()) {
                write_json(sink, *opt);
            } else {
                sink.write("null");
            }
        }
    };

    // std::variant<Ts...> / ara::core::Variant<Ts...>
    template <typename... Ts>
    struct JsonWriter<std::variant<Ts...>> {
        template <typename Sink>
        static void write(Sink& sink, const std::variant<Ts...>& var) {
            if (var.valueless_by_exception()) {
                sink.write("null");
                return;
            }
            std::visit([&sink](const auto& val) {
                using ValT = std::decay_t<decltype(val)>;
                if constexpr (std::is_same_v<ValT, std::monostate>) {
                    sink.write("null");
                } else {
                    write_json(sink, val);
                }
            }, var);
        }
    };

    // Maps / Dictionaries: std::map, std::unordered_map, ara::core::Map, etc.
    template <typename M>
    struct JsonWriter<M, std::enable_if_t<is_map_container<M>::value>> {
        template <typename Sink>
        static void write(Sink& sink, const M& map) {
            sink.write('{');
            bool first = true;
            for (const auto& [k, v] : map) {
                if (!first) {
                    sink.write(',');
                }
                first = false;
                if constexpr (std::is_same_v<std::decay_t<decltype(k)>, std::string> ||
                              std::is_same_v<std::decay_t<decltype(k)>, std::string_view> ||
                              std::is_same_v<std::decay_t<decltype(k)>, const char*> ||
                              is_custom_string_like<decltype(k)>::value) {
                    write_json(sink, k);
                } else {
                    sink.write('"');
                    write_json(sink, k);
                    sink.write('"');
                }
                sink.write(':');
                write_json(sink, v);
            }
            sink.write('}');
        }
    };

} // namespace detail

template <typename Sink, typename T>
inline void write_json(Sink& sink, const T& val) {
    detail::JsonWriter<std::decay_t<T>>::write(sink, val);
}

// Generic operator<< for standard containers using StreamSink
template <typename Stream, typename T, typename Alloc>
inline Stream& operator<<(Stream& os, const std::vector<T, Alloc>& v) {
    StreamSink<Stream> sink(os);
    write_json(sink, v);
    return os;
}

template <typename Stream, typename T, std::size_t N>
inline Stream& operator<<(Stream& os, const std::array<T, N>& v) {
    StreamSink<Stream> sink(os);
    write_json(sink, v);
    return os;
}

template <typename Stream, typename K, typename V, typename Compare, typename Alloc>
inline Stream& operator<<(Stream& os, const std::map<K, V, Compare, Alloc>& v) {
    StreamSink<Stream> sink(os);
    write_json(sink, v);
    return os;
}

template <typename Stream, typename K, typename V, typename Hash, typename KeyEqual, typename Alloc>
inline Stream& operator<<(Stream& os, const std::unordered_map<K, V, Hash, KeyEqual, Alloc>& v) {
    StreamSink<Stream> sink(os);
    write_json(sink, v);
    return os;
}

template <typename Stream, typename T>
inline auto operator<<(Stream& os, const T& opt) -> std::enable_if_t<is_optional_like<T>::value, Stream&> {
    StreamSink<Stream> sink(os);
    write_json(sink, opt);
    return os;
}

template <typename Stream, typename... Ts>
inline Stream& operator<<(Stream& os, const std::variant<Ts...>& var) {
    StreamSink<Stream> sink(os);
    write_json(sink, var);
    return os;
}

template <typename Stream, typename C>
inline auto operator<<(Stream& os, const C& container)
    -> std::enable_if_t<(is_sequence_container<C>::value || is_map_container<C>::value) &&
                        !is_optional_like<C>::value, Stream&> {
    StreamSink<Stream> sink(os);
    write_json(sink, container);
    return os;
}

} // namespace reaktar::json

namespace ara::core {
    using ::reaktar::json::operator<<;
}

namespace reaktar {
    using json::to_json;
    using json::write_json;
    using json::StringSink;
    using json::StreamSink;
    using json::FixedBufferSink;
    using json::NullSink;
    using json::operator<<;
}
