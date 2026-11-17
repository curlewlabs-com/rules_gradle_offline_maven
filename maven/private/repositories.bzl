"""Turns a lock's parsed components into component repositories and the layout.

A component's repository name is reversible from its coordinates, and its
attributes hold only what that component's fetch reads, so an edit to one
component leaves every other component's repository unchanged.
"""

def source_repositories(group, repositories, group_repositories):
    """Returns the repositories to try for a group, the group's first.

    The digest decides what is accepted, so a group's first repository only
    saves requests: Bazel logs a warning for each source that answers 404
    before one serves the file, which would be most of a cold fetch's log if
    every artifact tried the same repository first.

    Args:
        group: The component's Maven group.
        repositories: Every repository, in the order a group without a hint
            tries them.
        group_repositories: Group prefixes mapped to the repository their
            groups try first; the first prefix that matches wins.

    Returns:
        The repositories, the group's first repository leading.
    """
    first = repositories[0]
    for prefix, repository in group_repositories.items():
        if group.startswith(prefix):
            first = repository
            break
    return [first] + [repository for repository in repositories if repository != first]

def component_repositories(components, repositories, group_repositories):
    """Return component-local repository attributes with reversible names.

    Args:
        components: Parsed verification metadata components.
        repositories: Every source repository, in default order.
        group_repositories: Group prefixes mapped to the repository tried first.

    Returns:
        Repository names mapped to their component-local fetch attributes.
    """
    for prefix, repository in group_repositories.items():
        if repository not in repositories:
            fail("group prefix %s names %s, which is not one of the repositories" % (prefix, repository))
    result = {}
    for component in components:
        coordinates = [component.group, component.name, component.version]

        # Escape the separator itself so distinct Maven coordinates cannot
        # collapse onto the same repository name.
        name = "maven_" + "_1".join([value.replace("_", "_0") for value in coordinates])
        artifacts = {}
        for artifact in component.artifacts:
            if artifact.file in artifacts and artifacts[artifact.file] != artifact.sha256:
                fail("verification metadata pins %s with conflicting digests" % artifact.file)
            artifacts[artifact.file] = artifact.sha256
        attributes = {
            "group": component.group,
            "module": component.name,
            "version": component.version,
            "artifacts": artifacts,
            "repositories": source_repositories(component.group, repositories, group_repositories),
        }
        if name in result and result[name] != attributes:
            fail("verification metadata repeats a component with different artifacts: " + name)
        result[name] = attributes
    return result

def layout_components(repositories, outside_layout):
    """Splits component repositories into the layout's and those kept outside.

    Args:
        repositories: What component_repositories returned.
        outside_layout: `group:module` pairs whose components stay out of the
            layout.

    Returns:
        The sorted names of the repositories the offline Maven layout is
        assembled from, and of those kept outside it.
    """
    excluded = {}
    for coordinates in outside_layout:
        group, separator, module = coordinates.partition(":")
        if not separator or not group or not module or ":" in module:
            fail("outside_layout names %r, which is not group:module" % coordinates)
        excluded[(group, module)] = False
    layout = []
    outside = []
    for name, attributes in sorted(repositories.items()):
        key = (attributes["group"], attributes["module"])
        if key in excluded:
            excluded[key] = True
            outside.append(name)
        else:
            layout.append(name)

    # A name that matches nothing is a typo or a component the lock dropped,
    # and either way the target that reads the outside components is empty.
    unmatched = [":".join(key) for key, matched in excluded.items() if not matched]
    if unmatched:
        fail("outside_layout names components the lock does not pin: " + ", ".join(sorted(unmatched)))
    return layout, outside
