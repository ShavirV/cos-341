from typing import Optional
from itertools import count

class NodeIDGenerator:
    _counter = count(0)

    @classmethod
    def next_id(cls) -> int:
        return next(cls._counter)

class Node:
    def __init__(self, contents: str, node_type: str, parent: Optional["Node"] = None):
        assert node_type in ("root", "inner", "leaf"), f"Invalid node type: {node_type}"
        
        self.id: int = NodeIDGenerator.next_id()
        self.contents: str = contents
        self.node_type: str = node_type
        self.parent: Optional["Node"] = parent
        self.children: list["Node"] = []

    def add_child(self, child: "Node") -> None:
        if(self.node_type == "leaf"):
            raise ValueError("Cannot add a child to a leaf node.")
        child.parent = self
        self.children.append(child)

    def is_root(self) -> bool:
        return self.node_type == "root"

    def is_leaf(self) -> bool:
        return self.node_type == "leaf"

    def __repr__(self) -> str:
        return (
            f"Node(id={self.id}, type ={self.node_type},"
            f"contents={self.contents!r}, children={[c.id for c in self.children]})"
        )
