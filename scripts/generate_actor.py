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
    size = getattr(dt, "array_size", None)
    if hasattr(size, "__iter__") and not isinstance(size, (str, bytes)):
        size = list(size)[0] if len(size) > 0 else 1
    if size is not None:
        try:
            size = int(size)
        except Exception:
            size = 1
    elem_ref = None
    args = getattr(dt, "cpp_template_arguments", None) or getattr(dt, "template_arguments", None)
    if args and len(args) > 0:
        elem_ref = getattr(args[0], "template_type_ref", None) or getattr(args[0], "type_reference_ref", None)
    if not elem_ref:
        sub_els = getattr(dt, "sub_elements", None) or getattr(dt, "cpp_implementation_data_type_elements", None)
        if sub_els:
            for el in sub_els:
                if size is None:
                    size = getattr(el, "array_size", None)
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
    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            outgoing_items.append(('event', ev.short_name, t, p.short_name, intf, ev))

    # 2. P-Port field notifiers (Skeleton Field Update)
    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        for f in sorted_fields(intf.fields):
            if f.has_notifier:
                t = cpp_type(f.type_tref, domain)
                outgoing_items.append(('field_update', f.short_name, t, p.short_name, intf, f))

    # 3. R-Port RPC methods (single-arg directly without artificial Request structs)
    for r in app.r_port_prototypes:
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
    outgoing_unique_types = {t for t, count in out_type_counts.items() if count == 1}

    # Incoming items: R-Port events + R-Port field notifiers
    incoming_items = []
    for r in app.r_port_prototypes:
        intf = resolve_intf(r, domain)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            incoming_items.append(('event', ev.short_name, t, r.short_name, intf, ev))
        for f in sorted_fields(intf.fields):
            if f.has_notifier:
                t = cpp_type(f.type_tref, domain)
                incoming_items.append(('field_notify', f.short_name, t, r.short_name, intf, f))

    in_type_counts = Counter([item[2] for item in incoming_items])
    incoming_unique_types = {t for t, count in in_type_counts.items() if count == 1}

    # Skeleton field setters
    fset_items = []
    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        for f in sorted_fields(intf.fields):
            if f.has_setter:
                t = cpp_type(f.type_tref, domain)
                fset_items.append((f.short_name, t))

    fset_type_counts = Counter([item[1] for item in fset_items])
    field_setter_unique_types = {t for t, count in fset_type_counts.items() if count == 1}

    # 4. Skeleton methods for direct tagless on(args...)
    skeleton_methods = []
    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain)
            sig_types = tuple(a[1] for a in in_args)
            skeleton_methods.append((m.short_name, sig_types, in_args, m))

    skel_method_sig_counts = Counter([sm[1] for sm in skeleton_methods])
    skel_method_unique_sigs = {sig for sig, count in skel_method_sig_counts.items() if count == 1}

    # 5. Proxy methods for variadic tagless emit(args...)
    proxy_methods = []
    for r in app.r_port_prototypes:
        intf = resolve_intf(r, domain)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain)
            sig_types = tuple(a[1] for a in in_args)
            proxy_methods.append((m.short_name, sig_types, in_args, m, r))

    proxy_method_sig_counts = Counter([pm[1] for pm in proxy_methods])
    proxy_method_unique_sigs = {sig for sig, count in proxy_method_sig_counts.items() if count == 1}

    outgoing_conflicting_types = {t: [f"{item[0]}:{item[1]}" for item in outgoing_items if item[2] == t] for t, count in out_type_counts.items() if count > 1}
    incoming_conflicting_types = {t: [f"{item[0]}:{item[1]}" for item in incoming_items if item[2] == t] for t, count in in_type_counts.items() if count > 1}

    # 6. Extract all legal incoming types, tag types, and signature tuples for rogue handler detection
    legal_types = set()
    legal_tags = set()
    legal_signatures = set()

    for r in app.r_port_prototypes:
        intf = resolve_intf(r, domain)
        ns = service_ns(intf)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            legal_types.add(t)
            tag = f"::reaktar::tags::{ns}::events::{ev.short_name}"
            legal_tags.add(tag)
            # Both direct on(t) and tagged on(tag, t) are legal
            legal_signatures.add((t,))
            legal_signatures.add((tag, t))
        for f in sorted_fields(intf.fields):
            if f.has_notifier:
                t = cpp_type(f.type_tref, domain)
                legal_types.add(t)
                tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                legal_tags.add(tag)
                legal_signatures.add((t,))
                legal_signatures.add((tag, t))

    for p in app.p_port_prototypes:
        intf = resolve_intf(p, domain)
        ns = service_ns(intf)
        for m in sorted_methods(intf.methods):
            tag = f"::reaktar::tags::{ns}::methods::{m.short_name}"
            legal_tags.add(tag)
            in_args = method_in_args(m, domain)
            sig_types = tuple(a[1] for a in in_args)
            for t in sig_types:
                legal_types.add(t)
            # Direct on(args...)
            legal_signatures.add(sig_types)
            # Tagged on(Tag, args...)
            legal_signatures.add((tag,) + sig_types)
        for f in sorted_fields(intf.fields):
            if f.has_setter:
                t = cpp_type(f.type_tref, domain)
                legal_types.add(t)
                tag = f"::reaktar::tags::{ns}::fields::{f.short_name}"
                legal_tags.add(tag)
                legal_signatures.add((t,))
                legal_signatures.add((tag, t))

    # 7. Collect all app tags and build ergonomic tag aliases
    all_intfs = set()
    for p in app.p_port_prototypes:
        all_intfs.add(resolve_intf(p, domain))
    for r in app.r_port_prototypes:
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


