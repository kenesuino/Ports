"""Bounded parser for private shell prompt markers, preserving terminal bytes."""
import base64


class PromptParser:
    def __init__(self, token: str):
        self.prefix = f"\x1b]777;ports;{token};ready;".encode()
        self.pending = bytearray()

    def feed(self, data: bytes) -> tuple[bytes, list[str]]:
        self.pending.extend(data)
        out = bytearray()
        events = []
        while self.pending:
            start = self.pending.find(self.prefix)
            if start < 0:
                keep = 0
                for n in range(1, min(len(self.prefix), len(self.pending) + 1)):
                    if self.pending.endswith(self.prefix[:n]):
                        keep = n
                stop = len(self.pending) - keep
                out.extend(self.pending[:stop])
                del self.pending[:stop]
                break
            out.extend(self.pending[:start])
            del self.pending[:start]
            end = self.pending.find(b"\x07", len(self.prefix))
            if end < 0:
                if len(self.pending) > 8192:
                    out.extend(self.pending[:1])
                    del self.pending[:1]
                    continue
                break
            encoded = bytes(self.pending[len(self.prefix):end])
            try:
                cwd = base64.b64decode(encoded, validate=True).decode("utf-8")
            except (ValueError, UnicodeError):
                cwd = ""
            events.append(cwd)
            del self.pending[:end + 1]
        return bytes(out), events
