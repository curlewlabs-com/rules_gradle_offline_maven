"""The repository a lock is used through: its offline Maven layout and the rest.

It declares the layout assembled by maven_layout from the lock's component
repositories, the layout's marker, and the jars of the components the lock
keeps outside the layout.
"""

def _maven_hub_impl(ctx):
    components = ["@%s//:files" % name for name in ctx.attr.components]
    outside = ["@%s//:jars" % name for name in ctx.attr.outside_layout]
    ctx.file("BUILD.bazel", """load({layout_rule}, "maven_layout")

package(default_visibility = ["//visibility:public"])

maven_layout(
    name = "files",
    components = {components},
)

filegroup(
    name = "maven-repository.json",
    srcs = [":files"],
    output_group = "marker",
)

filegroup(
    name = "outside_layout_jars",
    srcs = {outside},
)
""".format(
        layout_rule = repr(str(Label("//maven:layout.bzl"))),
        components = repr(components),
        outside = repr(outside),
    ))
    return ctx.repo_metadata(reproducible = True)

maven_hub = repository_rule(
    implementation = _maven_hub_impl,
    attrs = {
        "components": attr.string_list(mandatory = True),
        "outside_layout": attr.string_list(mandatory = True),
    },
)