def collect_actor_json_types(app, domain, pass_by="const_ref"):
    """
    Collects all custom structs and enums used by this application by inspecting
    its ports and service interfaces, recursively exploring nested types.
    """
    visited_trefs = set()
    structs_map = {}
    enums_map = {}

    def process_tref(tref):
        if not tref or tref.is_null:
            return
        tref_id = tref.id if hasattr(tref, "id") else id(tref)
        if tref_id in visited_trefs:
            return
        visited_trefs.add(tref_id)

        name = tref.short_name or tref.name
        if not name or name in FUNDAMENTAL_CPP_TYPES:
            return

        cat = str(tref.category or "")
        ns_parts = tuple(ns.symbol or ns.short_name for ns in tref.namespaces) if tref.namespaces and not tref.namespaces.is_null else ()
        ns_str = "::".join(ns_parts)
        fq_name = f"{ns_str}::{name}" if ns_str else name

        if cat == "STRUCTURE":
            fields = []
            sub_els = tref.sub_elements or tref.cpp_implementation_data_type_elements
            if sub_els:
                for el in sub_els:
                    el_tref = el.type_reference_ref
                    el_type = cpp_type(el_tref, domain)
                    fields.append({"name": el.short_name, "type": el_type})
                    if el_tref:
                        process_tref(el_tref)
            guard_name = fq_name.replace("::", "_").replace(":", "_").upper()
            structs_map[fq_name] = {
                "name": name,
                "ns_parts": ns_parts,
                "fq_name": fq_name,
                "guard_name": guard_name,
                "fields": fields,
            }
        elif cat == "VECTOR":
            elem_ref = get_vector_element_tref(tref)
            if elem_ref:
                process_tref(elem_ref)
        elif cat == "ARRAY":
            elem_ref, _ = get_array_element_tref_and_size(tref)
            if elem_ref:
                process_tref(elem_ref)
        elif cat == "ASSOCIATIVE_MAP":
            k_ref, v_ref = get_map_key_value_trefs(tref)
            if k_ref:
                process_tref(k_ref)
            if v_ref:
                process_tref(v_ref)
        elif cat == "TYPE_REFERENCE":
            if tref.x and tref.x.compu_methods:
                underlying = tref.type_reference_ref
                under_name = cpp_type(underlying, domain) if underlying else "uint8_t"
                items = []
                compu_methods = tref.x.compu_methods
                if compu_methods and len(compu_methods) > 0:
                    scales = list(compu_methods[0].q.compu_scales)
                    for idx, s in enumerate(scales):
                        val = idx
                        if s.lower_limit is not None:
                            try:
                                val = int(s.lower_limit)
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

    all_ports = list(get_service_p_ports(app, domain)) + list(get_service_r_ports(app, domain))
    for p in all_ports:
        intf = resolve_intf(p, domain)
        if not is_service_interface(intf):
            continue

        for ev in intf.events:
            if ev.type_tref:
                process_tref(ev.type_tref)

        for f in intf.fields:
            if f.type_tref:
                process_tref(f.type_tref)

        for m in intf.methods:
            for arg in m.arguments:
                if arg.type_tref:
                    process_tref(arg.type_tref)

    structs_by_ns = defaultdict(list)
    for s in structs_map.values():
        structs_by_ns[s["ns_parts"]].append(s)

    enums_by_ns = defaultdict(list)
    for e in enums_map.values():
        enums_by_ns[e["ns_parts"]].append(e)

    return {
        "structs": list(structs_map.values()),
        "enums": list(enums_map.values()),
        "structs_by_ns": dict(structs_by_ns),
        "enums_by_ns": dict(enums_by_ns),
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

    proxy_headers = []
    for r in r_ports:
        h = proxy_header(resolve_intf(r, domain))
        if h not in proxy_headers:
            proxy_headers.append(h)

    consumed_proxies = []
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        pcls = proxy_cls(intf)
        instance_spec = resolve_instance_specifier(app, r_port)

        ev_list = []
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            tag = f"{ns}::events::{ev.short_name}"
            ev_list.append({
                "name": ev.short_name,
                "type": t,
                "tag": tag,
                "is_unique": is_unique_incoming(t, analysis),
            })

        field_list = []
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            tag = f"{ns}::fields::{f.short_name}"
            has_notif = bool(getattr(f, "has_notifier", False))
            has_get = bool(getattr(f, "has_getter", False))
            has_set = bool(getattr(f, "has_setter", False))
            field_list.append({
                "name": f.short_name,
                "type": t,
                "tag": tag,
                "has_notifier": has_notif,
                "has_getter": has_get,
                "has_setter": has_set,
                "is_unique": is_unique_incoming(t, analysis),
            })

        unsub_targets = [ev["name"] for ev in ev_list] + [f["name"] for f in field_list if f["has_notifier"]]

        consumed_proxies.append({
            "port_name": r_port.short_name,
            "ident": sident,
            "cls": pcls,
            "slot_name": f"{sident}_slot_",
            "find_handle_name": f"{sident}_find_handle_",
            "instance_spec": instance_spec,
            "events": ev_list,
            "fields": field_list,
            "all_unsubscribe_targets": unsub_targets,
        })

    skeletons = []
    skeleton_fields_flat = []
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        scls = skeleton_cls(intf)
        instance_spec = resolve_instance_specifier(app, p_port)
        var_name = f"{p_port.short_name.lower()}_skeleton_"
        adapter_name = f"{p_port.short_name}SkeletonAdapter"

        method_list = []
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = [a[1] for a in in_args]
            is_faf = is_fire_and_forget(m)
            ret_t = method_ret_type(m, domain)
            tag = f"::reaktar::tags::{ns}::methods::{m.short_name}"
            is_unique_sig = is_unique_skel_method(sig_types, analysis)

            method_list.append({
                "name": m.short_name,
                "tag": tag,
                "is_faf": is_faf,
                "ret_type": ret_t,
                "in_args": [
                    {"name": aname, "type": atype, "pass_type": ptype}
                    for aname, atype, ptype in in_args
                ],
                "is_unique_sig": is_unique_sig,
            })

        field_list = []
        for f in sorted_fields(intf.fields):
            t = cpp_type(f.type_tref, domain)
            tag = f"{ns}::fields::{f.short_name}"
            has_notif = bool(getattr(f, "has_notifier", False))
            has_get = bool(getattr(f, "has_getter", False))
            has_set = bool(getattr(f, "has_setter", False))
            is_uniq_set = is_unique_field_setter(t, analysis) if has_set else False

            f_info = {
                "name": f.short_name,
                "type": t,
                "tag": tag,
                "var_name": var_name,
                "has_notifier": has_notif,
                "has_getter": has_get,
                "has_setter": has_set,
                "is_unique_setter": is_uniq_set,
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
            "methods": method_list,
            "fields": field_list,
        })

    outbound_tagged = []
    # 1. Skeleton events & field updates
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        var_name = f"{p_port.short_name.lower()}_skeleton_"
        for ev in sorted_events(intf.events):
            outbound_tagged.append({
                "kind": "skeleton_event",
                "tag": f"{ns}::events::{ev.short_name}",
                "var_name": var_name,
                "member": ev.short_name,
                "service_ident": None,
            })
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_notifier", False):
                outbound_tagged.append({
                    "kind": "skeleton_field_update",
                    "tag": f"{ns}::fields::{f.short_name}",
                    "var_name": var_name,
                    "member": f.short_name,
                    "service_ident": None,
                })

    # 2. Proxy methods & fields
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        sident = service_ident(intf)
        for m in sorted_methods(intf.methods):
            is_faf = is_fire_and_forget(m)
            outbound_tagged.append({
                "kind": "proxy_faf" if is_faf else "proxy_rpc",
                "tag": f"::reaktar::tags::{ns}::methods::{m.short_name}",
                "var_name": None,
                "member": m.short_name,
                "service_ident": sident,
            })
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                outbound_tagged.append({
                    "kind": "proxy_field_set",
                    "tag": f"{ns}::fields::{f.short_name}",
                    "var_name": None,
                    "member": f.short_name,
                    "service_ident": sident,
                })

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
                    "service_ident": None,
                })
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_notifier", False):
                t = cpp_type(f.type_tref, domain)
                if is_unique_outgoing(t, analysis):
                    outbound_by_type.append({
                        "kind": "skeleton_field_update",
                        "type": t,
                        "var_name": var_name,
                        "member": f.short_name,
                        "service_ident": None,
                    })

    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        sident = service_ident(intf)
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
                        "service_ident": sident,
                    })

    outbound_multi = []
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        sident = service_ident(intf)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            if len(in_args) != 1:
                sig_types = tuple(a[1] for a in in_args)
                if is_unique_proxy_method(sig_types, analysis):
                    is_faf = is_fire_and_forget(m)
                    outbound_multi.append({
                        "sig_types": sig_types,
                        "is_faf": is_faf,
                        "member": m.short_name,
                        "service_ident": sident,
                    })

    all_ports = []
    for p in skeletons:
        all_ports.append({
            "port_name": p["port_name"],
            "kind": "Provided",
            "kind_tag": "::reaktar::ProvidedPortTag",
            "intf_name": p["intf_name"],
            "cls": p["cls"],
            "var_name": p["var_name"],
            "ident": p["port_name"].lower(),
        })
    for cp in consumed_proxies:
        all_ports.append({
            "port_name": cp["port_name"],
            "kind": "Required",
            "kind_tag": "::reaktar::RequiredPortTag",
            "cls": cp["cls"],
            "slot_name": cp["slot_name"],
            "find_handle_name": cp["find_handle_name"],
            "instance_spec": cp["instance_spec"],
            "ident": cp["ident"],
            "all_unsubscribe_targets": cp["all_unsubscribe_targets"],
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

    app_base = re.sub(r'(?:App|Application)$', '', app.short_name)
    example_class_name = f"{app_base}Example"
    example_alias_name = f"{app.short_name}Example"

    raw_snake = re.sub(r'(?<!^)(?=[A-Z])', '_', exe_name).lower()
    base_snake = re.sub(r'_exe$', '', raw_snake)

    example_interfaces = []
    # 1. Provided Ports (Skeletons)
    for p_port in p_ports:
        intf = resolve_intf(p_port, domain)
        ns = service_ns(intf)
        port_name = p_port.short_name
        port_ident = port_name.lower()
        candidate_alias = strip_port_affixes(port_name)

        incoming_handlers = []
        outgoing_emits = []

        # Skeleton methods (Incoming)
        for m in sorted_methods(intf.methods):
            in_args = method_in_args(m, domain, pass_by=pass_by)
            sig_types = tuple(a[1] for a in in_args)
            is_uniq = is_unique_skel_method(sig_types, analysis)
            ret_t = method_ret_type(m, domain)
            is_faf = is_fire_and_forget(m)
            bare_tag = m.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::methods::{m.short_name}"

            if not is_uniq:
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
                is_uniq = is_unique_field_setter(t, analysis)
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"

                if not is_uniq:
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

        # Skeleton events (Outgoing)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            is_uniq = is_unique_outgoing(t, analysis)
            bare_tag = ev.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::events::{ev.short_name}"
            dummy_val = generate_dummy_value(t)

            autosar_note = f"AUTOSAR: skeleton.{ev.short_name}.Send()"

            if is_uniq:
                call_untagged = f"emit({dummy_val})"
                tag_note = f"Untagged: emit(val). Alternative: emit<{tag_expr}>(val)"
            else:
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>(val)"

            call_tagged = f"emit<{tag_expr}>({dummy_val})"
            outgoing_emits.append({
                "kind": "skeleton_event",
                "name": ev.short_name,
                "tag": f"::reaktar::tags::{ns}::events::{ev.short_name}",
                "tag_expr": tag_expr,
                "is_unique": is_uniq,
                "example_call_untagged": call_untagged,
                "example_call_tagged": call_tagged,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
            })

        # Skeleton fields (Notifiers are Outgoing)
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_notifier", False):
                t = cpp_type(f.type_tref, domain)
                is_uniq = is_unique_outgoing(t, analysis)
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"
                dummy_val = generate_dummy_value(t)

                autosar_note = f"AUTOSAR: skeleton.{f.short_name}.Update()"

                if is_uniq:
                    call_untagged = f"emit({dummy_val})"
                    tag_note = f"Untagged: emit(val). Alternative: emit<{tag_expr}>(val)"
                else:
                    call_untagged = None
                    tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>(val)"

                call_tagged = f"emit<{tag_expr}>({dummy_val})"
                outgoing_emits.append({
                    "kind": "skeleton_field_update",
                    "name": f.short_name,
                    "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                    "tag_expr": tag_expr,
                    "is_unique": is_uniq,
                    "example_call_untagged": call_untagged,
                    "example_call_tagged": call_tagged,
                    "autosar_note": autosar_note,
                    "tag_note": tag_note,
                })

        example_interfaces.append({
            "port_name": port_name,
            "port_alias": candidate_alias,
            "port_kind": "Provided",
            "ident": port_ident,
            "intf_name": intf.short_name,
            "intf_ns": ns,
            "incoming_handlers": incoming_handlers,
            "outgoing_emits": outgoing_emits,
        })

    # 2. Required Ports (Proxies)
    for r_port in r_ports:
        intf = resolve_intf(r_port, domain)
        ns = service_ns(intf)
        port_name = r_port.short_name
        port_ident = port_name.lower()
        candidate_alias = strip_port_affixes(port_name)

        incoming_handlers = []
        outgoing_emits = []

        # Proxy events (Incoming)
        for ev in sorted_events(intf.events):
            t = cpp_type(ev.type_tref, domain)
            is_uniq = is_unique_incoming(t, analysis)
            bare_tag = ev.short_name
            is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
            tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::events::{ev.short_name}"

            if not is_uniq:
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
                is_uniq = is_unique_incoming(t, analysis)
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"

                if not is_uniq:
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
                is_uniq = is_unique_outgoing(t, analysis)
            else:
                is_uniq = is_unique_proxy_method(sig_types, analysis)

            call_kind = "fire-and-forget" if is_faf else "RPC"
            autosar_note = f"AUTOSAR: proxy->{m.short_name}() {call_kind}"

            if is_uniq:
                call_untagged = f"emit({dummy_args_str})"
                tag_note = f"Untagged (unique signature). Alternative: emit<{tag_expr}>({dummy_args_str})"
            else:
                call_untagged = None
                tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>({dummy_args_str})"

            call_tagged = f"emit<{tag_expr}>({dummy_args_str})"
            outgoing_emits.append({
                "kind": "proxy_faf" if is_faf else "proxy_rpc",
                "name": m.short_name,
                "tag": f"::reaktar::tags::{ns}::methods::{m.short_name}",
                "tag_expr": tag_expr,
                "is_unique": is_uniq,
                "example_call_untagged": call_untagged,
                "example_call_tagged": call_tagged,
                "autosar_note": autosar_note,
                "tag_note": tag_note,
            })

        # Proxy fields (Setters are Outgoing)
        for f in sorted_fields(intf.fields):
            if getattr(f, "has_setter", False):
                t = cpp_type(f.type_tref, domain)
                is_uniq = is_unique_outgoing(t, analysis)
                bare_tag = f.short_name
                is_ambig = is_bare_tag_ambiguous(bare_tag, analysis)
                tag_expr = bare_tag if not is_ambig else f"::reaktar::tags::{ns}::fields::{f.short_name}"
                dummy_val = generate_dummy_value(t)

                autosar_note = f"AUTOSAR: proxy->{f.short_name}.Set()"
                if is_uniq:
                    call_untagged = f"emit({dummy_val})"
                    tag_note = f"Untagged: emit(val). Alternative: emit<{tag_expr}>({dummy_val})"
                else:
                    call_untagged = None
                    tag_note = f"MANDATORY TAGGED: emit<{tag_expr}>({dummy_val})"
                call_tagged = f"emit<{tag_expr}>({dummy_val})"

                outgoing_emits.append({
                    "kind": "proxy_field_set",
                    "name": f.short_name,
                    "tag": f"::reaktar::tags::{ns}::fields::{f.short_name}",
                    "tag_expr": tag_expr,
                    "is_unique": is_uniq,
                    "example_call_untagged": call_untagged,
                    "example_call_tagged": call_tagged,
                    "autosar_note": autosar_note,
                    "tag_note": tag_note,
                })

        example_interfaces.append({
            "port_name": port_name,
            "port_alias": candidate_alias,
            "port_kind": "Required",
            "ident": port_ident,
            "intf_name": intf.short_name,
            "intf_ns": ns,
            "incoming_handlers": incoming_handlers,
            "outgoing_emits": outgoing_emits,
        })

    legal_signatures = list(analysis["legal_signatures"])
    legal_types = list(analysis["legal_types"])
    for p in all_ports:
        port_name = p["port_name"]
        conn_t = f"::reaktar::Connected<typename Base::ports::{port_name}>"
        disconn_t = f"::reaktar::Disconnected<typename Base::ports::{port_name}>"
        legal_signatures.append((conn_t,))
        legal_signatures.append((disconn_t,))
        legal_types.append(conn_t)
        legal_types.append(disconn_t)

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
        "port_aliases": port_aliases,
        "consumed_proxies": consumed_proxies,
        "consumed_proxy_count": len(consumed_proxies),
        "skeletons": skeletons,
        "skeleton_fields": skeleton_fields_flat,
        "outbound_tagged": outbound_tagged,
        "outbound_by_type": outbound_by_type,
        "outbound_multi": outbound_multi,
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

    # 1. Generate include/reaktar/tags.hpp
    reaktar_inc = output_dir.parent / "reaktar"
    reaktar_inc.mkdir(parents=True, exist_ok=True)
    tags_tmpl = env.get_template("tags.hpp.jinja")
    tags_code = tags_tmpl.render(interfaces=sorted_intfs)
    tags_path = reaktar_inc / "tags.hpp"
    tags_path.write_text(tags_code)
    print(f"  [OK] Generated Tag Definitions -> {tags_path}")

    # 2. Generate Actors, TestBenches, Example Applications, and JSON Serializers
    actor_tmpl = env.get_template("actor.hpp.jinja")
    bench_tmpl = env.get_template("test_bench.hpp.jinja")
    example_tmpl = env.get_template("example_app.hpp.jinja")
    json_tmpl = env.get_template("actor_json.hpp.jinja")

    output_dir.mkdir(parents=True, exist_ok=True)
    for app in apps:
        if not app_has_executable(app):
            print(f"  [SKIP] Component '{app.short_name}' has no associated Executable in model. Skipping actor generation.")
            continue

        import re
        exe_name = app_exe_name(app)
        raw_snake = re.sub(r'(?<!^)(?=[A-Z])', '_', exe_name).lower()
        base_snake = re.sub(r'_exe$', '', raw_snake)

        analysis = analyze_application_types(app, domain)
        model = build_actor_model(app, domain, analysis, pass_by=pass_by)
        actor_code = actor_tmpl.render(model=model, app=app, analysis=analysis)
        actor_path = output_dir / f"{base_snake}_actor.hpp"
        actor_path.write_text(actor_code)
        print(f"  [OK] Generated Actor           -> {actor_path}")

        bench_code = bench_tmpl.render(app=app)
        bench_path = output_dir / f"{base_snake}_test_bench.hpp"
        bench_path.write_text(bench_code)
        print(f"  [OK] Generated Test Bench      -> {bench_path}")

        json_data = collect_actor_json_types(app, domain, pass_by=pass_by)
        json_code = json_tmpl.render(app=app, base_snake=base_snake, **json_data)
        json_path = output_dir / f"{base_snake}_json.hpp"
        json_path.write_text(json_code)
        print(f"  [OK] Generated JSON Serializers-> {json_path}")

        example_code = example_tmpl.render(model=model, app=app, analysis=analysis)
        example_path = output_dir / f"{base_snake}_example.hpp"
        example_path.write_text(example_code)
        print(f"  [OK] Generated Example App     -> {example_path}")


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
    generate_code(arxml, out_include, pass_by=args.pass_by, type_style=args.type_style)
