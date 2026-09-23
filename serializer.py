from node import Node

def collect_all_nodes(node):
    result = [node]
    for child in node.children:
        result.extend(collect_all_nodes(child))
    return result
