"""Demand-loaded Anvil drawing kernels and their native call boundary."""

from pathlib import Path


class NativeDrawing:
    COORDINATE_LIMIT = 1073741824.0

    def __init__(self, window):
        self.window = window
        self.owner = window.owner
        self.pending = []
        self.library = None

    def primitive(self, shape, expressions, node, scope):
        o, c = self.owner, self.owner.code
        if self.library is None:
            from compiler.parser import parse
            path = Path(__file__).resolve().parents[1] / "runtime" / "native" / "drawing.ANVL"
            self.library = parse(path, path.read_text(encoding="utf-8"))[0]
        names = [f"_anvil_native_{shape}"]
        if shape == "line":
            names.append("_anvil_native_pixel_round")
        for name in names:
            if name not in o.functions:
                o.functions[name] = self.library[name]
                self.pending.append(name)
        depth = o._scratch_depth
        slots = []
        for expression in expressions:
            o.emit_expression(expression, node.line, scope)
            slot = o.push_temp()
            o.store_local(slot)
            slots.append(slot)
        failure, ready = o.label(f"{shape}_range"), o.label(f"{shape}_ready")
        for slot in slots[:3 if shape == "circle" else 4]:
            o.load_local(slot, scope, node.line)
            o._math.constant(1, self.COORDINATE_LIMIT)
            c.bytes(b"\x66\x0f\x2e\xc1")
            c.conditional_jump(0x87, failure)
            o._math.constant(1, -self.COORDINATE_LIMIT)
            c.bytes(b"\x66\x0f\x2e\xc1")
            c.conditional_jump(0x82, failure)
        c.jump(ready)
        c.label(failure)
        o.emit_runtime_error(f"Anvil native {shape} range error at line {node.line} ({o.path})\n")
        c.label(ready)
        for data in (self.window.back_width, self.window.back_height):
            c.rip_int(0, data)
            c.bytes(b"\xf2\x48\x0f\x2a\xc0")
            slot = o.push_temp()
            o.store_local(slot)
            slots.append(slot)
        o.emit_saved_call(f"_anvil_native_{shape}", slots)
        o._scratch_depth = depth

    def emit_pending(self):
        while self.pending:
            name = self.pending.pop(0)
            self.owner._emit_function(name, self.owner.functions[name])
