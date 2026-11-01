"""Bounded process-local TTL cache, no persistence of questions or credentials."""
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic


class SearchCache:
    def __init__(self, capacity=64, clock=monotonic):
        self.capacity, self.clock = capacity, clock
        self.items = OrderedDict()
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            now = self.clock()
            for expired in [k for k, (expiry, _) in self.items.items() if expiry <= now]:
                del self.items[expired]
            if key not in self.items: return None
            self.items.move_to_end(key)
            return deepcopy(self.items[key][1])

    def put(self, key, value, ttl):
        if ttl <= 0: return
        with self.lock:
            self.items[key] = (self.clock()+ttl, deepcopy(value))
            self.items.move_to_end(key)
            while len(self.items)>self.capacity: self.items.popitem(last=False)


search_cache = SearchCache()
