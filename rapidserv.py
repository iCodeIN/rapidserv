""" 
"""

from untwisted.network import xmap, zmap, core, spawn
from untwisted.iostd import Stdin, Stdout, Server, DUMPED, lose, LOAD, ACCEPT, CLOSE
from untwisted.splits import AccUntil, TmpFile
from untwisted.timer import Timer
from untwisted.event import get_event
from untwisted.debug import on_event, on_all
from untwisted import network

import struct
# from collections import deque
import codecs
from urlparse import parse_qs
from cgi import FieldStorage
from tempfile import TemporaryFile as tmpfile

from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR, SO_KEEPALIVE
from os.path import getsize
from mimetypes import guess_type
from os.path import isfile, join, abspath, basename, dirname
from jinja2 import Template, FileSystemLoader, Environment
import argparse
import hashlib
import base64

OP_STREAM = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

HEADERB1 = 1
HEADERB2 = 3
LENGTHSHORT = 4
LENGTHLONG = 5
MASK = 6
PAYLOAD = 7

CONTROL_OPCODE = set([OP_CLOSE, OP_PING, OP_PONG, OP_BINARY, OP_STREAM])

import sys
VER = sys.version_info[0]

def _check_unicode(val):
    if VER >= 3:
        return isinstance(val, str)
    else:
        return isinstance(val, unicode)

class Headers(dict):
    def __init__(self, data):
        for ind in data:
            field, sep, value = ind.partition(':')
            self[field.lower()] = value.strip()

