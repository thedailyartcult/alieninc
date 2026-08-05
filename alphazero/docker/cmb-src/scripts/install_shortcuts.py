#!/usr/bin/env python3
"""Install desktop and Start Menu shortcuts for the CMB dashboard WebUI.

    cmb-dashboard --install-shortcuts     # creates shortcuts interactively
    cmb-dashboard --install-shortcuts --silent  # no prompts

Shortcuts created on each platform:

* Windows   — Desktop .lnk + Start Menu .lnk (requires PowerShell)
* macOS     — Desktop .app bundle                    (no Start Menu analogue)
* Linux     — Desktop .desktop file                  (XDG-compliant)

Each shortcut runs ``cmb-dashboard`` which starts the server and opens
the browser. Requires ``cmb`` to be pip-installed with the ``[server]``
extra.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _icon_path(base: str) -> str:
    return str(Path(base) / "cmb" / "static" / "cmb.ico")


def _desktop_path(system: str, home: Path) -> Path:
    """Locate the Desktop folder using the same Windows known-folder API as installation."""
    if system != "Windows":
        return home / "Desktop"
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "[Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return home / "Desktop"
    desktop = result.stdout.strip()
    return Path(desktop) if desktop else home / "Desktop"


def _shortcut_paths(system: str, desktop: Path, start_menu: Path, *, home: Path) -> list[Path]:
    """Return only the exact launcher artifacts this installer owns."""
    if system == "Windows":
        return [
            desktop / "CMB Dashboard.lnk",
            desktop / "CMB Dashboard.bat",
            start_menu / "CMB" / "CMB Dashboard.lnk",
        ]
    if system == "Darwin":
        return [
            desktop / "CMB Dashboard.app",
            home / "Applications" / "CMB Dashboard.app",
        ]
    return [
        desktop / "cmb-dashboard.desktop",
        home / ".local" / "share" / "applications" / "cmb-dashboard.desktop",
    ]


def _remove_shortcuts(system: str, desktop: Path, start_menu: Path, *, home: Path) -> list[Path]:
    """Remove known launcher artifacts, leaving all neighboring user files untouched."""
    removed: list[Path] = []
    for path in _shortcut_paths(system, desktop, start_menu, home=home):
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                continue
        except FileNotFoundError:
            continue
        removed.append(path)
    return removed



def _windows(desktop: Path, start_menu: Path, args: argparse.Namespace) -> None:
    ps_cmd = f"""
#Requires -Version 5.1
$WshShell = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:ProgramData "Microsoft\\Windows\\Start Menu\\Programs"

# Desktop shortcut
$lnk = $WshShell.CreateShortcut((Join-Path $desktop "CMB Dashboard.lnk"))
$lnk.TargetPath = "cmb-dashboard.exe"    # resolved via PATH
$lnk.Arguments = ""
$lnk.WorkingDirectory = (Get-Location).Path
$lnk.IconLocation = "{args.icon}"
$lnk.Description = "CMB Dashboard WebUI — local AI memory engine"
$lnk.Save()
Write-Host "  Desktop shortcut created."

# Start Menu shortcut (per-user)
$smDir = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\CMB"
if (!(Test-Path $smDir)) {{ New-Item -ItemType Directory -Path $smDir | Out-Null }}
$lnk2 = $WshShell.CreateShortcut((Join-Path $smDir "CMB Dashboard.lnk"))
$lnk2.TargetPath = "cmb-dashboard.exe"
$lnk2.Arguments = ""
$lnk2.WorkingDirectory = (Get-Location).Path
$lnk2.IconLocation = "{args.icon}"
$lnk2.Description = "CMB Dashboard WebUI"
$lnk2.Save()
Write-Host "  Start Menu shortcut created."
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            check=True, capture_output=True, text=True)
        print("  Desktop shortcut created.")
        print("  Start Menu shortcut created.")
    except subprocess.CalledProcessError as exc:
        print(f"  ⚠ PowerShell shortcut creation failed: {exc.stderr.strip()}", file=sys.stderr)
        print("  Falling back to a simple .bat launcher on Desktop.", file=sys.stderr)
        # Don't `start` the URL here — cmb-dashboard already opens the
        # browser itself once the server is actually ready. Doing both opens
        # two tabs (one immediately, dead until the server boots; one live).
        bat = desktop / "CMB Dashboard.bat"
        bat.write_text('@echo off\ncmb-dashboard\n'
                       'echo.\necho Dashboard stopped. Press any key.\npause >nul\n')
        print(f"  Desktop launcher created: {bat}")


