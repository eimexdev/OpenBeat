from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


def resolve_payload_root() -> Path:
    if hasattr(sys, '_MEIPASS'):
        return Path(getattr(sys, '_MEIPASS')) / 'payload'
    return Path(__file__).resolve().parent / 'payload'


def default_resolve_root() -> Path:
    appdata = Path.home() / 'AppData' / 'Roaming'
    if 'APPDATA' in os.environ:
        appdata = Path(os.environ['APPDATA'])
    return appdata / 'Blackmagic Design' / 'DaVinci Resolve' / 'Support' / 'Fusion'


def default_log_path() -> Path:
    appdata = Path.home() / 'AppData' / 'Roaming'
    if 'APPDATA' in os.environ:
        appdata = Path(os.environ['APPDATA'])
    return appdata / 'Blackmagic Design' / 'DaVinci Resolve' / 'Support' / 'logs' / 'OpenBeat.log'


def resolve_process_running() -> bool:
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq Resolve.exe'],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    return 'Resolve.exe' in result.stdout


def installed_runtime_exe(module_target: Path) -> Path:
    onedir_exe = module_target / 'bin' / 'openbeat' / 'openbeat.exe'
    if onedir_exe.exists():
        return onedir_exe
    return module_target / 'bin' / 'openbeat.exe'


def open_path(path: Path) -> None:
    target = path if path.is_dir() else path.parent
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
    os.startfile(str(target))


def install_openbeat(destination: Path) -> dict[str, str]:
    payload = resolve_payload_root()
    resolve_root = destination.expanduser()

    utility_target = resolve_root / 'Scripts' / 'Utility' / 'OpenBeat'
    module_target = resolve_root / 'Modules' / 'OpenBeat'

    (resolve_root / 'Scripts' / 'Utility').mkdir(parents=True, exist_ok=True)
    (resolve_root / 'Modules').mkdir(parents=True, exist_ok=True)

    if utility_target.exists():
        shutil.rmtree(utility_target)
    if module_target.exists():
        shutil.rmtree(module_target)

    shutil.copytree(payload / 'Utility' / 'OpenBeat', utility_target)
    shutil.copytree(payload / 'Modules' / 'OpenBeat', module_target)
    (module_target / 'bin').mkdir(parents=True, exist_ok=True)
    shutil.copytree(payload / 'bin', module_target / 'bin', dirs_exist_ok=True)

    exe_path = installed_runtime_exe(module_target)
    config_text = f'return {{\n  python_bin = "{exe_path.as_posix()}",\n}}\n'
    (module_target / 'OpenBeatConfig.local.lua').write_text(config_text, encoding='utf-8')
    return {
        'destination': str(resolve_root),
        'utility_target': str(utility_target),
        'module_target': str(module_target),
        'runtime': str(exe_path),
        'log_path': str(default_log_path()),
    }


class InstallerWizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title('OpenBeat Setup')
        self.geometry('720x520')
        self.minsize(640, 460)
        self.resizable(False, False)
        self.protocol('WM_DELETE_WINDOW', self.cancel)

        self.step = 0
        self.install_error: str | None = None
        self.install_result: dict[str, str] | None = None
        self.destination = default_resolve_root()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.configure(background='#f6f7f9')

        self.content = ttk.Frame(self, padding=(28, 24, 28, 18))
        self.content.grid(row=0, column=0, sticky='nsew')
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(5, weight=1)

        self.nav = ttk.Frame(self, padding=(18, 12))
        self.nav.grid(row=1, column=0, sticky='ew')
        self.nav.columnconfigure(0, weight=1)

        self.back_button = ttk.Button(self.nav, text='< Back', command=self.go_back)
        self.next_button = ttk.Button(self.nav, text='Next >', command=self.go_next)
        self.cancel_button = ttk.Button(self.nav, text='Cancel', command=self.cancel)
        self.back_button.grid(row=0, column=1, padx=(0, 8))
        self.next_button.grid(row=0, column=2, padx=(0, 8))
        self.cancel_button.grid(row=0, column=3)

        self.frames = [
            self.welcome_step,
            self.ready_step,
            self.installing_step,
            self.finish_step,
        ]
        self.show_step(0)

    def clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def add_heading(self, title: str, body: str) -> None:
        ttk.Label(self.content, text=title, font=('Segoe UI', 18, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 12)
        )
        ttk.Label(self.content, text=body, wraplength=640, justify='left').grid(
            row=1, column=0, sticky='nw'
        )

    def show_step(self, step: int) -> None:
        self.step = step
        self.clear_content()
        self.frames[step]()

        self.back_button.configure(state='normal' if step == 1 else 'disabled')
        self.cancel_button.configure(state='normal' if step not in (2, 3) else 'disabled')

        if step == 1:
            self.next_button.configure(text='Install', state='normal')
        elif step == 2:
            self.next_button.configure(text='Next >', state='disabled')
        elif step == 3:
            self.next_button.configure(text='Finish', state='normal')
        else:
            self.next_button.configure(text='Next >', state='normal')

    def welcome_step(self) -> None:
        self.add_heading(
            'Welcome to OpenBeat Setup',
            'This wizard will install the OpenBeat scripts and bundled runtime for DaVinci Resolve. Close Resolve before continuing if it is currently open.',
        )

    def ready_step(self) -> None:
        self.add_heading(
            'Ready to Install',
            'OpenBeat will be copied into a DaVinci Resolve Fusion support folder and configured to use the bundled runtime.',
        )
        summary = ttk.LabelFrame(self.content, text='Install summary', padding=14)
        summary.grid(row=2, column=0, sticky='ew', pady=(24, 0))
        summary.columnconfigure(1, weight=1)
        ttk.Label(summary, text='Destination').grid(row=0, column=0, sticky='nw', padx=(0, 12))
        ttk.Label(summary, text=str(self.destination), wraplength=500).grid(row=0, column=1, sticky='w')
        ttk.Button(summary, text='Copy', command=lambda: self.copy_to_clipboard(str(self.destination))).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(summary, text='Runtime').grid(row=1, column=0, sticky='nw', padx=(0, 12), pady=(10, 0))
        ttk.Label(summary, text='Bundled OpenBeat runtime, no separate Python setup needed.', wraplength=470).grid(
            row=1, column=1, columnspan=2, sticky='w', pady=(10, 0)
        )

        if resolve_process_running():
            warning = ttk.Label(
                self.content,
                text='DaVinci Resolve appears to be running. Close it before installing so the script menu reloads cleanly.',
                wraplength=640,
                foreground='#8a4b00',
            )
            warning.grid(row=3, column=0, sticky='w', pady=(16, 0))

    def copy_to_clipboard(self, value: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()

    def open_install_folder(self) -> None:
        result = self.install_result or {'destination': str(self.destination)}
        open_path(Path(result['destination']))

    def open_log_location(self) -> None:
        result = self.install_result or {'log_path': str(default_log_path())}
        open_path(Path(result['log_path']))

    def installing_step(self) -> None:
        self.add_heading('Installing OpenBeat', 'Please wait while setup copies files into Resolve.')
        self.progress = ttk.Progressbar(self.content, mode='indeterminate')
        self.progress.grid(row=2, column=0, sticky='ew', pady=(24, 8))
        self.status = ttk.Label(self.content, text='Preparing install...')
        self.status.grid(row=3, column=0, sticky='w')
        self.progress.start(12)

    def finish_step(self) -> None:
        if self.install_error:
            self.add_heading(
                'Installation Did Not Complete',
                f'OpenBeat could not be installed.\n\n{self.install_error}',
            )
            actions = ttk.Frame(self.content)
            actions.grid(row=2, column=0, sticky='w', pady=(24, 0))
            ttk.Button(actions, text='Open install folder', command=self.open_install_folder).grid(row=0, column=0, padx=(0, 8))
            ttk.Button(actions, text='Open log folder', command=self.open_log_location).grid(row=0, column=1, padx=(0, 8))
            return

        self.add_heading(
            'OpenBeat Setup Complete',
            'OpenBeat has been installed successfully. Restart DaVinci Resolve if it is open, then use Workspace > Scripts > OpenBeat.',
        )
        result = self.install_result or {}
        summary = ttk.LabelFrame(self.content, text='Installed files', padding=14)
        summary.grid(row=2, column=0, sticky='ew', pady=(24, 0))
        summary.columnconfigure(1, weight=1)
        rows = [
            ('Scripts', result.get('utility_target', '')),
            ('Runtime', result.get('runtime', '')),
            ('Log file', result.get('log_path', str(default_log_path()))),
        ]
        for row_index, (label, value) in enumerate(rows):
            ttk.Label(summary, text=label).grid(row=row_index, column=0, sticky='nw', padx=(0, 12), pady=(0, 8))
            ttk.Label(summary, text=value, wraplength=500).grid(row=row_index, column=1, sticky='w', pady=(0, 8))

        actions = ttk.Frame(self.content)
        actions.grid(row=3, column=0, sticky='w', pady=(18, 0))
        ttk.Button(actions, text='Open install folder', command=self.open_install_folder).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text='Open log folder', command=self.open_log_location).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text='Copy destination', command=lambda: self.copy_to_clipboard(result.get('destination', ''))).grid(row=0, column=2)

    def go_back(self) -> None:
        if self.step > 0:
            self.show_step(self.step - 1)

    def go_next(self) -> None:
        if self.step == 3:
            self.destroy()
            return
        if self.step == 1:
            self.start_install()
            return
        self.show_step(self.step + 1)

    def cancel(self) -> None:
        if self.step == 2:
            messagebox.showinfo('OpenBeat Setup', 'Setup is currently installing OpenBeat.')
            return
        if messagebox.askyesno('Cancel Setup', 'Are you sure you want to cancel OpenBeat Setup?'):
            self.destroy()

    def start_install(self) -> None:
        if resolve_process_running():
            should_continue = messagebox.askyesno(
                'DaVinci Resolve Is Running',
                'DaVinci Resolve appears to be running. Close it before installing for the cleanest result. Continue anyway?',
            )
            if not should_continue:
                return

        self.install_error = None
        self.install_result = None
        destination = self.destination.expanduser()
        self.show_step(2)

        def worker() -> None:
            try:
                self.install_result = install_openbeat(destination)
            except Exception as exc:
                self.install_error = str(exc)
            self.after(0, self.install_finished)

        threading.Thread(target=worker, daemon=True).start()

    def install_finished(self) -> None:
        if hasattr(self, 'progress'):
            self.progress.stop()
        self.show_step(3)


def main() -> int:
    InstallerWizard().mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
