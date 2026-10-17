#!/usr/bin/env python3
# ==============================================================================
# Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
# Part of the Pyarx project: https://github.com/pyarxlab/reaktar
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Pyarx Lab
# ==============================================================================
"""
Reaktar Code Generator:
Directly processes pyarx domain nodes without intermediate dataclasses.
Walks the ARXML model directly and generates C++ Actor, TestBench, and Tags headers.
"""

import sys
import re
from pathlib import Path
from collections import Counter, defaultdict
import jinja2
from pyarx.domain import load_domain

# Reserved C++ keywords to prevent generating invalid identifier aliases
CPP_KEYWORDS = {
    "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
    "bool", "break", "case", "catch", "char", "char8_t", "char16_t", "char32_t",
    "class", "compl", "concept", "const", "consteval", "constexpr", "constinit",
    "const_cast", "continue", "co_await", "co_return", "co_yield", "decltype",
    "default", "delete", "do", "double", "dynamic_cast", "else", "enum",
    "explicit", "export", "extern", "false", "float", "for", "friend", "goto",
    "if", "inline", "int", "long", "mutable", "namespace", "new", "noexcept",
    "not", "not_eq", "nullptr", "operator", "or", "or_eq", "private", "protected",
    "public", "register", "reinterpret_cast", "requires", "return", "short",
    "signed", "sizeof", "static", "static_assert", "static_cast", "struct",
    "switch", "template", "this", "thread_local", "throw", "true", "try",
    "typedef", "typeid", "typename", "union", "unsigned", "using", "virtual",
    "void", "volatile", "wchar_t", "while", "xor", "xor_eq"
}


def sanitize_identifier(name: str) -> str:
    """Sanitizes an arbitrary string into a valid C++ identifier."""
    if not name or isinstance(name, dict):
        return ""
    s = str(name).strip()
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        return ""
    if sanitized[0].isdigit():
        sanitized = f"VAL_{sanitized}"
    if sanitized in CPP_KEYWORDS:
        sanitized = f"k_{sanitized}"
    return sanitized


def extract_compu_scale_symbol(scale, default_val=0) -> str:
    """
    Extracts the C++ enumerator name from an AUTOSAR COMPU-SCALE using standard
    resolution precedence:
      1. <SYMBOL>
      2. <SHORT-LABEL>
      3. <COMPU-CONST><VT>
      4. <COMPU-INVERSE-VALUE><VT>
      5. Fallback synthetic name (e.g. VAL_<default_val>)
    """
    def is_valid_str(val):
        if val is None or isinstance(val, dict):
            return False
        s = str(val).strip()
        return bool(s) and s != "{}"

    # 1. <SYMBOL>
    sym = getattr(scale, "symbol", None)
    if is_valid_str(sym):
        clean = sanitize_identifier(str(sym))
        if clean:
            return clean

    # 2. <SHORT-LABEL>
    short_lbl = getattr(scale, "short_label", None)
    if is_valid_str(short_lbl):
        clean = sanitize_identifier(str(short_lbl))
        if clean:
            return clean

    # 3. <COMPU-CONST><VT>
    cc = getattr(scale, "compu_const", None)
    if cc is not None:
        vt = getattr(cc, "vt", None)
        if is_valid_str(vt):
            clean = sanitize_identifier(str(vt))
            if clean:
                return clean

    # 4. <COMPU-INVERSE-VALUE><VT>
    civ = getattr(scale, "compu_inverse_value", None)
    if civ is not None:
        vt = getattr(civ, "vt", None)
        if is_valid_str(vt):
            clean = sanitize_identifier(str(vt))
            if clean:
                return clean

    # 5. Fallback synthetic name
    return f"VAL_{default_val}"


def strip_port_affixes(name: str) -> str:
    """
    Strips conventional AUTOSAR port affixes (e.g. PPort_, RPort_, _Port, Port, In, Out)
    returning a candidate ergonomic alias if valid and non-empty.
    """
    original = name
    # Prefixes with underscores (case-insensitive): PPort_, RPort_, pp_, rp_, p_, r_, provided_, required_
    candidate = re.sub(r'^(?:pport|rport|pp|rp|p|r|provided|required)_+', '', name, flags=re.IGNORECASE)
    # PascalCase prefixes: PPort, RPort, Provided, Required followed by uppercase/digit
    candidate = re.sub(r'^(?:PPort|RPort|Provided|Required)(?=[A-Z0-9])', '', candidate)
    # Suffixes with underscores (case-insensitive): _pport, _rport, _provided, _required, _port, _in, _out
    candidate = re.sub(r'_+(?:pport|rport|provided|required|port|in|out)$', '', candidate, flags=re.IGNORECASE)
    # PascalCase suffixes: PortProvided, PortRequired, ProvidedPort, RequiredPort, Provided, Required, Port, In, Out
    candidate = re.sub(r'(?:PortProvided|PortRequired|ProvidedPort|RequiredPort|Provided|Required|Port|In|Out)$', '', candidate)

    if candidate and candidate != original and len(candidate) >= 2 and candidate.isidentifier() and candidate not in CPP_KEYWORDS:
        return candidate
    return ""

# Primitive/fundamental types defined by C++ / AUTOSAR
CURRENT_TYPE_STYLE = "autosar"

FUNDAMENTAL_CPP_TYPES_AUTOSAR = {
    "bool": "bool",
    "float": "float",
    "double": "double",
    "uint8_t": "uint8_t",
    "uint16_t": "uint16_t",
    "uint32_t": "uint32_t",
    "uint64_t": "uint64_t",
    "int8_t": "int8_t",
    "int16_t": "int16_t",
    "int32_t": "int32_t",
    "int64_t": "int64_t",
    "std::string": "std::string",
    "String": "ara::core::String",
    "ara::core::String": "ara::core::String",
}

FUNDAMENTAL_CPP_TYPES_STD = {
    "bool": "bool",
    "float": "float",
    "double": "double",
    "uint8_t": "uint8_t",
    "uint16_t": "uint16_t",
    "uint32_t": "uint32_t",
    "uint64_t": "uint64_t",
    "int8_t": "int8_t",
    "int16_t": "int16_t",
    "int32_t": "int32_t",
    "int64_t": "int64_t",
    "std::string": "std::string",
    "String": "std::string",
    "ara::core::String": "std::string",
}

FUNDAMENTAL_CPP_TYPES = FUNDAMENTAL_CPP_TYPES_AUTOSAR


def get_vector_element_tref(dt):
    if hasattr(dt, "cpp_template_arguments") and dt.cpp_template_arguments:
        arg = dt.cpp_template_arguments[0]
        ref = getattr(arg, "template_type_ref", None) or getattr(arg, "type_reference_ref", None)
        if ref and not getattr(ref, "is_null", False):
            return ref
    if hasattr(dt, "template_arguments") and dt.template_arguments:
        arg = dt.template_arguments[0]
        ref = getattr(arg, "template_type_ref", None) or getattr(arg, "type_reference_ref", None)
        if ref and not getattr(ref, "is_null", False):
            return ref
    sub_els = getattr(dt, "sub_elements", None) or getattr(dt, "cpp_implementation_data_type_elements", None)
    if sub_els:
        for el in sub_els:
            ref = getattr(el, "type_reference_ref", None) or getattr(el, "type_tref", None)
            if ref and not getattr(ref, "is_null", False):
                return ref
    ref = getattr(dt, "type_reference_ref", None)
    if ref and not getattr(ref, "is_null", False):
        return ref
    return None


def get_array_element_tref_and_size(dt):
    def _extract_size(val):
        if val is None:
            return None
        if isinstance(val, dict) and "_text" in val:
            val = val["_text"]
        elif hasattr(val, "__iter__") and not isinstance(val, (str, bytes, dict)):
            val = list(val)[0] if len(val) > 0 else 1
        try:
            return int(val)
        except Exception:
            return 1

    size = _extract_size(getattr(dt, "array_size", None))
    elem_ref = None
    args = getattr(dt, "cpp_template_arguments", None) or getattr(dt, "template_arguments", None)
    if args and len(args) > 0:
        elem_ref = getattr(args[0], "template_type_ref", None) or getattr(args[0], "type_reference_ref", None)
    if not elem_ref:
        sub_els = getattr(dt, "sub_elements", None) or getattr(dt, "cpp_implementation_data_type_elements", None)
        if sub_els:
            for el in sub_els:
                if size is None:
                    size = _extract_size(getattr(el, "array_size", None))
                ref = getattr(el, "type_reference_ref", None) or getattr(el, "type_tref", None)
                if ref and not getattr(ref, "is_null", False):
                    elem_ref = ref
                    break
    if not elem_ref:
        ref = getattr(dt, "type_reference_ref", None)
        if ref and not getattr(ref, "is_null", False):
            elem_ref = ref
    if size is None:
        size = 1
    return elem_ref, size


def get_map_key_value_trefs(dt):
    args = getattr(dt, "cpp_template_arguments", None) or getattr(dt, "template_arguments", None)
    if args and len(args) >= 2:
        k_ref = getattr(args[0], "template_type_ref", None) or getattr(args[0], "type_reference_ref", None)
        v_ref = getattr(args[1], "template_type_ref", None) or getattr(args[1], "type_reference_ref", None)
        return k_ref, v_ref
    sub_els = getattr(dt, "sub_elements", None) or getattr(dt, "cpp_implementation_data_type_elements", None)
    if sub_els and len(sub_els) >= 2:
        k_ref = getattr(sub_els[0], "type_reference_ref", None) or getattr(sub_els[0], "type_tref", None)
        v_ref = getattr(sub_els[1], "type_reference_ref", None) or getattr(sub_els[1], "type_tref", None)
        return k_ref, v_ref
    return None, None


def get_optional_element_tref(dt):
    args = getattr(dt, "cpp_template_arguments", None) or getattr(dt, "template_arguments", None)
    if args and len(args) > 0:
        elem = getattr(args[0], "template_type_ref", None) or getattr(args[0], "type_reference_ref", None)
        if elem and not getattr(elem, "is_null", False):
            return elem
    ref = getattr(dt, "type_reference_ref", None)
    if ref and not getattr(ref, "is_null", False):
        return ref
    sub_els = getattr(dt, "sub_elements", None) or getattr(dt, "cpp_implementation_data_type_elements", None)
    if sub_els and len(sub_els) > 0:
        ref = getattr(sub_els[0], "type_reference_ref", None) or getattr(sub_els[0], "type_tref", None)
        if ref and not getattr(ref, "is_null", False):
            return ref
    return None


def get_union_alternative_trefs(dt):
    sub_els = getattr(dt, "sub_elements", None) or getattr(dt, "cpp_implementation_data_type_elements", None)
    if not sub_els:
        return []
    res = []
    for el in sub_els:
        ref = getattr(el, "type_reference_ref", None) or getattr(el, "type_tref", None)
        if ref and not getattr(ref, "is_null", False):
            res.append(ref)
    return res


def cpp_type(tref, domain=None, type_style=None):
    if type_style is None:
        type_style = CURRENT_TYPE_STYLE
    fundamental = FUNDAMENTAL_CPP_TYPES_AUTOSAR if type_style == "autosar" else FUNDAMENTAL_CPP_TYPES_STD
    if not tref or getattr(tref, "is_null", False):
        return "void"
    name = getattr(tref, "short_name", None) or getattr(tref, "name", None) or str(tref)
    if name in fundamental:
        return fundamental[name]

    cat = str(getattr(tref, "category", ""))
    if cat == "VECTOR":
        elem = get_vector_element_tref(tref)
        prefix = "ara::core::Vector" if type_style == "autosar" else "std::vector"
        return f"{prefix}<{cpp_type(elem, domain, type_style)}>"
    if cat == "ARRAY":
        elem, size = get_array_element_tref_and_size(tref)
        prefix = "ara::core::Array" if type_style == "autosar" else "std::array"
        return f"{prefix}<{cpp_type(elem, domain, type_style)}, {size}>"
    if cat == "ASSOCIATIVE_MAP":
        k, v = get_map_key_value_trefs(tref)
        prefix = "ara::core::Map" if type_style == "autosar" else "std::map"
        return f"{prefix}<{cpp_type(k, domain, type_style)}, {cpp_type(v, domain, type_style)}>"
    if cat == "OPTIONAL":
        elem = get_optional_element_tref(tref)
        prefix = "ara::core::Optional" if type_style == "autosar" else "std::optional"
        return f"{prefix}<{cpp_type(elem, domain, type_style)}>"
    if cat == "UNION":
        alts = get_union_alternative_trefs(tref)
        prefix = "ara::core::Variant" if type_style == "autosar" else "std::variant"
        alt_strs = [cpp_type(a, domain, type_style) for a in alts]
        return f"{prefix}<{', '.join(alt_strs)}>"
    if cat == "TYPE_REFERENCE" and not (getattr(tref, "x", None) and getattr(tref.x, "compu_methods", None)):
        target = getattr(tref, "type_reference_ref", None)
        if target:
            return cpp_type(target, domain, type_style)

    # If tref is already resolved DomainNode with namespaces
    dt = tref
    if hasattr(dt, "namespaces") and not dt.namespaces.is_null:
        parts = [ns.symbol or ns.short_name for ns in dt.namespaces]
        if parts:
            ns_str = "::".join(parts)
            return f"{ns_str}::{dt.short_name}"
    if hasattr(dt, "short_name"):
        return dt.short_name
    return name


def service_ns(intf) -> str:
    """Reads C++ namespace directly from the ServiceInterface's NAMESPACES in ARXML."""
    if hasattr(intf, "namespaces") and intf.namespaces and not intf.namespaces.is_null:
        parts = [ns.symbol or ns.short_name for ns in intf.namespaces]
        return "::".join(parts)
    return intf.short_name.lower()


def service_header_dir(intf) -> str:
    """Resolves header directory path from ServiceInterface's NAMESPACES in ARXML."""
    if hasattr(intf, "namespaces") and intf.namespaces and not intf.namespaces.is_null:
        parts = [ns.symbol or ns.short_name for ns in intf.namespaces]
        return "/".join(parts)
    return intf.short_name.lower()


def service_base_name(intf) -> str:
    """Derives standard base service name by stripping 'Interface' suffix."""
    import re
    return re.sub(r"Interface$", "", intf.short_name)


def service_ident(intf) -> str:
    """Derives a clean, valid C++ identifier from ServiceInterface base name.
    e.g. NavigationInterface -> navigation
         PowertrainInterface -> powertrain
         BodyControlInterface -> body_control
    """
    import re
    base = service_base_name(intf)
    return re.sub(r'(?<!^)(?=[A-Z])', '_', base).lower()


def skeleton_header(intf) -> str:
    """Computes include header path for Skeleton based on service namespace and base name."""
    import re
    dir_path = service_header_dir(intf)
    base = service_base_name(intf).lower()
    return f"{dir_path}/{base}_skeleton.h"


def proxy_header(intf) -> str:
    """Computes include header path for Proxy based on service namespace and base name."""
    import re
    dir_path = service_header_dir(intf)
    base = service_base_name(intf).lower()
    return f"{dir_path}/{base}_proxy.h"


def skeleton_cls(intf) -> str:
    """Computes fully qualified C++ Skeleton class name."""
    ns = service_ns(intf)
    base = service_base_name(intf)
    return f"{ns}::skeleton::{base}Skeleton"


def proxy_cls(intf) -> str:
    """Computes fully qualified C++ Proxy class name."""
    ns = service_ns(intf)
    base = service_base_name(intf)
    return f"{ns}::proxy::{base}Proxy"


def is_service_interface(intf) -> bool:
    """Returns True if the interface is an AUTOSAR SERVICE-INTERFACE, excluding Persistency, PHM, etc."""
    if not intf or getattr(intf, "is_null", False):
        return False
    intf_type = getattr(intf, "type", "")
    return intf_type == "SERVICE-INTERFACE"


def get_service_p_ports(app, domain):
    """Filters p_port_prototypes to only those referencing a SERVICE-INTERFACE."""
    valid_ports = []
    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        if is_service_interface(intf):
            valid_ports.append(p)
    return valid_ports


