import logging
import settings

from aiogram import Bot, Dispatcher, executor, types

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
    file_bytes = np.asarray(bytearray(bio.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_ANYCOLOR)
    text = ocr_img(img)
    print(text)
    thumb = thumbnail_img(img)
    is_success, buffer = cv2.imencode(".webp", thumb, [cv2.IMWRITE_WEBP_QUALITY, 100])
    thumb = BytesIO(buffer)

    file = types.input_file.InputFile(thumb, filename="quote.webp")
    sticker = await bot.upload_sticker_file(user_id=message.from_user.id, png_sticker=file)
    print(sticker.file_id)

    #res = await bot.create_new_sticker_set(user_id=message.from_user.id, name='quotes_by_quotterbot',
    #                                       title='Quotes', png_sticker=sticker.file_id, emojis=u'\U000026C4')
    res = await bot.add_sticker_to_set(user_id=message.from_user.id, name='quotes_by_quotterbot',
                                           png_sticker=sticker.file_id, emojis=u'\U000026C4')
    print(res)
    sticker_set = await bot.get_sticker_set(name='quotes_by_quotterbot')
    print(sticker_set)

    #await bot.send_sticker(chat_id=message.from_user.id, sticker=sticker.file_id)
    await message.answer_sticker(sticker_set.stickers[-1].file_id)
    #await bot.send_sticker(chat_id=message.from_user.id, sticker="CAACAgIAAxkBAAECmAlg807JU13P-DO7gjUEaMx5tz-9pAACEwAD8vr4C5NCBfcWVIQhIAQ")
    #img.thumbnail((512, 512))
    #cv2.imwrite('download/file.png', gray)
    #img.save('download/file.png')

    #await message.answer("Текст: " + text)


def thumbnail_img(img):
    max_size = 512
    (h, w, _) = img.shape

    (wR, hR) = (max_size / n for n in (w, h))
    r = min(wR, hR)
    new_size = tuple(int(round(n * r)) for n in (w, h))
    print(new_size)

    img = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)

    return img


def ocr_img(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (0, 0), fx=3, fy=3)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gray = cv2.bitwise_not(thresh)
    average = gray.mean(axis=0).mean(axis=0)
    if average < 100:
        gray = cv2.bitwise_not(gray)

    text = pytesseract.image_to_string(gray, lang='rus')
    return text


def main():
    try:
        executor.start_polling(dp, skip_updates=True)
    except KeyboardInterrupt:
        print("Received exit, exiting")


if __name__ == '__main__':
    main()