class Spin(network.Spin):
    def __init__(self, sock, app):
        network.Spin.__init__(self, sock)
        self.app      = app
        self.response = ''
        self.headers  = dict()
        self.data     = ''
        self.wsaccept = ''

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
        self.data = str(data)

    def handshake(self, request, protocol=''):
        """
        Do websocket handshake.
        """

        key    = request.headers['sec-websocket-key']
        GUID   = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        accept = base64.b64encode(hashlib.sha1('%s%s' % (key, GUID)).digest())

        self.set_response('HTTP/1.1 101 Switching Protocols')
        self.add_header(('Upgrade', 'websocket'), ('Connection', 'Keep-alive, Upgrade'), 
        # ('Sec-Websocket-Protocol', protocol),
        ('Sec-Websocket-version', '13'),
        ('Sec-Websocket-Accept', accept))
        WebSocket(self)

        self.send_headers()
        self.dump(self.data)
        self.data = ''
        self.headers.clear()

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
        for key, value in self.headers.iteritems():
            data = data + '\r\n' + '%s:%s' % (key, value)
        data = data + '\r\n\r\n'
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
        
        xmap(self.local, ACCEPT, self.handle_accept)

    def run(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-a', '--addr',  default='0.0.0.0', help='Address')
        parser.add_argument('-p', '--port', type=int, default=80, help='Port')
        parser.add_argument('-b', '--backlog',  type=int, default=50, help='Port')
        args = parser.parse_args()

        self.bind(args.addr, args.port, args.backlog)
        core.gear.mainloop()

    def handle_accept(self, local, spin):
        # spin.sock.setsockopt(SOL_SOCKET, SO_KEEPALIVE, 1)

        Stdin(spin)
        Stdout(spin)
        AccUntil(spin)
        TransferHandle(spin)
        RequestHandle(spin)
        MethodHandle(spin)

        # must be improved.
        # Locate(spin)

        # InvalidRequest(client)

        xmap(spin, CLOSE, lambda con, err: lose(con))

    def route(self, method):
        """
        """

        def shell(handle):
            xmap(self.local, ACCEPT, lambda local, spin: 
                 xmap(spin, method, self.build_kw, handle))
            return handle
        return shell

    def request(self, method):
        """
        """

        def shell(handle):
            xmap(self.local, ACCEPT, lambda local, spin: 
                 xmap(spin, method, handle))
            return handle
        return shell

    def build_kw(self, spin, request, handle):
        """
        """

        kwargs = dict()
        kwargs.update(request.query)

        if request.data: 
            kwargs.update(request.data)
        handle(spin, **kwargs)

    def accept(self, handle):
        xmap(self.local, ACCEPT, lambda local, spin: handle(spin))

    def overflow(self, handle):
        xmap(self.local, ACCEPT, lambda local, spin: 
                    xmap(spin, RequestHandle.OVERFLOW, handle))

class Request(object):
    def __init__(self, data):
        headers                              = data.split('\r\n')
        request                              = headers.pop(0)
        self.method, self.path, self.version = request.split(' ')
        self.headers                         = Headers(headers)
        self.fd                              = tmpfile('a+')
        self.data                            = None
        self.path, sep, self.query           = self.path.partition('?')
        self.query                           = parse_qs(self.query)

    def build_data(self):
        self.fd.seek(0)
        self.data = FieldStorage(fp=self.fd, environ=get_env(self.headers))

class TransferHandle(object):
    DONE = get_event()

    def __init__(self, spin):
        xmap(spin, AccUntil.DONE, lambda spin, request, data:
        spawn(spin, TransferHandle.DONE, Request(request), data))

class RequestHandle(object):
    DONE = get_event()
    OVERFLOW     = get_event()
    MAX_SIZE     = 1024 * 5024

    def __init__(self, spin):
        self.request = None
        xmap(spin, TransferHandle.DONE, self.process)

        # It will not be spawned if it is a websocket connection.
        xmap(spin, TmpFile.DONE,  
                   lambda spin, fd, data: spawn(spin, 
                                 RequestHandle.DONE, self.request))

    def process(self, spin, request, data):
        self.request = request
        contype      = request.headers.get('connection', '').lower()
        uptype       = request.headers.get('upgrade', '').lower()

        if  'upgrade' in contype or  'websocket' in uptype:
            spawn(spin, RequestHandle.DONE, request)
        else:
            self.accumulate(spin, data)

    def accumulate(self, spin, data):
        size = int(self.request.headers.get('content-length', '0'))

        NonPersistentConnection(spin)
        # PersistentConnection(spin)

        if RequestHandle.MAX_SIZE <= size:
            spawn(spin, RequestHandle.OVERFLOW, self.request)
        else:
            TmpFile(spin, data, size, self.request.fd)


class MethodHandle(object):
    def __init__(self, spin):
        xmap(spin, RequestHandle.DONE, self.process)

    def process(self, spin, request):
        request.build_data()
        spawn(spin, request.method, request)
        spawn(spin, '%s %s' % (request.method, request.path), request)
        spin.dump('')

class NonPersistentConnection(object):
    def __init__(self, spin):
        xmap(spin, DUMPED, lambda con: lose(con))

class PersistentConnection(object):
    TIMEOUT = 10
    MAX     = 10

    def __init__(self, spin):
        self.timer = Timer(PersistentConnection.TIMEOUT, lambda: lose(spin))
        self.count = 0
        xmap(spin, TmpFile.DONE, self.process)
        xmap(spin, DUMPED, self.install_timeout)

        xmap(spin, TransferHandle.DONE, 
        lambda spin, request, data: self.timer.cancel())

        spin.add_header(('connection', 'keep-alive'))
        spin.add_header(('keep-alive', 'timeout=%s, max=%s' % (
        PersistentConnection.TIMEOUT, PersistentConnection.MAX)))

    def process(self, spin, fd, data):
        self.count = self.count + 1

        if self.count < PersistentConnection.MAX:
            AccUntil(spin, data)

    def install_timeout(self, spin):
        self.timer = Timer(PersistentConnection.TIMEOUT, lambda: lose(spin))

class DebugRequest(object):
    def __init__(self, spin):
        xmap(spin, RequestHandle.DONE, self.process)

    def process(self, spin, request):
        print request.method
        print request.path
        print request.data
        print request.headers

class InvalidRequest(object):
    """ 
    """

    def __init__(self, spin):
        # xmap(spin, INVALID_BODY_SIZE, self.error)
        # xmap(spin, IDLE_TIMEOUT, self.error)
        pass

    def error(self, spin):
        spin.set_response('HTTP/1.1 400 Bad request')
        HTML = '<html> <body> <h1> Bad request </h1> </body> </html>'
        spin.add_data(HTML)
        spin.done()

class Locate(object):
    """
    """

    def __init__(self, spin):
        xmap(spin, 'GET', self.locate)

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
        xmap(spin, OPEN_FILE_ERR, lambda con, err: lose(con))
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


OPEN_FILE_ERR = get_event()
def drop(spin, filename):
    """
    Shouldn't be called outside this module.
    """

    try:
        fd = open(filename, 'rb')             
    except IOError as excpt:
        err = excpt.args[0]
        spawn(spin, OPEN_FILE_ERR, err)
    else:
        spin.dumpfile(fd)

def make(searchpath, folder):
    """
    Used to build a path search for Locate plugin.
    """

    from os.path import join, abspath, dirname
    searchpath = join(dirname(abspath(searchpath)), folder)
    return searchpath


# Below https://github.com/dpallot/simple-websocket-server is used,
# It was The MIT License ()

# TODO: Make them hidden
STREAM = 0x0
TEXT = 0x1
BINARY = 0x2
CLOSE = 0x8
PING = 0x9
PONG = 0xA

HEADERB1 = 1
HEADERB2 = 3
LENGTHSHORT = 4
LENGTHLONG = 5
MASK = 6
PAYLOAD = 7

MAXHEADER = 65536
MAXPAYLOAD = 33554432

_VALID_STATUS_CODES = [1000, 1001, 1002, 1003, 1007, 1008,
                        1009, 1010, 1011, 3000, 3999, 4000, 4999]

class WebSocket(object):
    TEXT = get_event()
    BINARY = get_event()

    def __init__(self, spin):
        self.spin = spin

        # self.handshaked = False
        self.headerbuffer = bytearray()

        self.fin = 0
        self.data = bytearray()
        self.opcode = 0
        self.hasmask = 0
        self.maskarray = None
        self.length = 0
        self.lengtharray = None
        self.index = 0
        self.request = None
        self.usingssl = False

        self.frag_start = False
        self.frag_type = BINARY
        self.frag_buffer = None
        self.frag_decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
        self.closed = False
        # self.sendq = deque()

        self.state = HEADERB1

        # restrict the size of header and payload for security reasons
        # self.maxheader = MAXHEADER  # not used
        self.maxpayload = MAXPAYLOAD

        # spin.add_map(LOAD, self.decode)
        spin.wsdump = self.wsdump  # hack?

        spin.add_map(LOAD, self._handleData)

    def _handlePacket(self):
        if self.opcode == CLOSE:
            pass
        elif self.opcode == STREAM:
            pass
        elif self.opcode == TEXT:
            pass
        elif self.opcode == BINARY:
            pass
        elif self.opcode == PONG or self.opcode == PING:
            if len(self.data) > 125:
                raise Exception('control frame length can not be > 125')
        else:
            # unknown or reserved opcode so just close
            raise Exception('unknown opcode')

        if self.opcode == CLOSE:
            status = 1000
            reason = u''
            length = len(self.data)

            if length == 0:
                pass
            elif length >= 2:
                status = struct.unpack_from('!H', self.data[:2])[0]
                reason = self.data[2:]

                if status not in _VALID_STATUS_CODES:
                    status = 1002

                if len(reason) > 0:
                    try:
                        reason = reason.decode('utf8', errors='strict')
                    except:
                        status = 1002
            else:
                status = 1002

            self.close(status, reason)
            return

        elif self.fin == 0:
            if self.opcode != STREAM:
                if self.opcode == PING or self.opcode == PONG:
                    raise Exception('control messages can not be fragmented')

                self.frag_type = self.opcode
                self.frag_start = True
                self.frag_decoder.reset()

                if self.frag_type == TEXT:
                    self.frag_buffer = []
                    utf_str = self.frag_decoder.decode(self.data, final=False)
                    if utf_str:
                        self.frag_buffer.append(utf_str)
                else:
                    self.frag_buffer = bytearray()
                    self.frag_buffer.extend(self.data)

            else:
                if self.frag_start is False:
                    raise Exception('fragmentation protocol error')

                if self.frag_type == TEXT:
                    utf_str = self.frag_decoder.decode(self.data, final=False)
                    if utf_str:
                        self.frag_buffer.append(utf_str)
                else:
                    self.frag_buffer.extend(self.data)

        else:
            if self.opcode == STREAM:
                if self.frag_start is False:
                    raise Exception('fragmentation protocol error')

                if self.frag_type == TEXT:
                    utf_str = self.frag_decoder.decode(self.data, final=True)
                    self.frag_buffer.append(utf_str)
                    self.data = u''.join(self.frag_buffer)
                else:
                    self.frag_buffer.extend(self.data)
                    self.data = self.frag_buffer

                self.handleMessage()

                self.frag_decoder.reset()
                self.frag_type = BINARY
                self.frag_start = False
                self.frag_buffer = None

            elif self.opcode == PING:
                self._sendMessage(False, PONG, self.data)

            elif self.opcode == PONG:
                pass

            else:
                if self.frag_start is True:
                    raise Exception('fragmentation protocol error')

                if self.opcode == TEXT:
                    try:
                        self.data = self.data.decode('utf8', errors='strict')
                    except Exception as exp:
                        raise Exception('invalid utf-8 payload')

                # self.handleMessage()
                if self.opcode == TEXT:
                    self.spin.drive(self.TEXT, self.data)
                elif self.opcode == BINARY:
                    self.spin.drive(self.BINARY, self.data)

    def _handleData(self, spin, data):
        # data = self.client.recv(16384)
        if not data:
            raise Exception("remote socket closed")

        if VER >= 3:
            for d in data:
                self._parseMessage(d)
        else:
            for d in data:
                self._parseMessage(ord(d))

    def close(self, status=1000, reason=u''):
        """
           Send Close frame to the client. The underlying socket is only closed
           when the client acknowledges the Close frame.
           status is the closing identifier.
           reason is the reason for the close.
         """
        try:
            if self.closed is False:
                close_msg = bytearray()
                close_msg.extend(struct.pack("!H", status))
                if _check_unicode(reason):
                    close_msg.extend(reason.encode('utf-8'))
                else:
                    close_msg.extend(reason)

                self._sendMessage(False, CLOSE, close_msg)

        finally:
            self.closed = True

    # def _sendBuffer(self, buff, send_all=False):
    #     size = len(buff)
    #     tosend = size
    #     already_sent = 0
    #
    #     while tosend > 0:
    #         try:
    #             # i should be able to send a bytearray
    #             sent = self.client.send(buff[already_sent:])
    #             if sent == 0:
    #                 raise RuntimeError('socket connection broken')
    #
    #             already_sent += sent
    #             tosend -= sent
    #
    #         except socket.error as e:
    #             # if we have full buffers then wait for them to drain and try again
    #             if e.errno in [errno.EAGAIN, errno.EWOULDBLOCK]:
    #                 if send_all:
    #                     continue
    #                 return buff[already_sent:]
    #             else:
    #                 raise e
    #
    #     return None

    def sendFragmentStart(self, data):
        """
            Send the start of a data fragment stream to a websocket client.
            Subsequent data should be sent using sendFragment().
            A fragment stream is completed when sendFragmentEnd() is called.
            If data is a unicode object then the frame is sent as Text.
            If the data is a bytearray object then the frame is sent as Binary.
        """
        opcode = BINARY
        if _check_unicode(data):
            opcode = TEXT
        self._sendMessage(True, opcode, data)

    def sendFragment(self, data):
        """
            see sendFragmentStart()
            If data is a unicode object then the frame is sent as Text.
            If the data is a bytearray object then the frame is sent as Binary.
        """
        self._sendMessage(True, STREAM, data)

    def sendFragmentEnd(self, data):
        """
            see sendFragmentEnd()
            If data is a unicode object then the frame is sent as Text.
            If the data is a bytearray object then the frame is sent as Binary.
        """
        self._sendMessage(False, STREAM, data)

    def sendMessage(self, data):
        """
            Send websocket data frame to the client.
            If data is a unicode object then the frame is sent as Text.
            If the data is a bytearray object then the frame is sent as Binary.
        """
        opcode = BINARY
        if _check_unicode(data):
            opcode = TEXT
        self._sendMessage(False, opcode, data)

    # TODO
    def wsdump(self, data):
        self.sendMessage(data)

    def _sendMessage(self, fin, opcode, data):

        payload = bytearray()

        b1 = 0
        b2 = 0
        if fin is False:
            b1 |= 0x80
        b1 |= opcode

        if _check_unicode(data):
            data = data.encode('utf-8')

        length = len(data)
        payload.append(b1)

        if length <= 125:
            b2 |= length
            payload.append(b2)

        elif length >= 126 and length <= 65535:
            b2 |= 126
            payload.append(b2)
            payload.extend(struct.pack("!H", length))

        else:
            b2 |= 127
            payload.append(b2)
            payload.extend(struct.pack("!Q", length))

        if length > 0:
            payload.extend(data)

        # self.sendq.append((opcode, payload))
        # payload[:0] = chr(opcode)
        self.spin.dump(payload)

    def _parseMessage(self, byte):
        # read in the header
        if self.state == HEADERB1:

            self.fin = byte & 0x80
            self.opcode = byte & 0x0F
            self.state = HEADERB2

            self.index = 0
            self.length = 0
            self.lengtharray = bytearray()
            self.data = bytearray()

            rsv = byte & 0x70
            if rsv != 0:
                raise Exception('RSV bit must be 0')

        elif self.state == HEADERB2:
            mask = byte & 0x80
            length = byte & 0x7F

            if self.opcode == PING and length > 125:
                raise Exception('ping packet is too large')

            if mask == 128:
                self.hasmask = True
            else:
                self.hasmask = False

            if length <= 125:
                self.length = length

                # if we have a mask we must read it
                if self.hasmask is True:
                    self.maskarray = bytearray()
                    self.state = MASK
                else:
                    # if there is no mask and no payload we are done
                    if self.length <= 0:
                        try:
                            self._handlePacket()
                        finally:
                            self.state = HEADERB1
                            self.data = bytearray()

                    # we have no mask and some payload
                    else:
                        # self.index = 0
                        self.data = bytearray()
                        self.state = PAYLOAD

            elif length == 126:
                self.lengtharray = bytearray()
                self.state = LENGTHSHORT

            elif length == 127:
                self.lengtharray = bytearray()
                self.state = LENGTHLONG


        elif self.state == LENGTHSHORT:
            self.lengtharray.append(byte)

            if len(self.lengtharray) > 2:
                raise Exception('short length exceeded allowable size')

            if len(self.lengtharray) == 2:
                self.length = struct.unpack_from('!H', self.lengtharray)[0]

                if self.hasmask is True:
                    self.maskarray = bytearray()
                    self.state = MASK
                else:
                    # if there is no mask and no payload we are done
                    if self.length <= 0:
                        try:
                            self._handlePacket()
                        finally:
                            self.state = HEADERB1
                            self.data = bytearray()

                    # we have no mask and some payload
                    else:
                        # self.index = 0
                        self.data = bytearray()
                        self.state = PAYLOAD

        elif self.state == LENGTHLONG:

            self.lengtharray.append(byte)

            if len(self.lengtharray) > 8:
                raise Exception('long length exceeded allowable size')

            if len(self.lengtharray) == 8:
                self.length = struct.unpack_from('!Q', self.lengtharray)[0]

                if self.hasmask is True:
                    self.maskarray = bytearray()
                    self.state = MASK
                else:
                    # if there is no mask and no payload we are done
                    if self.length <= 0:
                        try:
                            self._handlePacket()
                        finally:
                            self.state = HEADERB1
                            self.data = bytearray()

                    # we have no mask and some payload
                    else:
                        # self.index = 0
                        self.data = bytearray()
                        self.state = PAYLOAD

        # MASK STATE
        elif self.state == MASK:
            self.maskarray.append(byte)

            if len(self.maskarray) > 4:
                raise Exception('mask exceeded allowable size')

            if len(self.maskarray) == 4:
                # if there is no mask and no payload we are done
                if self.length <= 0:
                    try:
                        self._handlePacket()
                    finally:
                        self.state = HEADERB1
                        self.data = bytearray()

                # we have no mask and some payload
                else:
                    # self.index = 0
                    self.data = bytearray()
                    self.state = PAYLOAD

        # PAYLOAD STATE
        elif self.state == PAYLOAD:
            if self.hasmask is True:
                self.data.append(byte ^ self.maskarray[self.index % 4])
            else:
                self.data.append(byte)

            # if length exceeds allowable size then we except and remove the connection
            if len(self.data) >= self.maxpayload:
                raise Exception('payload exceeded allowable size')

            # check if we have processed length bytes; if so we are done
            if (self.index + 1) == self.length:
                try:
                    self._handlePacket()
                finally:
                    # self.index = 0
                    self.state = HEADERB1
                    self.data = bytearray()
            else:
                self.index += 1

    # def calc_mask_pos(self, value):
    #     size = value & 127
    #     if size == 126:
    #         return 4
    #     elif size == 127:
    #         return 10
    #     else:
    #         return 2
    #
    # def decode(self, spin, data):
    #     # Spawns LOAD only if it is a text message.
    #     if ord(data[0]) & 0xF == OP_TEXT:
    #         spin.drive(self.LOAD, self.build_msg(data))
    #
    # def build_msg(self, data):
    #     arr0  = [ord(ind) for ind in data]
    #     pos   = self.calc_mask_pos(arr0[1])
    #     arr1  = []
    #     masks = [m for m in arr0[pos : pos+4]]
    #
    #     indj  = 0
    #     seq0  = xrange(pos + 4, len(arr0))
    #     seq1  = xrange(0, len(arr0))
    #
    #     for indi, indj in zip(seq0, seq1):
    #         arr1.append(chr(arr0[indi] ^ masks[indj % 4]))
    #     return ''.join(arr1)
    #
    # def calc_payload(self, size):
    #     if size < 126:
    #         return chr(0 | size)
    #     elif size < (2 ** 16) - 1:
    #         return chr(0 | 126) + struct.pack(">H", size)
    #     else:
    #         return chr(0 | 127) + struct.pack(">Q", size)
    #
    # def wsdump(self, payload):
    #     """
    #     """
    #
    #     # Send an entire message as one frame.
    #     # Append 'FIN' flag to the message.
    #     fin = chr(0x80 |0x01)
    #
    #     size = self.calc_payload(len(payload))
    #     self.spin.dump('%s%s%s' % (fin, size, payload))
    