def get_service_r_ports(app, domain):
    """Filters r_port_prototypes to only those referencing a SERVICE-INTERFACE."""
    valid_ports = []
    for r in app.r_port_prototypes:
        intf = resolve_intf(r, domain)
        if is_service_interface(intf):
            valid_ports.append(r)
    return valid_ports

def resolve_intf(port, domain):
    """Resolves provided/required interface reference on a port prototype."""
    for prop in ["provided_interface_tref", "required_interface_tref"]:
        if hasattr(port, prop):
            ref = getattr(port, prop)
            if ref and not ref.is_null:
                return ref
    return None


def sorted_ports(ports):
    return sorted(list(ports), key=lambda p: p.short_name)


def sorted_events(events):
    return sorted(list(events), key=lambda e: e.short_name)


def sorted_fields(fields):
    return sorted(list(fields), key=lambda f: f.short_name)


def sorted_methods(methods):
    return sorted(list(methods), key=lambda m: m.short_name)


def method_in_args(method, domain=None, pass_by="const_ref"):
    """Extracts in-arguments as a list of (arg_name, cpp_type_str, pass_type_str).
    pass_by: 'const_ref' (default) passes all arguments as const T&.
             'value' passes primitive/fundamental scalar types by value.
    """
    args = []
    for arg in getattr(method, "arguments", []):
        direction = getattr(arg, "direction", "IN")
        if direction in ["IN", "INOUT"]:
            aname = arg.short_name
            atype = cpp_type(arg.type_tref, domain)
            if pass_by == "value" and atype in ["bool", "float", "double", "uint8_t", "uint16_t", "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t"]:
                ptype = atype
            else:
                ptype = f"const {atype}&"
            args.append((aname, atype, ptype))
    return args


def is_fire_and_forget(method):
    faf = getattr(method, "fire_and_forget", None)
    if faf is None or getattr(faf, "is_null", False):
        return False
    return bool(faf)


def app_has_executable(app) -> bool:
    """Returns True if the component has at least one associated Executable in the model."""
    try:
        execs = getattr(getattr(app, "x", None), "executables", [])
        return len(execs) > 0 and execs[0] is not None
    except Exception:
        return False


def app_exe_name(app):
    execs = getattr(getattr(app, "x", None), "executables", [])
    if execs and execs[0] is not None:
        return execs[0].name
    return None


def method_ret_type(method, domain=None):
    """Extracts return type from OUT arguments or returns 'void'."""
    for arg in getattr(method, "arguments", []):
        direction = getattr(arg, "direction", "")
        if direction == "OUT":
            return cpp_type(arg.type_tref, domain)
    return "void"


def method_snake_name(method):
    """Converts CamelCase method short name to snake_case."""
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', method.short_name).lower()


def resolve_instance_specifier(app, port) -> str:
    """Resolves canonical AUTOSAR InstanceSpecifier: <Executable>/<RootSwComponent>/<Port>"""
    exe = port.x.executables[0]
    comp = exe.root_sw_component_prototype
    return f"{exe.name}/{comp.name}/{port.name}"


def analyze_application_types(app, domain):
    """
    Analyzes all C++ types used in an application to detect type collisions.
    """
    outgoing_items = []
    # 1. P-Port events (Skeleton Events)
    for p in get_service_p_ports(app, domain):
        intf = resolve_intf(p, domain)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            outgoing_items.append(('event', ev.short_name, t, p.short_name, intf, ev))

    # 2. P-Port fields (Skeleton Field Update - Law 0: actor manages field signals)
    for p in get_service_p_ports(app, domain):
        intf = resolve_intf(p, domain)
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            outgoing_items.append(('field_update', f.short_name, t, p.short_name, intf, f))

    # 3. R-Port RPC methods (single-arg directly without artificial Request structs)
    for r in get_service_r_ports(app, domain):
        intf = resolve_intf(r, domain)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain)
            if len(in_args) == 1:
                t = in_args[0][1]
                outgoing_items.append(('rpc_arg', m.short_name, t, r.short_name, intf, m))
        # R-Port field setters (proxy->Field.Set(val))
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                t = cpp_type(f.type_tref, domain)
                outgoing_items.append(('field_set', f.short_name, t, r.short_name, intf, f))

    out_type_counts = Counter([item[2] for item in outgoing_items])

    # Incoming items: R-Port events + R-Port field notifiers
    incoming_items = []
    for r in get_service_r_ports(app, domain):
        intf = resolve_intf(r, domain)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            incoming_items.append(('event', ev.short_name, t, r.short_name, intf, ev))
        for f in sorted_fields(intf.fields):
            if f.has_notifier:
                t = cpp_type(f.type_tref, domain)
                incoming_items.append(('field_notify', f.short_name, t, r.short_name, intf, f))

    in_type_counts = Counter([item[2] for item in incoming_items])

    # Skeleton field setters
    fset_items = []
    for p in get_service_p_ports(app, domain):
        intf = resolve_intf(p, domain)
        for f in sorted_fields(intf.fields):
            if f.has_setter:
                t = cpp_type(f.type_tref, domain)
                fset_items.append((f.short_name, t))

    fset_type_counts = Counter([item[1] for item in fset_items])

    # 4. Skeleton methods for direct tagless on(args...)
    skeleton_methods = []
    for p in get_service_p_ports(app, domain):
        intf = resolve_intf(p, domain)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain)
            sig_types = tuple(a[1] for a in in_args)
            skeleton_methods.append((m.short_name, sig_types, in_args, m))

    skel_method_sig_counts = Counter([sm[1] for sm in skeleton_methods])

    # 5. Proxy methods for variadic tagless emit(args...)
    proxy_methods = []
    for r in get_service_r_ports(app, domain):
        intf = resolve_intf(r, domain)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain)
            sig_types = tuple(a[1] for a in in_args)
            proxy_methods.append((m.short_name, sig_types, in_args, m, r))

    proxy_method_sig_counts = Counter([pm[1] for pm in proxy_methods])

    # Single-argument method signatures that could collide with single-payload direct on(t) / emit(t)
    skel_single_arg_types = {sig[0] for sig in skel_method_sig_counts.keys() if len(sig) == 1}
    proxy_single_arg_types = {sig[0] for sig in proxy_method_sig_counts.keys() if len(sig) == 1}

    # Guardrail 3 (Fan-In Boundaries):
    # One-Way signals (returns void: pub/sub events, field notifiers) cannot fan-in with
    # Two-Way transactions (returns T/Result: field setters, request-response RPCs).
    # Ambiguous collisions between incoming channels must be rejected for direct tagless dispatch.
    incoming_unique_types = {
        t for t, count in in_type_counts.items()
        if count == 1 and t not in fset_type_counts and t not in skel_single_arg_types
    }

    field_setter_unique_types = {
        t for t, count in fset_type_counts.items()
        if count == 1 and t not in in_type_counts and t not in skel_single_arg_types
    }

    skel_method_unique_sigs = {
        sig for sig, count in skel_method_sig_counts.items()
        if count == 1 and not (len(sig) == 1 and (sig[0] in in_type_counts or sig[0] in fset_type_counts))
    }

    outgoing_unique_types = {t for t, count in out_type_counts.items() if count == 1}
    proxy_method_unique_sigs = {sig for sig, count in proxy_method_sig_counts.items() if count == 1}

    outgoing_conflicting_types = {t: [f"{item[0]}:{item[1]}" for item in outgoing_items if item[2] == t] for t, count in out_type_counts.items() if count > 1}
    incoming_conflicting_types = {t: [f"{item[0]}:{item[1]}" for item in incoming_items if item[2] == t] for t, count in in_type_counts.items() if count > 1}

    # 6. Extract all legal incoming types, tag types, and signature tuples for rogue handler detection
    legal_types = set()
    legal_tags = set()
    legal_signatures = set()

    for r in get_service_r_ports(app, domain):
        intf = resolve_intf(r, domain)
        ns = service_ns(intf)
        port_name = r.short_name
        port_tag = f"typename ActorBase::ports::{port_name}"
        port_Any_tag = f"typename ActorBase::ports::{port_name}::Any"
        legal_tags.add(port_tag)
        legal_tags.add(port_Any_tag)
        legal_tags.add("::reaktar::Any")
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            legal_types.add(t)
            tag = f"::reaktar::tags::{ns}::events::{ev.short_name}"
            tag_any = f"{tag}::Any"
            nested_port_tag = f"typename ActorBase::ports::{port_name}::{ev.short_name}"
            legal_tags.add(tag)
            legal_tags.add(tag_any)
            legal_tags.add(nested_port_tag)
            # Direct on(t), service-tagged on(tag, t), port-tagged on(nested, t), port-bare on(port, t), port-any on(port::Any, t), tag-any on(tag::Any, t), global-any on(::reaktar::Any, t)
            legal_signatures.add((t,))
            legal_signatures.add((tag, t))
            legal_signatures.add((tag_any, t))
            legal_signatures.add((nested_port_tag, t))
            legal_signatures.add((port_tag, t))
            legal_signatures.add((port_Any_tag, t))
            legal_signatures.add(("::reaktar::Any", t))
        for f in sorted_fields(intf.fields):
            if f.has_notifier:
                t = cpp_type(f.type_tref, domain)
                legal_types.add(t)
                tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                tag_any = f"{tag}::Any"
                nested_port_tag = f"typename ActorBase::ports::{port_name}::{f.short_name}"
                legal_tags.add(tag)
                legal_tags.add(tag_any)
                legal_tags.add(nested_port_tag)
                legal_signatures.add((t,))
                legal_signatures.add((tag, t))
                legal_signatures.add((tag_any, t))
                legal_signatures.add((nested_port_tag, t))
                legal_signatures.add((port_tag, t))
                legal_signatures.add((port_Any_tag, t))
                legal_signatures.add(("::reaktar::Any", t))

    for p in get_service_p_ports(app, domain):
        intf = resolve_intf(p, domain)
        ns = service_ns(intf)
        port_name = p.short_name
        port_tag = f"typename ActorBase::ports::{port_name}"
        port_Any_tag = f"typename ActorBase::ports::{port_name}::Any"
        legal_tags.add(port_tag)
        legal_tags.add(port_Any_tag)
        legal_tags.add("::reaktar::Any")
        for m in sorted_methods(intf.methods):
            tag = f"::reaktar::tags::{ns}::methods::{m.short_name}"
            tag_any = f"{tag}::Any"
            nested_port_tag = f"typename ActorBase::ports::{port_name}::{m.short_name}"
            legal_tags.add(tag)
            legal_tags.add(tag_any)
            legal_tags.add(nested_port_tag)
            in_args = method_in_args(m, domain)
            sig_types = tuple(a[1] for a in in_args)
            for t in sig_types:
                legal_types.add(t)
            # Direct on(args...)
            legal_signatures.add(sig_types)
            # Tagged on(Tag, args...)
            legal_signatures.add((tag,) + sig_types)
            legal_signatures.add((tag_any,) + sig_types)
            # Port-tagged on(Port::Method, args...)
            legal_signatures.add((nested_port_tag,) + sig_types)
            # Port-bare on(Port, args...)
            legal_signatures.add((port_tag,) + sig_types)
            # Port-any on(Port::Any, args...)
            legal_signatures.add((port_Any_tag,) + sig_types)
            # Global-any on(reaktar::Any, args...)
            legal_signatures.add(("::reaktar::Any",) + sig_types)
        for f in sorted_fields(intf.fields):
            if f.has_setter:
                t = cpp_type(f.type_tref, domain)
                legal_types.add(t)
                tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                tag_any = f"{tag}::Any"
                nested_port_tag = f"typename ActorBase::ports::{port_name}::{f.short_name}"
                legal_tags.add(tag)
                legal_tags.add(tag_any)
                legal_tags.add(nested_port_tag)
                legal_signatures.add((t,))
                legal_signatures.add((tag, t))
                legal_signatures.add((tag_any, t))
                legal_signatures.add((nested_port_tag, t))
                legal_signatures.add((port_tag, t))
                legal_signatures.add((port_Any_tag, t))
                legal_signatures.add(("::reaktar::Any", t))

    # 7. Collect all app tags and build ergonomic tag aliases
    all_intfs = set()
    for p in get_service_p_ports(app, domain):
        all_intfs.add(resolve_intf(p, domain))
    for r in get_service_r_ports(app, domain):
        all_intfs.add(resolve_intf(r, domain))

    app_tags = []
    for intf in sorted(list(all_intfs), key=lambda x: x.short_name):
        ns = service_ns(intf)
        for ev in getattr(intf, "events", []):
            app_tags.append((ev.short_name, f"::reaktar::tags::{ns}::events::{ev.short_name}"))
        for m in getattr(intf, "methods", []):
            app_tags.append((m.short_name, f"::reaktar::tags::{ns}::methods::{m.short_name}"))
        for f in getattr(intf, "fields", []):
            app_tags.append((f.short_name, f"::reaktar::tags::{ns}::fields::{f.short_name}"))

        # Skeleton member objects (events and fields on offered p-ports)
    skel_member_names = set()
    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        for ev in getattr(intf, "events", []):
            skel_member_names.add(ev.short_name)
        for f in getattr(intf, "fields", []):
            skel_member_names.add(f.short_name)

    tag_name_counts = Counter([name for name, fq in app_tags])
    tag_aliases = []
    for name, count in sorted(tag_name_counts.items()):
        if count == 1:
            matching = [fq for n, fq in app_tags if n == name][0]
            tag_aliases.append({"name": name, "target": matching, "is_ambiguous": False})
        else:
            conflicts = [fq for n, fq in app_tags if n == name]
            tag_aliases.append({"name": name, "conflicts": conflicts, "is_ambiguous": True})

    return {
        'outgoing_unique_types': outgoing_unique_types,
        'incoming_unique_types': incoming_unique_types,
        'field_setter_unique_types': field_setter_unique_types,
        'skel_method_unique_sigs': skel_method_unique_sigs,
        'proxy_method_unique_sigs': proxy_method_unique_sigs,
        'outgoing_conflicting_types': outgoing_conflicting_types,
        'incoming_conflicting_types': incoming_conflicting_types,
        'outgoing_items': outgoing_items,
        'incoming_items': incoming_items,
        'legal_types': sorted(list(legal_types)),
        'legal_tags': sorted(list(legal_tags)),
        'legal_signatures': sorted(list(legal_signatures), key=lambda s: (len(s), s)),
        'tag_aliases': tag_aliases,
    }


def is_unique_outgoing(t, analysis):
    return t in analysis['outgoing_unique_types']


def is_unique_incoming(t, analysis):
    return t in analysis['incoming_unique_types']


def is_unique_field_setter(t, analysis):
    return t in analysis['field_setter_unique_types']


def is_unique_skel_method(sig, analysis):
    return tuple(sig) in analysis['skel_method_unique_sigs']


def is_unique_proxy_method(sig, analysis):
    return tuple(sig) in analysis['proxy_method_unique_sigs']


def is_unique_r_service(r_port, app, domain):
    intf = resolve_intf(r_port, domain)
    sident = service_ident(intf)
    r_ports = get_service_r_ports(app, domain)
    sidents = [service_ident(resolve_intf(r, domain)) for r in r_ports]
    return sidents.count(sident) == 1


def is_unique_p_service(p_port, app, domain):
    intf = resolve_intf(p_port, domain)
    sident = service_ident(intf)
    p_ports = get_service_p_ports(app, domain)
    sidents = [service_ident(resolve_intf(p, domain)) for p in p_ports]
    return sidents.count(sident) == 1


def is_bare_tag_ambiguous(tag_name: str, analysis: dict) -> bool:
    for a in analysis.get("tag_aliases", []):
        if a["name"] == tag_name:
            return a["is_ambiguous"]
    return True


