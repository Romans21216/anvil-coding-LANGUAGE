"""Anvil-owned x64 mouse state, queries and Win32 message handling."""

import struct


class NativeMouse:
    IMPORTS = [("USER32.dll", name) for name in
               ("SetCapture", "GetCapture", "ReleaseCapture", "TrackMouseEvent")]

    def __init__(self, window):
        self.window = window
        self.owner = window.owner
        self.code = window.code
        self.held = self.owner.reserve_data(b"\0" * 24)
        self.pressed = self.owner.reserve_data(b"\0" * 24)
        self.wheel = self.owner.reserve_data(b"\0" * 8)
        self.x = self.owner.reserve_data(struct.pack("<dd", -1, -1))
        self.y = self.x + 8
        self.track = self.owner.reserve_data(struct.pack("<IIQQ", 24, 2, 0, 0))
        self.messages = {message: self.owner.label("mouse_message") for message in
                         (0x200, 0x201, 0x202, 0x204, 0x205, 0x207, 0x208,
                          0x20A, 0x2A3, 0x215)}

    def emit_query(self, name, button=None):
        if name in ("mouse_x", "mouse_y"):
            self.code.call("native:" + name)
        else:
            offset = self.wheel if name == "mouse_wheel" else (
                self.held if name == "mouse_held" else self.pressed) + button * 8
            self.code.rip_load_data(0, offset)

    def clear(self, offsets):
        self.code.mov_imm(0, 0)
        for offset in offsets:
            self.code.rip_int(0, offset, store=True)

    def clear_edges(self):
        self.clear([self.pressed + index * 8 for index in range(3)] + [self.wheel])

    def clear_focus(self):
        self.clear_edges()
        self.clear([self.held + index * 8 for index in range(3)])
        self.invalidate_position()
        self.release_capture()

    def invalidate_position(self):
        self.owner.emit_float(-1)
        for offset in (self.x, self.y):
            self.code.rip_store_data(0, offset)

    def release_capture(self):
        done = self.owner.label("mouse_capture_released")
        self.window.call("GetCapture")
        self.code.stack_int(1, self.window.HWND)
        self.code.bytes(b"\x48\x39\xc8")  # cmp rax,rcx
        self.code.conditional_jump(0x85, done)
        self.window.call("ReleaseCapture")
        self.code.label(done)

    def emit_dispatch(self):
        for message, label in self.messages.items():
            self.code.bytes(b"\x81\xfa" + struct.pack("<I", message))
            self.code.conditional_jump(0x84, label)

    def _position(self):
        # LPARAM contains two signed 16-bit client coordinates. R9 stays intact.
        for offset, high in ((self.x, False), (self.y, True)):
            self.code.bytes(b"\x4c\x89\xc8")  # mov rax,r9
            if high:
                self.code.bytes(b"\x48\xc1\xe8\x10")
            self.code.bytes(b"\x48\x0f\xbf\xc0\xf2\x48\x0f\x2a\xc0")
            self.code.rip_store_data(0, offset)

    def emit_handlers(self):
        c = self.code
        w = self.window
        for message, label in self.messages.items():
            c.label(label)
            if message == 0x200:
                self._position()
                c.stack_int(0, w.HWND)
                c.rip_int(0, self.track + 8, store=True)
                c.rip_lea_data(1, self.track)
                w.call("TrackMouseEvent")
            elif message == 0x2A3:
                self.invalidate_position()
            elif message == 0x215:
                same = self.owner.label("same_mouse_capture")
                c.stack_int(0, w.HWND)
                c.bytes(b"\x49\x39\xc1")  # cmp r9,rax (new capture HWND)
                c.conditional_jump(0x84, same)
                self.clear([self.held + i * 8 for i in range(3)])
                c.label(same)
            elif message == 0x20A:
                c.bytes(b"\x4c\x89\xc0\x48\xc1\xe8\x10\x48\x0f\xbf\xc0")
                c.bytes(b"\xf2\x48\x0f\x2a\xc0")
                w._double_xmm1(120)
                c.bytes(b"\xf2\x0f\x5e\xc1")
                c.rip_load_data(1, self.wheel)
                c.bytes(b"\xf2\x0f\x58\xc1")
                c.rip_store_data(0, self.wheel)
            else:
                self._position()
                index = {0x201: 0, 0x202: 0, 0x204: 1, 0x205: 1,
                         0x207: 2, 0x208: 2}[message]
                offset = self.held + index * 8
                if message in (0x201, 0x204, 0x207):
                    already = self.owner.label("mouse_already_down")
                    c.rip_int(0, offset)
                    c.bytes(b"\x48\x85\xc0")
                    c.conditional_jump(0x85, already)
                    self.owner.emit_float(1)
                    c.rip_store_data(0, self.pressed + index * 8)
                    c.label(already)
                    self.owner.emit_float(1)
                    c.rip_store_data(0, offset)
                    c.stack_int(1, w.HWND)
                    w.call("SetCapture")
                else:
                    self.clear([offset])
                    still_down = self.owner.label("mouse_still_down")
                    for i in range(3):
                        c.rip_int(0, self.held + i * 8)
                        c.bytes(b"\x48\x85\xc0")
                        c.conditional_jump(0x85, still_down)
                    self.release_capture()
                    c.label(still_down)
            c.mov_imm(0, 0)
            w.return_frame(w.FRAME)

    def emit_helpers(self):
        c = self.code
        w = self.window
        for name, offset in (("mouse_x", self.x), ("mouse_y", self.y)):
            c.label("native:" + name)
            w.frame(0x48)
            invalid = self.owner.label("mouse_outside_client")
            done = self.owner.label("mouse_coordinate_done")
            # Query the client bounds of this generated window.
            c.rip_int(1, w.window_handle)
            c.stack_int(2, 32, address=True)
            w.call("GetClientRect")
            c.bytes(b"\x85\xc0")
            c.conditional_jump(0x84, invalid)
            for position, dimension in ((self.x, 40), (self.y, 44)):
                c.rip_load_data(0, position)
                c.bytes(b"\x66\x0f\xef\xc9\x66\x0f\x2e\xc1")
                c.conditional_jump(0x82, invalid)
                c.stack_int(0, dimension)
                c.bytes(b"\xf2\x0f\x2a\xc8\x66\x0f\x2e\xc1")
                c.conditional_jump(0x83, invalid)
            c.rip_load_data(0, offset)
            c.jump(done)
            c.label(invalid)
            self.owner.emit_float(-1)
            c.label(done)
            w.return_frame(0x48)
