try:
    import Image
except ImportError:
    from PIL import Image

import pytesseract

import cv2
import numpy as np

from os import walk
import os

def ocr(filename):
    print("---------------------")
    print(filename + ": ")
    try:
        # img = Image.open(bio)
        img = cv2.imread(os.path.join('download', filename))

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (0, 0), fx=3, fy=3)

        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        gray = cv2.bitwise_not(thresh)
        average = gray.mean(axis=0).mean(axis=0)
        if average < 100:
            gray = cv2.bitwise_not(gray)

        text = pytesseract.image_to_string(gray, lang='rus')
        print(text)
        print("------------------")
        thumb = thumbnail_img(img)

        cv2.imwrite(os.path.join('download', 'res', filename), thumb)

    except Exception as e:
        print(e)


def thumbnail_img(img):
    max_size = 512
    (h, w, _) = img.shape
    if h > max_size or w > max_size:
        (wR, hR) = (max_size / n for n in (w, h))
        r = min(wR, hR)
        new_size = tuple(int(n * r) for n in (w, h))
        img = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)

    return img

def main():
    filenames = next(walk("./download"), (None, None, []))[2]
    for file in filenames:
        ocr(file)

# Проблемы:
# 1. не всегда threshold правильно убирает фон: где-то он становится черным, где-то белым, где-то текст исчезает.
# Как найти золотую середину?
# 2. Как выделить на скрине только текст и вырезать аву, и другие графические элементы? Они мешают распознаванию
# 3. Натренировать tesseract на стандартный шрифт телеграмма?

if __name__ == '__main__':
    main()
