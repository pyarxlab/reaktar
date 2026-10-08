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
FUNDAMENTAL_CPP_TYPES = {
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


def cpp_type(tref, domain=None):
    if not tref or getattr(tref, "is_null", False):
        return "void"
    name = getattr(tref, "short_name", None) or getattr(tref, "name", None) or str(tref)
    if name in FUNDAMENTAL_CPP_TYPES:
        return FUNDAMENTAL_CPP_TYPES[name]
    
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

    return {
        "exe_name": exe_name,
        "app_short_name": app_short_name,
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
        "legal_signatures": analysis["legal_signatures"],
        "legal_types": analysis["legal_types"],
        "legal_tags": analysis["legal_tags"],
    }


def generate_code(arxml_path: Path, output_dir: Path, pass_by: str = "const_ref"):
    print(f"Directly traversing Adaptive Applications in ARXML '{arxml_path}' via pyarx...")
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

    # 2. Generate Actors and TestBenches
    actor_tmpl = env.get_template("actor.hpp.jinja")
    bench_tmpl = env.get_template("test_bench.hpp.jinja")

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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reaktar Actor & TestBench Generator")
    parser.add_argument("arxml", nargs="?", default="arxml/vehicle_system.arxml",
                        help="Path to input ARXML model file (.arxml) [default: arxml/vehicle_system.arxml]")
    parser.add_argument("-o", "--output", default="include/generated_framework", help="Output directory for generated headers")
    parser.add_argument("--pass-by", choices=["const_ref", "value"], default="const_ref",
                        help="Argument passing style for method arguments: 'const_ref' (default) or 'value'")
    args = parser.parse_args()

    arxml = Path(args.arxml)
    if not arxml.exists():
        print(f"Error: {arxml} not found.", file=sys.stderr)
        sys.exit(1)

    out_include = Path(args.output)
    generate_code(arxml, out_include, pass_by=args.pass_by)
