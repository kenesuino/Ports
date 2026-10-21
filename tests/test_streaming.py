import base64
import threading
import time

from ports.stream_buffer import OutputBuffer


def test_stream_preserves_split_unicode_and_ack_accounting():
    buffer = OutputBuffer(limit=64)
    value = "世🌍".encode()
    for byte in value:
        buffer.put(bytes([byte]))
    chunk = buffer.take(64)
    assert chunk == value
    assert buffer.used == len(value)
    buffer.ack(len(base64.b64encode(value)))  # invalid ack must be ignored
    assert buffer.used == len(value)
    buffer.ack(len(value))
    assert buffer.used == 0


def test_large_write_blocks_at_limit_and_close_releases():
    buffer = OutputBuffer(limit=16)
    thread = threading.Thread(target=lambda: buffer.put(b"x" * 100))
    thread.start()
    time.sleep(.05)
    assert buffer.used <= 16
    buffer.close()
    thread.join(timeout=1)
    assert not thread.is_alive()
