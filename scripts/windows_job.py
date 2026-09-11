"""Own the complete service process tree on Windows and POSIX."""
import os
import signal
import subprocess

class OwnedJob:
    def __init__(self):
        self.handle = None
        self.groups = {}
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', w.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def add(self, process):
        if self.handle:
            import ctypes
            if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        elif os.name != 'nt':
            try:
                self.groups[process.pid] = os.getpgid(process.pid)
            except ProcessLookupError:
                pass

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def terminate(self, process, timeout=10):
        """Stop a process and all descendants owned by its isolated group."""
        group = None
        owned_group = False
        if os.name != 'nt':
            group = self.groups.pop(process.pid, None)
            try:
                group = os.getpgid(process.pid) if group is None else group
            except ProcessLookupError:
                pass
            # The supervisor must never signal its own process group. The
            # worker starts run children with start_new_session=True below.
            owned_group = group is not None and group != os.getpgrp()
            if owned_group:
                try:
                    os.killpg(group, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
        else:
            # Closing the job applies KILL_ON_JOB_CLOSE to the full tree.
            self.close()
            if process.poll() is None:
                process.terminate()

        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if owned_group:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        finally:
            # The group leader can exit while a descendant ignores SIGTERM.
            # Escalate the still-owned group even when process.wait() did not
            # time out, otherwise an orphan can survive the supervisor.
            if owned_group:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
