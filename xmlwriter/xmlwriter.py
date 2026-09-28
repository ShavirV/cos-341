from node import Node

def collect_all_nodes(node):
    result = [node]
    for child in node.children:
        result.extend(collect_all_nodes(child))
    return result

def escape_xml(text):
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text

def node_to_xml(node):
    lines = [" <node>"]
    lines.append(f"  <id>{node.id}</id>")
    lines.append(f"  <contents>{escape_xml(node.contents)}</contents>")

    if node.node_type != "leaf":
        lines.append("  <children>")
        for child in node.children:
            lines.append(f" <child>{child.id}</child>")
        lines.append("  </children>")

    if node.node_type != "root":
        lines.append(f" <parent>{node.parent.id}</parent>")

    lines.append("  </node>")
    return "\n".join(lines)
    

def tree_to_xml(root):
    all_nodes = collect_all_nodes(root)
    node_blocks = [node_to_xml(n) for n in all_nodes]
    return "<tree>\n" + "\n".join(node_blocks) + "\n</tree>"

def write_tree_to_file(root, filename="tree.xml"):
    xml_string = tree_to_xml(root)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_string)

