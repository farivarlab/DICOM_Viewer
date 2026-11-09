#!/usr/bin/env python3
"""Extract all non-pixel DICOM elements to JSON using pydicom.

Install:
    python -m pip install "pydicom>=3,<4"

Usage:
    python extract_dicom_metadata.py image.dcm
    python extract_dicom_metadata.py image.dcm -o metadata.json
    python extract_dicom_metadata.py image.dcm --force -o metadata.json

Includes file meta information, private tags, and nested sequences. Binary
metadata is preserved as base64 in InlineBinary. Pixel payloads are omitted.
Private values without a known definition remain encoded as raw binary.
"""

import argparse
import json
from pathlib import Path
import sys

try:
    import pydicom
except ImportError:
    raise SystemExit('Install the dependency: python -m pip install "pydicom>=3,<4"')


PIXEL_TAGS = {
    0x7FE00008,  # Float Pixel Data
    0x7FE00009,  # Double Float Pixel Data
    0x7FE00010,  # Pixel Data
}


def dataset_to_metadata(dataset):
    """Return every non-pixel element, recursively, without truncating values."""
    metadata = {}
    # Check tags before accessing values so deferred pixel data stays unread.
    for tag in sorted(dataset.keys()):
        if tag in PIXEL_TAGS:
            continue

        element = dataset[tag]
        if element.VR == "SQ":
            value = {
                "vr": "SQ",
                "Value": [dataset_to_metadata(item) for item in element.value],
            }
        else:
            # pydicom handles names, multiple values, numbers, and binary data.
            value = element.to_json_dict(
                bulk_data_element_handler=None,
                bulk_data_threshold=1024,
            )

        metadata[f"{tag:08X}"] = {
            "name": element.name,
            "keyword": element.keyword,
            **value,
        }

    return metadata


def extract_metadata(path, force=False):
    """Read the complete dataset, including tags located after pixel data."""
    dataset = pydicom.dcmread(
        path,
        force=force,
        defer_size="1 KB",
        stop_before_pixels=False,
    )
    return {
        "source_file": str(Path(path).resolve()),
        "excluded_pixel_data_tags": [f"{tag:08X}" for tag in sorted(PIXEL_TAGS)],
        "file_meta": dataset_to_metadata(dataset.file_meta),
        "dataset": dataset_to_metadata(dataset),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dicom_file", type=Path, help="Input DICOM file")
    parser.add_argument("-o", "--output", type=Path, help="Save JSON to this file")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Attempt to read a DICOM dataset without a standard file header",
    )
    args = parser.parse_args()

    try:
        if args.output and args.output.resolve() == args.dicom_file.resolve():
            parser.error("The output must be different from the input DICOM file.")

        metadata = extract_metadata(args.dicom_file, force=args.force)
        text = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
            print(f"Saved metadata to {args.output.resolve()}", file=sys.stderr)
        else:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(text)
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
