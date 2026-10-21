from ports.shell_protocol import PromptParser


def test_prompt_marker_split_and_unicode():
    parser = PromptParser("nonce")
    marker = b"\x1b]777;ports;nonce;ready;L3RtcA==\x07"
    data = "hello 世界".encode() + marker + b"prompt>"
    output = bytearray()
    events = []
    for byte in data:
        clean, ready = parser.feed(bytes([byte]))
        output.extend(clean)
        events.extend(ready)
    assert bytes(output) == "hello 世界prompt>".encode()
    assert events == ["/tmp"]


def test_wrong_nonce_is_terminal_output():
    data = b"\x1b]777;ports;wrong;ready;\x07"
    clean, events = PromptParser("right").feed(data)
    assert clean == data
    assert not events


def test_two_markers_in_one_read():
    marker = b"\x1b]777;ports;n;ready;\x07"
    output, events = PromptParser("n").feed(marker + b"a" + marker)
    assert output == b"a"
    assert events == ["", ""]
