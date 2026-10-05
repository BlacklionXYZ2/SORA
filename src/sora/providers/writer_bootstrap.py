"""Start an owned writer only after Core assigns this waiting process to its job.

Use an unbuffered single byte handshake so App Server's subsequent JSON stdin is
inherited untouched. Children inherit the non-breakaway Windows job at creation.
"""

import os
import subprocess
import sys

if __name__ == "__main__":
    if os.read(0, 1) != b"\n":
        sys.exit(125)
    sys.exit(subprocess.call(sys.argv[1:]))
