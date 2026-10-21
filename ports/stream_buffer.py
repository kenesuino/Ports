"""Byte-accurate bounded producer/consumer bridge for terminal output."""
from collections import deque
import threading


class OutputBuffer:
    def __init__(self, limit=1024 * 1024):
        self.limit = limit
        self.queue = deque()
        self.used = 0
        self.inflight = 0
        self.closed = False
        self.condition = threading.Condition()

    def put(self, data):
        position = 0
        with self.condition:
            while position < len(data) and not self.closed:
                available = self.limit - self.used
                if not available:
                    self.condition.wait(.25)
                    continue
                chunk = data[position:position + min(available, 65536)]
                self.queue.append(chunk)
                self.used += len(chunk)
                position += len(chunk)

    def take(self, size=65536):
        with self.condition:
            output = bytearray()
            while self.queue and len(output) < size:
                first = self.queue.popleft()
                available = size - len(output)
                output.extend(first[:available])
                if len(first) > available:
                    self.queue.appendleft(first[available:])
            self.inflight += len(output)
            return bytes(output)

    def ack(self, count):
        with self.condition:
            if type(count) is int and 0 < count <= self.inflight:
                self.inflight -= count
                self.used -= count
                self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed = True
            self.queue.clear()
            self.used = self.inflight = 0
            self.condition.notify_all()