def generate_dummy_value(t: str) -> str:
    t = t.strip()
    if t == "bool":
        return "true"
    elif t in ("float",):
        return "25.0f"
    elif t in ("double",):
        return "25.0"
    elif t in ("uint8_t",):
        return "10u"
    elif t in ("uint16_t",):
        return "100u"
    elif t in ("uint32_t",):
        return "1000u"
    elif t in ("uint64_t",):
        return "10000ULL"
    elif t in ("int8_t",):
        return "5"
    elif t in ("int16_t",):
        return "50"
    elif t in ("int32_t",):
        return "500"
    elif t in ("int64_t",):
        return "5000LL"
    elif t in ("std::string",):
        return 'std::string("sample_text")'
    elif t in ("ara::core::String", "String"):
        return 'ara::core::String{"sample_text"}'
    elif t == "vehicle_data::SpeedData":
        return "vehicle_data::SpeedData{65.0f, 1000000ULL}"
    elif t == "vehicle_data::CabinSensorData":
        return "vehicle_data::CabinSensorData{21.5f, 45.0f, true}"
    elif t == "vehicle_data::EmergencyAlert":
        return 'vehicle_data::EmergencyAlert{1001u, ara::core::String{"Speed limit exceeded"}}'
    elif t == "vehicle_data::LocationPoint":
        return "vehicle_data::LocationPoint{37.7749f, -122.4194f, 15.0f, 65.0f}"
    elif t == "vehicle_data::DriveMode":
        return "vehicle_data::DriveMode::COMFORT"
    elif t == "vehicle_data::SystemStatus":
        return "vehicle_data::SystemStatus::OK"
    elif t == "vehicle_data::BatteryCell":
        return "vehicle_data::BatteryCell{1u, 3.7f, 28.0f}"
    else:
        return f"{t}{{}}"


def generate_dummy_ret(ret_t: str) -> str:
    ret_t = ret_t.strip()
    if ret_t == "void":
        return ""
    elif ret_t == "bool":
        return "true"
    elif ret_t in ("uint8_t", "uint16_t", "uint32_t", "uint64_t"):
        return "1u"
    elif ret_t in ("int8_t", "int16_t", "int32_t", "int64_t"):
        return "1"
    elif ret_t in ("float", "double"):
        return "1.0f"
    elif ret_t in ("ara::core::String", "String", "std::string"):
        return 'ara::core::String{"ok"}'
    elif ret_t == "vehicle_data::DriveMode":
        return "vehicle_data::DriveMode::COMFORT"
    else:
        return f"{ret_t}{{}}"


def resolve_example_handlers(port, domain, analysis, is_shared_service, is_provided, pass_by="const_ref"):
    intf = resolve_intf(port, domain)
    ns = service_ns(intf)
    port_name = port.short_name
    port_ident = port_name.lower()
    incoming_handlers = []

    if is_provided:
        # Skeleton methods (Incoming)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = tuple(a[1] for a in in_args)
            is_uniq = is_unique_skel_method(sig_types, analysis) and not is_shared_service
            ret_t = method_ret_type(m, domain)
            is_faf = is_fire_and_forget(m)
            bare_tag = m.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::methods::{m.short_name}"

            if is_shared_service:
                tag_expr = f"ports::{port_name}::{m.short_name}"
                sig_str = ", ".join(sig_types) if sig_types else "void"
                tag_note = f"MANDATORY TAGGED: on(ports::{port_name}::{m.short_name}, ...) (shared service across ports)"
            elif not is_uniq:
                sig_str = ", ".join(sig_types) if sig_types else "void"
                tag_note = f"Tagged (resolves collision on {sig_str})"
            else:
                tag_note = "Untagged (unique signature)"

            call_kind = "fire-and-forget" if is_faf else "RPC"
            autosar_note = f"AUTOSAR: skeleton.{m.short_name}() {call_kind}"

            incoming_handlers.append({
                "kind": "skel_method",
                "name": m.short_name,
                "tag": f"::reaktar::tags::{ns}::methods::{m.short_name}",
                "tag_expr": tag_expr,
                "bare_tag": bare_tag,
                "is_unique": is_uniq,
                "in_args": [{"name": a[0], "type": a[1], "pass_type": a[2]} for a in in_args],
                "ret_type": ret_t,
                "dummy_ret_expr": generate_dummy_ret(ret_t),
                "is_faf": is_faf,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
                "member_var": f"{port_ident}_{m.short_name.lower()}",
            })

        # Skeleton fields (Setters are Incoming)
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                t = cpp_type(f.type_tref, domain)
                is_uniq = is_unique_field_setter(t, analysis) and not is_shared_service
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"

                if is_shared_service:
                    tag_expr = f"ports::{port_name}::{f.short_name}"
                    tag_note = f"MANDATORY TAGGED: on(ports::{port_name}::{f.short_name}, ...) (shared service across ports)"
                elif not is_uniq:
                    tag_note = f"Tagged (resolves collision on {t})"
                else:
                    tag_note = "Untagged (unique field type)"

                autosar_note = f"AUTOSAR: skeleton.{f.short_name}.RegisterSetHandler()"

                incoming_handlers.append({
                    "kind": "skel_field_set",
                    "name": f.short_name,
                    "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                    "tag_expr": tag_expr,
                    "bare_tag": bare_tag,
                    "is_unique": is_uniq,
                    "payload_type": t,
                    "ret_type": t,
                    "autosar_note": autosar_note,
                    "tag_note": tag_note,
                    "member_var": f"{port_ident}_{f.short_name.lower()}_set",
                })
    else:
        # Proxy events (Incoming)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            is_uniq = is_unique_incoming(t, analysis) and not is_shared_service
            bare_tag = ev.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::events::{ev.short_name}"

            if is_shared_service:
                tag_expr = f"ports::{port_name}::{ev.short_name}"
                tag_note = f"MANDATORY TAGGED: on(ports::{port_name}::{ev.short_name}, val) (shared service across ports)"
            elif not is_uniq:
                tag_note = f"Tagged (resolves collision on {t})"
            else:
                tag_note = "Untagged (unique type)"

            autosar_note = f"AUTOSAR: proxy->{ev.short_name}.Subscribe()"

            incoming_handlers.append({
                "kind": "event",
                "name": ev.short_name,
                "tag": f"::reaktar::tags::{ns}::events::{ev.short_name}",
                "tag_expr": tag_expr,
                "bare_tag": bare_tag,
                "is_unique": is_uniq,
                "payload_type": t,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
                "member_var": f"{port_ident}_{ev.short_name.lower()}",
            })

        # Proxy fields (Notifiers are Incoming)
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_notifier", False):
                t = cpp_type(f.type_tref, domain)
                is_uniq = is_unique_incoming(t, analysis) and not is_shared_service
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"

                if is_shared_service:
                    tag_expr = f"ports::{port_name}::{f.short_name}"
                    tag_note = f"MANDATORY TAGGED: on(ports::{port_name}::{f.short_name}, val) (shared service across ports)"
                elif not is_uniq:
                    tag_note = f"Tagged (resolves collision on {t})"
                else:
                    tag_note = "Untagged (unique type)"

                autosar_note = f"AUTOSAR: proxy->{f.short_name}.Subscribe() notifier"

                incoming_handlers.append({
                    "kind": "field_notify",
                    "name": f.short_name,
                    "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                    "tag_expr": tag_expr,
                    "bare_tag": bare_tag,
                    "is_unique": is_uniq,
                    "payload_type": t,
                    "autosar_note": autosar_note,
                    "tag_note": tag_note,
                    "member_var": f"{port_ident}_{f.short_name.lower()}_notify",
                })

    return incoming_handlers


def resolve_example_emits(port, domain, analysis, port_single_counts_by_port, port_multi_counts_by_port,
                          is_shared_service, is_provided, pass_by="const_ref"):
    intf = resolve_intf(port, domain)
    ns = service_ns(intf)
    port_name = port.short_name
    outgoing_emits = []

    if is_provided:
        # Skeleton events (Outgoing)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            is_uniq = is_unique_outgoing(t, analysis) and not is_shared_service
            bare_tag = ev.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::events::{ev.short_name}"
            dummy_val = generate_dummy_value(t)

            autosar_note = f"AUTOSAR: skeleton.{ev.short_name}.Send()"

            if is_shared_service:
                tag_expr = f"ports::{port_name}::{ev.short_name}"
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>(val) (shared service across ports)"
            elif is_uniq:
                call_untagged = f"emit({dummy_val})"
                tag_note = f"Untagged: emit(val). Alternative: emit<{tag_expr}>(val)"
            else:
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>(val)"

            call_tagged = f"emit<{tag_expr}>({dummy_val})"
            call_port_only = None
            if port_single_counts_by_port.get(port_name, {}).get(t, 0) == 1:
                call_port_only = f"emit<ports::{port_name}>({dummy_val})"

            outgoing_emits.append({
                "kind": "skeleton_event",
                "name": ev.short_name,
                "tag": f"::reaktar::tags::{ns}::events::{ev.short_name}",
                "tag_expr": tag_expr,
                "is_unique": is_uniq,
                "example_call_untagged": call_untagged,
                "example_call_tagged": call_tagged,
                "example_call_port_only": call_port_only,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
            })

        # Skeleton fields (Updates are Outgoing under Law 0: all fields)
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            is_uniq = is_unique_outgoing(t, analysis) and not is_shared_service
            bare_tag = f.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"
            dummy_val = generate_dummy_value(t)

            has_notifier = getattr(f, "has_notifier", False)
            autosar_note = f"AUTOSAR: skeleton.{f.short_name}.Update()" if has_notifier else f"AUTOSAR: skeleton.{f.short_name}.Update() (local state update, no notifier)"

            if is_shared_service:
                tag_expr = f"ports::{port_name}::{f.short_name}"
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>(val) (shared service across ports)"
            elif is_uniq:
                call_untagged = f"emit({dummy_val})"
                tag_note = f"Untagged: emit(val). Alternative: emit<{tag_expr}>(val)"
            else:
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>(val)"

            call_tagged = f"emit<{tag_expr}>({dummy_val})"
            call_port_only = None
            if port_single_counts_by_port.get(port_name, {}).get(t, 0) == 1:
                call_port_only = f"emit<ports::{port_name}>({dummy_val})"

            outgoing_emits.append({
                "kind": "skeleton_field_update",
                "name": f.short_name,
                "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                "tag_expr": tag_expr,
                "is_unique": is_uniq,
                "example_call_untagged": call_untagged,
                "example_call_tagged": call_tagged,
                "example_call_port_only": call_port_only,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
            })
    else:
        # Proxy methods (Outgoing RPC & Fire-and-Forget)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = tuple(a[1] for a in in_args)
            is_faf = is_fire_and_forget(m)
            bare_tag = m.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::methods::{m.short_name}"
            dummy_args_list = [generate_dummy_value(a[1]) for a in in_args]
            dummy_args_str = ", ".join(dummy_args_list)

            if len(in_args) == 1:
                t = in_args[0][1]
                is_uniq = is_unique_outgoing(t, analysis) and not is_shared_service
                port_can_emit = (port_single_counts_by_port.get(port_name, {}).get(t, 0) == 1)
            else:
                is_uniq = is_unique_proxy_method(sig_types, analysis) and not is_shared_service
                port_can_emit = (port_multi_counts_by_port.get(port_name, {}).get(sig_types, 0) == 1)

            call_kind = "fire-and-forget" if is_faf else "RPC"
            autosar_note = f"AUTOSAR: proxy->{m.short_name}() {call_kind}"

            if is_shared_service:
                call_untagged = None
                tag_expr = f"ports::{port_name}::{m.short_name}"
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>({dummy_args_str})"
            elif is_uniq:
                call_untagged = f"emit({dummy_args_str})"
                tag_note = f"Untagged (unique signature). Alternative: emit<{tag_expr}>({dummy_args_str})"
            else:
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>({dummy_args_str})"

            call_tagged = f"emit<{tag_expr}>({dummy_args_str})"
            call_port_only = f"emit<ports::{port_name}>({dummy_args_str})" if port_can_emit else None

            outgoing_emits.append({
                "kind": "proxy_faf" if is_faf else "proxy_rpc",
                "name": m.short_name,
                "tag": f"::reaktar::tags::{ns}::methods::{m.short_name}",
                "tag_expr": tag_expr,
                "is_unique": is_uniq,
                "example_call_untagged": call_untagged,
                "example_call_tagged": call_tagged,
                "example_call_port_only": call_port_only,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
            })

        # Proxy fields (Setters are Outgoing)
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                t = cpp_type(f.type_tref, domain)
                is_uniq = is_unique_outgoing(t, analysis) and not is_shared_service
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"
                dummy_val = generate_dummy_value(t)

                autosar_note = f"AUTOSAR: proxy->{f.short_name}.Set()"
                if is_shared_service:
                    call_untagged = None
                    tag_expr = f"ports::{port_name}::{f.short_name}"
                    tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>({dummy_val})"
                elif is_uniq:
                    call_untagged = f"emit({dummy_val})"
                    tag_note = f"Untagged: emit(val). Alternative: emit<{tag_expr}>({dummy_val})"
                else:
                    call_untagged = None
                    tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>({dummy_val})"

                call_tagged = f"emit<{tag_expr}>({dummy_val})"
                call_port_only = f"emit<ports::{port_name}>({dummy_val})" if (port_single_counts_by_port.get(port_name, {}).get(t, 0) == 1) else None

                outgoing_emits.append({
                    "kind": "proxy_field_set",
                    "name": f.short_name,
                    "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                    "tag_expr": tag_expr,
                    "is_unique": is_uniq,
                    "example_call_untagged": call_untagged,
                    "example_call_tagged": call_tagged,
                    "example_call_port_only": call_port_only,
                    "autosar_note": autosar_note,
                    "tag_note": tag_note,
                })

    return outgoing_emits


def resolve_example_reads(port, domain, analysis, is_shared_service, read_port_info, unique_read_types, read_unique_bare_fields):
    intf = resolve_intf(port, domain)
    ns = service_ns(intf)
    port_name = port.short_name
    readable_queries = []

    for f in sorted_fields(intf.fields):
        if getattr(f, "has_getter", False):
            t = cpp_type(f.type_tref, domain)
            tag_fq = f"::reaktar::tags::{ns}::fields::{f.short_name}"
            port_scoped_tag = f"ports::{port_name}::{f.short_name}"

            can_read_untagged = (t in unique_read_types)
            can_read_port_only = (read_port_info is not None and read_port_info.get("readable_field_count", 0) == 1)

            is_in_read_unique = any(rf["tag"] == tag_fq for rf in read_unique_bare_fields)
            is_ambig_bare = is_bare_tag_ambiguous(f.short_name, analysis)

            if is_in_read_unique and not is_shared_service:
                can_read_bare_tag = True
                bare_tag_expr = f.short_name if not is_ambig_bare else tag_fq
                call_bare_tag = f"read<{bare_tag_expr}>()"
            else:
                can_read_bare_tag = False
                bare_tag_expr = None
                call_bare_tag = None

            call_untagged = f"read<{t}>()" if can_read_untagged else None
            call_port_only = f"read<ports::{port_name}>()" if can_read_port_only else None
            call_port_scoped = f"read<{port_scoped_tag}>()"

            readable_queries.append({
                "name": f.short_name,
                "type": t,
                "tag": tag_fq,
                "port_scoped_tag": port_scoped_tag,
                "can_read_untagged": can_read_untagged,
                "can_read_port_only": can_read_port_only,
                "can_read_bare_tag": can_read_bare_tag,
                "example_call_untagged": call_untagged,
                "example_call_port_only": call_port_only,
                "example_call_bare_tag": call_bare_tag,
                "example_call_port_scoped": call_port_scoped,
                "autosar_note": f"AUTOSAR: proxy->{f.short_name}.Get()",
            })

    return readable_queries


