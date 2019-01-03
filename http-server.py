# -*- coding: utf-8 -*-
import os
import re
import socket
import select
import urllib
import datetime

# TODO: read config file
# TODO: write logfile
# TODO: multiprocessing

SERVER_NAME = 'http-server 1.0.0'
SERVER_ADDR = '0.0.0.0'
SERVER_PORT = 8080
HTTP_VERSION = 'HTTP/1.1'
DOCUMENT_ROOT = u'/tmp/bin/http-test-suite'
INDEX_DEFAULT = 'index.html'

METHOD_GET = 1
METHOD_POST = 2
METHOD_HEAD = 3

METHOD_SIGNATURES = {
    METHOD_GET: 'GET',
    METHOD_POST: 'POST',
    METHOD_HEAD: 'HEAD',
}

ALLOWED_METHODS = (METHOD_GET, METHOD_HEAD)

RESPONSE_CODE_200_OK = 200
RESPONSE_CODE_400_BAD_REQUEST = 400
RESPONSE_CODE_404_NOT_FOUND = 404
RESPONSE_CODE_405_METHOD_NOT_ALLOWED = 405
RESPONSE_CODE_500_SERVER_ERROR = 500

RESPONSE_CODE_MESSAGES = {
    RESPONSE_CODE_200_OK: 'OK',
    RESPONSE_CODE_400_BAD_REQUEST: 'Bad Request',
    RESPONSE_CODE_404_NOT_FOUND: 'Not Found',
    RESPONSE_CODE_405_METHOD_NOT_ALLOWED: 'Method Not Allowed',
    RESPONSE_CODE_500_SERVER_ERROR: 'Internal Server Error',
}

MIMETYPES = {
    'html': 'text/html',
    'htm': 'text/html',
    'css': 'text/css',
    'js': 'application/javascript',
    'jpeg': 'image/jpeg',
    'jpg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'swf': 'application/x-shockwave-flash',
    'txt': 'text/plain',
}


class Request:

    header_raw = None

    method = None
    uri = None
    page = None
    page_args = None
    headers = {}

    def __init__(self, header_raw):
        self.header_raw = header_raw
        self.parse_header(self.header_raw)

    @staticmethod
    def get_method(method_str):
        for method_key, method_value in METHOD_SIGNATURES.items():
            if method_str.upper() == method_value:
                return method_key
        return None

    def parse_header(self, header_raw):
        methods = '|'.join(METHOD_SIGNATURES.values())
        r = re.compile('^(?P<method>' + methods + ') (?P<uri>[^ ]+) HTTP/1\.(0|1)(?P<attributes>.+)$', re.DOTALL)
        res = r.match(header_raw)
        if res:
            self.method = self.get_method(res.group('method'))
            self.uri = urllib.unquote(res.group('uri'))
            self.parse_uri(self.uri)
            self.headers = {}
            for attributes in res.group('attributes').splitlines():
                if attributes:
                    name, value = attributes.split(':', 1)
                    self.headers[name.lower()] = value.strip()

    def parse_uri(self, uri):
        uri_parts = str(uri).split('?', 1)
        self.page = uri_parts[0]
        self.page_args = uri_parts[1] if len(uri_parts) > 1 else None


