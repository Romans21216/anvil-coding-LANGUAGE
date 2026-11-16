"""Demand-emitted nonblocking IPv4 UDP helpers using the Win64 Winsock ABI."""

import ipaddress
import json
import struct
from compiler.expressions import split_args


class NativeNetwork:
    def __init__(self,owner):
        self.owner=owner;self.code=owner.code;self.active=False;self.requests=set()

    def ensure(self,request):
        self.requests.add(request)
        if self.active:return
        self.active=True
        for name,payload in [('socket',b'\xff'*8),('started',b'\0'*8),('has_peer',b'\0'*8),
                             ('bind_ip',b'\0'*8),('local',b'\0'*16),('peer',b'\0'*16),
                             ('from_address',b'\0'*16),('received',b'\0'*16),
                             ('value',b'\0'*8),('sending',b'\0'*8)]:
            setattr(self,name,self.owner.reserve_data(payload))

    def frame(self,label,size):
        self.code.label('network:'+label)
        self.code.bytes(b'\x48\x81\xec'+struct.pack('<I',size))

    def ret(self,size):
        self.code.bytes(b'\x48\x81\xc4'+struct.pack('<I',size)+b'\xc3')

    def zero_flag(self,offset):
        self.code.mov_imm(0,0);self.code.rip_int(0,offset,store=True)

    def check_result(self,node,message):
        done=self.owner.label('network_success')
        self.code.bytes(b'\x85\xc0');self.code.conditional_jump(0x85,done)
        self.owner.emit_runtime_error(f'{node.source or self.owner.path}:{node.line}: {message}\n')
        self.code.label(done)

    @staticmethod
    def address_header(address,port):
        return int.from_bytes(struct.pack('<H',2)+struct.pack('>H',port)+ipaddress.IPv4Address(address).packed,'little')

    def emit_node(self,node,scope):
        c=self.code
        if node.kind=='net_ip':
            self.ensure('config')
            c.mov_imm(0,int.from_bytes(ipaddress.IPv4Address(node.value).packed,'little'))
            c.rip_int(0,self.bind_ip,store=True)
        elif node.kind=='net_host':
            self.ensure('host')
            c.mov_imm(1,self.address_header('0.0.0.0',int(node.value)))
            c.mov_imm(2,int(node.params==['local']))
            c.call('network:host');self.check_result(node,'unable to host UDP socket')
        elif node.kind=='net_join':
            self.ensure('join')
            address,port=split_args(node.value)
            c.mov_imm(1,self.address_header(json.loads(address),int(port)))
            c.call('network:join');self.check_result(node,'unable to join UDP peer')
        elif node.kind=='net_send':
            self.ensure('send')
            self.owner.emit_expression(node.value,node.line,scope)
            self.owner.emit_finite_check(node.line)
            c.rip_store_data(0,self.sending);c.call('network:send')
        elif node.kind=='net_leave':
            self.ensure('cleanup');c.call('network:cleanup')

    def receive(self,line):
        self.ensure('receive')
        self.code.call('network:receive')
        self.owner.emit_finite_check(line)

    @property
    def imports(self):
        if not self.active:return []
        names={'closesocket','WSACleanup'}
        if self.requests & {'host','join'}:names.update(('WSAStartup','socket','ioctlsocket'))
        if 'host' in self.requests:names.add('bind')
        if 'receive' in self.requests:names.add('recvfrom')
        if 'send' in self.requests:names.add('sendto')
        return [('WS2_32.dll',name) for name in sorted(names)]

    def emit(self):
        if not self.active:return
        c=self.code
        self.frame('close_socket',0x28)
        done=self.owner.label('socket_closed')
        c.rip_int(1,self.socket);c.bytes(b'\x48\x83\xf9\xff');c.conditional_jump(0x84,done)
        c.rip_call_import('closesocket')
        c.label(done);c.mov_imm(0,-1);c.rip_int(0,self.socket,store=True)
        self.zero_flag(self.has_peer);self.ret(0x28)
        self.frame('cleanup',0x28)
        c.call('network:close_socket')
        done=self.owner.label('winsock_closed')
        c.rip_int(0,self.started);c.bytes(b'\x48\x85\xc0');c.conditional_jump(0x84,done)
        c.rip_call_import('WSACleanup');self.zero_flag(self.started)
        c.label(done);self.ret(0x28)
        if self.requests & {'host','join'}:self.emit_open()
        if 'host' in self.requests:self.emit_host()
        if 'join' in self.requests:self.emit_join()
        if 'receive' in self.requests:self.emit_receive()
        if 'send' in self.requests:self.emit_send()

    def emit_open(self):
        c=self.code
        self.frame('ready',0x1C8)
        done=self.owner.label('winsock_ready');failed=self.owner.label('winsock_failed')
        c.rip_int(0,self.started);c.bytes(b'\x48\x85\xc0');c.conditional_jump(0x85,done)
        c.mov_imm(1,0x202);c.stack_int(2,0x20,address=True)
        c.rip_call_import('WSAStartup');c.bytes(b'\x85\xc0');c.conditional_jump(0x85,failed)
        c.mov_imm(0,1);c.rip_int(0,self.started,store=True)
        c.label(done);c.mov_imm(0,1);self.ret(0x1C8)
        c.label(failed);c.mov_imm(0,0);self.ret(0x1C8)
        self.frame('open',0x38)
        failed=self.owner.label('socket_open_failed');io_failed=self.owner.label('socket_ioctl_failed')
        c.call('network:close_socket');c.call('network:ready')
        c.bytes(b'\x85\xc0');c.conditional_jump(0x84,failed)
        c.mov_imm(1,2);c.mov_imm(2,2);c.mov_imm(8,17);c.rip_call_import('socket')
        c.bytes(b'\x48\x83\xf8\xff');c.conditional_jump(0x84,failed)
        c.rip_int(0,self.socket,store=True);c.mov_reg(1,0)
        c.mov_imm(0,1);c.stack_int(0,0x20,store=True)
        c.mov_imm(2,0x8004667E);c.stack_int(8,0x20,address=True)
        c.rip_call_import('ioctlsocket');c.bytes(b'\x85\xc0');c.conditional_jump(0x85,io_failed)
        c.mov_imm(0,1);self.ret(0x38)
        c.label(io_failed);c.call('network:close_socket')
        c.label(failed);c.mov_imm(0,0);self.ret(0x38)

    def emit_host(self):
        c=self.code;self.frame('host',0x68)
        failed=self.owner.label('host_failed');bind_failed=self.owner.label('bind_failed');configured=self.owner.label('bind_configured')
        c.stack_int(1,0x50,store=True);c.stack_int(2,0x58,store=True)
        c.call('network:open');c.bytes(b'\x85\xc0');c.conditional_jump(0x84,failed)
        c.rip_int(2,self.bind_ip);c.stack_int(0,0x58);c.bytes(b'\x48\x85\xc0');c.conditional_jump(0x84,configured)
        c.mov_imm(2,0x0100007F)
        c.label(configured);c.bytes(b'\x48\xc1\xe2\x20');c.stack_int(0,0x50);c.bytes(b'\x48\x09\xd0')
        c.rip_int(0,self.local,store=True)
        c.rip_int(1,self.socket);c.rip_lea_data(2,self.local);c.mov_imm(8,16)
        c.rip_call_import('bind');c.bytes(b'\x85\xc0');c.conditional_jump(0x85,bind_failed)
        c.mov_imm(0,1);self.ret(0x68)
        c.label(bind_failed);c.call('network:close_socket')
        c.label(failed);c.mov_imm(0,0);self.ret(0x68)

    def emit_join(self):
        c=self.code;self.frame('join',0x38)
        failed=self.owner.label('join_failed')
        c.stack_int(1,0x20,store=True);c.call('network:open')
        c.bytes(b'\x85\xc0');c.conditional_jump(0x84,failed)
        c.stack_int(0,0x20);c.rip_int(0,self.peer,store=True)
        self.zero_flag(self.peer+8)
        c.mov_imm(0,1);c.rip_int(0,self.has_peer,store=True);self.ret(0x38)
        c.label(failed);c.mov_imm(0,0);self.ret(0x38)

    def emit_receive(self):
        c=self.code;self.frame('receive',0x68)
        done=self.owner.label('receive_done');peer_known=self.owner.label('receive_peer_known')
        c.rip_int(1,self.socket);c.bytes(b'\x48\x83\xf9\xff');c.conditional_jump(0x84,done)
        c.mov_imm(0,16);c.stack_int(0,0x50,store=True)
        c.rip_lea_data(2,self.received);c.mov_imm(8,16);c.mov_imm(9,0)
        c.rip_lea_data(0,self.from_address);c.stack_int(0,0x20,store=True)
        c.stack_int(0,0x50,address=True);c.stack_int(0,0x28,store=True)
        c.rip_call_import('recvfrom');c.bytes(b'\x83\xf8\x08');c.conditional_jump(0x85,done)
        c.rip_int(0,self.received);c.rip_int(0,self.value,store=True)
        c.rip_int(0,self.has_peer);c.bytes(b'\x48\x85\xc0');c.conditional_jump(0x85,peer_known)
        for offset in (0,8):
            c.rip_int(0,self.from_address+offset);c.rip_int(0,self.peer+offset,store=True)
        c.mov_imm(0,1);c.rip_int(0,self.has_peer,store=True)
        c.label(peer_known);c.label(done);c.rip_load_data(0,self.value);self.ret(0x68)

    def emit_send(self):
        c=self.code;self.frame('send',0x38)
        done=self.owner.label('send_done')
        c.rip_int(1,self.socket);c.bytes(b'\x48\x83\xf9\xff');c.conditional_jump(0x84,done)
        c.rip_int(0,self.has_peer);c.bytes(b'\x48\x85\xc0');c.conditional_jump(0x84,done)
        c.rip_lea_data(2,self.sending);c.mov_imm(8,8);c.mov_imm(9,0)
        c.rip_lea_data(0,self.peer);c.stack_int(0,0x20,store=True)
        c.mov_imm(0,16);c.stack_int(0,0x28,store=True)
        c.rip_call_import('sendto');c.label(done);self.ret(0x38)
