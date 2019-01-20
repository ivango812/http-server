# -*- coding: utf-8 -*-
import os
import re
import urllib
import logging
import datetime


SERVER_NAME = 'http-server 1.0.0'
HTTP_VERSION = 'HTTP/1.1'

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
        # 'Connection': 'keep-alive',
        'Connection': 'close',
        # 'Cache-Control': 'no-cache, private',
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
            msg = RESPONSE_CODE_MESSAGES[RESPONSE_CODE_404_NOT_FOUND]
            return RESPONSE_CODE_404_NOT_FOUND, len(msg), msg

    def prepare(self):
        self.code, self.content_length, self.content = self.get_content(self.document_path, self.request)
        self.headers['Date'] = datetime.datetime.strftime(datetime.datetime.now(), "%a, %d %b %Y %H:%M:%S")
        self.headers['Content-Type'] = self.content_type
        self.headers['Content-Length'] = self.content_length

    def get_header(self):
        self.prepare()
        header = HTTP_VERSION + ' ' + str(self.code) + ' ' + RESPONSE_CODE_MESSAGES[self.code] + self.NEWLINE
        for name, value in self.headers.iteritems():
            header += name + ': ' + str(value) + self.NEWLINE
        header += self.NEWLINE
        logging.debug(header)
        logging.debug('Header size: %d bytes' % len(header))
        return header

    def get_response(self):
        response = self.get_header() + self.content
        return bytes(response)
