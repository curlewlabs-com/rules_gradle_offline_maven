"""The repository rule that fetches one Maven component into its Maven layout.

Each component is fetched with only its own coordinates, artifact digests and
source repositories as repository attributes. Unchanged components therefore
keep their repository-cache identities when another component in the lock
changes.
"""

# Bounds each component fetch so a large component does not open a connection
# per artifact to the public repositories.
_CONCURRENT_DOWNLOADS = 32

_COMPONENT_BUILD = """package(default_visibility = ["//visibility:public"])

filegroup(
    name = "files",
    srcs = glob(["**"], exclude = ["BUILD.bazel", "REPO.bazel"]),
)

filegroup(
    name = "jars",
    srcs = glob(["**/*.jar"], allow_empty = True),
)
"""

def _normalize(path):
    parts = []
    for part in path.split("/"):
        if part == "..":
            if not parts:
                fail("a pinned file's location leaves the repository: " + path)
            parts.pop()
        elif part in ("", ".") or ":" in part or "\\" in part:
            fail("a pinned file has an unusable location: " + path)
        else:
            parts.append(part)
    return "/".join(parts)

def module_file_locations(text, module_path):
    """Maps each file a Gradle module names to its location beside the module.

    The lock names an artifact as the module's variants name it, which need not
    be its file name in the repository: an AndroidX module names
    `lifecycle-runtime.aar` and serves it as
    `lifecycle-runtime-android-2.11.0.aar`, and Guava's jre module serves its
    Android variant from the sibling `-android` version's directory.

    Args:
        text: The module file's contents.
        module_path: The module file's path in the Maven layout, for errors.

    Returns:
        Each file name the module's variants list, mapped to its URL relative
        to the module's directory.
    """
    module = json.decode(text)
    locations = {}
    for variant in module.get("variants", []):
        for file in variant.get("files", []):
            name = file["name"]
            url = file["url"]
            if "://" in url or url.startswith("/"):
                fail("%s serves %s from outside the repository" % (module_path, name))
            if locations.get(name, url) != url:
                fail("%s serves %s from two locations" % (module_path, name))
            locations[name] = url
    return locations

# Every file fetched here is one the lock pins by digest, so the Gradle build
# that wrote the lock was served it, and no repository serving it now is far
# more often a moment's fault than a verdict: Maven Central has answered 404
# for a published pom and served it on the next run. Bazel's downloader takes
# a 404 as final, so a file no repository served with its pinned digest is
# asked for again after each of these waits, in seconds, and only the last
# attempt fails the fetch, with the downloader's own error. A pin no repository
# serves at all fails a quarter-minute later than it would without them.
_RETRY_WAITS = [1, 2, 4, 8]

def _download(ctx, path, download, allow_fail):
    return ctx.download(
        url = download.urls,
        output = path,
        sha256 = download.sha256,
        block = False,
        allow_fail = allow_fail,
    )

def _fetch_batch(ctx, downloads, paths):
    for wait in _RETRY_WAITS:
        pending = [(path, _download(ctx, path, downloads[path], True)) for path in paths]
        paths = [path for path, download in pending if not download.wait().success]
        if not paths:
            return

        # buildifier: disable=print
        print("no repository served %s; asking again in %ds" % (", ".join(paths), wait))
        ctx.execute(["sleep", str(wait)])
    pending = [_download(ctx, path, downloads[path], False) for path in paths]
    for download in pending:
        download.wait()

def _fetch(ctx, downloads):
    paths = sorted(downloads.keys())
    for start in range(0, len(paths), _CONCURRENT_DOWNLOADS):
        _fetch_batch(ctx, downloads, paths[start:start + _CONCURRENT_DOWNLOADS])

def _add(downloads, repositories, path, sha256):
    path = _normalize(path)
    known = downloads.get(path)
    if known != None and known.sha256 != sha256:
        fail("verification metadata pins %s with two digests" % path)
    downloads[path] = struct(
        sha256 = sha256,
        urls = [repository + "/" + path for repository in repositories],
    )

def _maven_component_impl(ctx):
    directory = "/".join([ctx.attr.group.replace(".", "/"), ctx.attr.module, ctx.attr.version])

    # The pom and module files are read first: a module says where each of its
    # artifacts lives.
    metadata = {}
    for artifact, sha256 in ctx.attr.artifacts.items():
        if artifact in (
            "%s-%s.pom" % (ctx.attr.module, ctx.attr.version),
            "%s-%s.module" % (ctx.attr.module, ctx.attr.version),
        ):
            _add(metadata, ctx.attr.repositories, directory + "/" + artifact, sha256)
    _fetch(ctx, metadata)

    # One registry across both phases: a variant placed at the pom's or the
    # module's own path with another digest must fail here, since the layout
    # would otherwise hold whichever download landed last.
    downloads = dict(metadata)
    module = "%s/%s-%s.module" % (directory, ctx.attr.module, ctx.attr.version)
    locations = module_file_locations(ctx.read(module), module) if module in metadata else {}
    for artifact, sha256 in ctx.attr.artifacts.items():
        if directory + "/" + artifact not in metadata:
            location = locations.get(artifact, artifact)
            _add(downloads, ctx.attr.repositories, directory + "/" + location, sha256)
    _fetch(ctx, {path: download for path, download in downloads.items() if path not in metadata})
    ctx.file("BUILD.bazel", _COMPONENT_BUILD)

    # Digests fix the fetched bytes, including the module metadata that places
    # variant artifacts in the Maven layout.
    return ctx.repo_metadata(reproducible = True)

maven_component = repository_rule(
    implementation = _maven_component_impl,
    attrs = {
        "group": attr.string(mandatory = True),
        "module": attr.string(mandatory = True),
        "version": attr.string(mandatory = True),
        "artifacts": attr.string_dict(mandatory = True),
        # In the order they are tried; each serves a pinned file by its digest.
        "repositories": attr.string_list(mandatory = True),
    },
)
