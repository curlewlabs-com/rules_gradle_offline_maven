"""Assemble independently acquired Maven components for offline Gradle consumers."""

def _maven_layout_impl(ctx):
    repository = ctx.actions.declare_directory("repository")
    marker = ctx.actions.declare_file("maven-repository.json")
    manifest = ctx.actions.declare_file(ctx.label.name + ".manifest.json")
    files = depset(transitive = [component[DefaultInfo].files for component in ctx.attr.components])
    entries = []
    for file in files.to_list():
        prefix = file.owner.workspace_root + "/"
        if not file.path.startswith(prefix):
            fail("Maven component must provide repository source files: " + file.path)
        entries.append([file.path, file.path[len(prefix):]])
    ctx.actions.write(manifest, json.encode(sorted(entries)) + "\n")
    args = ctx.actions.args()
    args.add("--manifest", manifest)
    args.add("--repository", repository.path)
    args.add("--marker", marker)
    ctx.actions.run(
        executable = ctx.executable._assembler,
        arguments = [args],
        inputs = depset([manifest], transitive = [files]),
        outputs = [repository, marker],
        mnemonic = "MavenLayout",
        progress_message = "Assembling offline Maven repository %{label}",
    )
    return [
        DefaultInfo(files = depset([repository, marker])),
        OutputGroupInfo(marker = depset([marker])),
    ]

maven_layout = rule(
    implementation = _maven_layout_impl,
    attrs = {
        "components": attr.label_list(mandatory = True),
        "_assembler": attr.label(
            default = Label("//maven:assemble_maven_layout"),
            executable = True,
            cfg = "exec",
        ),
    },
)