def _macos(desktop: Path, args: argparse.Namespace) -> None:
    app_dir = Path.home() / "Applications" / "CMB Dashboard.app"
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"

    # Clean and rebuild
    if app_dir.exists():
        shutil.rmtree(app_dir)
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    launcher = macos_dir / "cmb-dashboard"
    launcher.write_text(f"""#!/bin/bash
    cd "{Path.cwd()}"
    cmb-dashboard
""")
    launcher.chmod(0o755)

    # Copy icon
    ico_src = Path(args.icon)
    if ico_src.exists():
        shutil.copy2(ico_src, resources / "cmb.icns")

    (contents / "Info.plist").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>CMB Dashboard</string>
    <key>CFBundleDisplayName</key>
    <string>CMB Dashboard</string>
    <key>CFBundleIdentifier</key>
    <string>dev.cmb.dashboard</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>cmb-dashboard</string>
    <key>CFBundleIconFile</key>
    <string>cmb.icns</string>
    <key>LSBackgroundOnly</key>
    <string>0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.14</string>
</dict>
</plist>""")

    # Symlink to Desktop
    desktop_link = desktop / "CMB Dashboard.app"
    if desktop_link.exists() or desktop_link.is_symlink():
        desktop_link.unlink()
    desktop_link.symlink_to(app_dir)

    print(f"  Application created: {app_dir}")
    print("  Desktop alias created.")


def _linux(desktop: Path, args: argparse.Namespace) -> None:
    desktop_file_path = desktop / "cmb-dashboard.desktop"
    app_dir = Path.home() / ".local" / "share" / "applications"
    app_dir.mkdir(parents=True, exist_ok=True)

    desktop_file = f"""[Desktop Entry]
Type=Application
Name=CMB Dashboard
Comment=Local AI memory engine WebUI
Exec=cmb-dashboard
Icon={args.icon}
Terminal=false
Categories=Development;Utility;
Keywords=AI;memory;agent;dashboard;
StartupWMClass=cmb-dashboard
"""

    desktop_file_path.write_text(desktop_file)
    desktop_file_path.chmod(0o755)

    # Also install to applications directory for Start Menu
    app_entry = app_dir / "cmb-dashboard.desktop"
    shutil.copy2(desktop_file_path, app_entry)
    os.chmod(app_entry, 0o755)

    print(f"  Desktop shortcut created: {desktop_file_path}")
    print(f"  Application menu entry created: {app_entry}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Install desktop/Start Menu shortcuts for CMB Dashboard.")
    ap.add_argument("--silent", action="store_true",
                    help="Skip confirmation prompts.")
    ap.add_argument("--icon",
                    default=_icon_path(os.path.dirname(os.path.dirname(__file__))),
                    help="Path to the icon file.")
    ap.add_argument("--uninstall", action="store_true",
                    help="Remove previously installed shortcuts.")
    args = ap.parse_args()

    system = platform.system()
    home = Path.home()
    desktop = _desktop_path(system, home)
    start_menu = (Path(os.environ.get("APPDATA", ""))
                  / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    if args.uninstall:
        print("Removing shortcuts...")
        removed = _remove_shortcuts(system, desktop, start_menu, home=home)
        if removed:
            for path in removed:
                print(f"  Removed: {path}")
        else:
            print("  No CMB shortcuts were found.")
        return

    if not desktop.exists():
        desktop = home / "Desktop"
    if not desktop.exists():
        print("Could not locate the Desktop folder.", file=sys.stderr)
        sys.exit(1)

    if not args.silent:
        print("CMB Dashboard — Shortcut Installer")
        print(f"  Platform: {system}")
        print("  Command:  cmb-dashboard (opens http://127.0.0.1:8700)")
        print(f"  Icon:     {args.icon}")
        print()
        ok = input("Create shortcuts? [Y/n] ").strip().lower()
        if ok not in ("", "y", "yes"):
            sys.exit(0)

    print("Creating shortcuts...")

    if system == "Windows":
        _windows(desktop, start_menu, args)
    elif system == "Darwin":
        _macos(desktop, args)
    else:
        _linux(desktop, args)

    print()
    print("Done. Double-click the shortcut to open the CMB dashboard.")
    print("  http://127.0.0.1:8700")
    print()


if __name__ == "__main__":
    main()
