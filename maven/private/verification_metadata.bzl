"""Parses Gradle's verification-metadata.xml into the components it pins.

The parser reads the subset of Gradle's verification-metadata schema that
`--write-verification-metadata sha256` writes, and fails on any other element.
A signature, an alternative checksum or a trusted-artifact rule changes which
files Gradle reads, so meeting one means this fetch has to learn it, not skip
it.
"""

def _attributes(text, element):
    attributes = {}
    rest = text.strip()
    for _ in range(len(text)):
        if not rest:
            break
        name, separator, rest = rest.partition("=")
        name = name.strip()
        if not separator or not name or not rest.startswith("\""):
            fail("verification metadata has a malformed attribute in <%s>" % element)
        value, closed, rest = rest[1:].partition("\"")
        if not closed:
            fail("verification metadata has an unterminated attribute in <%s>" % element)
        if "&" in value or "<" in value:
            fail("verification metadata escapes a character in <%s>, which the parser does not read" % element)
        if name in attributes:
            fail("verification metadata repeats %s in <%s>" % (name, element))
        attributes[name] = value
        rest = rest.lstrip()
    return attributes

def _segment(value, role):
    if not value or "/" in value or value in (".", ".."):
        fail("verification metadata has an unusable %s: %r" % (role, value))
    return value

def parse_verification_metadata(text):
    """Returns each pinned component with its artifacts' names and digests.

    Args:
        text: The contents of a verification-metadata.xml.

    Returns:
        A list of structs with `group`, `name`, `version` and `artifacts`, each
        artifact a struct with `file` and `sha256`.
    """
    tags = text.split("<")
    if tags[0].strip():
        fail("verification metadata has text before its first element")
    components = []
    configuration = {}
    component = None
    artifact = None
    for tag in tags[1:]:
        content, closed, tail = tag.partition(">")
        if not closed:
            fail("verification metadata has an unterminated element")
        for whitespace in ("\n", "\r", "\t"):
            content = content.replace(whitespace, " ")
        element, _, body = content.strip().partition(" ")
        body = body.strip()
        empty = body.endswith("/")
        body = body.removesuffix("/")
        if element in ("verify-metadata", "verify-signatures"):
            configuration[element] = tail.strip()
            continue
        if tail.strip():
            fail("verification metadata has text after <%s>" % element)
        if element == "?xml" or element.startswith("/"):
            if element == "/component":
                if component == None or not component.artifacts:
                    fail("verification metadata closes a component that pins no artifact")
                components.append(component)
                component = None
            elif element == "/artifact":
                if artifact == None or artifact.sha256 == None:
                    fail("verification metadata closes an artifact that pins no sha256")
                component.artifacts.append(artifact)
                artifact = None
            continue
        if element in ("verification-metadata", "configuration", "components"):
            continue

        # Only a digest is written as an empty element. An empty component or
        # artifact never reaches its closing tag, so it would drop out of the
        # fetch unread rather than fail.
        if empty != (element == "sha256"):
            fail("verification metadata has an unexpected %s <%s>" % ("empty" if empty else "open", element))
        attributes = _attributes(body, element)
        if element == "component":
            component = struct(
                artifacts = [],
                group = _segment(attributes.get("group"), "group"),
                name = _segment(attributes.get("name"), "module name"),
                version = _segment(attributes.get("version"), "version"),
            )
        elif element == "artifact":
            if component == None:
                fail("verification metadata has an artifact outside a component")
            artifact = struct(
                file = _segment(attributes.get("name"), "artifact name"),
                sha256 = None,
            )
        elif element == "sha256":
            if artifact == None or artifact.sha256 != None:
                fail("verification metadata needs exactly one sha256 per artifact")
            value = attributes.get("value", "")
            if len(value) != 64:
                fail("verification metadata has a malformed sha256 for " + artifact.file)
            artifact = struct(file = artifact.file, sha256 = value)
        else:
            fail("verification metadata has <%s>, which this fetch does not read" % element)

    # Without metadata pins the lock names no pom or module file, so a build
    # reading only these files could not resolve; with signatures on, Gradle
    # also reads signature files the lock does not name.
    if configuration != {"verify-metadata": "true", "verify-signatures": "false"}:
        fail("verification metadata must verify metadata and not signatures, found %s" % configuration)
    if not components:
        fail("verification metadata pins no components")
    return components
