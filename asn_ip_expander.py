"""Standalone ASN IP expander.

Run this script to use the interactive ASN browser and export the expanded
IP list to a text file.
"""

from cores.ui_asn import menu_export_asn_ips


def main():
    menu_export_asn_ips()


if __name__ == "__main__":
    main()