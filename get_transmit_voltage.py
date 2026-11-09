#!/usr/bin/env python3
"""Print the Siemens XA transmit reference voltage in volts.

Install: python -m pip install pydicom
Usage:   python get_transmit_voltage.py "scan.dcm"
Output:  346.318 V

Reads the TransmitterCalibration field in the shared Siemens MR SDS sequence.
"""

import argparse
import math
from pathlib import Path

try:
    import pydicom
except ImportError:
    raise SystemExit("Install the dependency: python -m pip install pydicom")


def get_transmit_voltage(path):
    """Read the reference voltage without loading the image pixel payload."""
    dataset = pydicom.dcmread(path, defer_size="1 KB")
    shared = dataset.SharedFunctionalGroupsSequence[0]

    # Resolve the private creator so a different private block also works.
    shared_block = shared.private_block(0x0021, "SIEMENS MR SDS 01", create=False)
    siemens = shared_block[0xFE].value[0]
    siemens_block = siemens.private_block(0x0021, "SIEMENS MR SDS 01", create=False)
    voltage = float(siemens_block[0x38].value)
    if not math.isfinite(voltage) or voltage <= 0:
        raise ValueError("The stored transmit reference voltage is invalid.")
    return voltage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dicom_file", type=Path, help="Path to the Siemens XA DICOM file")
    args = parser.parse_args()

    try:
        voltage = get_transmit_voltage(args.dicom_file)
    except (AttributeError, IndexError, KeyError):
        parser.exit(1, "Error: Siemens XA transmit reference voltage was not found.\n")
    except (OSError, ValueError, pydicom.errors.InvalidDicomError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(f"{voltage:.3f} V")


if __name__ == "__main__":
    main()
