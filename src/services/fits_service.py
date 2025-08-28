# app/service/fits_service.py
from astropy.io import fits

def read_fits(file_path):
    with fits.open(file_path) as hdul:
        hdul.info()  # 구조 확인용 (콘솔 출력)
        data = hdul[0].data
        header = hdul[0].header
    return data, header
