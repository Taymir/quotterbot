import logging

import aiogram.utils.exceptions

import settings

from aiogram import Bot, Dispatcher, executor, types

import cv2
import numpy as np

from io import BytesIO

import pytesseract

import pymongo, pymongo.errors


bot_name = "quotterbot"
bot_postfix = "_by_" + bot_name
default_emoji = u'\U00002b50'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=settings.token)
dp = Dispatcher(bot)

client = pymongo.MongoClient(host=settings.mongodb['host'], port=settings.mongodb['port'],
                             username=settings.mongodb['username'], password=settings.mongodb['password'],
                             tls=settings.mongodb['tls'])
db = client.quotterbot


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    found_user = db.users.find_one({'user_id': message.from_user.id})
    if not found_user:
        db.users.insert_one({'user_id': message.from_user.id,
                             'first_name': message.from_user.first_name,
                             'username': message.from_user.username,
                             'language_code': message.from_user.language_code,
                             'stickerset': None
                             })

    await message.reply("Welcome to quotterBot!")


@dp.message_handler(content_types=['photo', 'document', 'sticker'])
async def photo_recieved(message: types.Message):
    stickerset = db.users.find_one({"user_id": message.from_user.id})
    if not stickerset or not stickerset['stickerset']:
        return await message.reply("Ошибка. Перед загрузкой изображения, создайте стикер-пак командой /new")
    stickerset = stickerset['stickerset']

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

    res = await bot.add_sticker_to_set(user_id=message.from_user.id, name=stickerset,
                                       png_sticker=sticker.file_id, emojis=default_emoji)
    sticker_set = await bot.get_sticker_set(name=stickerset)
    sticker = sticker_set.stickers[-1].file_id
    db.stickers.insert_one({"user_id": message.from_user.id, "sticker": sticker, "text": text})
    await message.answer_sticker(sticker)


@dp.message_handler(commands=['new'])
async def create_stickerset(message: types.Message):
    params = message.text.split(" ")
    if len(params) > 1:
        name = params[1]
        if not name.endswith(bot_postfix):
            name += bot_postfix
        title = name
        if len(params) > 2:
            title = params[2]

        file = types.input_file.InputFile('./download/logo.png')
        sticker = await bot.upload_sticker_file(user_id=message.from_user.id, png_sticker=file)
        try:
            await bot.create_new_sticker_set(message.from_user.id, name, title, emojis=default_emoji, png_sticker=sticker.file_id)
        except Exception as e:
            return await message.reply(str(e))

        db.users.update_one({"user_id": message.from_user.id}, {"$set": {"stickerset": name}})
        await message.reply("http://t.me/addstickers/" + name)
    else:
        await message.reply("TODO: вывод кнопок для создания стикерпака")


@dp.message_handler(commands=['use'])
async def use_stickerset(message: types.Message):
    params = message.text.split(" ")
    if len(params) > 1:
        stickerset_name = params[1]

        if not stickerset_name.endswith(bot_postfix):
            return await message.reply(f"Ошибка: стикерпак должен заканчиваться на \"{bot_postfix}\"")

        sticker_set = await bot.get_sticker_set(name=stickerset_name)

        try:
            db.uses.insert_one({"user_id": message.from_user.id, "stickerset": stickerset_name})
        except pymongo.errors.DuplicateKeyError:
            await message.reply("Вами уже был подключен стикерпак: http://t.me/addstickers/" + stickerset_name)
        else:
            await message.reply("Вы подключили стикерпак: http://t.me/addstickers/" + stickerset_name)
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

