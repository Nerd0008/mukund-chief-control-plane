import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_e3_provider import E3ModelClient


class FakeE3:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {"content": "", "tool_calls": [{"id": "t1", "type": "function",
                                                     "function": {"name": "status", "arguments": "{}"}}],
                    "worker_id": "longcat-2.0", "provider": "longcat", "model": "longcat-2.0"}
        return {"content": "final", "worker_id": "codex-cli", "provider": "codex", "model": "codex"}


def test_hermes_loop_keeps_tool_iteration_on_e3_provider_boundary():
    service = FakeE3()
    client = E3ModelClient(service)
    messages = [{"role": "user", "content": "inspect status"}]
    first = client.chat.completions.create(model="e3-auto", messages=messages,
                                            tools=[{"type": "function", "function": {"name": "status"}}])
    assert first.choices[0].finish_reason == "tool_calls"
    messages.extend([{"role": "assistant", "tool_calls": first.choices[0].message.tool_calls},
                     {"role": "tool", "content": "healthy", "tool_call_id": "t1"}])
    second = client.chat.completions.create(model="e3-auto", messages=messages,
                                             tools=[{"type": "function", "function": {"name": "status"}}])
    assert second.choices[0].message.content == "final"
    assert len(service.calls) == 2
    assert all(call["context"]["hermes_tools_present"] for call in service.calls)