def build_example_interfaces(app, domain, analysis, p_ports, r_ports,
                             port_single_counts_by_port, port_multi_counts_by_port,
                             read_ports, read_by_type, read_unique_bare_fields,
                             pass_by="const_ref") -> list:
    example_interfaces = []
    p_sident_counts = Counter([service_ident(resolve_intf(p, domain)) for p in p_ports])
    r_sident_counts = Counter([service_ident(resolve_intf(r, domain)) for r in r_ports])
    unique_read_types = {item["type"] for item in read_by_type if not item.get("is_ambiguous", False)}
    read_port_map = {p["name"]: p for p in read_ports}

    # 1. Provided Ports (Skeletons)
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        is_shared_service = (p_sident_counts[sident] > 1)
        port_name = p_port.short_name
        port_ident = port_name.lower()
        candidate_alias = strip_port_affixes(port_name)

        incoming_handlers = resolve_example_handlers(
            p_port, domain, analysis, is_shared_service, is_provided=True, pass_by=pass_by
        )
        outgoing_emits = resolve_example_emits(
            p_port, domain, analysis, port_single_counts_by_port, port_multi_counts_by_port,
            is_shared_service, is_provided=True, pass_by=pass_by
        )
        readable_queries = []

        example_interfaces.append({
            "port_name": port_name,
            "port_alias": candidate_alias,
            "port_kind": "Provided",
            "ident": port_ident,
            "intf_name": intf.short_name,
            "intf_ns": ns,
            "incoming_handlers": incoming_handlers,
            "outgoing_emits": outgoing_emits,
            "readable_queries": readable_queries,
        })

    # 2. Required Ports (Proxies)
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        is_shared_service = (r_sident_counts[sident] > 1)
        port_name = r_port.short_name
        port_ident = port_name.lower()
        candidate_alias = strip_port_affixes(port_name)

        incoming_handlers = resolve_example_handlers(
            r_port, domain, analysis, is_shared_service, is_provided=False, pass_by=pass_by
        )
        outgoing_emits = resolve_example_emits(
            r_port, domain, analysis, port_single_counts_by_port, port_multi_counts_by_port,
            is_shared_service, is_provided=False, pass_by=pass_by
        )
        readable_queries = resolve_example_reads(
            r_port, domain, analysis, is_shared_service,
            read_port_map.get(port_name), unique_read_types, read_unique_bare_fields
        )

        example_interfaces.append({
            "port_name": port_name,
            "port_alias": candidate_alias,
            "port_kind": "Required",
            "ident": port_ident,
            "intf_name": intf.short_name,
            "intf_ns": ns,
            "incoming_handlers": incoming_handlers,
            "outgoing_emits": outgoing_emits,
            "readable_queries": readable_queries,
        })

    return example_interfaces


def collect_actor_json_types(app, domain, pass_by="const_ref"):
    """
    Collects all custom structs and enums used by this application by inspecting
    its ports and service interfaces, recursively exploring nested types.
    Gracefully handles unknown or unsupported ARXML types with diagnostics.
    """
    visited_trefs = set()
    structs_map = {}
    enums_map = {}
    warnings = []
    app_name = app.short_name

    def process_tref(tref):
        if not tref or getattr(tref, "is_null", False):
            return
        tref_id = id(tref)
        if tref_id in visited_trefs:
            return
        visited_trefs.add(tref_id)

        name = tref.short_name
        if not name or name in FUNDAMENTAL_CPP_TYPES:
            return

        cat = str(tref.category or "")
        ns_parts = tuple(ns.symbol if hasattr(ns, "symbol") else ns.short_name
                         for ns in (tref.namespaces or []))
        ns_str = "::".join(ns_parts)
        fq_name = f"{ns_str}::{name}" if ns_str else name

        if cat == "STRUCTURE":
            fields = []
            sub_els = tref.sub_elements or tref.cpp_implementation_data_type_elements
            if sub_els:
                for el in sub_els:
                    el_name = el.short_name
                    try:
                        el_tref = el.type_reference_ref
                        el_type = cpp_type(el_tref, domain)
                        fields.append({"name": el_name, "type": el_type})
                        if el_tref:
                            process_tref(el_tref)
                    except Exception as ex:
                        msg = f"Component '{app_name}', struct '{fq_name}': skipping field '{el_name}' (type resolution error: {ex})"
                        warnings.append(msg)
                        print(f"  [WARN] {msg}")
            guard_name = fq_name.replace("::", "_").replace(":", "_").upper()
            structs_map[fq_name] = {
                "name": name,
                "ns_parts": ns_parts,
                "fq_name": fq_name,
                "guard_name": guard_name,
                "fields": fields,
            }
        elif cat == "VECTOR":
            try:
                elem_ref = get_vector_element_tref(tref)
                if elem_ref:
                    process_tref(elem_ref)
            except Exception as ex:
                msg = f"Component '{app_name}': failed resolving vector element for '{name}': {ex}"
                warnings.append(msg)
                print(f"  [WARN] {msg}")
        elif cat == "ARRAY":
            try:
                elem_ref, _ = get_array_element_tref_and_size(tref)
                if elem_ref:
                    process_tref(elem_ref)
            except Exception as ex:
                msg = f"Component '{app_name}': failed resolving array element for '{name}': {ex}"
                warnings.append(msg)
                print(f"  [WARN] {msg}")
        elif cat == "ASSOCIATIVE_MAP":
            try:
                k_ref, v_ref = get_map_key_value_trefs(tref)
                if k_ref:
                    process_tref(k_ref)
                if v_ref:
                    process_tref(v_ref)
            except Exception as ex:
                msg = f"Component '{app_name}': failed resolving map types for '{name}': {ex}"
                warnings.append(msg)
                print(f"  [WARN] {msg}")
        elif cat == "TYPE_REFERENCE":
            try:
                tx = getattr(tref, "x", None)
                compu_methods = tx.compu_methods if tx and hasattr(tx, "compu_methods") else None
                if compu_methods:
                    underlying = tref.type_reference_ref
                    under_name = cpp_type(underlying, domain) if underlying else "uint8_t"
                    items = []
                    cm0 = compu_methods[0]
                    q = getattr(cm0, "q", None) or cm0
                    scales = list(getattr(q, "compu_scales", []) or [])
                    for idx, s in enumerate(scales):
                        val = idx
                        lower_lim = getattr(s, "lower_limit", None)
                        if lower_lim is not None:
                            try:
                                val = int(lower_lim)
                            except (ValueError, TypeError):
                                val = idx
                        sym_name = extract_compu_scale_symbol(s, val)
                        items.append({"name": sym_name, "value": val})
                    guard_name = fq_name.replace("::", "_").replace(":", "_").upper()
                    enums_map[fq_name] = {
                        "name": name,
                        "ns_parts": ns_parts,
                        "fq_name": fq_name,
                        "guard_name": guard_name,
                        "underlying_type": under_name,
                        "enum_items": items,
                    }
                elif tref.type_reference_ref:
                    process_tref(tref.type_reference_ref)
            except Exception as ex:
                msg = f"Component '{app_name}': failed resolving type reference / enum '{name}': {ex}"
        elif cat == "OPTIONAL":
            try:
                elem_ref = get_optional_element_tref(tref)
                if elem_ref:
                    process_tref(elem_ref)
            except Exception as ex:
                msg = f"Component '{app_name}': failed resolving optional element for '{name}': {ex}"
                warnings.append(msg)
                print(f"  [WARN] {msg}")
        elif cat == "UNION":
            try:
                for alt_ref in get_union_alternative_trefs(tref):
                    process_tref(alt_ref)
            except Exception as ex:
                msg = f"Component '{app_name}': failed resolving union alternatives for '{name}': {ex}"
                warnings.append(msg)
                print(f"  [WARN] {msg}")
        elif cat == "OPAQUE":
            msg = f"Component '{app_name}': ARXML category '{cat}' for '{fq_name}' is not supported for JSON serialization; skipping."
            warnings.append(msg)
            print(f"  [WARN] {msg}")

    try:
        all_ports = list(get_service_p_ports(app, domain)) + list(get_service_r_ports(app, domain))
        for p in all_ports:
            intf = resolve_intf(p, domain)
            if not is_service_interface(intf):
                continue

            for ev in intf.events or []:
                if ev.type_tref:
                    process_tref(ev.type_tref)

            for f in intf.fields or []:
                if f.type_tref:
                    process_tref(f.type_tref)

            for m in intf.methods or []:
                for arg in m.arguments or []:
                    if arg.type_tref:
                        process_tref(arg.type_tref)
    except Exception as ex:
        msg = f"Component '{app_name}': port inspection encountered error during JSON type collection: {ex}"
        warnings.append(msg)
        print(f"  [WARN] {msg}")

    structs_by_ns = defaultdict(list)
    sorted_structs = sorted(structs_map.values(), key=lambda s: s["fq_name"])
    for s in sorted_structs:
        structs_by_ns[s["ns_parts"]].append(s)

    enums_by_ns = defaultdict(list)
    sorted_enums = sorted(enums_map.values(), key=lambda e: e["fq_name"])
    for e in sorted_enums:
        enums_by_ns[e["ns_parts"]].append(e)

    return {
        "structs": sorted_structs,
        "enums": sorted_enums,
        "structs_by_ns": dict(sorted(structs_by_ns.items())),
        "enums_by_ns": dict(sorted(enums_by_ns.items())),
        "warnings": warnings,
    }


