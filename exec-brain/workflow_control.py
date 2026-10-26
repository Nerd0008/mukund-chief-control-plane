"""Operation-scoped deadlines, worker constraints and bounded child cleanup."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import subprocess, threading, time, uuid
from router_brain import RouterDecisionError

CURRENT = ContextVar('router_operation', default=None)
CONTENT_WORKER = ContextVar('router_content_worker', default=None)


class WorkflowTimeoutError(RouterDecisionError,TimeoutError):pass


def seconds(value, default=90):
    if value is None:return float(default)
    if hasattr(value,'read'):value=value.read
    try:value=float(value)
    except (TypeError,ValueError):raise RouterDecisionError('invalid_workflow_timeout') from None
    if not 0<value<float('inf'):raise WorkflowTimeoutError('workflow_deadline_exceeded')
    return value


def requested_worker(message):
    import re
    text=str(message)
    if re.search(r"\b(?:do not|don't|avoid|without)\s+(?:use\s+|using\s+)?codex\b",text,re.I):return 'native'
    if re.search(r'\b(?:use|using|through|via|with)\s+(?:the\s+)?codex\b',text,re.I):
        if re.search(r'\bcodex\s+(?:as|for)\s+(?:the\s+)?(?:router|routing|brain)\b',text,re.I):return None
        return 'codex'
    return None


class Operation:
    def __init__(self,timeout,worker=None,parent=None):
        if worker not in (None,'auto','codex','native'):raise RouterDecisionError('unsupported_worker_preference')
        self.id=parent.id if parent else uuid.uuid4().hex
        self.deadline=min(time.monotonic()+seconds(timeout),parent.deadline if parent else float('inf'))
        self.cancel=parent.cancel if parent else threading.Event()
        self.worker=parent.worker if parent and parent.worker not in (None,'auto') else worker
        if parent and parent.worker not in (None,'auto') and worker not in (None,'auto',parent.worker):
            raise RouterDecisionError('conflicting_worker_preference')
    def remaining(self,cap=None):
        if self.cancel.is_set():raise RouterDecisionError('workflow_cancelled')
        value=self.deadline-time.monotonic()
        if value<=0:raise WorkflowTimeoutError('workflow_deadline_exceeded')
        return min(value,cap) if cap is not None else value


@contextmanager
def operation(timeout=90,worker=None):
    state=Operation(timeout,worker,CURRENT.get());token=CURRENT.set(state)
    try:yield state
    finally:CURRENT.reset(token)


def constrain(offers,worker=None):
    state=CURRENT.get()
    worker=worker or (state.worker if state else None)
    if worker in (None,'auto'):return offers
    result=[offer for offer in offers if offer['id']==worker]
    if not result:raise RouterDecisionError('worker_preference_incompatible')
    return result


async def cancellable_thread(function,*args,**kwargs):
    state=CURRENT.get();future=asyncio.create_task(asyncio.to_thread(function,*args,**kwargs))
    try:return await asyncio.shield(future)
    except asyncio.CancelledError:
        if state:state.cancel.set()
        try:await asyncio.wait_for(asyncio.shield(future),6)
        except BaseException:pass
        raise


class DeadlineStream:
    """Own only this stream's cleanup; never close a shared SDK client."""
    def __init__(self,stream,state):
        self.stream=stream;self.state=state;self._closed=False;self._expired=False;self._timer=None;self._close_lock=threading.Lock()
    def __getattr__(self,name):return getattr(self.stream,name)
    def close(self):
        with self._close_lock:
            if self._closed:return
            self._closed=True
            if self._timer:self._timer.cancel()
        close=getattr(self.stream,'close',None)
        if callable(close):close()
    def _remaining(self):
        if self._expired:raise WorkflowTimeoutError('workflow_deadline_exceeded')
        return self.state.remaining()
    def _expire(self):
        self._expired=True
        self.state.cancel.set()
        try:self.close()
        except Exception:pass
    def __iter__(self):
        try:
            self._remaining();self._timer=threading.Timer(self._remaining(),self._expire)
            self._timer.daemon=True;self._timer.start();iterator=iter(self.stream)
            while True:
                self._remaining()
                try:chunk=next(iterator)
                except StopIteration:self._remaining();return
                except Exception:self._remaining();raise
                self._remaining();yield chunk
        finally:self.close()
    async def aclose(self):
        with self._close_lock:
            if self._closed:return
            self._closed=True
        close=getattr(self.stream,'aclose',None) or getattr(self.stream,'close',None)
        if callable(close):
            value=close()
            if __import__('inspect').isawaitable(value):await value
    async def __aiter__(self):
        try:
            iterator=self.stream.__aiter__()
            while True:
                try:chunk=await asyncio.wait_for(iterator.__anext__(),self.state.remaining())
                except StopAsyncIteration:return
                except asyncio.TimeoutError:raise WorkflowTimeoutError('workflow_deadline_exceeded') from None
                self.state.remaining();yield chunk
        finally:await self.aclose()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.aclose()


def finish(value,state,stream=False):
    state.remaining()
    return DeadlineStream(value,state) if stream and (hasattr(value,'__iter__') or hasattr(value,'__aiter__')) else value


class ProcessCancelled(Exception):pass


def stop_child(proc):
    """Terminate only the subprocess tree started by this invocation."""
    if proc.poll() is not None:return
    if __import__('os').name=='nt':
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,
            timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    else:proc.kill()
    try:proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.communicate(timeout=5)


def run_process(command,*,cancel_event=None,timeout,input=None,**kwargs):
    """communicate() polling keeps stdin private and makes cancellation observable."""
    if cancel_event is None:
        return subprocess.run(command,input=input,timeout=timeout,**kwargs)
    if cancel_event.is_set():raise ProcessCancelled()
    kwargs.pop('capture_output',None)
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    deadline=time.monotonic()+seconds(timeout);first=True
    try:
        while True:
            if cancel_event.is_set():raise ProcessCancelled()
            left=deadline-time.monotonic()
            if left<=0:raise subprocess.TimeoutExpired(command,timeout)
            try:
                stdout,stderr=proc.communicate(input=input if first else None,timeout=min(.1,left))
                return subprocess.CompletedProcess(command,proc.returncode,stdout,stderr)
            except subprocess.TimeoutExpired:first=False
    finally:
        if proc.poll() is None:stop_child(proc)
