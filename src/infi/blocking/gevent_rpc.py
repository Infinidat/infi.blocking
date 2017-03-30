import logging
import socket
import mprpc
import gevent
import gevent.server
import gevent.event
import msgpackrpc
import uuid
from infi.blocking import rpc

logger = logging.getLogger(__name__)

class Base(mprpc.RPCServer):
    def __init__(self):
        super(Base, self).__init__()
        self._server = gevent.server.StreamServer(('127.0.0.1', 0), self)
        self._id = str(uuid.uuid1())

    def start(self):
        self._server.start()
        logger.debug("server {} started".format(self._id))

    def join(self, timeout=None):
        self._server._stop_event.wait(timeout)

    def ensure_stopped(self, timeout=None):
        self._server.stop(timeout)
        logger.debug("server {} stopped".format(self._id))

    def get_port(self):
        return self._server.socket.getsockname()[1]

    def get_id(self):
        return self._id


class Server(Base, rpc.ServerMixin):
    def __init__(self):
        super(Server, self).__init__()
        self._client_ack_event = gevent.event.Event()
        self._client_port = None

    def _run(self, *args, **kwargs):
        try:
            super(Server, self)._run(*args, **kwargs)
        except socket.error:
            pass
        except:
            logger.exception("unhandled exception")

class ChildServer(Base, rpc.ChildServerMixin):
    pass


class Client(mprpc.RPCClient):
    def __init__(self, port, timeout=None):
        super(Client, self).__init__("127.0.0.1", port, timeout=timeout)
        self._port = port

    def get_port(self):
        return self._port

timeout_exceptions = (msgpackrpc.error.TimeoutError, gevent.Timeout, socket.timeout, IOError)
