#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys

from bridge_core import (
    SHARED_DIR,
    restart_tunnel,
    start_file_server,
    start_tunnel,
    to_markdown,
    upload_file_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a local image as a public HTTPS link for IDE agents."
    )
    parser.add_argument(
        "image",
        nargs="?",
        help="Path to a local image file to publish",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print only markdown output",
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help="Print only the public URL",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the local server and Cloudflare tunnel, then exit",
    )
    parser.add_argument(
        "--restart-tunnel",
        action="store_true",
        help="Restart the Cloudflare tunnel and print the new base URL",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove imgbridge, command wrappers, and the install directory",
    )
    args = parser.parse_args()

    try:
        if args.uninstall:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            uninstall_sh = os.path.join(script_dir, "uninstall.sh")
            if not os.path.isfile(uninstall_sh):
                print("uninstall.sh was not found next to imgbridge.py", file=sys.stderr)
                return 1
            return subprocess.call(["bash", uninstall_sh])
        if args.restart_tunnel:
            url = restart_tunnel()
            if not url:
                print("Failed to restart Cloudflare tunnel.", file=sys.stderr)
                return 1
            print(url)
            return 0

        if args.serve:
            start_file_server()
            url = start_tunnel()
            if not url:
                print("Failed to start Cloudflare tunnel.", file=sys.stderr)
                return 1
            print(f"Server running on port 8999")
            print(f"Shared directory: {SHARED_DIR}")
            print(f"Tunnel: {url}")
            return 0

        if not args.image:
            parser.print_help()
            return 1

        public_url, _filename = upload_file_path(args.image)
        markdown = to_markdown(public_url)

        if args.markdown:
            print(markdown)
        elif args.url_only:
            print(public_url)
        else:
            print(public_url)
            print(markdown)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
