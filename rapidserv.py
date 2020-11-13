""" 
"""

from untwisted.sock_writer import SockWriter
from untwisted.sock_reader import SockReader
from untwisted.client import lose
from untwisted.server import Server
from untwisted.event import ACCEPT, CLOSE, DUMPED, Event
from untwisted import core
from untwisted.splits import AccUntil, TmpFile
from untwisted import network

from urllib.parse import parse_qs
from cgi import FieldStorage, parse_header
from tempfile import TemporaryFile as tmpfile

from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from os.path import getsize
from mimetypes import guess_type
from os.path import isfile, join, abspath, basename, dirname
from jinja2 import FileSystemLoader, Environment
import argparse

class Headers(dict):
    def __init__(self, data):
        for ind in data:
            field, sep, value = ind.partition(':')
            self[field.lower()] = value

class Spin(network.Spin):
    def __init__(self, sock, app):
        network.Spin.__init__(self, sock)
        self.app      = app
        self.response = ''
        self.headers  = dict()
        self.data     = b''

        self.add_default_headers()

    def add_default_headers(self):
        self.set_response('HTTP/1.1 200 OK')
        self.add_header(('Server', 'Rapidserv'))

    def set_response(self, data):
        self.response = data

    def add_header(self, *args):
        for key, value in args:
            self.headers[str(key).lower()] = str(value)

    def add_data(self, data, mimetype='text/html;charset=utf-8'):
        self.add_header(('Content-Type', mimetype))
        mimetype, options = parse_header(mimetype)

        try:
            charset = options['charset']
        except KeyError:
            self.data = data
        else:
            self.data = data.encode()
        
    def done(self):
        self.headers['Content-Length'] = len(self.data)
        self.send_headers()
        self.dump(self.data)
        self.data = ''
        self.headers.clear()
        self.add_default_headers()

    def send_headers(self):
        """
        """

        data = self.response
        for key, value in self.headers.items():
            data = data + '\r\n' + '%s:%s' % (key, value)
        data = data + '\r\n\r\n'
        data = data.encode('ascii')
        self.dump(data)

    def render(self, template_name, *args, **kwargs):
        template = self.app.env.get_template(template_name)
        self.add_data(template.render(*args, **kwargs))

