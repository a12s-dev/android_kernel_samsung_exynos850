#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script is needed for buildtime integrity routine.
It calculates and embeds HMAC and other needed stuff for in terms of FIPS 140-2
"""

import os
import sys
from IntegrityRoutine import IntegrityRoutine
from Utils import Utils


__author__ = "Vadym Stupakov"
__copyright__ = "Copyright (c) 2017 Samsung Electronics"
__credits__ = ["Vadym Stupakov"]
__version__ = "1.0"
__maintainer__ = "Vadym Stupakov"
__email__ = "v.stupakov@samsung.com"
__status__ = "Production"


sec_sym = {".text":     ["first_fmp_text", "last_fmp_text"],
           ".rodata":   ["first_fmp_rodata", "last_fmp_rodata"],
           "init.text": ["first_fmp_init",   "last_fmp_init"]
           }

module_name = "fmp"

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage " + sys.argv[0] + " elf_file readelf_path")
        sys.exit(-1)

    elf_file = os.path.abspath(sys.argv[1])
    # READELF is often just "llvm-readelf" (Makefile LLVM=1). abspath() would
    # turn that into $PWD/llvm-readelf which does not exist — keep bare names
    # on PATH and only absolutize real paths.
    _re = sys.argv[2]
    readelf_path = _re if os.path.sep not in _re else os.path.abspath(_re)
    modules = sys.argv[3:]

    utils = Utils()
    utils.paths_exists([elf_file])

    integrity = IntegrityRoutine(elf_file, readelf_path)
    integrity.make_integrity(sec_sym=sec_sym, module_name=module_name, debug=False, print_reloc_addrs=False,
                             sort_by="address", reverse=False)
