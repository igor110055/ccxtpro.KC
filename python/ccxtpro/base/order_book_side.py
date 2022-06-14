# -*- coding: utf-8 -*-

import sys
import bisect
import itertools

"""Author: Carlo Revelli"""
"""Fast bisect bindings"""
"""https://github.com/python/cpython/blob/master/Modules/_bisectmodule.c"""
"""Performs a binary search when inserting keys in sorted order"""


class OrderBookSide(list):
    side = None  # set to True for bids and False for asks

    def __init__(self, deltas=[], depth=None):
        super(OrderBookSide, self).__init__()
        self._depth = depth or sys.maxsize
        self._n = sys.maxsize
        # parallel to self
        self._index = []
        for delta in deltas:
            self.storeArray(list(delta))

    def storeArray(self, delta):
        price = delta[0]
        size = delta[1]
        index_price = -price if self.side else price
        index = bisect.bisect_left(self._index, index_price)
        if size:
            if index < len(self._index) and self._index[index] == index_price:
                self[index][1] = size
            else:
                self._index.insert(index, index_price)
                self.insert(index, delta)
        elif index < len(self._index) and self._index[index] == index_price:
            del self._index[index]
            del self[index]

    def store(self, price, size):
        self.storeArray([price, size])

    def limit(self, n=None):
        self._n = sys.maxsize if n is None else n
        difference = len(self) - self._depth
        for _ in range(difference):
            self.remove_index(self.pop())
            self._index.pop()

    def remove_index(self, order):
        pass

    def __iter__(self):
        # a call to limit only temporarily limits the order book
        # so we hide the rest of the cached data after self._n
        iterator = super(OrderBookSide, self).__iter__()
        return itertools.islice(iterator, self._n)

    def __len__(self):
        length = super(OrderBookSide, self).__len__()
        return min(length, self._n)

    def __getitem__(self, item):
        if isinstance(item, slice):
            start, stop, step = item.indices(len(self))
            return [self[i] for i in range(start, stop, step)]
        else:
            return super(OrderBookSide, self).__getitem__(item)

    def __eq__(self, other):
        if isinstance(other, list):
            return list(self) == other
        return super(OrderBookSide, self).__eq__(other)

    def __repr__(self):
        return str(list(self))

# -----------------------------------------------------------------------------
# overwrites absolute volumes at price levels
# or deletes price levels based on order counts (3rd value in a bidask delta)
# this class stores vector arrays of values indexed by price


class CountedOrderBookSide(OrderBookSide):
    def __init__(self, deltas=[], depth=None):
        super(CountedOrderBookSide, self).__init__(deltas, depth)

    def storeArray(self, delta):
        price = delta[0]
        size = delta[1]
        count = delta[2]
        index_price = -price if self.side else price
        index = bisect.bisect_left(self._index, index_price)
        if size and count:
            if index < len(self._index) and self._index[index] == index_price:
                self[index][1] = size
                self[index][2] = count
            else:
                self._index.insert(index, index_price)
                self.insert(index, delta)
        elif index < len(self._index) and self._index[index] == index_price:
            del self._index[index]
            del self[index]

    def store(self, price, size, count):
        self.storeArray([price, size, count])

# -----------------------------------------------------------------------------
# indexed by order ids (3rd value in a bidask delta)


