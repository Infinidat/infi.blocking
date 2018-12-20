import pickle
import os
import sys
import logging
import types
import tblib
import six
import contextlib
import uuid

logger = logging.getLogger(__name__)

SCRIPT = """# -*- coding: utf-8 -*-
import sys
import logging
import os
import contextlib

sys.path = {path!r}
server_port = {server_port!r}
logging_port = {logging_port!r}
gevent_friendly = {gevent_friendly!r}
tempdir = {tempdir!r}
worker_id = {worker_id!r}


from infi.blocking.worker_process import main

main(server_port, logging_port, gevent_friendly, tempdir, worker_id)
"""


class Timeout(Exception):
    pass


class Worker(object):
    def __init__(self, server, tempdir, gevent_friendly):
        from .worker_process import get_rpc
        self.server = server
        self.tempdir = tempdir
        self.gevent_friendly = gevent_friendly
        self._result = None
        self._id = os.path.basename(tempdir)
        self.logging_port = self.server.get_port()

        for handler in logging.root.handlers:
            if isinstance(handler, LoggingHandler):
                self.logging_port = logging.root.handlers[-1].get_client().get_port()

        rpc = get_rpc(gevent_friendly)
        self.client_class, self.timeout_exceptions = rpc.Client, rpc.timeout_exceptions

    @contextlib.contextmanager
    def client_context(self, timeout):
        server_port = self.server.get_child_port()
        logger.debug("worker {} attempting to connect to child over port {} with timeout {}".format(self._id, server_port, timeout))
        child = self.client_class(server_port, timeout=timeout)
        with contextlib.closing(child):
            yield child

    def call(self, call_method, call_args, timeout=None):
        logger.debug("worker {} calling {!r} {!r} with timeout {}".format(self._id, call_method, call_args, timeout))
        with self.client_context(timeout) as child:
            try:
                logger.debug('worker {} client connected to server'.format(self._id))
                response = child.call(call_method, *call_args)
                result = pickle.loads(response)
            except self.timeout_exceptions:
                six.reraise(Timeout, Timeout(), sys.exc_info()[2])
            except:
                logger.exception("caught unhandled rpc exception")
                raise
            logger.debug("got {!r}".format(result))
            if result['code'] == 'error':
                _type, value, tb = result['result']
                exc_info = _type, value, tb.as_traceback()
                six.reraise(*exc_info)
            return result['result']

    def run(self, target, args=None, kwargs=None, timeout=None):
        logger.debug("worker {} running {!r} {!r} {!r} with timeout {!r}".format(self._id, target, args, kwargs, timeout))
        call_method, call_args = self.prepare(target, args, kwargs)
        return self.call(call_method, call_args, timeout=timeout)

    def prepare(self, target, args=None, kwargs=None):
        args = tuple() if args is None else args
        kwargs = dict() if kwargs is None else kwargs
        assert callable(target)

        if isinstance(target, types.MethodType):
            call_args = (pickle.dumps(target.__self__), pickle.dumps(target.__func__.__name__),
                         pickle.dumps(args), pickle.dumps(kwargs))
            call_method = 'run_method'
        else:
            call_args = pickle.dumps(target), pickle.dumps(args), pickle.dumps(kwargs)
            call_method = 'run_func'
        return call_method, call_args

    def start(self):
        from os import path
        from sys import executable, path as sys_path
        from infi.execute import execute_async

        script = path.join(self.tempdir, 'script.py')
        with open(script, 'w') as fd:
            kwargs = dict(path=sys_path, server_port=self.server.get_port(),
                          gevent_friendly=self.gevent_friendly,
                          worker_id=self._id,
                          tempdir=self.tempdir, logging_port=self.logging_port)
            fd.write(SCRIPT.format(**kwargs))
        logger.debug("starting worker {}: {} {}".format(self._id, executable, script))
        self._result = execute_async([executable, script])

    def is_running(self):
        return self._result and not self._result.is_finished()

    def wait(self, timeout=None):
        from infi.execute import CommandTimeout
        if self._result:
            try:
                self._result.wait(timeout)
            except CommandTimeout:
                raise Timeout()

    def shutdown(self, timeout=None):
        if not self.server.get_child_port():
            return
        with self.client_context(timeout) as child:
            try:
                child.call('shutdown')
            except self.timeout_exceptions:
                pass
        self.wait(timeout)

    def get_exitcode(self):
        if self._result:
            return self._result.get_returncode()

    def ensure_stopped(self):
        if not self._result.is_finished():
            try:
                self._result.kill()
            except:
                logger.error("could not kill {}".format(self._result))
        if self._result.get_stdout():
            logger.debug(self._result.get_stdout())
        if self._result.get_stderr():
            logger.debug(self._result.get_stderr())
        logger.debug("worker {} stoppped with exit code {}".format(self._id, self.get_exitcode()))

    def get_id(self):
        return self._id


class LoggingHandler(logging.Handler):
    def __init__(self, client, worker_id, *args, **kwargs):
        self._client = client
        self._worker_id = worker_id
        super(LoggingHandler, self).__init__(*args, **kwargs)

    def get_client(self):
        return self._client

    def handle(self, record):
        record.msg += ' (message from worker {})'.format(self._worker_id)
        if record.exc_info:
            record.exc_info = (record.exc_info[0], record.exc_info[1], tblib.Traceback(record.exc_info[2]))
        try:
            self._client.call('log', pickle.dumps(record))
        except:
            pass
