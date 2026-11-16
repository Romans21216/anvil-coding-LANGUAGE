"""Anvil-owned pixel surface, DIB lifetime and exact integer source-over blending."""

import struct


class NativeSurface:
    IMPORTS = [("GDI32.dll", "CreateDIBSection"), ("GDI32.dll", "GdiFlush")]
    MAX_PIXELS = 16 * 1024 * 1024  # 64 MiB of BGRX storage per surface
    FRAME = 0x88
    LEFT, TOP, RIGHT, BOTTOM, COLOUR, ALPHA = 0x20, 0x28, 0x30, 0x38, 0x40, 0x48
    SAVED_BX, SAVED_SI, SAVED_DI = 0x50, 0x58, 0x60

    def __init__(self, window):
        self.window, self.owner, self.code = window, window.owner, window.code
        self.pixels = self.owner.reserve_data(b"\0" * 8)
        self.pending_pixels = self.owner.reserve_data(b"\0" * 8)
        self.pending_gdi = self.owner.reserve_data(b"\0" * 8)
        self.info = self.owner.reserve_data(struct.pack("<IiiHHIIiiII",40,0,0,1,32,0,0,0,0,0,0)+b"\0"*4)

    def mark_gdi(self):
        self.code.mov_imm(0,1)
        self.code.rip_int(0,self.pending_gdi,store=True)

    def sync(self, failure=None):
        """Complete queued GDI work before CPU access, resize or destruction."""
        c = self.code
        ready = self.owner.label("surface_synced")
        c.rip_int(0,self.pending_gdi)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x84,ready)
        self.window.call("GdiFlush")
        if failure is not None:
            c.bytes(b"\x85\xc0")
            c.conditional_jump(0x84,failure)
        c.mov_imm(0,0)
        c.rip_int(0,self.pending_gdi,store=True)
        c.label(ready)

    def allocate(self, failure):
        w,c = self.window,self.code
        self.sync(failure)
        c.stack_int(0,w.WIDTH)
        c.stack_int(2,w.HEIGHT)
        c.bytes(b"\x48\x0f\xaf\xc2")  # positive int32 dimensions: product fits int64
        c.mov_imm(2,self.MAX_PIXELS)
        c.bytes(b"\x48\x39\xd0")
        c.conditional_jump(0x87,failure)
        c.rip_lea_data(10,self.info)
        c.stack_int(0,w.WIDTH)
        c.memory_int(0,10,4,store=True,width=4)
        c.stack_int(0,w.HEIGHT)
        c.bytes(b"\xf7\xd8")  # top-down rows
        c.memory_int(0,10,8,store=True,width=4)
        c.mov_imm(0,0)
        c.rip_int(0,self.pending_pixels,store=True)
        c.stack_int(1,w.PAINT_DC)
        c.rip_lea_data(2,self.info)
        c.mov_imm(8,0)  # DIB_RGB_COLORS
        c.rip_lea_data(9,self.pending_pixels)
        c.stack_int(0,32,store=True)  # no file-mapping handle: OS owns storage
        c.stack_int(0,40,store=True)
        w.call("CreateDIBSection")
        w.require_rax(failure)
        c.rip_int(0,w.pending_bitmap,store=True)
        c.rip_int(0,self.pending_pixels)
        w.require_rax(failure)

    def commit(self):
        c = self.code
        c.rip_int(0,self.pending_pixels)
        c.rip_int(0,self.pixels,store=True)
        c.mov_imm(0,0)
        c.rip_int(0,self.pending_pixels,store=True)

    def reset(self):
        for offset in (self.pixels,self.pending_pixels,self.pending_gdi):
            self.code.rip_int(0,offset,store=True)  # caller supplies zero in RAX

    def rectangle(self):
        """RCX -> x,y,w,h,r,g,b,a doubles. Every pixel operation is Anvil-emitted."""
        w,c,o = self.window,self.code,self.owner
        c.label("native:rectangle")
        w.frame(self.FRAME)
        for register,slot in ((3,self.SAVED_BX),(6,self.SAVED_SI),(7,self.SAVED_DI)):
            c.stack_int(register,slot,store=True)
        done,failure = o.label("rectangle_done"),o.label("rectangle_failure")
        for data in (w.hdc,self.pixels):
            c.rip_int(0,data)
            c.bytes(b"\x48\x85\xc0")
            c.conditional_jump(0x84,done)
        for index,source in enumerate((0,8,0,8)):
            c.scalar_memory(0,1,source)
            if index >= 2:
                c.scalar_memory(1,1,16 if index == 2 else 24)
                c.bytes(b"\xf2\x0f\x58\xc1")
            c.bytes(b"\x66\x0f\xef\xc9\xf2\x0f\x5f\xc1")  # max(value,0)
            c.rip_int(0,w.back_width if index % 2 == 0 else w.back_height)
            c.bytes(b"\xf2\x48\x0f\x2a\xc8\xf2\x0f\x5d\xc1")
            c.bytes(b"\xf2\x48\x0f\x2c\xc0")
            if index >= 2:
                c.bytes(b"\xf2\x48\x0f\x2a\xc8\x66\x0f\x2e\xc1")
                rounded = o.label("rectangle_ceiling")
                c.conditional_jump(0x86,rounded)
                c.bytes(b"\x48\xff\xc0")
                c.label(rounded)
            c.stack_int(0,(self.LEFT,self.TOP,self.RIGHT,self.BOTTOM)[index],store=True)
        for upper,lower in ((self.RIGHT,self.LEFT),(self.BOTTOM,self.TOP)):
            c.stack_int(0,upper)
            c.stack_int(2,lower)
            c.bytes(b"\x48\x39\xd0")
            c.conditional_jump(0x8E,done)
        c.scalar_memory(0,1,56)
        w._clamp(0.0,255.0)
        c.bytes(b"\xf2\x0f\x2c\xc0")
        c.stack_int(0,self.ALPHA,store=True)
        c.bytes(b"\x85\xc0")
        c.conditional_jump(0x84,done)
        c.bytes(b"\x45\x31\xd2")
        for index in range(3):
            c.scalar_memory(0,1,32+index*8)
            w._clamp(0.0,255.0)
            c.bytes(b"\xf2\x0f\x2c\xc0")
            if index < 2:
                c.bytes(b"\xc1\xe0"+bytes((16-index*8,)))
            c.bytes(b"\x41\x09\xc2")
        c.stack_int(10,self.COLOUR,store=True)
        self.sync(failure)
        c.stack_int(3,self.RIGHT)
        c.stack_int(0,self.LEFT)
        c.bytes(b"\x48\x29\xc3")  # RBX span width
        c.stack_int(9,self.BOTTOM)
        c.stack_int(0,self.TOP)
        c.bytes(b"\x49\x29\xc1")  # R9 remaining rows
        c.rip_int(6,w.back_width)
        c.stack_int(1,self.TOP)
        c.bytes(b"\x48\x0f\xaf\xce")
        c.stack_int(2,self.LEFT)
        c.bytes(b"\x48\x01\xd1\x48\xc1\xe1\x02")
        c.rip_int(7,self.pixels)
        c.bytes(b"\x48\x01\xcf\x48\x29\xde\x48\xc1\xe6\x02")  # row gap in RSI
        c.stack_int(0,self.ALPHA)
        opaque,alpha_row,pixel = (o.label(name) for name in
                                 ("opaque_row","alpha_row","alpha_pixel"))
        c.bytes(b"\x3d\xff\x00\x00\x00")
        c.conditional_jump(0x84,opaque)
        self._blend_constants()
        c.label(alpha_row)
        c.mov_reg(1,3)
        c.label(pixel)
        c.memory_int(0,7,width=4)
        # Four 16-bit components. (n+1+(n>>8))>>8 is exact floor(n/255)
        # for 0<=n<=65025; coefficients sum to255, so no word overflows.
        c.bytes(bytes.fromhex("66 0f 6e c0 66 0f 60 c5 66 0f d5 c4 66 0f fd c2 66 0f 6f c8 66 0f 71 d1 08 66 0f fd c3 66 0f fd c1 66 0f 71 d0 08 66 0f 67 c5 66 0f 7e c0 25 ff ff ff 00"))
        c.memory_int(0,7,store=True,width=4)
        c.bytes(b"\x48\x83\xc7\x04\x48\xff\xc9")
        c.conditional_jump(0x85,pixel)
        c.bytes(b"\x48\x01\xf7\x49\xff\xc9")
        c.conditional_jump(0x85,alpha_row)
        c.jump(done)
        c.label(opaque)
        c.stack_int(0,self.COLOUR)
        c.mov_reg(1,3)
        c.bytes(b"\xfc\xf3\xab\x48\x01\xf7\x49\xff\xc9")  # REP STOSD, advance row
        c.conditional_jump(0x85,opaque)
        c.label(done)
        for register,slot in ((3,self.SAVED_BX),(6,self.SAVED_SI),(7,self.SAVED_DI)):
            c.stack_int(register,slot)
        c.bytes(b"\x0f\x57\xc0")
        w.return_frame(self.FRAME)
        c.label(failure)
        o.emit_runtime_error("Anvil native rectangle error\n")

    def _blend_constants(self):
        c = self.code
        c.stack_int(0,self.COLOUR)
        c.bytes(bytes.fromhex("66 0f ef ed 66 0f 6e d0 66 0f 60 d5"))
        c.stack_int(0,self.ALPHA)
        c.bytes(bytes.fromhex("66 0f 6e d8 f2 0f 70 db 00 66 0f d5 d3"))
        c.mov_imm(0,255)
        c.stack_int(2,self.ALPHA)
        c.bytes(bytes.fromhex("29 d0 66 0f 6e e0 f2 0f 70 e4 00"))
        c.mov_imm(0,1)
        c.bytes(bytes.fromhex("66 0f 6e d8 f2 0f 70 db 00"))
