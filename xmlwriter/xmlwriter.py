"""
Writes the syntax tree to tree.xml (see the OUTPUT section of the spec).

Every node becomes one <node> struct, listed in pre-order (parent before its
children). Fields, per the spec:

    root  : id, contents, children
    inner : id, contents, children, parent
    leaf  : id, contents, parent
"""

from .node import Node


def collect_all_nodes(node):
    """All nodes of the tree in pre-order.

    Iterative on purpose: ALGO / V_DECL / F_DECL nest once per statement or
    name, so a long program makes the tree deep enough to blow Python's
    recursion limit with a recursive walk.
    """
    result = []
    stack = [node]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(reversed(current.children))
    return result


def escape_xml(text):
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def node_to_xml(node):
    lines = ["  <node>"]
    lines.append(f"    <id>{node.id}</id>")
    lines.append(f"    <contents>{escape_xml(node.contents)}</contents>")

    if node.node_type != "leaf":
        lines.append("    <children>")
        for child in node.children:
            lines.append(f"      <child>{child.id}</child>")
        lines.append("    </children>")

    if node.node_type != "root":
        lines.append(f"    <parent>{node.parent.id}</parent>")

    lines.append("  </node>")
    return "\n".join(lines)


def tree_to_xml(root):
    all_nodes = collect_all_nodes(root)
    ids = [n.id for n in all_nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("Node ids are not unique; cannot write tree.xml")
    node_blocks = [node_to_xml(n) for n in all_nodes]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            "<tree>\n" + "\n".join(node_blocks) + "\n</tree>\n")


def write_tree_to_file(root, filename="tree.xml"):
    xml_string = tree_to_xml(root)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)


# main.py imports this name
write_tree = write_tree_to_file