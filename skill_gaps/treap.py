"""Randomized treap: ordered set with O(log n) insert/delete/smallest-k.

Keys must be unique and totally ordered. Split/merge based; expected depth
is O(log n), far below the recursion limit for this library's key counts.
"""

import random

__all__ = ["Treap"]

_rng = random.Random(0x5EED)


class _Node:
    __slots__ = ("key", "prio", "left", "right")

    def __init__(self, key, prio):
        self.key = key
        self.prio = prio
        self.left = None
        self.right = None


def _split(node, key):
    """Split into (< key, >= key) subtrees."""
    if node is None:
        return None, None
    if key <= node.key:
        left, right = _split(node.left, key)
        node.left = right
        return left, node
    left, right = _split(node.right, key)
    node.right = left
    return node, right


def _merge(left, right):
    if left is None:
        return right
    if right is None:
        return left
    if left.prio < right.prio:
        left.right = _merge(left.right, right)
        return left
    right.left = _merge(left, right.left)
    return right


def _remove_min(node):
    """Detach and return (min_node, remaining_tree)."""
    if node.left is None:
        return node, node.right
    min_node, rest = _remove_min(node.left)
    node.left = rest
    return min_node, node


class Treap:
    """Ordered set of unique keys supporting min-order iteration."""

    __slots__ = ("root", "_size")

    def __init__(self):
        self.root = None
        self._size = 0

    def __len__(self):
        return self._size

    def __contains__(self, key):
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return True
        return False

    def insert(self, key):
        fresh = _Node(key, _rng.random())
        left, right = _split(self.root, key)
        self.root = _merge(_merge(left, fresh), right)
        self._size += 1

    def discard(self, key):
        if key not in self:
            return
        left, ge = _split(self.root, key)
        min_node, rest = _remove_min(ge)
        self.root = _merge(left, rest)
        self._size -= 1

    def smallest(self, k):
        """Return the k smallest keys in ascending order."""
        out = []
        stack = []
        node = self.root
        while (stack or node is not None) and len(out) < k:
            while node is not None:
                stack.append(node)
                node = node.left
            node = stack.pop()
            out.append(node.key)
            node = node.right
        return out
