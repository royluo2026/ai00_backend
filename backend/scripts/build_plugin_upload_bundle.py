"""Bundle an already signed release for the App's single-file upload entry."""
import argparse
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.plugin_platform.package_upload import unpack_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--signature', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, path in [('release.json', args.release), ('publisher.sig', args.signature), ('plugin.zip', args.package)]:
            archive.writestr(name, path.read_bytes())
    data = buffer.getvalue()
    unpack_bundle(data)
    with args.output.open('xb') as output:
        output.write(data)
    print(f'Created {args.output}; publisher signature will be verified against the registered key by the server.')


if __name__ == '__main__':
    main()
