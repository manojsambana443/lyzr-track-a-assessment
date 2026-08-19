import csv


def load_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