def build_actor_model(app, domain, analysis, pass_by="const_ref"):
    exe_name = app_exe_name(app)
    app_short_name = app.short_name

    p_ports = sorted_ports(get_service_p_ports(app, domain))
    r_ports = sorted_ports(get_service_r_ports(app, domain))

    skeleton_headers = []
    for p in p_ports:
        h = skeleton_header(resolve_intf(p, domain))
        if h not in skeleton_headers:
            skeleton_headers.append(h)
    skeleton_headers.sort()

    proxy_headers = []
    for r in r_ports:
        h = proxy_header(resolve_intf(r, domain))
        if h not in proxy_headers:
            proxy_headers.append(h)
    proxy_headers.sort()

    r_sident_counts = Counter([service_ident(resolve_intf(r, domain)) for r in r_ports])
    p_sident_counts = Counter([service_ident(resolve_intf(p, domain)) for p in p_ports])

    r_event_counts = Counter()
    r_field_notif_counts = Counter()
    r_event_ports = defaultdict(list)
    r_field_notif_ports = defaultdict(list)
    for r in r_ports:
        r_intf = resolve_intf(r, domain)
        r_ns = service_ns(r_intf)
        for ev in r_intf.events:
            tag = f"{r_ns}::events::{ev.short_name}"
            r_event_counts[tag] += 1
            r_event_ports[tag].append(r.short_name)
        for f in r_intf.fields:
            if getattr(f, "has_notifier", False):
                tag = f"{r_ns}::fields::{f.short_name}"
                r_field_notif_counts[tag] += 1
                r_field_notif_ports[tag].append(r.short_name)

    p_method_counts = Counter()
    p_field_setter_counts = Counter()
    p_method_ports = defaultdict(list)
    p_field_setter_ports = defaultdict(list)
    for p in p_ports:
        p_intf = resolve_intf(p, domain)
        p_ns = service_ns(p_intf)
        for m in p_intf.methods:
            tag = f"::reaktar::tags::{p_ns}::methods::{m.short_name}"
            p_method_counts[tag] += 1
            p_method_ports[tag].append(p.short_name)
        for f in p_intf.fields:
            if getattr(f, "has_setter", False):
                tag = f"{p_ns}::fields::{f.short_name}"
                p_field_setter_counts[tag] += 1
                p_field_setter_ports[tag].append(p.short_name)

    consumed_proxies = []
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        port_ident = r_port.short_name.lower()
        is_unique_service = (r_sident_counts[sident] == 1)
        pcls = proxy_cls(intf)
        instance_spec = resolve_instance_specifier(app, r_port)

        port_incoming_types = [cpp_type(ev.type_tref, domain) for ev in intf.events] + \
                              [cpp_type(f.type_tref, domain) for f in intf.fields if getattr(f, "has_notifier", False)]

        port_inbound_signals = []
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            port_inbound_signals.append({"name": ev.short_name, "type": t, "kind": "event"})
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_notifier", False):
                t = cpp_type(f.type_tref, domain)
                port_inbound_signals.append({"name": f.short_name, "type": t, "kind": "field notifier"})

        ev_list = []
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            tag = f"{ns}::events::{ev.short_name}"
            matching_ports = sorted(r_event_ports[tag])
            competing_on_port = [it for it in port_inbound_signals if it["type"] == t]
            ev_list.append({
                "name": ev.short_name,
                "type": t,
                "tag": tag,
                "is_unique": is_unique_incoming(t, analysis),
                "is_unique_on_port": (port_incoming_types.count(t) == 1),
                "is_unique_across_ports": (r_event_counts[tag] == 1),
                "port_count": r_event_counts[tag],
                "matching_ports": matching_ports,
                "competing_on_port": competing_on_port,
            })

        field_list = []
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            tag = f"{ns}::fields::{f.short_name}"
            has_notif = bool(getattr(f, "has_notifier", False))
            has_get = bool(getattr(f, "has_getter", False))
            has_set = bool(getattr(f, "has_setter", False))
            matching_ports = sorted(r_field_notif_ports[tag]) if has_notif else []
            competing_on_port = [it for it in port_inbound_signals if it["type"] == t] if has_notif else []
            field_list.append({
                "name": f.short_name,
                "type": t,
                "tag": tag,
                "has_notifier": has_notif,
                "has_getter": has_get,
                "has_setter": has_set,
                "is_unique": is_unique_incoming(t, analysis),
                "is_unique_on_port": (port_incoming_types.count(t) == 1) if has_notif else True,
                "is_unique_across_ports": (r_field_notif_counts[tag] == 1) if has_notif else True,
                "port_count": r_field_notif_counts[tag],
                "matching_ports": matching_ports,
                "competing_on_port": competing_on_port,
            })

        proxy_methods_list = []
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]
            proxy_methods_list.append({
                "name": m.short_name,
                "is_faf": is_fire_and_forget(m),
                "in_args": [
                    {"name": aname, "type": atype, "pass_type": ptype}
                    for aname, atype, ptype in in_args
                ],
                "sig_types": sig_types,
            })

        unsub_targets = [ev["name"] for ev in ev_list] + [f["name"] for f in field_list if f["has_notifier"]]

        inbound_signals = []
        for ev in ev_list:
            inbound_signals.append({
                "name": ev["name"],
                "type": ev["type"],
                "tag": ev["tag"],
                "signal_kind": "event",
                "signal_label": "event",
                "signal_label_cap": "Event",
                "shared_type_label": "event payload type",
                "port_tag_label": "port event tag",
                "is_unique": ev["is_unique"],
                "is_unique_on_port": ev["is_unique_on_port"],
                "is_unique_across_ports": ev["is_unique_across_ports"],
                "port_count": ev["port_count"],
                "port_name": r_port.short_name,
                "port_ident": port_ident,
                "matching_ports": ev["matching_ports"],
                "competing_on_port": ev["competing_on_port"],
            })
        for f in field_list:
            if f["has_notifier"]:
                inbound_signals.append({
                    "name": f["name"],
                    "type": f["type"],
                    "tag": f["tag"],
                    "signal_kind": "field_notifier",
                    "signal_label": "field notifier",
                    "signal_label_cap": "Field notifier",
                    "shared_type_label": "field notifier type",
                    "port_tag_label": "port field tag",
                    "is_unique": f["is_unique"],
                    "is_unique_on_port": f["is_unique_on_port"],
                    "is_unique_across_ports": f["is_unique_across_ports"],
                    "port_count": f["port_count"],
                    "port_name": r_port.short_name,
                    "port_ident": port_ident,
                    "matching_ports": f["matching_ports"],
                    "competing_on_port": f["competing_on_port"],
                })

        consumed_proxies.append({
            "port_name": r_port.short_name,
            "ident": port_ident,
            "service_ident": sident,
            "service_ns": ns,
            "is_unique_service": is_unique_service,
            "cls": pcls,
            "slot_name": f"{port_ident}_slot_",
            "find_handle_name": f"{port_ident}_find_handle_",
            "instance_spec": instance_spec,
            "events": ev_list,
            "fields": field_list,
            "inbound_signals": inbound_signals,
            "methods": proxy_methods_list,
            "all_unsubscribe_targets": unsub_targets,
        })

    inbound_signals_flat = [sig for cp in consumed_proxies for sig in cp["inbound_signals"]]

    skeletons = []
    skeleton_fields_flat = []
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        scls = skeleton_cls(intf)
        instance_spec = resolve_instance_specifier(app, p_port)
        var_name = f"{p_port.short_name.lower()}_skeleton_"
        adapter_name = f"{p_port.short_name}SkeletonAdapter"

        ev_list = []
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            tag = f"{ns}::events::{ev.short_name}"
            ev_list.append({
                "name": ev.short_name,
                "type": t,
                "tag": tag,
                "is_unique": is_unique_outgoing(t, analysis),
            })

        port_method_sigs = []
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = tuple(a[1] for a in in_args)
            port_method_sigs.append(sig_types)

        port_setter_items = [{"name": f.short_name, "type": cpp_type(f.type_tref, domain)} for f in sorted_fields(intf.fields) if getattr(f, "has_setter", False)]

        method_list = []
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]
            is_faf = is_fire_and_forget(m)
            ret_t = method_ret_type(m, domain)
            tag = f"::reaktar::tags::{ns}::methods::{m.short_name}"
            is_unique_sig = is_unique_skel_method(sig_types, analysis)
            is_unique_sig_on_port = (port_method_sigs.count(tuple(sig_types)) == 1)
            matching_ports = sorted(p_method_ports[tag])

            method_list.append({
                "name": m.short_name,
                "tag": tag,
                "is_faf": is_faf,
                "ret_type": ret_t,
                "in_args": [
                    {"name": aname, "type": atype, "pass_type": ptype}
                    for aname, atype, ptype in in_args
                ],
                "sig_types": sig_types,
                "is_unique_sig": is_unique_sig,
                "is_unique_sig_on_port": is_unique_sig_on_port,
                "is_unique_across_ports": (p_method_counts[tag] == 1),
                "port_count": p_method_counts[tag],
                "matching_ports": matching_ports,
            })

        for m in method_list:
            m["competing_on_port"] = [om for om in method_list if om["sig_types"] == m["sig_types"]]

        port_setter_types = [cpp_type(f.type_tref, domain) for f in intf.fields if getattr(f, "has_setter", False)]

        field_list = []
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            tag = f"{ns}::fields::{f.short_name}"
            has_notif = bool(getattr(f, "has_notifier", False))
            has_get = bool(getattr(f, "has_getter", False))
            has_set = bool(getattr(f, "has_setter", False))
            is_uniq_set = is_unique_field_setter(t, analysis) if has_set else False
            is_uniq_setter_on_port = (port_setter_types.count(t) == 1) if has_set else False
            matching_ports = sorted(p_field_setter_ports[tag]) if has_set else []
            competing_on_port = [it for it in port_setter_items if it["type"] == t] if has_set else []

            f_info = {
                "name": f.short_name,
                "type": t,
                "tag": tag,
                "var_name": var_name,
                "port_name": p_port.short_name,
                "port_ident": p_port.short_name.lower(),
                "has_notifier": has_notif,
                "has_getter": has_get,
                "has_setter": has_set,
                "is_unique_setter": is_uniq_set,
                "is_unique_setter_on_port": is_uniq_setter_on_port,
                "is_unique_across_ports": (p_field_setter_counts[tag] == 1) if has_set else True,
                "port_count": p_field_setter_counts[tag],
                "matching_ports": matching_ports,
                "competing_on_port": competing_on_port,
            }
            field_list.append(f_info)
            skeleton_fields_flat.append(f_info)

        skeletons.append({
            "port_name": p_port.short_name,
            "intf_name": intf.short_name,
            "var_name": var_name,
            "getter_name": f"get_{p_port.short_name.lower()}_skeleton",
            "adapter_name": adapter_name,
            "cls": scls,
            "instance_spec": instance_spec,
            "events": ev_list,
            "methods": method_list,
            "fields": field_list,
            "service_ident": sident,
            "service_ns": ns,
            "is_unique_service": (p_sident_counts[sident] == 1),
        })

    outbound_tagged = []
    outbound_ambiguous_tags = []
    # 1. Skeleton events & field updates
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        var_name = f"{p_port.short_name.lower()}_skeleton_"
        is_unique = (p_sident_counts[sident] == 1)

        for ev in sorted_events(intf.events):
            ev_arg_types = [cpp_type(ev.type_tref, domain)]
            outbound_tagged.append({
                "kind": "skeleton_event",
                "tag": f"typename ActorBase::ports::{p_port.short_name}::{ev.short_name}",
                "var_name": var_name,
                "member": ev.short_name,
                "slot_name": None,
                "port_name": p_port.short_name,
                "service_ident": None,
                "arg_types": ev_arg_types,
            })
            if is_unique:
                outbound_tagged.append({
                    "kind": "skeleton_event",
                    "tag": f"::reaktar::tags::{ns}::events::{ev.short_name}",
                    "var_name": var_name,
                    "member": ev.short_name,
                    "slot_name": None,
                    "port_name": p_port.short_name,
                    "service_ident": None,
                    "arg_types": ev_arg_types,
                })
            else:
                ambig_tag = f"::reaktar::tags::{ns}::events::{ev.short_name}"
                matching_ports = sorted([p.short_name for p in p_ports if service_ident(resolve_intf(p, domain)) == sident])
                if ambig_tag not in [x["tag"] for x in outbound_ambiguous_tags]:
                    outbound_ambiguous_tags.append({
                        "tag": ambig_tag,
                        "service": sident,
                        "name": ev.short_name,
                        "ports": matching_ports,
                    })
        for f in sorted_fields(intf.fields):
            f_arg_types = [cpp_type(f.type_tref, domain)]
            outbound_tagged.append({
                "kind": "skeleton_field_update",
                "tag": f"typename ActorBase::ports::{p_port.short_name}::{f.short_name}",
                "var_name": var_name,
                "member": f.short_name,
                "slot_name": None,
                "port_name": p_port.short_name,
                "service_ident": None,
                "arg_types": f_arg_types,
            })
            if is_unique:
                outbound_tagged.append({
                    "kind": "skeleton_field_update",
                    "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                    "var_name": var_name,
                    "member": f.short_name,
                    "slot_name": None,
                    "port_name": p_port.short_name,
                    "service_ident": None,
                    "arg_types": f_arg_types,
                })
            else:
                ambig_tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                matching_ports = sorted([p.short_name for p in p_ports if service_ident(resolve_intf(p, domain)) == sident])
                if ambig_tag not in [x["tag"] for x in outbound_ambiguous_tags]:
                    outbound_ambiguous_tags.append({
                        "tag": ambig_tag,
                        "service": sident,
                        "name": f.short_name,
                        "ports": matching_ports,
                    })

    # 2. Proxy methods & fields
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        port_ident = r_port.short_name.lower()
        slot_name = f"{port_ident}_slot_"
        is_unique = (r_sident_counts[sident] == 1)

        for m in sorted_methods(intf.methods):
            is_faf = is_fire_and_forget(m)
            m_in_args = method_in_args(m, domain, pass_by=pass_by)
            m_arg_types = [a[1] for a in m_in_args]
            outbound_tagged.append({
                "kind": "proxy_faf" if is_faf else "proxy_rpc",
                "tag": f"typename ActorBase::ports::{r_port.short_name}::{m.short_name}",
                "var_name": None,
                "member": m.short_name,
                "slot_name": slot_name,
                "port_name": r_port.short_name,
                "service_ident": sident,
                "arg_types": m_arg_types,
            })
            if is_unique:
                outbound_tagged.append({
                    "kind": "proxy_faf" if is_faf else "proxy_rpc",
                    "tag": f"::reaktar::tags::{ns}::methods::{m.short_name}",
                    "var_name": None,
                    "member": m.short_name,
                    "slot_name": slot_name,
                    "port_name": r_port.short_name,
                    "service_ident": sident,
                    "arg_types": m_arg_types,
                })
            else:
                ambig_tag = f"::reaktar::tags::{ns}::methods::{m.short_name}"
                matching_ports = sorted([r.short_name for r in r_ports if service_ident(resolve_intf(r, domain)) == sident])
                if ambig_tag not in [x["tag"] for x in outbound_ambiguous_tags]:
                    outbound_ambiguous_tags.append({
                        "tag": ambig_tag,
                        "service": sident,
                        "name": m.short_name,
                        "ports": matching_ports,
                    })
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                f_set_arg_types = [cpp_type(f.type_tref, domain)]
                outbound_tagged.append({
                    "kind": "proxy_field_set",
                    "tag": f"typename ActorBase::ports::{r_port.short_name}::{f.short_name}",
                    "var_name": None,
                    "member": f.short_name,
                    "slot_name": slot_name,
                    "port_name": r_port.short_name,
                    "service_ident": sident,
                    "arg_types": f_set_arg_types,
                })
                if is_unique:
                    outbound_tagged.append({
                        "kind": "proxy_field_set",
                        "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                        "var_name": None,
                        "member": f.short_name,
                        "slot_name": slot_name,
                        "port_name": r_port.short_name,
                        "service_ident": sident,
                        "arg_types": f_set_arg_types,
                    })
                else:
                    ambig_tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                    matching_ports = sorted([r.short_name for r in r_ports if service_ident(resolve_intf(r, domain)) == sident])
                    if ambig_tag not in [x["tag"] for x in outbound_ambiguous_tags]:
                        outbound_ambiguous_tags.append({
                            "tag": ambig_tag,
                            "service": sident,
                            "name": f.short_name,
                            "ports": matching_ports,
                        })

    # -------------------------------------------------------------------------
    # Fan-Out Outbound Interface Tags (Tier 3: emit<Tag::Any> / emit<Tag::All>)
    # -------------------------------------------------------------------------
    outbound_fan_out_tags = []
    # Collect all unique service interfaces referenced across p_ports and r_ports
    all_intfs = set()
    for p in p_ports:
        all_intfs.add(resolve_intf(p, domain))
    for r in r_ports:
        all_intfs.add(resolve_intf(r, domain))
    fan_out_seen_tags = set()
    for intf in sorted(list(all_intfs), key=lambda x: x.short_name):
        ns = service_ns(intf)
        sident = service_ident(intf)

        for ev in sorted_events(intf.events):
            tag_name = ev.short_name
            fq_tag = f"::reaktar::tags::{ns}::events::{tag_name}::Any"
            if fq_tag in fan_out_seen_tags:
                continue
            fan_out_seen_tags.add(fq_tag)

            matching_ports = []
            for p in skeletons:
                if p["intf_name"] == intf.short_name:
                    matching_ports.append({
                        "kind": "skeleton_event",
                        "port_name": p["port_name"],
                        "var_name": p["var_name"],
                        "member": ev.short_name,
                    })

            t = cpp_type(ev.type_tref, domain)
            outbound_fan_out_tags.append({
                "kind": "event",
                "tag": fq_tag,
                "name": tag_name,
                "service": sident,
                "payload_type": t,
                "matching_ports": matching_ports,
            })

        for m in sorted_methods(intf.methods):
            tag_name = m.short_name
            fq_tag = f"::reaktar::tags::{ns}::methods::{tag_name}::Any"
            if fq_tag in fan_out_seen_tags:
                continue
            fan_out_seen_tags.add(fq_tag)

            is_faf = is_fire_and_forget(m)
            ret_t = method_ret_type(m, domain)
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]

            matching_ports = []
            for cp in consumed_proxies:
                if cp["service_ident"] == sident:
                    matching_ports.append({
                        "kind": "proxy_faf",
                        "port_name": cp["port_name"],
                        "slot_name": cp["slot_name"],
                        "member": m.short_name,
                    })

            first_port_name = matching_ports[0]["port_name"] if matching_ports else "UnknownPort"

            outbound_fan_out_tags.append({
                "kind": "method",
                "tag": fq_tag,
                "name": tag_name,
                "service": sident,
                "is_faf": is_faf,
                "ret_type": ret_t,
                "sig_types": sig_types,
                "matching_ports": matching_ports,
                "first_port_name": first_port_name,
            })

        for f in sorted_fields(intf.fields):
            tag_name = f.short_name
            fq_tag = f"::reaktar::tags::{ns}::fields::{tag_name}::Any"
            if fq_tag in fan_out_seen_tags:
                continue
            fan_out_seen_tags.add(fq_tag)

            has_set = bool(getattr(f, "has_setter", False))
            has_get = bool(getattr(f, "has_getter", False))
            has_notif = bool(getattr(f, "has_notifier", False))
            t = cpp_type(f.type_tref, domain)

            matching_ports = []
            if has_notif:
                for p in skeletons:
                    if p["intf_name"] == intf.short_name:
                        matching_ports.append({
                            "kind": "skeleton_field_update",
                            "port_name": p["port_name"],
                            "var_name": p["var_name"],
                            "member": f.short_name,
                        })

            outbound_fan_out_tags.append({
                "kind": "field",
                "tag": fq_tag,
                "name": tag_name,
                "service": sident,
                "has_setter": has_set,
                "has_getter": has_get,
                "has_notifier": has_notif,
                "type": t,
                "matching_ports": matching_ports,
            })

    # -------------------------------------------------------------------------
    # Global Outbound Items (for Tier 4: emit<reaktar::Any>(payload) and Ambiguity Checking)
    # -------------------------------------------------------------------------
    all_raw_outbound_items = []
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        var_name = f"{p_port.short_name.lower()}_skeleton_"
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            all_raw_outbound_items.append({
                "kind": "skeleton_event",
                "type": t,
                "var_name": var_name,
                "member": ev.short_name,
                "slot_name": None,
                "port_name": p_port.short_name,
            })
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            all_raw_outbound_items.append({
                "kind": "skeleton_field_update",
                "type": t,
                "var_name": var_name,
                "member": f.short_name,
                "slot_name": None,
                "port_name": p_port.short_name,
            })

    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        port_ident = r_port.short_name.lower()
        slot_name = f"{port_ident}_slot_"
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            if len(in_args) == 1 and is_fire_and_forget(m):
                all_raw_outbound_items.append({
                    "kind": "proxy_faf",
                    "type": in_args[0][1],
                    "var_name": None,
                    "member": m.short_name,
                    "slot_name": slot_name,
                    "port_name": r_port.short_name,
                })

    global_type_map = defaultdict(list)
    for it in all_raw_outbound_items:
        global_type_map[it["type"]].append(it)

    global_outbound_by_type = []
    for t in sorted(global_type_map.keys()):
        global_outbound_by_type.append({
            "type": t,
            "targets": global_type_map[t],
        })

    outbound_ambiguous_types = sorted(list(
        set(analysis.get("outgoing_conflicting_types", {}).keys()) |
        {t for t, items in global_type_map.items() if len(items) > 1}
    ))

    outgoing_items = analysis.get("outgoing_items", [])

    def format_outbound_kind(kind, obj=None):
        if kind in ("event", "skeleton_event"):
            return "event"
        elif kind in ("field_update", "field", "skeleton_field_update"):
            return "field"
        elif kind in ("rpc_arg", "proxy_rpc", "proxy_faf"):
            if obj is not None and is_fire_and_forget(obj):
                return "fire-and-forget method"
            return "RPC method"
        elif kind in ("field_set", "proxy_field_set"):
            return "field setter"
        return kind

    ambiguous_untagged_emit_details = []
    for t in outbound_ambiguous_types:
        seen_targets = set()
        targets = []
        for it in outgoing_items:
            # it: (kind, member_name, type, port_name, intf, raw_obj)
            if it[2] == t:
                k = format_outbound_kind(it[0], it[5])
                key = (it[3], it[1], k)
                if key not in seen_targets:
                    seen_targets.add(key)
                    targets.append({
                        "port": it[3],
                        "member": it[1],
                        "kind": k,
                    })
        if not targets and t in global_type_map:
            for it in global_type_map[t]:
                k = format_outbound_kind(it["kind"])
                key = (it["port_name"], it["member"], k)
                if key not in seen_targets:
                    seen_targets.add(key)
                    targets.append({
                        "port": it["port_name"],
                        "member": it["member"],
                        "kind": k,
                    })
        targets.sort(key=lambda x: (x["port"], x["member"]))
        ambiguous_untagged_emit_details.append({
            "type": t,
            "targets": targets,
        })
    ambiguous_untagged_emit_details.sort(key=lambda x: x["type"])

    outbound_by_type = []
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        var_name = f"{p_port.short_name.lower()}_skeleton_"
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            if is_unique_outgoing(t, analysis):
                outbound_by_type.append({
                    "kind": "skeleton_event",
                    "type": t,
                    "var_name": var_name,
                    "member": ev.short_name,
                    "slot_name": None,
                    "port_name": p_port.short_name,
                    "service_ident": None,
                })
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            if is_unique_outgoing(t, analysis):
                outbound_by_type.append({
                    "kind": "skeleton_field_update",
                    "type": t,
                    "var_name": var_name,
                    "member": f.short_name,
                    "slot_name": None,
                    "port_name": p_port.short_name,
                    "service_ident": None,
                })

    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        sident = service_ident(intf)
        port_ident = r_port.short_name.lower()
        slot_name = f"{port_ident}_slot_"
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            if len(in_args) == 1:
                t = in_args[0][1]
                if is_unique_outgoing(t, analysis):
                    is_faf = is_fire_and_forget(m)
                    outbound_by_type.append({
                        "kind": "proxy_faf" if is_faf else "proxy_rpc",
                        "type": t,
                        "var_name": None,
                        "member": m.short_name,
                        "slot_name": slot_name,
                        "port_name": r_port.short_name,
                        "service_ident": sident,
                    })
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                t = cpp_type(f.type_tref, domain)
                if is_unique_outgoing(t, analysis):
                    outbound_by_type.append({
                        "kind": "proxy_field_set",
                        "type": t,
                        "var_name": None,
                        "member": f.short_name,
                        "slot_name": slot_name,
                        "port_name": r_port.short_name,
                        "service_ident": sident,
                    })

    outbound_multi = []
    proxy_methods_by_sig = defaultdict(list)
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        sident = service_ident(intf)
        port_ident = r_port.short_name.lower()
        slot_name = f"{port_ident}_slot_"
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            if len(in_args) != 1:
                sig_types = tuple(a[1] for a in in_args)
                is_faf = is_fire_and_forget(m)
                disp_k = "fire-and-forget method" if is_faf else "RPC method"
                proxy_methods_by_sig[sig_types].append({
                    "port_name": r_port.short_name,
                    "member": m.short_name,
                    "is_faf": is_faf,
                    "display_kind": disp_k,
                    "slot_name": slot_name,
                    "service_ident": sident,
                })
                if is_unique_proxy_method(sig_types, analysis):
                    outbound_multi.append({
                        "sig_types": sig_types,
                        "is_faf": is_faf,
                        "display_kind": disp_k,
                        "member": m.short_name,
                        "slot_name": slot_name,
                        "port_name": r_port.short_name,
                        "service_ident": sident,
                    })

    ambiguous_outbound_multi = []
    for sig_types, targets in sorted(proxy_methods_by_sig.items(), key=lambda x: (len(x[0]), x[0])):
        if len(targets) > 1:
            ambiguous_outbound_multi.append({
                "sig_types": sig_types,
                "targets": sorted(targets, key=lambda x: (x["port_name"], x["member"])),
            })

    all_ports = []
    for p in skeletons:
        all_ports.append({
            "port_name": p["port_name"],
            "kind": "Provided",
            "kind_tag": "::reaktar::ProvidedPortTag",
            "intf_name": p["intf_name"],
            "service_ns": p["service_ns"],
            "cls": p["cls"],
            "var_name": p["var_name"],
            "ident": p["port_name"].lower(),
            "events": p["events"],
            "fields": p["fields"],
            "methods": p["methods"],
        })
    for cp in consumed_proxies:
        all_ports.append({
            "port_name": cp["port_name"],
            "kind": "Required",
            "kind_tag": "::reaktar::RequiredPortTag",
            "service_ns": cp["service_ns"],
            "cls": cp["cls"],
            "slot_name": cp["slot_name"],
            "find_handle_name": cp["find_handle_name"],
            "instance_spec": cp["instance_spec"],
            "ident": cp["ident"],
            "all_unsubscribe_targets": cp["all_unsubscribe_targets"],
            "events": cp["events"],
            "fields": cp["fields"],
            "methods": cp["methods"],
        })

    # Determine collision-free ergonomic port aliases
    canonical_port_names = {p["port_name"] for p in all_ports}
    alias_map = defaultdict(list)
    for p in all_ports:
        candidate = strip_port_affixes(p["port_name"])
        if candidate and candidate not in canonical_port_names:
            alias_map[candidate].append(p["port_name"])

    port_aliases = []
    for alias, origins in sorted(alias_map.items()):
        if len(origins) == 1:
            port_aliases.append({
                "alias": alias,
                "target": origins[0],
                "is_ambiguous": False,
            })
        else:
            port_aliases.append({
                "alias": alias,
                "conflicts": ", ".join(origins),
                "is_ambiguous": True,
            })

    # -------------------------------------------------------------------------
    # Port-Only Outbound Emit Dispatch Structures
    # -------------------------------------------------------------------------
    ports_outbound = []
    port_single_counts_by_port = {}
    port_multi_counts_by_port = {}

    for port in all_ports:
        port_name = port["port_name"]
        is_provided = (port["kind"] == "Provided")
        raw_single_items = []
        raw_multi_items = []

        if is_provided:
            var_name = port["var_name"]
            for ev in port["events"]:
                raw_single_items.append({
                    "kind": "skeleton_event",
                    "type": ev["type"],
                    "var_name": var_name,
                    "member": ev["name"],
                    "port_name": port_name,
                })
            for f in port["fields"]:
                raw_single_items.append({
                    "kind": "skeleton_field_update",
                    "type": f["type"],
                    "var_name": var_name,
                    "member": f["name"],
                    "port_name": port_name,
                })
        else:
            slot_name = port["slot_name"]
            for m in port["methods"]:
                is_faf = m["is_faf"]
                sig_types = m["sig_types"]
                if len(sig_types) == 1:
                    raw_single_items.append({
                        "kind": "proxy_faf" if is_faf else "proxy_rpc",
                        "type": sig_types[0],
                        "var_name": None,
                        "member": m["name"],
                        "slot_name": slot_name,
                        "port_name": port_name,
                    })
                else:
                    raw_multi_items.append({
                        "kind": "proxy_faf" if is_faf else "proxy_rpc",
                        "sig_types": sig_types,
                        "var_name": None,
                        "member": m["name"],
                        "slot_name": slot_name,
                        "port_name": port_name,
                        "is_faf": is_faf,
                    })
            for f in port["fields"]:
                if f.get("has_setter", False):
                    raw_single_items.append({
                        "kind": "proxy_field_set",
                        "type": f["type"],
                        "var_name": None,
                        "member": f["name"],
                        "slot_name": slot_name,
                        "port_name": port_name,
                    })

        single_type_counts = Counter([it["type"] for it in raw_single_items])
        multi_sig_counts = Counter([tuple(it["sig_types"]) for it in raw_multi_items])
        port_single_counts_by_port[port_name] = single_type_counts
        port_multi_counts_by_port[port_name] = multi_sig_counts

        display_kinds = {
            "skeleton_event": "event",
            "skeleton_field_update": "field",
            "proxy_faf": "fire-and-forget method",
            "proxy_rpc": "RPC method",
            "proxy_field_set": "field setter",
        }

        seen_types = set()
        single_arg_items = []
        for it in sorted(raw_single_items, key=lambda x: (x["type"], x["member"])):
            t = it["type"]
            if t in seen_types:
                continue
            seen_types.add(t)
            is_ambig = (single_type_counts[t] > 1)
            item_copy = dict(it)
            item_copy["is_ambiguous"] = is_ambig
            item_copy["display_kind"] = display_kinds.get(it["kind"], it["kind"])
            single_arg_items.append(item_copy)

        ambiguous_single_groups = []
        ambig_single_types = sorted([t for t, count in single_type_counts.items() if count > 1])
        for t in ambig_single_types:
            matching = [dict(it) for it in raw_single_items if it["type"] == t]
            for it in matching:
                it["display_kind"] = display_kinds.get(it["kind"], it["kind"])
            matching.sort(key=lambda x: x["member"])
            ambiguous_single_groups.append({
                "type": t,
                "targets": matching,
            })

        seen_sigs = set()
        multi_arg_items = []
        for it in sorted(raw_multi_items, key=lambda x: (tuple(x["sig_types"]), x["member"])):
            sig = tuple(it["sig_types"])
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            is_ambig = (multi_sig_counts[sig] > 1)
            item_copy = dict(it)
            item_copy["is_ambiguous"] = is_ambig
            if is_ambig:
                item_copy["conflicting_methods"] = sorted([
                    {
                        "member": x["member"],
                        "display_kind": ("fire-and-forget method" if x["is_faf"] else "RPC method"),
                    }
                    for x in raw_multi_items if tuple(x["sig_types"]) == sig
                ], key=lambda x: x["member"])
            else:
                item_copy["conflicting_methods"] = []
            multi_arg_items.append(item_copy)

        wildcard_type_map = defaultdict(list)
        for it in raw_single_items:
            if it["kind"] in ("skeleton_event", "skeleton_field_update", "proxy_faf"):
                wildcard_type_map[it["type"]].append(it)

        wildcard_single_groups = []
        for t in sorted(wildcard_type_map.keys()):
            wildcard_single_groups.append({
                "type": t,
                "targets": wildcard_type_map[t],
            })

        total_outbound = len(raw_single_items) + len(raw_multi_items)
        ports_outbound.append({
            "name": port_name,
            "total_outbound_count": total_outbound,
            "single_arg_items": single_arg_items,
            "multi_arg_items": multi_arg_items,
            "wildcard_single_groups": wildcard_single_groups,
            "ambiguous_single_groups": ambiguous_single_groups,
        })

    ports_outbound.sort(key=lambda x: x["name"])

    # -------------------------------------------------------------------------
    # Inbound Handlers (on) Ambiguity & Port Dispatch Structures
    # -------------------------------------------------------------------------
    # Inbound sources:
    # 1. R-Port Events (kind: "event", 1-arg payload)
    # 2. R-Port Field Notifiers (kind: "field_notifier", 1-arg payload)
    # 3. P-Port Skeleton Methods (kind: "method", single-arg or multi-arg)
    # 4. P-Port Field Setters (kind: "field_setter", 1-arg payload)
    all_raw_inbound_items = []
    inbound_tagged = []
    inbound_ambiguous_tags = []

    # 1. R-Ports (Events & Field Notifiers)
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        is_unique_intf = (r_sident_counts[sident] == 1)

        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            all_raw_inbound_items.append({
                "kind": "event",
                "type": t,
                "member": ev.short_name,
                "port_name": r_port.short_name,
                "display_kind": "event",
            })
            inbound_tagged.append({
                "kind": "event",
                "tag": f"typename ActorBase::ports::{r_port.short_name}::{ev.short_name}",
                "member": ev.short_name,
                "port_name": r_port.short_name,
                "type": t,
            })
            if is_unique_intf:
                inbound_tagged.append({
                    "kind": "event",
                    "tag": f"::reaktar::tags::{ns}::events::{ev.short_name}",
                    "member": ev.short_name,
                    "port_name": r_port.short_name,
                    "type": t,
                })
            else:
                ambig_tag = f"::reaktar::tags::{ns}::events::{ev.short_name}"
                matching_ports = sorted([r.short_name for r in r_ports if service_ident(resolve_intf(r, domain)) == sident])
                if ambig_tag not in [x["tag"] for x in inbound_ambiguous_tags]:
                    inbound_ambiguous_tags.append({
                        "tag": ambig_tag,
                        "service": sident,
                        "name": ev.short_name,
                        "kind": "event",
                        "ports": matching_ports,
                    })

        for f in sorted_fields(intf.fields):
            if getattr(f, "has_notifier", False):
                t = cpp_type(f.type_tref, domain)
                all_raw_inbound_items.append({
                    "kind": "field_notifier",
                    "type": t,
                    "member": f.short_name,
                    "port_name": r_port.short_name,
                    "display_kind": "field notifier",
                })
                inbound_tagged.append({
                    "kind": "field_notifier",
                    "tag": f"typename ActorBase::ports::{r_port.short_name}::{f.short_name}",
                    "member": f.short_name,
                    "port_name": r_port.short_name,
                    "type": t,
                })
                if is_unique_intf:
                    inbound_tagged.append({
                        "kind": "field_notifier",
                        "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                        "member": f.short_name,
                        "port_name": r_port.short_name,
                        "type": t,
                    })
                else:
                    ambig_tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                    matching_ports = sorted([r.short_name for r in r_ports if service_ident(resolve_intf(r, domain)) == sident])
                    if ambig_tag not in [x["tag"] for x in inbound_ambiguous_tags]:
                        inbound_ambiguous_tags.append({
                            "tag": ambig_tag,
                            "service": sident,
                            "name": f.short_name,
                            "kind": "field notifier",
                            "ports": matching_ports,
                        })

    # 2. P-Ports (Methods & Field Setters)
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        is_unique_intf = (p_sident_counts[sident] == 1)

        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]
            is_faf = is_fire_and_forget(m)
            disp_k = "fire-and-forget method" if is_faf else "RPC method"
            if len(in_args) == 1:
                all_raw_inbound_items.append({
                    "kind": "method",
                    "type": in_args[0][1],
                    "member": m.short_name,
                    "port_name": p_port.short_name,
                    "display_kind": disp_k,
                    "is_faf": is_faf,
                    "sig_types": sig_types,
                })
            inbound_tagged.append({
                "kind": "method",
                "tag": f"typename ActorBase::ports::{p_port.short_name}::{m.short_name}",
                "member": m.short_name,
                "port_name": p_port.short_name,
                "sig_types": sig_types,
                "is_faf": is_faf,
            })
            if is_unique_intf:
                inbound_tagged.append({
                    "kind": "method",
                    "tag": f"::reaktar::tags::{ns}::methods::{m.short_name}",
                    "member": m.short_name,
                    "port_name": p_port.short_name,
                    "sig_types": sig_types,
                    "is_faf": is_faf,
                })
            else:
                ambig_tag = f"::reaktar::tags::{ns}::methods::{m.short_name}"
                matching_ports = sorted([p.short_name for p in p_ports if service_ident(resolve_intf(p, domain)) == sident])
                if ambig_tag not in [x["tag"] for x in inbound_ambiguous_tags]:
                    inbound_ambiguous_tags.append({
                        "tag": ambig_tag,
                        "service": sident,
                        "name": m.short_name,
                        "kind": disp_k,
                        "ports": matching_ports,
                    })

        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                t = cpp_type(f.type_tref, domain)
                all_raw_inbound_items.append({
                    "kind": "field_setter",
                    "type": t,
                    "member": f.short_name,
                    "port_name": p_port.short_name,
                    "display_kind": "field setter",
                })
                inbound_tagged.append({
                    "kind": "field_setter",
                    "tag": f"typename ActorBase::ports::{p_port.short_name}::{f.short_name}",
                    "member": f.short_name,
                    "port_name": p_port.short_name,
                    "type": t,
                })
                if is_unique_intf:
                    inbound_tagged.append({
                        "kind": "field_setter",
                        "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                        "member": f.short_name,
                        "port_name": p_port.short_name,
                        "type": t,
                    })
                else:
                    ambig_tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                    matching_ports = sorted([p.short_name for p in p_ports if service_ident(resolve_intf(p, domain)) == sident])
                    if ambig_tag not in [x["tag"] for x in inbound_ambiguous_tags]:
                        inbound_ambiguous_tags.append({
                            "tag": ambig_tag,
                            "service": sident,
                            "name": f.short_name,
                            "kind": "field setter",
                            "ports": matching_ports,
                        })

    # Group all 1-arg inbound items by type to detect bare on(payload) ambiguity
    inbound_type_map = defaultdict(list)
    for it in all_raw_inbound_items:
        inbound_type_map[it["type"]].append(it)

    # Inbound ambiguous types across the actor
    inbound_ambiguous_types = sorted(list(
        set(analysis.get("incoming_conflicting_types", {}).keys()) |
        {t for t, items in inbound_type_map.items() if len(items) > 1}
    ))

    ambiguous_untagged_on_details = []
    for t in inbound_ambiguous_types:
        seen_targets = set()
        targets = []
        for it in inbound_type_map[t]:
            key = (it["port_name"], it["member"], it["display_kind"])
            if key not in seen_targets:
                seen_targets.add(key)
                targets.append({
                    "port": it["port_name"],
                    "member": it["member"],
                    "kind": it["display_kind"],
                })
        targets.sort(key=lambda x: (x["port"], x["member"]))
        ambiguous_untagged_on_details.append({
            "type": t,
            "targets": targets,
        })
    ambiguous_untagged_on_details.sort(key=lambda x: x["type"])

    inbound_by_type = []
    for t, items in sorted(inbound_type_map.items(), key=lambda x: x[0]):
        if len(items) == 1:
            inbound_by_type.append(items[0])

    inbound_all_types = sorted(list(inbound_type_map.keys()))

    inbound_fan_in_tags = []
    seen_fan_in = set()
    for it in inbound_tagged:
        tag_str = it["tag"]
        if tag_str.startswith("::reaktar::tags::"):
            if tag_str not in seen_fan_in:
                seen_fan_in.add(tag_str)
                inbound_fan_in_tags.append({"tag": tag_str})
    for amb in inbound_ambiguous_tags:
        tag_str = amb["tag"]
        if tag_str not in seen_fan_in:
            seen_fan_in.add(tag_str)
            inbound_fan_in_tags.append({"tag": tag_str})
    inbound_fan_in_tags.sort(key=lambda x: x["tag"])

    # Per-port inbound breakdown
    ports_inbound = []
    for port in all_ports:
        port_name = port["port_name"]
        raw_items_for_port = [it for it in all_raw_inbound_items if it["port_name"] == port_name]
        port_type_counts = Counter([it["type"] for it in raw_items_for_port])

        seen_types = set()
        single_arg_items = []
        for it in sorted(raw_items_for_port, key=lambda x: (x["type"], x["member"])):
            t = it["type"]
            if t in seen_types:
                continue
            seen_types.add(t)
            is_ambig = (port_type_counts[t] > 1)
            item_copy = dict(it)
            item_copy["is_ambiguous"] = is_ambig
            single_arg_items.append(item_copy)

        ambiguous_single_groups = []
        ambig_types = sorted([t for t, count in port_type_counts.items() if count > 1])
        for t in ambig_types:
            matching = [dict(it) for it in raw_items_for_port if it["type"] == t]
            matching.sort(key=lambda x: x["member"])
            ambiguous_single_groups.append({
                "type": t,
                "targets": matching,
            })

        # Method signature conflicts on port (methods with 1 or more args)
        if port.get("kind") == "Provided":
            port_methods = [m for m in port.get("methods", []) if "sig_types" in m]
        else:
            port_methods = []
        method_sig_counts = Counter([tuple(m["sig_types"]) for m in port_methods])
        ambiguous_method_sigs = []
        for sig_tuple, count in sorted(method_sig_counts.items()):
            if count > 1:
                matching_m = [m["name"] for m in port_methods if tuple(m["sig_types"]) == sig_tuple]
                ambiguous_method_sigs.append({
                    "sig_types": list(sig_tuple),
                    "methods": sorted(matching_m),
                })

        total_inbound = len(raw_items_for_port) + sum(1 for m in port_methods if len(m["sig_types"]) != 1)
        ports_inbound.append({
            "name": port_name,
            "total_inbound_count": total_inbound,
            "single_arg_items": single_arg_items,
            "ambiguous_single_groups": ambiguous_single_groups,
            "ambiguous_method_sigs": ambiguous_method_sigs,
        })
    ports_inbound.sort(key=lambda x: x["name"])

    app_base = re.sub(r'(?:App|Application)$', '', app.short_name)
    example_class_name = f"{app_base}Example"
    example_alias_name = f"{app.short_name}Example"

    raw_snake = re.sub(r'(?<!^)(?=[A-Z])', '_', exe_name).lower()
    base_snake = re.sub(r'_exe$', '', raw_snake)

    legal_signatures = list(analysis["legal_signatures"])
    legal_types = list(analysis["legal_types"])
    for p in all_ports:
        port_name = p["port_name"]
        conn_t = f"::reaktar::Connected<typename ActorBase::ports::{port_name}>"
        disconn_t = f"::reaktar::Disconnected<typename ActorBase::ports::{port_name}>"
        legal_signatures.append((conn_t,))
        legal_signatures.append((disconn_t,))
        legal_types.append(conn_t)
        legal_types.append(disconn_t)

    def dedup_list(lst):
        seen = set()
        res = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                res.append(x)
        return res

    legal_signatures = dedup_list(sorted(legal_signatures, key=lambda s: (len(s), s)))
    legal_types = dedup_list(sorted(legal_types))

    req_ports = [p for p in all_ports if p.get("kind") != "Provided"]
    skeleton_setters = [f for f in skeleton_fields_flat if f.get("has_setter")]

    ambiguous_untagged_on_map = {d["type"]: d["targets"] for d in ambiguous_untagged_on_details}
    for sig in inbound_signals_flat:
        sig["competing_all"] = ambiguous_untagged_on_map.get(sig["type"], [])
    for f in skeleton_setters:
        f["competing_all"] = ambiguous_untagged_on_map.get(f["type"], [])

    all_skel_methods_by_sig = defaultdict(list)
    for skel in skeletons:
        for m in skel["methods"]:
            all_skel_methods_by_sig[tuple(m["sig_types"])].append({
                "port": skel["port_name"],
                "name": m["name"],
            })
    for skel in skeletons:
        for m in skel["methods"]:
            m["competing_all"] = all_skel_methods_by_sig.get(tuple(m["sig_types"]), [])

    # -------------------------------------------------------------------------
    # Inbound Read (Field Getters) Model Structures
    # -------------------------------------------------------------------------
    read_ports = []
    read_fields_by_port_tag = []
    r_all_field_counts = Counter()
    tag_to_ports = defaultdict(list)
    for cp in consumed_proxies:
        for f in cp["fields"]:
            tag_name = f"::reaktar::tags::{f['tag']}"
            r_all_field_counts[tag_name] += 1
            if cp["port_name"] not in tag_to_ports[tag_name]:
                tag_to_ports[tag_name].append(cp["port_name"])

    type_to_readable_fields = defaultdict(list)

    for cp in consumed_proxies:
        p_name = cp["port_name"]
        p_slot = cp["slot_name"]
        
        # Check type counts among readable fields on this port
        port_field_type_counts = Counter([f["type"] for f in cp["fields"] if f.get("has_getter")])

        all_fields_for_port = []
        for f in cp["fields"]:
            field_data = {
                "name": f["name"],
                "type": f["type"],
                "tag": f"::reaktar::tags::{f['tag']}",
                "has_getter": f.get("has_getter", False),
                "port_name": p_name,
                "slot_name": p_slot,
                "is_unique_type_on_port": (port_field_type_counts[f["type"]] == 1) if f.get("has_getter") else False,
            }
            all_fields_for_port.append(field_data)
            read_fields_by_port_tag.append(field_data)
            if f.get("has_getter"):
                type_to_readable_fields[f["type"]].append(field_data)

        readable_fields_on_port = [f for f in all_fields_for_port if f["has_getter"]]
        unique_readable_field = readable_fields_on_port[0] if len(readable_fields_on_port) == 1 else None

        read_ports.append({
            "name": p_name,
            "ident": cp["ident"],
            "slot_name": p_slot,
            "service_ns": cp["service_ns"],
            "events": cp["events"],
            "methods": cp["methods"],
            "readable_field_count": len(readable_fields_on_port),
            "unique_field": unique_readable_field,
            "readable_fields": readable_fields_on_port,
            "all_fields": all_fields_for_port,
        })

    read_unique_bare_fields = []
    read_ambiguous_bare_tags = []
    seen_ambig_tags = set()

    for cp in consumed_proxies:
        for f in cp["fields"]:
            tag_name = f"::reaktar::tags::{f['tag']}"
            if r_all_field_counts[tag_name] == 1:
                read_unique_bare_fields.append({
                    "tag": tag_name,
                    "name": f["name"],
                    "port_name": cp["port_name"],
                    "slot_name": cp["slot_name"],
                    "type": f["type"],
                    "has_getter": f.get("has_getter", False),
                })
            else:
                if tag_name not in seen_ambig_tags:
                    seen_ambig_tags.add(tag_name)
                    matching_ports = sorted(tag_to_ports[tag_name])
                    ports_str = ", ".join(f"'{p}'" for p in matching_ports)
                    read_ambiguous_bare_tags.append({
                        "tag": tag_name,
                        "name": f["name"],
                        "service": cp["service_ident"],
                        "ports": matching_ports,
                        "ports_str": ports_str,
                    })

    read_by_type = []
    read_ambiguous_types = []
    for t in sorted(type_to_readable_fields.keys()):
        fields = sorted(type_to_readable_fields[t], key=lambda x: (x["port_name"], x["name"]))
        if len(fields) == 1:
            read_by_type.append({
                "type": t,
                "is_ambiguous": False,
                "field": fields[0],
            })
        else:
            item = {
                "type": t,
                "is_ambiguous": True,
                "fields": fields,
            }
            read_by_type.append(item)
            read_ambiguous_types.append(item)

    read_available_types = sorted(list(type_to_readable_fields.keys()))
    read_available_tags = sorted(list({f["tag"] for f in read_fields_by_port_tag if f.get("has_getter")}))

    # -------------------------------------------------------------------------
    # Diagnostics collections for emit(...) and on(...) validation
    # -------------------------------------------------------------------------
    proxy_fields_without_setter = []
    proxy_fields_without_notifier = []
    all_provided_events = set()
    all_provided_methods = set()
    all_provided_fields_with_setter = set()
    all_provided_fields_with_notifier = set()

    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        for ev in intf.events:
            all_provided_events.add((ns, ev.short_name))
        for m in intf.methods:
            all_provided_methods.add((ns, m.short_name))
        for f in intf.fields:
            if getattr(f, "has_setter", False):
                all_provided_fields_with_setter.add((ns, f.short_name))
            if getattr(f, "has_notifier", False):
                all_provided_fields_with_notifier.add((ns, f.short_name))

    all_required_events = set()
    all_required_methods = set()
    all_required_fields_with_setter = set()
    all_required_fields_with_notifier = set()

    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        for ev in intf.events:
            all_required_events.add((ns, ev.short_name))
        for m in intf.methods:
            all_required_methods.add((ns, m.short_name))
        for f in intf.fields:
            if getattr(f, "has_setter", False):
                all_required_fields_with_setter.add((ns, f.short_name))
            if getattr(f, "has_notifier", False):
                all_required_fields_with_notifier.add((ns, f.short_name))

    proxy_fields_without_setter = []
    proxy_fields_without_notifier = []
    proxy_events = []
    proxy_methods = []

    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        is_unique_intf = (r_sident_counts[sident] == 1)

        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            tag_port = f"typename ActorBase::ports::{r_port.short_name}::{ev.short_name}"
            tag_bare = f"::reaktar::tags::{ns}::events::{ev.short_name}"
            proxy_events.append({
                "port_name": r_port.short_name,
                "name": ev.short_name,
                "tag": tag_port,
                "type": t,
            })
            if is_unique_intf and (ns, ev.short_name) not in all_provided_events:
                proxy_events.append({
                    "port_name": r_port.short_name,
                    "name": ev.short_name,
                    "tag": tag_bare,
                    "type": t,
                })

        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]
            is_faf = is_fire_and_forget(m)
            tag_port = f"typename ActorBase::ports::{r_port.short_name}::{m.short_name}"
            tag_bare = f"::reaktar::tags::{ns}::methods::{m.short_name}"
            proxy_methods.append({
                "port_name": r_port.short_name,
                "name": m.short_name,
                "tag": tag_port,
                "sig_types": sig_types,
                "is_faf": is_faf,
            })
            if is_unique_intf and (ns, m.short_name) not in all_provided_methods:
                proxy_methods.append({
                    "port_name": r_port.short_name,
                    "name": m.short_name,
                    "tag": tag_bare,
                    "sig_types": sig_types,
                    "is_faf": is_faf,
                })

        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            tag_port = f"typename ActorBase::ports::{r_port.short_name}::{f.short_name}"
            tag_bare = f"::reaktar::tags::{ns}::fields::{f.short_name}"
            has_setter = bool(getattr(f, "has_setter", False))
            has_notifier = bool(getattr(f, "has_notifier", False))
            if not has_setter:
                proxy_fields_without_setter.append({
                    "port_name": r_port.short_name,
                    "name": f.short_name,
                    "tag": tag_port,
                    "type": t,
                })
                if is_unique_intf and (ns, f.short_name) not in all_required_fields_with_setter and (ns, f.short_name) not in all_provided_fields_with_notifier:
                    proxy_fields_without_setter.append({
                        "port_name": r_port.short_name,
                        "name": f.short_name,
                        "tag": tag_bare,
                        "type": t,
                    })
            if not has_notifier:
                proxy_fields_without_notifier.append({
                    "port_name": r_port.short_name,
                    "name": f.short_name,
                    "tag": tag_port,
                    "type": t,
                })
                if is_unique_intf and (ns, f.short_name) not in all_required_fields_with_notifier and (ns, f.short_name) not in all_provided_fields_with_setter:
                    proxy_fields_without_notifier.append({
                        "port_name": r_port.short_name,
                        "name": f.short_name,
                        "tag": tag_bare,
                        "type": t,
                    })

    skeleton_fields_without_notifier = []
    skeleton_fields_without_setter = []
    skeleton_events = []
    skeleton_methods = []

    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        is_unique_intf = (p_sident_counts[sident] == 1)

        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            tag_port = f"typename ActorBase::ports::{p_port.short_name}::{ev.short_name}"
            tag_bare = f"::reaktar::tags::{ns}::events::{ev.short_name}"
            skeleton_events.append({
                "port_name": p_port.short_name,
                "name": ev.short_name,
                "tag": tag_port,
                "type": t,
            })
            if is_unique_intf and (ns, ev.short_name) not in all_required_events:
                skeleton_events.append({
                    "port_name": p_port.short_name,
                    "name": ev.short_name,
                    "tag": tag_bare,
                    "type": t,
                })

        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]
            is_faf = is_fire_and_forget(m)
            tag_port = f"typename ActorBase::ports::{p_port.short_name}::{m.short_name}"
            tag_bare = f"::reaktar::tags::{ns}::methods::{m.short_name}"
            skeleton_methods.append({
                "port_name": p_port.short_name,
                "name": m.short_name,
                "tag": tag_port,
                "sig_types": sig_types,
                "is_faf": is_faf,
            })
            if is_unique_intf and (ns, m.short_name) not in all_required_methods:
                skeleton_methods.append({
                    "port_name": p_port.short_name,
                    "name": m.short_name,
                    "tag": tag_bare,
                    "sig_types": sig_types,
                    "is_faf": is_faf,
                })

        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            tag_port = f"typename ActorBase::ports::{p_port.short_name}::{f.short_name}"
            tag_bare = f"::reaktar::tags::{ns}::fields::{f.short_name}"
            has_setter = bool(getattr(f, "has_setter", False))
            has_notifier = bool(getattr(f, "has_notifier", False))
            if not has_notifier:
                skeleton_fields_without_notifier.append({
                    "port_name": p_port.short_name,
                    "name": f.short_name,
                    "tag": tag_port,
                    "type": t,
                })
                if is_unique_intf and (ns, f.short_name) not in all_provided_fields_with_notifier and (ns, f.short_name) not in all_required_fields_with_setter:
                    skeleton_fields_without_notifier.append({
                        "port_name": p_port.short_name,
                        "name": f.short_name,
                        "tag": tag_bare,
                        "type": t,
                    })
            if not has_setter:
                skeleton_fields_without_setter.append({
                    "port_name": p_port.short_name,
                    "name": f.short_name,
                    "tag": tag_port,
                    "type": t,
                })
                if is_unique_intf and (ns, f.short_name) not in all_provided_fields_with_setter and (ns, f.short_name) not in all_required_fields_with_notifier:
                    skeleton_fields_without_setter.append({
                        "port_name": p_port.short_name,
                        "name": f.short_name,
                        "tag": tag_bare,
                        "type": t,
                    })

    all_fields_without_setter = []
    seen_no_setter = set()
    for item in proxy_fields_without_setter + skeleton_fields_without_setter:
        if item["tag"] not in seen_no_setter:
            seen_no_setter.add(item["tag"])
            all_fields_without_setter.append(item)

    all_fields_without_notifier = []
    seen_no_notifier = set()
    for item in proxy_fields_without_notifier + skeleton_fields_without_notifier:
        if item["tag"] not in seen_no_notifier:
            seen_no_notifier.add(item["tag"])
            all_fields_without_notifier.append(item)

    example_interfaces = build_example_interfaces(
        app=app,
        domain=domain,
        analysis=analysis,
        p_ports=p_ports,
        r_ports=r_ports,
        port_single_counts_by_port=port_single_counts_by_port,
        port_multi_counts_by_port=port_multi_counts_by_port,
        read_ports=read_ports,
        read_by_type=read_by_type,
        read_unique_bare_fields=read_unique_bare_fields,
        pass_by=pass_by,
    )

    return {
        "exe_name": exe_name,
        "app_short_name": app_short_name,
        "example_class_name": example_class_name,
        "example_alias_name": example_alias_name,
        "base_snake": base_snake,
        "example_interfaces": example_interfaces,
        "skeleton_headers": skeleton_headers,
        "proxy_headers": proxy_headers,
        "tag_aliases": analysis["tag_aliases"],
        "ports": all_ports,
        "req_ports": req_ports,
        "ports_outbound": ports_outbound,
        "port_aliases": port_aliases,
        "consumed_proxies": consumed_proxies,
        "consumed_proxy_count": len(consumed_proxies),
        "skeletons": skeletons,
        "skeleton_fields": skeleton_fields_flat,
        "skeleton_setters": skeleton_setters,
        "inbound_signals_flat": inbound_signals_flat,
        "outbound_tagged": outbound_tagged,
        "outbound_ambiguous_tags": outbound_ambiguous_tags,
        "outbound_fan_out_tags": outbound_fan_out_tags,
        "global_outbound_by_type": global_outbound_by_type,
        "outbound_ambiguous_types": outbound_ambiguous_types,
        "ambiguous_untagged_emit_details": ambiguous_untagged_emit_details,
        "outbound_by_type": outbound_by_type,
        "outbound_multi": outbound_multi,
        "ambiguous_outbound_multi": ambiguous_outbound_multi,
        "all_raw_inbound_items": all_raw_inbound_items,
        "inbound_tagged": inbound_tagged,
        "inbound_ambiguous_tags": inbound_ambiguous_tags,
        "inbound_ambiguous_types": inbound_ambiguous_types,
        "ambiguous_untagged_on_details": ambiguous_untagged_on_details,
        "inbound_by_type": inbound_by_type,
        "inbound_all_types": inbound_all_types,
        "inbound_fan_in_tags": inbound_fan_in_tags,
        "ports_inbound": ports_inbound,
        "read_ports": read_ports,
        "read_fields_by_port_tag": read_fields_by_port_tag,
        "read_unique_bare_fields": read_unique_bare_fields,
        "read_ambiguous_bare_tags": read_ambiguous_bare_tags,
        "read_by_type": read_by_type,
        "read_ambiguous_types": read_ambiguous_types,
        "read_available_types": read_available_types,
        "read_available_tags": read_available_tags,
        "proxy_fields_without_setter": proxy_fields_without_setter,
        "proxy_fields_without_notifier": proxy_fields_without_notifier,
        "proxy_events": proxy_events,
        "proxy_methods": proxy_methods,
        "skeleton_fields_without_notifier": skeleton_fields_without_notifier,
        "skeleton_fields_without_setter": skeleton_fields_without_setter,
        "skeleton_events": skeleton_events,
        "skeleton_methods": skeleton_methods,
        "all_fields_without_setter": all_fields_without_setter,
        "all_fields_without_notifier": all_fields_without_notifier,
        "legal_signatures": legal_signatures,
        "legal_types": legal_types,
        "legal_tags": analysis["legal_tags"],
    }


