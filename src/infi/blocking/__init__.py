import os
import functools
import contextlib
import logging

from .worker import Timeout

__import__("pkg_resources").declare_namespace(__name__)

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def tempdir_context():
    from tempfile import mkdtemp
    from shutil import rmtree
    tempdir = mkdtemp()
    try:
        yield tempdir
    finally:
        if os.environ.get('INFI_BLOCKING_LEAVE_TEMPDIR', '0') != '1':
            rmtree(tempdir, ignore_errors=True)


@contextlib.contextmanager
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


@contextlib.contextmanager
def worker_context(server, tempdir, timeout=10, gevent_friendly=False):
    from .worker import Worker, Timeout
    worker = Worker(server, tempdir, gevent_friendly=gevent_friendly)
    worker.start()
    try:
        server.wait_for_worker(timeout)
        yield worker
    except Timeout:
        logger.debug("worker {} timed out, will not shut down properly".format(worker.get_id()))
        raise
    except:
        logger.debug("worker {} had an exception".format(worker.get_id()))
        raise
    else:
        try:
            worker.shutdown(timeout=timeout)
            logger.debug("worker {} has shut down gracefully".format(worker.get_id()))
        except Timeout:
            logger.debug("worker {} timed out during shut down".format(worker.get_id()))
    finally:
        worker.ensure_stopped()


@contextlib.contextmanager
def blocking_context(gevent_friendly=None):
    if gevent_friendly is None:
        gevent_friendly = can_use_gevent_rpc()
    with server_context(gevent_friendly=gevent_friendly) as server:
        with tempdir_context() as tempdir:
            with worker_context(server, tempdir, gevent_friendly=gevent_friendly) as worker:
                yield server, worker


def make_blocking(func, timeout=10, gevent_friendly=None):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with blocking_context(gevent_friendly=gevent_friendly) as server_and_worker:
            return server_and_worker[1].run(func, args, kwargs, timeout=timeout)
    return wrapper


def can_use_gevent_rpc():
    try:
        from . import gevent_rpc
        gevent_rpc
    except ImportError:
        return False
    return True
