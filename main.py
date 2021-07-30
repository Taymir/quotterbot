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
    #TODO: On start, add user to DB


#@dp.message_handler()
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

    res = await bot.add_sticker_to_set(user_id=message.from_user.id, name='quotes_by_quotterbot',
                                       png_sticker=sticker.file_id, emojis=u'\U00002b50')
    print(res)
    sticker_set = await bot.get_sticker_set(name='quotes_by_quotterbot')
    print(sticker_set)
    #todo: добавить стикер в текущий стикерпак юзера.
    #Если пака нет, вывести ошибку

    await message.answer_sticker(sticker_set.stickers[-1].file_id)

@dp.message_handler(commands=['pack'])
async def get_stickerpack(message: types.Message):
    sticker_set = await bot.get_sticker_set(name='FreeFlyQuotes')

    await message.answer_sticker(sticker_set.stickers[-1].file_id)
    await message.reply("http://t.me/addstickers/FreeFlyQuotes")

@dp.message_handler(commands=['new'])
async def create_stickerpack(message: types.Message):
    params = message.text.split(" ")
    if len(params) > 1:
        await message.reply("TODO: Обработка команды для создания стикерпака")
        #Todo: Запросить name и title (?), сохранить пак с пустым стикером?
        #сохранить в бд текущий стикерсет для юзера
    else:
        await message.reply("TODO: вывод кнопок для создания стикерпака")


@dp.message_handler(commands=['load'])#Todo: переименовать в use?
async def load_stickerpack(message: types.Message):
    params = message.text.split(" ")
    if len(params) > 1:
        stickerset_name = params[1]

        if not stickerset_name.endswith("by_quotterbot"):
            return await message.reply("Ошибка: стикерпак должен заканчиваться на \"by_quotterbot\"")

        sticker_set = await bot.get_sticker_set(name=stickerset_name)
        await message.reply("http://t.me/addstickers/" + stickerset_name)
        await message.answer_sticker(sticker_set.stickers[-1].file_id)
        #TODO: Добавить в БД, что user_id использует данный стикер-сет
    else:
        await message.reply("TODO: вывод кнопок для использования стикерпака")

@dp.message_handler(commands=['test'])
async def test_function(message: types.Message):
    markup = types.reply_keyboard.ReplyKeyboardMarkup([
        [types.reply_keyboard.KeyboardButton("Option 1")],
        [types.reply_keyboard.KeyboardButton("Option 2")],
        [types.reply_keyboard.KeyboardButton("Option 3")]
    ])
    await message.reply("Ок, выберите пункт меню", reply_markup=markup)

def thumbnail_img(img):
    max_size = 512
    (h, w, _) = img.shape

    (wR, hR) = (max_size / n for n in (w, h))
    r = min(wR, hR)
    new_size = tuple(int(round(n * r)) for n in (w, h))

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

