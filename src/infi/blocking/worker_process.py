import sys
import logging
import os
import contextlib

logger = logging.getLogger(__name__)

def get_rpc(gevent_friendly):
    if gevent_friendly:
        from infi.blocking import gevent_rpc as rpc
    else:
        from infi.blocking import rpc
    return rpc


def cleanup_tornado_logging():
    from tornado import options
    for handler in list(logging.root.handlers):
        logging.root.removeHandler(handler)
    logging.shutdown()


def setup_log_txt(tempdir):
    filename = os.path.join(tempdir, 'log.txt')
    logging.root.setLevel(logging.DEBUG)
    logging.root.addHandler(logging.FileHandler(filename))


def main(server_port, logging_port, gevent_friendly, tempdir, worker_id):
    from infi.blocking.worker import LoggingHandler
    rpc = get_rpc(gevent_friendly)

    # tornado creates a StreamHandler
    cleanup_tornado_logging()
    setup_log_txt(tempdir)


    with contextlib.closing(rpc.Client(logging_port)) as logging_client:
        logging.root.addHandler(LoggingHandler(logging_client, worker_id))

        with contextlib.closing(rpc.Client(server_port)) as client:
            child = rpc.ChildServer()
            child.start()

            logger.debug("child process for worker %s started with pid %s " % (worker_id, os.getpid()))
            logger.debug("gevent_friendly: %s" % gevent_friendly)
            client.call('ack', child.get_port())
            logger.debug("ack sent")

            child.join()
            logger.debug("shutting down gracefully")
            logging.shutdown()
