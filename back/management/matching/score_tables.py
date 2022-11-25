"""
This files strores all the scores in a readble parasable manner
user below helpers to transform them to numpy arrays
"""
import numpy as np

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
