"""
Nmap path resolver for bundled nmap executable.
Tries bundled nmap first, falls back to system nmap.
"""

import subprocess
import os
import sys


def get_nmap_executable():
    """
    Get path to nmap executable.
    Returns path from environment variable WHITEPROXY_NMAP_PATH if set,
    otherwise searches for system nmap.
    """
    # Try environment variable set by Go application
    bundled_nmap = os.environ.get("WHITEPROXY_NMAP_PATH")
    if bundled_nmap and os.path.exists(bundled_nmap):
        return bundled_nmap
    
    # Fall back to system nmap
    nmap_path = _find_system_nmap()
    if nmap_path:
        return nmap_path
    
    return "nmap"  # Let subprocess fail with clear error if not found


def _find_system_nmap():
    """Find system nmap using which/where"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["where", "nmap"],
                capture_output=True,
                text=True,
                timeout=2
            )
        else:
            result = subprocess.run(
                ["which", "nmap"],
                capture_output=True,
                text=True,
                timeout=2
            )
        
        path = result.stdout.strip()
        if path and os.path.exists(path):
            return path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return None


def has_nmap():
    """Check if nmap is available (bundled or system)"""
    exe = get_nmap_executable()
    return exe != "nmap" or _find_system_nmap() is not None
