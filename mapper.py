#!/usr/bin/env python

import sys

# input comes from STDIN (standard input)
for line in sys.stdin:
    # remove leading and trailing whitespace
    line = line.strip()
    cellar_id = line.split(',')[1]
    key = cellar_id.split('.')[0].split(':')[1]
    # split the line into words
    # increase counters
    print('%s\t%s' %(key,line))
