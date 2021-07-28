import logging
import settings

from aiogram import Bot, Dispatcher, executor, types

try:
    import Image
except ImportError:
    from PIL import Image

import cv2
import numpy as np

from io import BytesIO

import pytesseract


logging.basicConfig(level=logging.INFO)
bot = Bot(token=settings.token)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    """
    This handler will be called when user sends `/start` or `/help` command
    """
    await message.reply("Hi!\nI'm EchoBot!\nPowered by aiogram.")


@dp.message_handler()
async def echo(message: types.Message):
    # old style:
    # await bot.send_message(message.chat.id, message.text)

    await message.answer(message.text)


@dp.message_handler(content_types=['photo', 'document', 'sticker'])
async def photo_recieved(message: types.Message):
    if len(message.photo):
        photo = message.photo[-1]
    elif message.document:
        photo = message.document
    elif message.sticker:
        photo = message.sticker

    bio = BytesIO()
    await photo.download(bio)
    #img = Image.open(bio)
    #img2 = cv2.imread(bio)
    file_bytes = np.asarray(bytearray(bio.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_ANYCOLOR)
    gray = img
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, (0, 0), fx=4, fy=4)

    #gray, img_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    #gray = cv2.bitwise_not(img_bin)
    #kernel = np.ones((2, 1), np.uint8)
    #img = cv2.erode(gray, kernel, iterations=1)
    #img = cv2.dilate(img, kernel, iterations=1)
    #img = img_binkernel = np.ones((5,5),np.uint8)
    #kernel = np.ones((5, 5), np.uint8)
    #gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)

    gray, img_bin = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
    gray = cv2.bitwise_not(img_bin)

    text = pytesseract.image_to_string(gray, lang='rus+eng')

    #img.thumbnail((512, 512))
    cv2.imwrite('download/file.png', gray)
    #img.save('download/file.png')

    await message.answer("Текст: " + text)


def main():
    try:
        executor.start_polling(dp, skip_updates=True)
    except KeyboardInterrupt:
        print("Received exit, exiting")


if __name__ == '__main__':
    main()

