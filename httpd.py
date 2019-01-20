# -*- coding: utf-8 -*-
import os
import time
import socket
import select
import logging
import argparse
import multiprocessing
from http_request_response import *

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SERVER_ADDR = '0.0.0.0'
SERVER_PORT = 8080
DOCUMENT_ROOT = os.path.join(BASE_DIR, 'http-test-suite')
INDEX_DEFAULT = 'index.html'


class ProcessHandler:

    document_root = None
    serversocket = None
    epoll = None

    connections = {}
    requests = {}
    responses = {}

    def __init__(self, serversocket, document_root):
        self.serversocket = serversocket
        self.document_root = document_root

    def get_validated_document_path(self, uri):
        if not uri:
            return False
        document_path = os.path.abspath(os.path.join(self.document_root, uri[1:]))  # folding all /../../..
        if uri[-1] == os.sep and os.path.isfile(document_path):  # for "...page.html/" case
            document_path += os.sep
        if os.path.isdir(document_path):  # add default index file
            document_path = os.path.join(document_path, INDEX_DEFAULT)
        if document_path.startswith(self.document_root):  # check document_root scope
            return document_path
        else:
            return False

    def handle_new_connection(self):
        # accept a new client connection and register EPOLLIN event for this connection
        connection, address = self.serversocket.accept()
        connection.setblocking(0)
        conn_fileno = connection.fileno()
        self.epoll.register(conn_fileno, select.EPOLLIN)
        self.connections[conn_fileno] = connection
        self.requests[conn_fileno] = b''
        self.responses[conn_fileno] = b''
        return conn_fileno

    def handle_recv(self, fileno):
        self.requests[fileno] += self.connections[fileno].recv(1024)

        if not self.requests[fileno]:  # if received data='', it means remote client has closed connection
            self.epoll.modify(fileno, select.EPOLLET)
            self.connections[fileno].shutdown(socket.SHUT_RDWR)
            return

        EOL1 = b'\n\n'
        EOL2 = b'\n\r\n'
        if EOL1 in self.requests[fileno] or EOL2 in self.requests[fileno]:
            req = self.requests[fileno]
            self.epoll.modify(fileno, select.EPOLLOUT)
            self.connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 1)
            request_header_raw = req.decode()[:-2]
            logging.debug('PPID: %d, PID: %d' % (os.getppid(), os.getpid()))
            logging.debug(request_header_raw)
            request = Request(request_header_raw)
            document_path = self.get_validated_document_path(request.page)
            response = Response(document_path, request)
            self.responses[fileno] = response.get_response()
            logging.info("%s %s %d" % (METHOD_SIGNATURES[request.method], request.uri, response.code))

    def handle_send(self, fileno):
        try:
            bytessent = self.connections[fileno].send(self.responses[fileno])
        except Exception as e:
            logging.debug('Sending error: %s' % e)
            self.connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 0)
            self.epoll.modify(fileno, 0)
            self.connections[fileno].close()
            del self.connections[fileno]
            return

        logging.debug('Sent total: %d bytes' % bytessent)
        self.responses[fileno] = self.responses[fileno][bytessent:]
        if len(self.responses[fileno]) == 0:
            self.connections[fileno].setsockopt(socket.IPPROTO_TCP, socket.TCP_CORK, 0)
            self.epoll.modify(fileno, 0)
            self.connections[fileno].shutdown(socket.SHUT_RDWR)
            self.connections[fileno].close()
            del self.connections[fileno]

    def run(self):
        logging.info('Worker started! PID=%d' % os.getpid())
        self.epoll = select.epoll()
        self.epoll.register(self.serversocket.fileno(), select.EPOLLIN)
        try:
            while True:
                events = self.epoll.poll(1)
                for fileno, event in events:
                    if fileno == self.serversocket.fileno():
                        self.handle_new_connection()

                    elif event & select.EPOLLIN:
                        self.handle_recv(fileno)

                    elif event & select.EPOLLOUT:
                        self.handle_send(fileno)

                    elif event & select.EPOLLHUP:
                        self.epoll.unregister(fileno)
                        self.connections[fileno].close()
                        del self.connections[fileno]
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logging.debug(e)
        finally:
            self.epoll.unregister(self.serversocket.fileno())
            self.epoll.close()


class HTTPServer(object):

    name = SERVER_NAME
    document_root = None
    server_addr = None
    server_port = None

    serversocket = None
    workers_count = 1
    epoll = None

    connections = {}
    requests = {}
    responses = {}

    def __init__(self, server_addr, server_port, document_root, workers_count=1):

        self.document_root = document_root
        self.server_addr = server_addr
        self.server_port = server_port
        self.workers_count = workers_count

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.settimeout(4)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    def start(self):
        self.serversocket.bind((self.server_addr, self.server_port))
        self.serversocket.listen(5)
        self.serversocket.setblocking(0)
        self.serversocket.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)

        for i in range(self.workers_count):
            process_handler = ProcessHandler(self.serversocket, self.document_root)
            worker = multiprocessing.Process(target=process_handler.run)
            worker.deamon = True
            worker.start()

    def shutdown(self):
        try:
            logging.info("Shutting down server")
            for process in multiprocessing.active_children():
                logging.info("Shutting down worker PID=%d" % process.pid)
                process.terminate()
                process.join()
            self.serversocket.close()
        except Exception as e:
            logging.error("Shutting down server error")
            logging.debug(e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--root", default=DOCUMENT_ROOT, help="document root")
    parser.add_argument("-w", "--workers", default=multiprocessing.cpu_count(), help="count of workers", type=int)
    parser.add_argument("-a", "--host", default=SERVER_ADDR, help="server host")
    parser.add_argument("-p", "--port", default=SERVER_PORT, help="server port", type=int)
    parser.add_argument("-l", "--log", default=None, help='log file')
    parser.add_argument("-d", "--debug", default=False, help='debug level log', action="store_true")
    settings = parser.parse_args()

    logging.basicConfig(filename=settings.log, level=logging.INFO if not settings.debug else logging.DEBUG,
                        format='[%(asctime)s] %(levelname).1s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')
    logging.info('Starting server at %s:%d ...' % (settings.host, settings.port))
    server = HTTPServer(server_addr=settings.host,
                        server_port=settings.port,
                        document_root=settings.root,
                        workers_count=settings.workers)
    try:
        server.start()
        while True:  # for 'finally' section
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info('Stopped by user! Goodbye!')
    finally:
        server.shutdown()
