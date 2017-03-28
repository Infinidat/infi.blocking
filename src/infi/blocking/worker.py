import pickle
import sys
import logging
from six import reraise

logger = logging.getLogger(__name__)

SCRIPT = """# -*- coding: utf-8 -*-
import sys
import logging
sys.path = {path!r}
server_port = {server_port!r}
gevent_friendly = {gevent_friendly!r}

from infi.blocking.worker import LoggingHandler

if gevent_friendly:
    from infi.blocking import gevent_rpc as rpc
else:
    from infi.blocking import rpc

child = rpc.ChildServer()
child.start()

client = rpc.Client(server_port)

logging.root.addHandler(LoggingHandler(client))
logging.root.setLevel(logging.DEBUG)

client.call('ack', child.get_port())
child.join()

"""

class Timeout(Exception):
    pass

class Worker(object):
    def __init__(self, server, tempdir, gevent_friendly):
        self.server = server
        self.tempdir = tempdir
        self.gevent_friendly = gevent_friendly
        self._result = None

    def run(self, target, args=None, kwargs=None, timeout=None):
        if self.gevent_friendly:
            from .gevent_rpc import Client, timeout_exceptions
        else:
            from .rpc import Client, timeout_exceptions
        child = Client(self.server.get_child_port(), timeout=timeout)
        logger.debug("running {!r} {!r} {!r}".format(target, args, kwargs))
        call_args = pickle.dumps(target), pickle.dumps(args), pickle.dumps(kwargs)
        try:
            result = pickle.loads(child.call('run', *call_args))
        except timeout_exceptions as error:
            reraise(Timeout, Timeout(), sys.exc_info()[2])
        logger.debug("got {!r}".format(result))
        if result['code'] == 'error':
            _type, value, tb = result['result']
            exc_info = _type, value, tb.as_traceback()
            reraise(*exc_info)
        return result['result']

    def start(self):
        from os import path
        from sys import executable, path as sys_path
        from infi.execute import execute_async

        script = path.join(self.tempdir, 'script.py')
        with open(script, 'w') as fd:
            fd.write(SCRIPT.format(path=sys_path, server_port=self.server.get_port(),
                                   gevent_friendly=self.gevent_friendly))
        logger.debug("starting {} {}".format(executable, script))
        self._result = execute_async([executable, script])

    def ensure_stopped(self):
        if not self._result:
            return
        if not self._result.is_finished():
            self._result.kill()
        logger.debug(self._result.get_stdout())
        logger.debug(self._result.get_stderr())

class LoggingHandler(logging.Handler):
    def __init__(self, client, *args, **kwargs):
        self._client = client
        super(LoggingHandler, self).__init__(*args, **kwargs)

    def emit(self, record):
        self._client.call('log', pickle.dumps(record))
