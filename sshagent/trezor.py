import io
import binascii

from trezorlib.client import TrezorClient
from trezorlib.transport_hid import HidTransport
from trezorlib.types_pb2 import IdentityType

from . import util
from . import formats

import logging
log = logging.getLogger(__name__)


class Client(object):

    def __init__(self):
        devices = HidTransport.enumerate()
        if len(devices) != 1:
            raise ValueError('{:d} Trezor devices found'.format(len(devices)))
        client = TrezorClient(HidTransport(devices[0]))
        f = client.features
        log.info('connected to Trezor')
        log.debug('ID       : %s', f.device_id)
        log.debug('label    : %s', f.label)
        log.debug('vendor   : %s', f.vendor)
        version = [f.major_version, f.minor_version, f.patch_version]
        log.debug('version  : %s', '.'.join([str(v) for v in version]))
        log.debug('revision : %s', binascii.hexlify(f.revision))
        self.client = client

    def close(self):
        self.client.close()

    def get_public_key(self, label):
        addr = _get_address(_get_identity(label))
        log.info('getting %r SSH public key from Trezor...', label)
        node = self.client.get_public_node(addr)
        return node.node.public_key

    def sign_ssh_challenge(self, label, blob):
        ident = _get_identity(label)
        msg = _parse_ssh_blob(blob)
        request = 'user: "{user}"'.format(**msg)

        log.info('confirm %s connection to %r using Trezor...',
                 request, label)
        s = self.client.sign_identity(identity=ident,
                                      challenge_hidden=blob,
                                      challenge_visual=request)
        assert len(s.signature) == 65
        assert s.signature[0] == b'\x00'

        sig = s.signature[1:]
        r = util.bytes2num(sig[:32])
        s = util.bytes2num(sig[32:])
        return (r, s)


def _get_identity(label, proto='ssh'):
    return IdentityType(host=label, proto=proto)


def _get_address(ident):
    index = '\x00' * 4
    addr = index + '{}://{}'.format(ident.proto, ident.host)
    digest = formats.hashfunc(addr).digest()
    s = io.BytesIO(bytearray(digest))

    address_n = [22] + list(util.recv(s, '<LLLL'))
    return [-a for a in address_n]  # prime each address component


def _parse_ssh_blob(data):
    res = {}
    if data:
        i = io.BytesIO(data)
        res['nonce'] = util.read_frame(i)
        i.read(1)  # TBD
        res['user'] = util.read_frame(i)
        res['conn'] = util.read_frame(i)
        res['auth'] = util.read_frame(i)
        i.read(1)  # TBD
        res['key_type'] = util.read_frame(i)
        res['pubkey'] = util.read_frame(i)
        log.debug('%s: user %r via %r (%r)',
                  res['conn'], res['user'], res['auth'], res['key_type'])
    return res
