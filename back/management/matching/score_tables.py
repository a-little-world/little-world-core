"""
This files strores all the scores in a readble parasable manner
user below helpers to transform them to numpy arrays
"""
import numpy as np


def raw_sheets_print_to_md(data):
    # This is just cause tim is too lazy to convert the tables to markdown
    # So he made a helper that simply allowes to copy paste the data from a goole sheet
    # TODO: they should all the in markdown format directly ( or some other format )
    rows = []
    _rows = data.split("\n")
    for r in _rows:
        _rn = r.replace("\t", " | ")
        if _rn != "":
            rows.append(_rn)

    return '\n'.join(rows)


helping_group: str = r"""
| v\l |  0 |  1 |  2 | 3  |
|:---:|:--:|:--:|:--:|----|
|  0  | 25 | 30 | 20 | 20 |
|  1  |  0 | 25 |  0 | 0  |
| 2   | 0  | 0  | 25 | 0  |
| 3   | 0  | 0  | 0  | 25 |
"""

helping_group_msg: str = r"""
| v\l |  0       |  1       |  2     |  3     |
|:---:|:--------:|:--------:|:------:|:------:|
|  0  | both:any | v:any    | v:any  | v:any  |
|  1  |  -       | matching |  -     | -      |
|  2  |  -       | -        |matching| -      |
|  3  |  -       | -        |  -     |matching|
"""

language_level: str = r"""
| v\l |  0       |  1       |  2     |  3     |
|:---:|:--------:|:--------:|:------:|:------:|
|  0  | 30       | 20       | 15     | 10     |
|  1  |  0       | 30       |   20   | 15     |
|  2  |  0       | 0        |   30   | 20     |
|  3  |  0       | 0        |  0     | 30     |
"""

language_level_msg: str = raw_sheets_print_to_md(r"""
Volunteer	0	1	2	3
0	Matching	V: lower possible	V: lower possible	V: lower possible
1	NOT matching	Matching	V: lower possible	V: lower possible
2	NOT matching	NOT matching	Matching	V: lower possible
3	NOT matching	NOT matching	NOT matching	Matching
""")

partner_location: str = raw_sheets_print_to_md(r"""
Volunteer	0	1	2
0	40	X	25
1	X	15	10
2	25	10	5 
""")

partner_location_msg: str = raw_sheets_print_to_md(r"""
Volunteer	0	1	2
0	! Caution, CLOSE ! V: close (TODO) L:  close(TODO)	no match - far & close 	! Caution, CLOSE ! V: close (TODO) L:  any (TODO)
1	no match - far & close 	V: far L: far	V: far L: any
2	! Caution, CLOSE ! V: any (TODO) L:  close (TODO)	V: any L: far	V: any L: any
""")


def markdown_to_nparray(markdown_string):
    # 1 - we load the all into an array format
    matrix = []
    lines = markdown_string.split("\n")
    for l in lines:
        if not all([":" in l, "---" in l]) and l != '':
            _r = [a.replace(" ", "") for a in l.split("|") if a != '']
            matrix.append(_r)

    # 2 - then we strip the rows and colum indexes so it contains only the raw data
    indexes = dict(x=matrix[0][1:], y=[item[0] for item in matrix[1:]])
    _matrix = []
    for m in matrix[1:]:
        _matrix.append(m[1:])

    return np.array(_matrix)
