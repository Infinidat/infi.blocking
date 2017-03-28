import threading
import pickle
import sys
import logging
import msgpackrpc
import tblib

logger = logging.getLogger(__name__)

class Base(object):
    def __init__(self):
        self._server = msgpackrpc.Server(self)
        self._blocking_thread = None

    def start(self):
        self._server.listen(msgpackrpc.Address("127.0.0.1", 0))
        self._blocking_thread = threading.Thread(target=self._server.start)
        self._blocking_thread.start()

    def join(self, timeout=None):
        self._blocking_thread.join(timeout)

    def ensure_stopped(self, timeout=None):
        self._server.stop()
        self._blocking_thread.join(timeout)

    def get_port(self):
        return self._server._listeners[0]._mp_server._sockets.values()[0].getsockname()[1]


class ServerMixin(object):
    def wait_for_worker(self, timeout=None):
        self._client_ack_event.wait(timeout)
        assert self._client_ack_event.is_set()

    def ack(self, client_port):
        self._client_port = client_port
        self._client_ack_event.set()

    def log(self, log_record):
        record = pickle.loads(log_record)
        logging.getLogger(record.name).handle(record)

    def get_child_port(self):
        return self._client_port


class Server(Base, ServerMixin):
    def __init__(self):
        super(Server, self).__init__()
        self._client_ack_event = threading.Event()
        self._client_port = None


class ChildServerMixin(object):
    def run(self, target, args, kwargs):
        target = pickle.loads(target)
        args = pickle.loads(args)
        kwargs = pickle.loads(kwargs)
        logger.debug("running {!r} {!r} {!r}".format(target, args, kwargs))
        try:
            result = dict(code='success', result=target(*args, **kwargs))
        except:
            _type, value, _tb = sys.exc_info()
            exc_info = (_type, value, tblib.Traceback(_tb))
            logger.error("caught exception", exc_info=exc_info)
            logger.debug("returning {!r}".format(value))
            result = dict(code='error', result=exc_info)
        logger.debug("returning {!r}".format(result))
        return pickle.dumps(result)


class ChildServer(Base, ChildServerMixin):
    pass


class Client(msgpackrpc.Client):
    def __init__(self, port, timeout=None):
        super(Client, self).__init__(msgpackrpc.Address("127.0.0.1", port), timeout=timeout)


timeout_exceptions = (msgpackrpc.error.TimeoutError, )
