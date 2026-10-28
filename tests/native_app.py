"""A generated test process with window-local messages and global-state inspection."""

import ctypes
from ctypes import wintypes
import pathlib
import struct
import subprocess
import tempfile
import time

from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


class NativeApp:
    def __init__(self, source, *, instrument=None, source_path=None):
        self.source = source
        self.instrument = instrument
        self.source_path = source_path
        self.process = None
        self.process_handle = None
        self.hwnd = None
        self.temp = None

    def __enter__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.enum_proc, wintypes.LPARAM]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT,
                                                wintypes.WPARAM, wintypes.LPARAM,
                                                wintypes.UINT, wintypes.UINT,
                                                ctypes.POINTER(ctypes.c_size_t)]
        self.user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                                 ctypes.c_void_p, ctypes.c_size_t,
                                                 ctypes.POINTER(ctypes.c_size_t)]
        try:
            self.temp = tempfile.TemporaryDirectory()
            path = self.source_path or pathlib.Path(self.temp.name) / "input.ANVL"
            path.write_text(self.source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, self.source)
            generator = NativeCodegen(path, functions, top, variables, arrays)
            self.image = generator.generate()
            if self.instrument is not None:
                self.image = self.instrument(generator)
            self.offsets = generator._data_offsets
            pe = struct.unpack_from("<I", self.image, 0x3C)[0]
            section_count = struct.unpack_from("<H", self.image, pe + 6)[0]
            first = pe + 24 + struct.unpack_from("<H", self.image, pe + 20)[0]
            base = struct.unpack_from("<Q", self.image, pe + 48)[0]
            data = next(struct.unpack_from("<I", self.image, section + 12)[0]
                        for section in range(first, first + 40 * section_count, 40)
                        if self.image[section:section + 8].rstrip(b"\0") == b".data")
            self.data_address = base + data
            executable = pathlib.Path(self.temp.name) / "input.exe"
            executable.write_bytes(self.image)
            self.process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.process_handle = self.kernel.OpenProcess(0x410, False, self.process.pid)
            if not self.process_handle:
                raise OSError(ctypes.get_last_error(), "cannot inspect generated process")
            self.wait(self._find_window)
            return self
        except BaseException:
            self.close()
            raise

    def _find_window(self):
        @self.enum_proc
        def visit(hwnd, unused):
            owner = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == self.process.pid and self.user.IsWindowVisible(hwnd):
                self.hwnd = hwnd
            return True

        self.user.EnumWindows(visit, 0)
        return self.hwnd is not None

    def wait(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                output = self.process.communicate()
                raise AssertionError(f"generated app exited {self.process.returncode}: {output}")
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("generated app condition did not become true")

    def read(self, name):
        value = ctypes.c_double()
        size = ctypes.c_size_t()
        ok = self.kernel.ReadProcessMemory(
            self.process_handle, self.data_address + self.offsets[name],
            ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(size))
        if not ok or size.value != ctypes.sizeof(value):
            raise OSError(ctypes.get_last_error(), "cannot read generated global")
        return value.value

    def send(self, message, key=0, flags=0):
        result = ctypes.c_size_t()
        if not self.user.SendMessageTimeoutW(self.hwnd, message, key, flags, 2, 2000,
                                             ctypes.byref(result)):
            raise TimeoutError("generated window did not process its test message")
        return result.value

    def close(self):
        try:
            if self.process is not None:
                if self.process.poll() is None and self.hwnd:
                    self.user.PostMessageW(self.hwnd, 0x10, 0, 0)
                try:
                    output = self.process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    output = self.process.communicate()
                self.result = (self.process.returncode, output)
        finally:
            if self.process_handle:
                self.kernel.CloseHandle(self.process_handle)
                self.process_handle = None
            if self.temp:
                self.temp.cleanup()

    def __exit__(self, *exc):
        self.close()
