"""Indexed min-heap keyed by exact (mean, competency_id) order."""

from fractions import Fraction
from typing import Dict, List, Tuple


class IndexedMinHeap:
    """Min-heap of competency ids ordered by (Fraction mean, competency_id).

    Supports insert/update/discard by competency id in O(log n) and
    retrieval of the k smallest entries in O(k log n). Memory is
    proportional to the number of live entries only.
    """

    __slots__ = ("_keys", "_heap", "_pos")

    def __init__(self) -> None:
        self._keys: Dict[int, Fraction] = {}
        self._heap: List[int] = []
        self._pos: Dict[int, int] = {}

    def __len__(self) -> int:
        return len(self._heap)

    def __contains__(self, competency_id: int) -> bool:
        return competency_id in self._pos

    def _less(self, a: int, b: int) -> bool:
        return (self._keys[a], a) < (self._keys[b], b)

    def _swap(self, i: int, j: int) -> None:
        heap = self._heap
        heap[i], heap[j] = heap[j], heap[i]
        self._pos[heap[i]] = i
        self._pos[heap[j]] = j

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._less(self._heap[i], self._heap[parent]):
                self._swap(i, parent)
                i = parent
            else:
                break

    def _sift_down(self, i: int) -> None:
        n = len(self._heap)
        while True:
            smallest = i
            left = 2 * i + 1
            right = left + 1
            if left < n and self._less(self._heap[left], self._heap[smallest]):
                smallest = left
            if right < n and self._less(self._heap[right], self._heap[smallest]):
                smallest = right
            if smallest == i:
                break
            self._swap(i, smallest)
            i = smallest

    def set(self, competency_id: int, mean: Fraction) -> None:
        """Insert competency or replace its mean."""
        if competency_id in self._pos:
            old = self._keys[competency_id]
            self._keys[competency_id] = mean
            i = self._pos[competency_id]
            if mean < old:
                self._sift_up(i)
            elif mean > old:
                self._sift_down(i)
        else:
            self._keys[competency_id] = mean
            self._pos[competency_id] = len(self._heap)
            self._heap.append(competency_id)
            self._sift_up(len(self._heap) - 1)

    def discard(self, competency_id: int) -> None:
        """Remove competency if present."""
        i = self._pos.get(competency_id)
        if i is None:
            return
        last = self._heap.pop()
        del self._pos[competency_id]
        del self._keys[competency_id]
        if i < len(self._heap):
            self._heap[i] = last
            self._pos[last] = i
            self._sift_up(i)
            self._sift_down(self._pos[last])

    def smallest(self, k: int) -> List[Tuple[int, Fraction]]:
        """Return up to k (competency_id, mean) pairs in ascending order."""
        popped: List[Tuple[int, Fraction]] = []
        for _ in range(min(k, len(self._heap))):
            root = self._heap[0]
            popped.append((root, self._keys[root]))
            self.discard(root)
        for competency_id, mean in popped:
            self.set(competency_id, mean)
        return popped