class RapidServ(object):
    """
    """

    def __init__(self, app_dir, static_dir='static', template_dir='templates', auto_reload=True):
        self.app_dir      = dirname(abspath(app_dir))
        self.static_dir   = static_dir
        self.template_dir = template_dir
        self.loader       = FileSystemLoader(searchpath = join(self.app_dir, self.template_dir))
        self.env          = Environment(loader=self.loader, auto_reload=auto_reload)
        sock              = socket(AF_INET, SOCK_STREAM)
        self.local        = network.Spin(sock)
        self.local.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)


    def bind(self, addr, port, backlog):
        Server(self.local, lambda sock: Spin(sock, self)) 
        self.local.bind((addr, port))
        self.local.listen(backlog)
        
        self.local.add_map(ACCEPT, self.handle_accept)

    def run(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-a', '--addr',  default='0.0.0.0', help='Address')
        parser.add_argument('-p', '--port', type=int, default=80, help='Port')
        parser.add_argument('-b', '--backlog',  type=int, default=50, help='Port')
        args = parser.parse_args()

        self.bind(args.addr, args.port, args.backlog)
        core.gear.mainloop()

    def handle_accept(self, local, spin):
        SockWriter(spin)
        SockReader(spin)
        AccUntil(spin)
        TransferHandle(spin)
        RequestHandle(spin)
        MethodHandle(spin)

        # must be improved.
        Locate(spin)

        # InvalidRequest(client)

        spin.add_map(CLOSE, lambda con, err: lose(con))

    def request(self, method):
        """
        """

        def shell(handle):
            self.local.add_map(ACCEPT, lambda local, spin: 
                 spin.add_map(method, handle))
            return handle
        return shell

    def accept(self, handle):
        self.local.add_map(ACCEPT, lambda local, spin: handle(spin))

    def overflow(self, handle):
        self.local.add_map(ACCEPT, lambda local, spin: 
                    spin.add_map(RequestHandle.OVERFLOW, handle))

class Request(object):
    def __init__(self, data):
        headers                              = data.decode('ascii').split('\r\n')
        request                              = headers.pop(0)
        self.method, self.path, self.version = request.split(' ')
        self.headers                         = Headers(headers)
        self.fd                              = tmpfile('a+b')
        self.data                            = None
        self.path, sep, self.query           = self.path.partition('?')
        self.query                           = parse_qs(self.query)

    def build_data(self):
        self.fd.seek(0)
        self.data = FieldStorage(fp=self.fd, environ=get_env(self.headers))

class TransferHandle(object):
    class DONE(Event):
        pass

    def __init__(self, spin):
        spin.add_map(AccUntil.DONE, lambda spin, request, data:
        spin.drive(TransferHandle.DONE, Request(request), data))

class RequestHandle(object):
    class DONE(Event):
        pass

    class OVERFLOW(Event):
        pass

    MAX_SIZE     = 1024 * 5024
    def __init__(self, spin):
        self.request = None
        spin.add_map(TransferHandle.DONE, self.process)

        # It will not be spawned if it is a websocket connection.
        spin.add_map(TmpFile.DONE,  
                   lambda spin, fd, data: spin.drive(
                                 RequestHandle.DONE, self.request))

    def process(self, spin, request, data):
        self.request = request
        contype      = request.headers.get('connection', '').lower()
        uptype       = request.headers.get('upgrade', '').lower()

        if contype == 'upgrade' and uptype == 'websocket':
            spin.drive(RequestHandle.DONE, request)
        else:
            self.accumulate(spin, data)

    def accumulate(self, spin, data):
        size = int(self.request.headers.get('content-length', '0'))

        NonPersistentConnection(spin)

        if RequestHandle.MAX_SIZE <= size:
            spin.drive(RequestHandle.OVERFLOW, self.request)
        else:
            TmpFile(spin, data, size, self.request.fd)


class MethodHandle(object):
    def __init__(self, spin):
        spin.add_map(RequestHandle.DONE, self.process)

    def process(self, spin, request):
        request.build_data()
        spin.drive(request.method, request)
        spin.drive('%s %s' % (request.method, request.path), request)
        # When there is no route found it is necessary to spawn DUMPED
        # anyway otherwise we dont get the connection closed. 
        # The browser will remain waiting for the service response.
        spin.dump(b'')

class NonPersistentConnection(object):
    def __init__(self, spin):
        spin.add_map(DUMPED, lambda con: lose(con))

class DebugRequest(object):
    def __init__(self, spin):
        spin.add_map(RequestHandle.DONE, self.process)

    def process(self, spin, request):
        print(request.method)
        print(request.path)
        print(request.data)
        print(request.headers)

class Locate(object):
    """
    """

    def __init__(self, spin):
        spin.add_map('GET', self.locate)

    def locate(self, spin, request):
        path = join(spin.app.app_dir, spin.app.static_dir, basename(request.path))
        if not isfile(path):
            return

        # Where we are going to serve files.
        # I might spawn an event like FILE_NOT_FOUND.
        # So, users could use it to send appropriate answers.
        type_file, encoding = guess_type(path)
        default_type = 'application/octet-stream'

        spin.add_header(('Content-Type', type_file if type_file else default_type),
                     ('Content-Length', getsize(path)))

        spin.send_headers()
        spin.add_map(OPEN_FILE_ERR, lambda con, err: lose(con))
        drop(spin, path)

def get_env(header):
    """
    Shouldn't be called outside this module.
    """

    environ = {
                'REQUEST_METHOD':'POST',
                'CONTENT_LENGTH':header.get('content-length', 0),
                'CONTENT_TYPE':header.get('content-type', 'text')
              }

    return environ


class OPEN_FILE_ERR(Event):
    pass

def drop(spin, filename):
    """
    Shouldn't be called outside this module.
    """

    try:
        fd = open(filename, 'rb')             
    except IOError as excpt:
        err = excpt.args[0]
        spin.drive(OPEN_FILE_ERR, err)
    else:
        spin.dumpfile(fd)

def make(searchpath, folder):
    """
    Used to build a path search for Locate plugin.
    """

    from os.path import join, abspath, dirname
    searchpath = join(dirname(abspath(searchpath)), folder)
    return searchpath


