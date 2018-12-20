import threading
import pickle
import sys
import logging
import msgpackrpc
import tblib
import uuid
import functools


logger = logging.getLogger(__name__)

class Base(object):
    def __init__(self):
        self._server = msgpackrpc.Server(self)
        self._blocking_thread = None
        self._id = str(uuid.uuid1())

    def start(self):
        self._server.listen(msgpackrpc.Address("127.0.0.1", 0))
        self._blocking_thread = threading.Thread(target=self._server.start)
        self._blocking_thread.start()
        logger.debug("server {} started".format(self._id))

    def join(self, timeout=None):
        self._blocking_thread.join(timeout)

    def ensure_stopped(self, timeout=None):
        self._server.stop()
        self._blocking_thread.join(timeout)
        logger.debug("server {} stopped".format(self._id))

    def get_port(self):
        return list(self._server._listeners[0]._mp_server._sockets.values())[0].getsockname()[1]

    def get_id(self):
        return self._id


class ServerMixin(object):
    def wait_for_worker(self, timeout=None):
        self._client_ack_event.wait(timeout)
        assert self._client_ack_event.is_set()

    def ack(self, client_port):
        logger.debug("server {} got ack".format(self._id))
        self._client_port = client_port
        self._client_ack_event.set()

    def log(self, log_record):
        try:
            record = pickle.loads(log_record)
            if record.exc_info:
                record.exc_info = (record.exc_info[0], record.exc_info[1], tblib.Traceback(record.exc_info[2].as_traceback()))
            logging.getLogger(record.name).handle(record)
        except:
            pass

    def get_child_port(self):
        return self._client_port


class Server(Base, ServerMixin):
    def __init__(self):
        super(Server, self).__init__()
        self._client_ack_event = threading.Event()
        self._client_port = None


def rpc_result(func):
    from infi.traceback import traceback_decorator
    @traceback_decorator
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = dict(code='success', result=func(*args, **kwargs))
        except:
            logger.exception("Exception in child rpc_result")
            _type, value, _tb = sys.exc_info()
            exc_info = (_type, value, tblib.Traceback(_tb))
            result = dict(code='error', result=exc_info)
        logger.debug("returning {!r} for".format(result))
        return pickle.dumps(result)
    return wrapper

class ChildServerMixin(object):
    @rpc_result
    def run_method(self, instance, method_name, args, kwargs):
        instance = pickle.loads(instance)
        method_name = pickle.loads(method_name)
        args = pickle.loads(args)
        kwargs = pickle.loads(kwargs)
        method = getattr(instance, method_name)
        logger.debug("running {!r} {!r} {!r}".format(method, args, kwargs))
        return method(*args, **kwargs)

    @rpc_result
    def run_func(self, target, args, kwargs):
        target = pickle.loads(target)
        args = pickle.loads(args)
        kwargs = pickle.loads(kwargs)
        logger.debug("running {!r} {!r} {!r}".format(target, args, kwargs))
        return target(*args, **kwargs)

    def shutdown(self):
        logger.debug('child server {!r} shutting down'.format(self.get_id()))
        self._server.close()
        self._server.stop()


class ChildServer(Base, ChildServerMixin):
    pass


class Client(msgpackrpc.Client):
    def __init__(self, port, timeout=None):
        super(Client, self).__init__(msgpackrpc.Address("127.0.0.1", port), timeout=timeout)
        self._port = port

    def get_port(self):
        return self._port


timeout_exceptions = (msgpackrpc.error.TimeoutError, )
