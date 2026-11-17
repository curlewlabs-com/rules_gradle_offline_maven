"""Writes the private rules' real results on fixed inputs as JSON for the tests."""

load("//maven/private:component.bzl", "module_file_locations")
load("//maven/private:repositories.bzl", "component_repositories", "layout_components", "source_repositories")
load("//maven/private:verification_metadata.bzl", "parse_verification_metadata")
load(":fixtures.bzl", "LOCK", "MODULE")

_CENTRAL = "https://central.example"
_GOOGLE = "https://google.example"
_REPOSITORIES = [_CENTRAL, _GOOGLE]
_HINTS = {"androidx.": _GOOGLE}

def _component(group, name, version, checksum):
    return struct(
        group = group,
        name = name,
        version = version,
        artifacts = [struct(file = name + ".jar", sha256 = checksum)],
    )

def _repositories(components):
    return component_repositories(components, _REPOSITORIES, _HINTS)

def _cases_impl(ctx):
    a = _component("org.example", "a", "1.0", "a" * 64)
    b = _component("org.example", "b", "1.0", "b" * 64)
    c = _component("org.example", "c", "1.0", "c" * 64)
    d = _component("org.example", "d", "1.0", "d" * 64)
    runtime = _component("org.example", "runtime", "15", "f" * 64)
    layout, outside = layout_components(_repositories([a, runtime, b]), ["org.example:runtime"])
    parsed = parse_verification_metadata(LOCK)
    output = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(output, json.encode({
        "before": _repositories([a, b, c]),
        "after": _repositories([a, b, d]),
        "repinned": _repositories([a, _component("org.example", "b", "1.0", "e" * 64), c]),
        "upgraded": _repositories([a, _component("org.example", "b", "2.0", "b" * 64), c]),
        "layout": layout,
        "outside": outside,
        "separators": _repositories([
            _component("org.example", "a_b", "c", "a" * 64),
            _component("org.example", "a", "b_c", "b" * 64),
            _component("org.example", "a_1b", "c", "c" * 64),
        ]),
        "sources": {
            "hinted": source_repositories("androidx.core", _REPOSITORIES, _HINTS),
            "default": source_repositories("org.example", _REPOSITORIES, _HINTS),
        },
        "parsed": [
            {
                "group": component.group,
                "name": component.name,
                "version": component.version,
                "artifacts": {artifact.file: artifact.sha256 for artifact in component.artifacts},
            }
            for component in parsed
        ],
        "locations": module_file_locations(MODULE, "fixture.module"),
    }) + "\n")
    return [DefaultInfo(files = depset([output]))]

cases = rule(implementation = _cases_impl)
