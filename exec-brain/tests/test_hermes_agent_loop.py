import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_e3_provider import E3ModelClient


class FakeE3:
    def __init__(self):
        self.calls = []

    def execute_chat(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "content": (
                    '<longcat_tool_call>'
                    '{"name":"status","arguments":{}}'
                    '</longcat_tool_call>'
                ),
                "worker_id": "longcat-2.0",
                "provider": "longcat",
                "model": "LongCat-2.0",
            }
        return {
            "content": "final",
            "worker_id": "longcat-2.0",
            "provider": "longcat",
            "model": "LongCat-2.0",
        }

    def execute(self, **kwargs):
        raise AssertionError("tool-capable Hermes turns must use execute_chat")


def _tools():
    return [{
        "type": "function",
        "function": {
            "name": "status",
            "description": "Read current status",
            "parameters": {"type": "object", "properties": {}},
        },
    }]


def test_hermes_loop_converts_longcat_markup_to_native_tool_call():
    service = FakeE3()
    client = E3ModelClient(service)
    messages = [{"role": "user", "content": "inspect status"}]

    first = client.chat.completions.create(
        model="e3-auto", messages=messages, tools=_tools())

    assert first.choices[0].finish_reason == "tool_calls"
    calls = first.choices[0].message.tool_calls
    assert len(calls) == 1
    assert calls[0].function.name == "status"

    messages.extend([
        {
            "role": "assistant",
            "content": first.choices[0].message.content,
            "tool_calls": [{
                "id": calls[0].id,
                "type": "function",
                "function": {
                    "name": calls[0].function.name,
                    "arguments": calls[0].function.arguments,
                },
            }],
        },
        {
            "role": "tool",
            "content": "healthy",
            "tool_call_id": calls[0].id,
            "name": "status",
        },
    ])

    second = client.chat.completions.create(
        model="e3-auto", messages=messages, tools=_tools())

    assert second.choices[0].finish_reason == "stop"
    assert second.choices[0].message.content == "final"
    assert len(service.calls) == 2
    wire = service.calls[1]["messages"]
    assert any("<tool_response>" in row.get("content", "") for row in wire)


class UnknownToolE3:
    def execute_chat(self, **kwargs):
        return {
            "content": (
                '<longcat_tool_call>'
                '{"name":"dangerous_unknown","arguments":{}}'
                '</longcat_tool_call>'
            ),
            "worker_id": "longcat-2.0",
            "provider": "longcat",
            "model": "LongCat-2.0",
        }


def test_unknown_tool_markup_never_becomes_executable():
    client = E3ModelClient(UnknownToolE3())
    result = client.chat.completions.create(
        model="e3-auto",
        messages=[{"role": "user", "content": "inspect status"}],
        tools=_tools(),
    )
    assert result.choices[0].finish_reason == "stop"
    assert not getattr(result.choices[0].message, "tool_calls", None)


class MalformedLongCatE3:
    def execute_chat(self, **kwargs):
        return {
            "content": (
                '<longcat_tool_call>'
                '{"name":"status","arguments":'
                '</longcat_tool_call>'
            ),
            "worker_id": "longcat-2.0",
            "provider": "longcat",
            "model": "LongCat-2.0",
        }


def test_malformed_longcat_markup_stays_non_executable():
    client = E3ModelClient(MalformedLongCatE3())
    result = client.chat.completions.create(
        model="e3-auto",
        messages=[{"role": "user", "content": "inspect status"}],
        tools=_tools(),
    )
    assert result.choices[0].finish_reason == "stop"
    assert not getattr(result.choices[0].message, "tool_calls", None)
    assert "<longcat_tool_call>" in result.choices[0].message.content
