"""Device ids must separate machines and stay stable for one machine.

The bug: ids were the first 10 base64 characters of the seed, i.e. its first
7 letters, so every Windows instant scan shared AFL-V2LUZG93CY -- different
machines merged into one device history.
"""
import re

from afterlife import passport as P

FORMAT = re.compile(r"^AFL-[A-Z2-7]{10}$")


def scan(**kw):
    base = dict(os="Windows 11", gpu="Intel Iris Xe", cpu_cores=8, ram_gb=8, architecture="x86")
    return {**base, **kw}



def test_two_windows_machines_get_different_instant_ids():
    a = P.scan_device_id(scan(gpu="Intel Iris Xe"))
    b = P.scan_device_id(scan(gpu="NVIDIA GeForce RTX 3050"))
    assert a != b


def test_the_same_machine_keeps_its_id():
    assert P.scan_device_id(scan()) == P.scan_device_id(scan())


def test_format_is_unchanged():
    assert FORMAT.match(P.scan_device_id(scan()))


def test_the_collided_id_is_gone():
    assert P.scan_device_id(scan()) != "AFL-V2LUZG93CY"