def generate_code(arxml_path: Path, output_dir: Path, pass_by: str = "const_ref", type_style: str = "autosar"):
    global CURRENT_TYPE_STYLE
    CURRENT_TYPE_STYLE = type_style
    print(f"Directly traversing Adaptive Applications in ARXML '{arxml_path}' via pyarx (type-style: {type_style})...")
    domain = load_domain(str(arxml_path))

    apps = list(getattr(domain, "adaptive_application_sw_component_types", []))
    apps.sort(key=lambda a: a.short_name)

    template_dir = Path(__file__).resolve().parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True
    )
    env.globals.update({
        "service_ns": service_ns,
        "service_ident": service_ident,
        "skeleton_cls": skeleton_cls,
        "proxy_cls": proxy_cls,
        "cpp_type": cpp_type,
        "method_in_args": lambda m, d=domain: method_in_args(m, d, pass_by=pass_by),
        "method_ret_type": method_ret_type,
        "is_fire_and_forget": is_fire_and_forget,
        "method_snake_name": method_snake_name,
        "sorted_ports": sorted_ports,
        "sorted_events": sorted_events,
        "sorted_fields": sorted_fields,
        "sorted_methods": sorted_methods,
        "resolve_intf": resolve_intf,
        "resolve_instance_specifier": resolve_instance_specifier,
        "is_unique_outgoing": is_unique_outgoing,
        "is_unique_incoming": is_unique_incoming,
        "is_unique_field_setter": is_unique_field_setter,
        "is_unique_skel_method": is_unique_skel_method,
        "is_unique_proxy_method": is_unique_proxy_method,
        "is_unique_r_service": is_unique_r_service,
        "is_unique_p_service": is_unique_p_service,
        "skeleton_header": skeleton_header,
        "proxy_header": proxy_header,
        "domain": domain,
        "app_exe_name": app_exe_name,
        "service_p_ports": lambda ports: [p for p in ports if is_service_interface(resolve_intf(p, domain))],
        "service_r_ports": lambda ports: [p for p in ports if is_service_interface(resolve_intf(p, domain))],
    })
    env.filters["service_p_ports"] = lambda ports: [p for p in ports if is_service_interface(resolve_intf(p, domain))]
    env.filters["service_r_ports"] = lambda ports: [p for p in ports if is_service_interface(resolve_intf(p, domain))]

    # Collect all unique service interfaces across all apps
    all_intfs = set()
    for app in apps:
        for p in app.p_port_prototypes:
            intf = resolve_intf(p, domain)
            if is_service_interface(intf):
                all_intfs.add(intf)
        for r in app.r_port_prototypes:
            intf = resolve_intf(r, domain)
            if is_service_interface(intf):
                all_intfs.add(intf)
    sorted_intfs = sorted(list(all_intfs), key=lambda x: x.short_name)

    stats = {
        "tags_succeeded": 0,
        "apps_processed": 0,
        "apps_skipped": 0,
        "actors_succeeded": 0,
        "actors_failed": 0,
        "benches_succeeded": 0,
        "benches_failed": 0,
        "json_succeeded": 0,
        "json_stubbed": 0,
        "json_failed": 0,
        "examples_succeeded": 0,
        "examples_failed": 0,
    }
    warnings_list = []
    errors_list = []

    # 1. Generate include/reaktar/tags.hpp (Tier 0 - Critical Global Tags)
    try:
        reaktar_inc = output_dir.parent / "reaktar"
        reaktar_inc.mkdir(parents=True, exist_ok=True)
        tags_tmpl = env.get_template("tags.hpp.jinja")
        tags_code = tags_tmpl.render(interfaces=sorted_intfs)
        tags_path = reaktar_inc / "tags.hpp"
        tags_path.write_text(tags_code)
        # Also sync to submodule include if different
        alt_tags_path = Path("reaktar/include/reaktar/tags.hpp")
        if alt_tags_path.parent.exists() and alt_tags_path.resolve() != tags_path.resolve():
            alt_tags_path.write_text(tags_code)
        stats["tags_succeeded"] = 1
        print(f"  [OK] Generated Tag Definitions -> {tags_path}")
    except Exception as ex:
        import traceback
        err_msg = f"Failed to generate global tags.hpp: {ex}"
        errors_list.append(err_msg)
        print(f"  [FATAL] {err_msg}", file=sys.stderr)
        print(f"  [DIAGNOSTIC] Traceback:\n{traceback.format_exc().strip()}", file=sys.stderr)

    # 2. Generate Actors, TestBenches, Example Applications, and JSON Serializers
    actor_tmpl = env.get_template("actor.hpp.jinja")
    bench_tmpl = env.get_template("test_bench.hpp.jinja")
    example_tmpl = env.get_template("example_app.hpp.jinja")
    json_tmpl = env.get_template("actor_json.hpp.jinja")

    output_dir.mkdir(parents=True, exist_ok=True)
    for app in apps:
        app_name = app.short_name
        if not app_has_executable(app):
            print(f"  [SKIP] Component '{app_name}' has no associated Executable in model. Skipping actor generation.")
            stats["apps_skipped"] += 1
            continue

        stats["apps_processed"] += 1
        print(f"\n==> Processing Component: {app_name}")

        import re
        # Step 2a: Generate Actor (Tier 1 - Core Component)
        try:
            exe_name = app_exe_name(app)
            raw_snake = re.sub(r'(?<!^)(?=[A-Z])', '_', exe_name).lower()
            base_snake = re.sub(r'_exe$', '', raw_snake)

            analysis = analyze_application_types(app, domain)
            model = build_actor_model(app, domain, analysis, pass_by=pass_by)
            actor_code = actor_tmpl.render(model=model, app=app, analysis=analysis)
            actor_path = output_dir / f"{base_snake}_actor.hpp"
            actor_path.write_text(actor_code)
            stats["actors_succeeded"] += 1
            print(f"  [OK] Generated Actor           -> {actor_path}")
        except Exception as ex:
            import traceback
            err_msg = f"Component '{app_name}': Failed to generate Actor: {ex}"
            errors_list.append(err_msg)
            stats["actors_failed"] += 1
            print(f"  [ERROR] {err_msg}", file=sys.stderr)
            print(f"  [DIAGNOSTIC] Traceback:\n{traceback.format_exc().strip()}", file=sys.stderr)
            print(f"  [RECOVERY] Skipping dependent artifacts for '{app_name}' and continuing to next component...", file=sys.stderr)
            continue

        # Step 2b: Generate Test Bench (Tier 2 - Tooling)
        try:
            bench_code = bench_tmpl.render(app=app, model=model, analysis=analysis)
            bench_path = output_dir / f"{base_snake}_test_bench.hpp"
            bench_path.write_text(bench_code)
            stats["benches_succeeded"] += 1
            print(f"  [OK] Generated Test Bench      -> {bench_path}")
        except Exception as ex:
            import traceback
            err_msg = f"Component '{app_name}': Failed to generate Test Bench: {ex}"
            errors_list.append(err_msg)
            stats["benches_failed"] += 1
            print(f"  [ERROR] {err_msg}", file=sys.stderr)
            print(f"  [DIAGNOSTIC] Traceback:\n{traceback.format_exc().strip()}", file=sys.stderr)

        # Step 2c: Generate JSON Serializers (Tier 3 - Peripheral / Graceful Degradation)
        json_path = output_dir / f"{base_snake}_json.hpp"
        try:
            json_data = collect_actor_json_types(app, domain, pass_by=pass_by)
            if "warnings" in json_data and json_data["warnings"]:
                warnings_list.extend(json_data["warnings"])
            json_code = json_tmpl.render(app=app, base_snake=base_snake, **json_data)
            json_path.write_text(json_code)
            stats["json_succeeded"] += 1
            print(f"  [OK] Generated JSON Serializers-> {json_path}")
        except Exception as ex:
            import traceback
            warn_msg = f"Component '{app_name}': JSON generation failed: {ex}"
            warnings_list.append(warn_msg)
            stats["json_stubbed"] += 1
            print(f"  [WARN] {warn_msg}", file=sys.stderr)
            print(f"  [DIAGNOSTIC] Traceback snippet:\n{traceback.format_exc().strip()}", file=sys.stderr)
            print(f"  [STUB] Generating fallback JSON stub -> {json_path}")
            stub_content = (
                f"// ==============================================================================\n"
                f"// Reaktar - Fallback JSON Stub\n"
                f"// Component: {app_name}\n"
                f"// Notice: Full JSON serializers could not be generated from ARXML model:\n"
                f"//         {ex}\n"
                f"// ==============================================================================\n\n"
                f"#pragma once\n\n"
                f"#include <reaktar/json.hpp>\n\n"
                f"// Fallback unqualified imports so includes and basic JSON APIs don't break\n"
                f"using ::reaktar::json::to_json;\n"
                f"using ::reaktar::json::write_json;\n"
                f"using ::reaktar::json::operator<<;\n"
            )
            json_path.write_text(stub_content)

        # Step 2d: Generate Example App (Tier 2 - Tooling)
        try:
            example_code = example_tmpl.render(model=model, app=app, analysis=analysis)
            example_path = output_dir / f"{base_snake}_example.hpp"
            example_path.write_text(example_code)
            stats["examples_succeeded"] += 1
            print(f"  [OK] Generated Example App     -> {example_path}")
        except Exception as ex:
            import traceback
            err_msg = f"Component '{app_name}': Failed to generate Example App: {ex}"
            errors_list.append(err_msg)
            stats["examples_failed"] += 1
            print(f"  [ERROR] {err_msg}", file=sys.stderr)
            print(f"  [DIAGNOSTIC] Traceback:\n{traceback.format_exc().strip()}", file=sys.stderr)

    print("\n" + "=" * 70)
    print(" Reaktar Code Generation Summary")
    print("=" * 70)
    print(f"  Global Tags:       {stats['tags_succeeded']} / 1 generated")
    print(f"  Components:        {stats['apps_processed']} processed ({stats['apps_skipped']} skipped)")
    print(f"  Actors:            {stats['actors_succeeded']} / {stats['apps_processed']} generated")
    print(f"  Test Benches:      {stats['benches_succeeded']} / {stats['apps_processed']} generated")
    print(f"  JSON Serializers:  {stats['json_succeeded']} generated, {stats['json_stubbed']} stubbed")
    print(f"  Example Apps:      {stats['examples_succeeded']} / {stats['apps_processed']} generated")
    print("-" * 70)
    print(f"  Warnings:          {len(warnings_list)}")
    print(f"  Errors:            {len(errors_list)}")
    print("=" * 70)

    if errors_list or stats['tags_succeeded'] == 0:
        print("\n[ERROR] Generation encountered critical errors. Check diagnostics above.\n", file=sys.stderr)
        return False
    if warnings_list:
        print("\n[INFO] Generation completed with warnings. Peripheral fallbacks were applied.\n")
    else:
        print("\n[SUCCESS] All artifacts generated cleanly.\n")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reaktar Actor & TestBench Generator")
    parser.add_argument("arxml", nargs="?", default="arxml/vehicle_system.arxml",
                        help="Path to input ARXML model file (.arxml) [default: arxml/vehicle_system.arxml]")
    parser.add_argument("-o", "--output", default="include/generated_framework", help="Output directory for generated headers")
    parser.add_argument("--pass-by", choices=["const_ref", "value"], default="const_ref",
                        help="Argument passing style for method arguments: 'const_ref' (default) or 'value'")
    parser.add_argument("--type-style", choices=["autosar", "std"], default="autosar",
                        help="Data type style: 'autosar' (ara::core::*) or 'std' (std::*) [default: autosar]")
    args = parser.parse_args()

    arxml = Path(args.arxml)
    if not arxml.exists():
        print(f"Error: {arxml} not found.", file=sys.stderr)
        sys.exit(1)

    out_include = Path(args.output)
    success = generate_code(arxml, out_include, pass_by=args.pass_by, type_style=args.type_style)
    if not success:
        sys.exit(1)