class IndexedOrderBookSide(OrderBookSide):
    def __init__(self, deltas=[], depth=None):
        self._hashmap = {}
        super(IndexedOrderBookSide, self).__init__(deltas, depth)

    def storeArray(self, delta):
        price = delta[0]
        if price is not None:
            index_price = -price if self.side else price
        else:
            index_price = None
        size = delta[1]
        order_id = delta[2]
        if size:
            if order_id in self._hashmap:
                old_price = self._hashmap[order_id]
                index_price = index_price or old_price
                # in case the price is not defined
                delta[0] = abs(index_price)
                # matches if price is not defined or if price matches
                if index_price == old_price:
                    # just overwrite the old index
                    index = bisect.bisect_left(self._index, index_price)
                    self._index[index] = index_price
                    self[index] = delta
                    return
                else:
                    # remove old price level
                    old_index = bisect.bisect_left(self._index, old_price)
                    del self._index[old_index]
                    del self[old_index]
            # insert new price level
            self._hashmap[order_id] = index_price
            index = bisect.bisect_left(self._index, index_price)
            self._index.insert(index, index_price)
            self.insert(index, delta)
        elif order_id in self._hashmap:
            old_price = self._hashmap[order_id]
            index = bisect.bisect_left(self._index, old_price)
            del self._index[index]
            del self[index]
            del self._hashmap[order_id]

    def remove_index(self, order):
        order_id = order[2]
        if order_id in self._hashmap:
            del self._hashmap[order_id]

    def store(self, price, size, order_id):
        self.storeArray([price, size, order_id])

# -----------------------------------------------------------------------------
# adjusts the volumes by positive or negative relative changes or differences


class IncrementalOrderBookSide(OrderBookSide):
    def __init__(self, deltas=[], depth=None):
        super(IncrementalOrderBookSide, self).__init__(deltas, depth)

    def storeArray(self, delta):
        price = delta[0]
        size = delta[1]
        index_price = -price if self.side else price
        index = bisect.bisect_left(self._index, index_price)
        index_exists = index < len(self._index) and self._index[index] == index_price
        if index_exists:
            size += self[index][1]
        if size > 0:
            if index_exists:
                self[index][1] = size
            else:
                self._index.insert(index, index_price)
                self.insert(index, delta)
        elif index < len(self._index) and self._index[index] == index_price:
            del self._index[index]
            del self[index]

# -----------------------------------------------------------------------------
# incremental and indexed (2 in 1)


class IncrementalIndexedOrderBookSide(IndexedOrderBookSide):
    def storeArray(self, delta):
        price = delta[0]
        if price is not None:
            index_price = -price if self.side else price
        else:
            index_price = None
        size = delta[1]
        order_id = delta[2]

        old_price = None
        index = None
        contains_index = order_id in self._hashmap
        if size > 0 and contains_index:
            # handling for incremental stuff
            old_price = self._hashmap[order_id]
            index_price = index_price or old_price
            index = bisect.bisect_left(self._index, index_price)
            size += self[index][1]
            # update the order if price is not defined
            delta[0] = abs(index_price)
            # incremental
            delta[1] = size

        if size > 0:
            if contains_index:
                # matches if price is not defined or if price matches
                if index_price == old_price:
                    # just overwrite the old index
                    self._index[index] = index_price
                    self[index] = delta
                    return
                else:
                    # remove old price level
                    old_index = bisect.bisect_left(self._index, old_price)
                    del self._index[old_index]
                    del self[old_index]
            # insert new price level
            self._hashmap[order_id] = index_price
            index = bisect.bisect_left(self._index, index_price)
            self._index.insert(index, index_price)
            self.insert(index, delta)
        elif contains_index:
            old_price = self._hashmap[order_id]
            index = bisect.bisect_left(self._index, old_price)
            del self._index[index]
            del self[index]
            del self._hashmap[order_id]

# -----------------------------------------------------------------------------
# a more elegant syntax is possible here, but native inheritance is portable

class Asks(OrderBookSide): side = False                                     # noqa
class Bids(OrderBookSide): side = True                                      # noqa
class CountedAsks(CountedOrderBookSide): side = False                       # noqa
class CountedBids(CountedOrderBookSide): side = True                        # noqa
class IndexedAsks(IndexedOrderBookSide): side = False                       # noqa
class IndexedBids(IndexedOrderBookSide): side = True                        # noqa
class IncrementalAsks(IncrementalOrderBookSide): side = False               # noqa
class IncrementalBids(IncrementalOrderBookSide): side = True                # noqa
class IncrementalIndexedAsks(IncrementalIndexedOrderBookSide): side = False # noqa
class IncrementalIndexedBids(IncrementalIndexedOrderBookSide): side = True  # noqa