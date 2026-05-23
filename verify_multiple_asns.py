#!/usr/bin/env python3
"""Verify multiple Iranian ASNs have correct CIDR expansion"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '..')

from utils.asn_engine import expand_target

print("=" * 80)
print("VERIFYING MULTIPLE ASNs FOR CIDR READING ACCURACY")
print("=" * 80)
print()

test_asns = [
    ("AS44244", "Iran Cell Service and Communication Company"),
    ("AS58224", "Iran Telecommunication Company PJS"),
    ("AS197207", "Mobile Communication Company of Iran (Hamrah)"),
    ("AS57218", "Rightel Communication Service Company"),
    ("AS31549", "Aria Shatel PJSC"),
]

expected_counts = {
    "AS44244": 330752,
    "AS58224": 2868736,
    "AS197207": 1504256,
    "AS57218": 295424,
    "AS31549": 265472,
}

all_pass = True
for asn, org in test_asns:
    print(f"[{asn}] {org}")
    try:
        ips = expand_target(asn, silent=True)
        count = len(ips)
        expected = expected_counts[asn]
        match = "✓ PASS" if count == expected else "✗ FAIL"
        print(f"  Expanded to: {count:,} IPs")
        print(f"  Expected:    {expected:,} IPs")
        print(f"  Result: {match}")
        if count != expected:
            all_pass = False
    except Exception as e:
        print(f"  ERROR: {e}")
        all_pass = False
    print()

print("=" * 80)
if all_pass:
    print("✓ ALL TESTS PASSED - No CIDR reading bugs detected!")
    print("✓ Cross-platform binaries ready for deployment")
else:
    print("✗ SOME TESTS FAILED - Review CIDR expansion logic")
    sys.exit(1)
