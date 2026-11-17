"""The module extension that fetches what a Gradle verification-metadata.xml pins.

Each `gradle_maven.lock` tag creates the repository named by its `name`, whose
targets are listed in the README, and one repository per pinned component.
"""

load("//maven/private:component.bzl", "maven_component")
load("//maven/private:hub.bzl", "maven_hub")
load("//maven/private:repositories.bzl", "component_repositories", "layout_components")
load("//maven/private:verification_metadata.bzl", "parse_verification_metadata")

_lock = tag_class(
    doc = "An offline Maven repository holding every file one lock pins.",
    attrs = {
        "name": attr.string(
            mandatory = True,
            doc = "The repository to create.",
        ),
        "lock": attr.label(
            mandatory = True,
            doc = "Gradle's verification-metadata.xml, written by `--write-verification-metadata sha256`.",
        ),
        "repositories": attr.string_list(
            mandatory = True,
            doc = "Every Maven repository the Gradle build declares, in the order a group without a hint tries them.",
        ),
        "group_repositories": attr.string_dict(
            doc = "Group prefixes mapped to the repository their groups try first. The first matching prefix wins.",
        ),
        "outside_layout": attr.string_list(
            doc = "`group:module` pairs fetched but left out of the layout, available as `:outside_layout_jars`.",
        ),
    },
)

def _gradle_maven_impl(module_ctx):
    components = {}
    hubs = {}
    root_direct = []
    root_direct_dev = []
    for module in module_ctx.modules:
        for tag in module.tags.lock:
            if tag.name in hubs:
                fail("gradle_maven.lock declares %s twice" % tag.name)
            repositories = component_repositories(
                parse_verification_metadata(module_ctx.read(tag.lock)),
                tag.repositories,
                tag.group_repositories,
            )
            for name, attributes in repositories.items():
                if components.get(name, attributes) != attributes:
                    fail("two locks pin %s with different artifacts or repositories" % name)
                components[name] = attributes
            hubs[tag.name] = layout_components(repositories, tag.outside_layout)
            if module.is_root:
                if module_ctx.is_dev_dependency(tag):
                    root_direct_dev.append(tag.name)
                else:
                    root_direct.append(tag.name)
    for name, attributes in components.items():
        maven_component(name = name, **attributes)
    for name, (layout, outside) in hubs.items():
        maven_hub(name = name, components = layout, outside_layout = outside)
    return module_ctx.extension_metadata(
        root_module_direct_deps = root_direct,
        root_module_direct_dev_deps = root_direct_dev,
        reproducible = True,
    )

gradle_maven = module_extension(
    implementation = _gradle_maven_impl,
    tag_classes = {"lock": _lock},
)