class Response:

    NEWLINE = b'\r\n'
    server = SERVER_NAME

    request = None

    document_path = None
    content_type = None
    content = None
    content_length = 0
    code = None

    headers = {
        'Date': None,
        'Content-Type': None,
        'Content-Length': 0,
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache, private',
        'Server': 'my_web_server/1.0.0',
    }

    def __init__(self, document_path, request):
        self.document_path = document_path
        self.request = request
        self.content_type = self.get_mimetype(self.document_path)

    @staticmethod
    def get_mimetype(document_path):
        if document_path:
            file_ext = re.search('\.([^\.]+)$', document_path)
            if file_ext and str(file_ext.groups(0)[0]).lower() in MIMETYPES:
                return MIMETYPES[str(file_ext.groups(0)[0]).lower()]
        return MIMETYPES['txt']

    @staticmethod
    def get_content(document_path, request):
        if not document_path:
            return RESPONSE_CODE_404_NOT_FOUND, 10, 'Forbidden!'
        if request.method not in ALLOWED_METHODS:
            return RESPONSE_CODE_405_METHOD_NOT_ALLOWED, 25, 'Method not supported yet!'
        try:
            if request.method == METHOD_GET:
                with open(document_path, 'r') as f:
                    content = f.read(100000000)
                    length = len(content)
            if request.method == METHOD_HEAD:
                content = ''
                length = os.path.getsize(document_path)
            return RESPONSE_CODE_200_OK, length, content
        except (IOError, OSError, KeyError) as e:
            # print(e)
            msg = RESPONSE_CODE_MESSAGES[RESPONSE_CODE_404_NOT_FOUND]
            return RESPONSE_CODE_404_NOT_FOUND, len(msg), msg

    def prepare(self):
        self.code, self.content_length, self.content = self.get_content(self.document_path, self.request)
        self.headers['Date'] = datetime.datetime.now()
        self.headers['Content-Type'] = self.content_type
        self.headers['Content-Length'] = self.content_length

    def get_header(self):
        self.prepare()
        header = HTTP_VERSION + ' ' + str(self.code) + ' ' + RESPONSE_CODE_MESSAGES[self.code] + self.NEWLINE
        for name, value in self.headers.iteritems():
            header += name + ': ' + str(value) + self.NEWLINE
        header += self.NEWLINE
        print(header)
        print('Header size: %d bytes' % len(header))
        return header

    def get_response(self):
        response = self.get_header() + self.content
        return bytes(response)


class Server:

    name = SERVER_NAME
    document_root = None
    serversocket = None
    epoll = None

    connections = {}
    requests = {}
    responses = {}

    def __init__(self, server_addr, server_port, document_root):

        self.document_root = document_root

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.bind((server_addr, server_port))
        self.serversocket.listen(100)
        self.serversocket.setblocking(0)
        self.serversocket.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)

        self.epoll = select.epoll()
        self.epoll.register(self.serversocket.fileno(), select.EPOLLIN)

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

    def handle_recv(self, conn_fileno, fileno):
        self.requests[fileno] += self.connections[fileno].recv(1024)
        EOL1 = b'\n\n'
        EOL2 = b'\n\r\n'
        if EOL1 in self.requests[fileno] or EOL2 in self.requests[fileno]:
            req = self.requests[fileno]
            self.epoll.modify(fileno, select.EPOLLOUT)
            request_header_raw = req.decode()[:-2]
            print('-' * 40)
            print(request_header_raw)
            request = Request(request_header_raw)
            document_path = self.get_validated_document_path(request.page)
            self.responses[conn_fileno] = Response(document_path, request).get_response()

    def handle_send(self, fileno):
        bytessent = self.connections[fileno].send(self.responses[fileno])
        print('Sent total: %d bytes' % bytessent)
        self.responses[fileno] = self.responses[fileno][bytessent:]
        if len(self.responses[fileno]) == 0:
            self.epoll.modify(fileno, 0)
            self.connections[fileno].shutdown(socket.SHUT_RDWR)
            self.connections[fileno].close()

    def run(self):
        try:
            while True:
                events = self.epoll.poll(0.05)
                for fileno, event in events:
                    if fileno == self.serversocket.fileno():
                        conn_fileno = self.handle_new_connection()

                    elif event & select.EPOLLIN:
                        self.handle_recv(conn_fileno, fileno)

                    elif event & select.EPOLLOUT:
                        self.handle_send(fileno)

                    elif event & select.EPOLLHUP:
                        self.epoll.unregister(fileno)
                        self.connections[fileno].close()
                        del self.connections[fileno]
        finally:
            self.epoll.unregister(self.serversocket.fileno())
            self.epoll.close()
            self.serversocket.close()


if __name__ == '__main__':
    server = Server(SERVER_ADDR, SERVER_PORT, DOCUMENT_ROOT)
    server.run()
