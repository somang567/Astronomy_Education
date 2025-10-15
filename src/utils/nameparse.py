import re
from datetime import datetime

# 예: nxst_20241106_225310.658925_l1 혹은 nxst_20241106_225310.658925_l1_chA
NAME_RE = re.compile(
    r'^(?P<prefix>[a-z0-9]+)_(?P<date>\d{8})_(?P<time>\d{6}\.\d+)_l(?P<level>\d+)(?:_(?P<chan>[A-Za-z0-9]+))?$',
    re.IGNORECASE
)

def parse_stem(stem: str):
    """
    stem: 확장자 제거한 파일명
    return: dict(prefix,date,time,level,chan, dt) or None
    """
    m = NAME_RE.match(stem)
    if not m:
        return None
    d = m.groupdict()
    dt = datetime.strptime(f"{d['date']} {d['time']}", "%Y%m%d %H%M%S.%f")
    d["dt"] = dt
    return d
