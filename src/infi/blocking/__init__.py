from functools import wraps
from contextlib import contextmanager
from .worker import Timeout

__import__("pkg_resources").declare_namespace(__name__)

@contextmanager
def tempdir_context():
    from tempfile import mkdtemp
    from shutil import rmtree
    tempdir = mkdtemp()
    try:
        yield tempdir
    finally:
        pass#rmtree(tempdir, ignore_errors=True)


@contextmanager
def server_context(gevent_friendly=False):
    if gevent_friendly:
        from .gevent_rpc import Server
    else:
        from .rpc import Server
    server = Server()
    server.start()
    try:
        yield server
    finally:
        server.ensure_stopped()


@contextmanager
def worker_context(server, tempdir, timeout=3, gevent_friendly=False):
    from .worker import Worker
    worker = Worker(server, tempdir, gevent_friendly=gevent_friendly)
    worker.start()
    try:
        server.wait_for_worker(timeout)
        yield worker
    finally:
        worker.ensure_stopped()


def make_blocking(func, timeout=10, gevent_friendly=None):
    if gevent_friendly == None:
        gevent_friendly = can_use_gevent_rpc()

    @wraps(func)
    def wrapper(*args, **kwargs):
        with server_context(gevent_friendly=gevent_friendly) as server:
            with tempdir_context() as tempdir:
                with worker_context(server, tempdir, gevent_friendly=gevent_friendly) as worker:
                    return worker.run(func, args, kwargs, timeout=timeout)
    return wrapper


def can_use_gevent_rpc():
    try:
        from . import gevent_rpc
    except ImportError:
        return False
    return True
