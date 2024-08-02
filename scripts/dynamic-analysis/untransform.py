#!/usr/bin/env python3
import sys, os

print(f"untransforming {sys.argv[1]}....")
first_half_lines = []
second_half_lines = []
lines = []
if os.path.isfile(sys.argv[1]):
    with open(sys.argv[1], "r") as f:
        # Remove all until last marker
        for line in f:

            if "BEGINNING-JS-TRANSFORM-MARKER-THINGY" in line: 
                first_half_lines = lines 
                lines = []
            if "END-JS-TRANSFORM-MARKER-THINGY" in line:
                lines = []
            else:
                lines.append(line)
    second_half_lines = lines 
    with open(sys.argv[1], "w+") as f:
        for line in first_half_lines: 
            f.write(line)    
        for line in second_half_lines:
            f.write(line)
print("untransforming done!")