#!/usr/bin/env python
import sys

def read_input(file):
    for line in file:
        # split the line into words
        yield line

def main():
    data = read_input(sys.stdin)
    for line in data:
        # remove leading and trailing whitespace
        line = line.strip()
        # extract cellar id, e.g., cellar:e2bd631d-1f1d-4dd9-aa4b-61af9b2045cd.0001.02
        cellar_id = line.split(',')[1]
        # use work part of cellar id as key, e.g., e2bd631d-1f1d-4dd9-aa4b-61af9b2045cd
        key = cellar_id.split('.')[0].split(':')[1]
        # output to stdout, e.g.,
        print('%s\t%s' %(key,line))

if __name__ == "__main__":
    main()
