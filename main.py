import logging
import typing

import aiogram.utils.exceptions

import settings
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.callback_data import CallbackData
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineQuery, \
    InputTextMessageContent, InlineQueryResultArticle, InlineQueryResultCachedSticker
import cv2
import numpy as np
from io import BytesIO
import pytesseract
import pymongo, pymongo.errors
from bson.objectid import ObjectId
import html
import re


bot_name = "quotterbot"
bot_postfix = "_by_" + bot_name
default_emoji = u'\U00002b50'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=settings.token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class States(StatesGroup):
    editText = State()
    useStickerPack = State()
    createStickerPack1 = State()
    createStickerPack2 = State()


client = pymongo.MongoClient(host=settings.mongodb['host'], port=settings.mongodb['port'],
                             username=settings.mongodb['username'], password=settings.mongodb['password'],
                             tls=settings.mongodb['tls'])
db = client.quotterbot

cb_stickers = CallbackData('sticker', 'id', 'action')


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

    await help_command(message)


@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
    await message.reply("Добро пожаловать! \n"
                        f"Подключите стикерсет для использования коммандой /use [название стикерсета_{bot_postfix}] или"
                        "создайте свой стикерсет коммандой /create."
                        f"После этого вы сможете использовать тег @{bot_name} для поиска по тексту в стикерах")


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
    img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)
    if message.caption:
        text = message.caption
    else:
        text = ocr_img(img)
    thumb = thumbnail_img(img)
    is_success, buffer = cv2.imencode(".webp", thumb, [cv2.IMWRITE_WEBP_QUALITY, 100])
    thumb = BytesIO(buffer)

    file = types.input_file.InputFile(thumb, filename="quote.webp")
    sticker = await bot.upload_sticker_file(user_id=message.from_user.id, png_sticker=file)

    res = await bot.add_sticker_to_set(user_id=message.from_user.id, name=stickerset,
                                       png_sticker=sticker.file_id, emojis=default_emoji)
    sticker_set = await bot.get_sticker_set(name=stickerset)
    sticker = sticker_set.stickers[-1].file_id
    sticker_unique_id = sticker_set.stickers[-1].file_unique_id
    res = db.stickers.insert_one({"user_id": message.from_user.id, "sticker": sticker,
                                  'sticker_unique_id': sticker_unique_id, "stickerset": stickerset, "text": text})

    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.row(
        types.InlineKeyboardButton('DEL', callback_data=cb_stickers.new(id=res.inserted_id, action='del')),
        types.InlineKeyboardButton('EDIT', callback_data=cb_stickers.new(id=res.inserted_id, action='edit'))
    )

    msg = await message.answer_sticker(sticker, reply_markup=markup)
    await msg.reply('<b>Текст:</b>\n <code>' + text + "</code>", parse_mode="HTML")


@dp.callback_query_handler(cb_stickers.filter(action='del'))
async def sticker_del(query: types.CallbackQuery, callback_data: typing.Dict[str, str]):
    sticker = db.stickers.find_one({'_id': ObjectId(callback_data['id'])})

    await bot.delete_sticker_from_set(sticker['sticker'])
    await query.message.delete()
    db.stickers.delete_one({'_id': ObjectId(callback_data['id'])})
    return await query.answer('Sticker deleted')


@dp.callback_query_handler(cb_stickers.filter(action='edit'))
async def sticker_edit(query: types.CallbackQuery, callback_data: typing.Dict[str, str], state: FSMContext):
    sticker = db.stickers.find_one({'_id': ObjectId(callback_data['id'])})
    text = html.escape(sticker['text'])

    await query.message.reply('<b>Текст на стикере:</b>\n <code>' + text +
                              "</code>\n <b>Введите новый текст или /cancel для отмены</b>", parse_mode="HTML")

    await States.editText.set()
    await state.update_data(id=callback_data['id'])


@dp.message_handler(state='*', commands='cancel')
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.finish()
    await message.reply("Отмена.")


@dp.message_handler(state=States.editText)
async def sticker_editing(message: types.Message, state: FSMContext):
    text = html.escape(message.text)
    data = await state.get_data()
    sticker_id = data.get("id")
    db.stickers.update_one({"_id": ObjectId(sticker_id)}, {"$set": {"text": text}})

    await message.answer(f"Текст для стикера сохранен:\n <code>{text}</code>", parse_mode="HTML")
    await state.finish()


@dp.message_handler(commands=['new'])
async def create_stickerset(message: types.Message):
    user = db.users.find_one({"user_id": message.from_user.id})
    if user['stickerset']:
        return await message.answer("Ошибка: вы уже создали стикерсет. На данный момент бот может работать"
                                    " только с одним активным стикерсетом.")

    params = message.text.split(" ")
    if len(params) > 1:
        name = params[1]
        if not name.endswith(bot_postfix):
            name += bot_postfix
        title = name
        if len(params) > 2:
            title = params[2]

        await create_stickerset_ex(message, name, title)
    else:
        await message.reply("Введите название стикерпака, который хотите создать ")
        #                    f"(Оно должно заканчиваться на {bot_postfix})")
        await States.createStickerPack1.set()


@dp.message_handler(state=States.createStickerPack1)
async def create_stickerset1_fsm(message: types.Message, state: FSMContext):
    title = message.text
    async with state.proxy() as data:
        data['title'] = title
    await message.reply("Введите короткий адрес стикерпака "
                        f"(Он должен заканчиваться на {bot_postfix})")
    await States.createStickerPack2.set()


@dp.message_handler(state=States.createStickerPack2)
async def create_stickerset2_fsm(message: types.Message, state: FSMContext):
    name = message.text
    if not name.endswith(bot_postfix):
        return await message.answer(f"Ошибка: Название стикерпака должно заканчиваться на {bot_postfix}")
    async with state.proxy() as data:
        title = data['title']

    if await create_stickerset_ex(message, name, title):
        await state.finish()


async def create_stickerset_ex(message: types.Message, name, title):
    file = types.input_file.InputFile('./download/logo.png')
    sticker = await bot.upload_sticker_file(user_id=message.from_user.id, png_sticker=file)
    try:
        await bot.create_new_sticker_set(message.from_user.id, name, title, emojis=default_emoji,
                                         png_sticker=sticker.file_id)
    except Exception as e:
        err_text = str(e)
        if err_text == "Sticker set name is already occupied":
            err_text = "Такой адрес стикерпака уже занят, попробуйте другой"
        await message.reply(str(e))
        return False

    db.users.update_one({"user_id": message.from_user.id}, {"$set": {"stickerset": name}})
    db.uses.insert_one({"user_id": message.from_user.id, "stickerset": name})
    await message.reply("http://t.me/addstickers/" + name)
    return True


@dp.message_handler(commands=['use'])
async def use_stickerset(message: types.Message):
    params = message.text.split(" ")
    if len(params) > 1:
        stickerset_name = params[1]

        await use_stickerset_ex(message, stickerset_name)
    else:
        await message.reply(f"Введите название стикерпака, который хотите использовать "
                            f"(Оно должно заканчиваться на {bot_postfix})")
        await States.useStickerPack.set()


@dp.message_handler(state=States.useStickerPack)
async def use_stickerset_fsm(message: types.Message, state: FSMContext):
    stickerset_name = message.text
    if await use_stickerset_ex(message, message.text):
        await state.finish()


async def use_stickerset_ex(message: types.Message, stickerset_name: str):
    if not stickerset_name.endswith(bot_postfix):
        await message.reply(f"Ошибка: стикерпак должен заканчиваться на \"{bot_postfix}\"")
        return False

    try:
        sticker_set = await bot.get_sticker_set(name=stickerset_name)
    except aiogram.utils.exceptions.InvalidStickersSet:
        await message.reply("Ошибка: стикерпак не найден")
        return False

    try:
        db.uses.insert_one({"user_id": message.from_user.id, "stickerset": stickerset_name})
    except pymongo.errors.DuplicateKeyError:
        await message.reply("Вами уже был подключен стикерпак: http://t.me/addstickers/" + stickerset_name)
        return False

    await message.reply("Вы подключили стикерпак: http://t.me/addstickers/" + stickerset_name)
    return True


@dp.message_handler(commands=['del'])
async def del_last_sticker_function(message: types.Message):
    params = message.text.split(" ")
    if len(params) > 1:
        stickerset_name = params[1]
    else:
        return await message.answer("Отсутствует стикерпак")

    try:
        stickerset = await bot.get_sticker_set(stickerset_name)
    except Exception as e:
        return await message.answer(str(e))

    if len(stickerset.stickers) < 1:
        return await message.answer("Стикеров не осталось")
    sticker = stickerset.stickers[-1].file_id
    sticker_unique_id = stickerset.stickers[-1].file_unique_id
    await bot.delete_sticker_from_set(sticker)

    res = db.stickers.delete_one({'sticker_unique_id': sticker_unique_id})

    return await message.answer("Последний стикер удален")


@dp.inline_handler()
async def inline_request(inline_query: InlineQuery):
    text = inline_query.query
    if not text:
        return
    # select stickersets, that user is using
    stickersets = db.uses.find({'user_id': inline_query.from_user.id})
    stickersets = [s['stickerset'] for s in stickersets]
    stickers = db.stickers.find({'stickerset': {'$in': stickersets}, '$text': {'$search': text}})

    items = []
    for sticker in stickers:
        item = InlineQueryResultCachedSticker(
            id=str(sticker['_id']),
            sticker_file_id=sticker['sticker'],
        )
        items.append(item)

    await bot.answer_inline_query(inline_query.id, results=items, cache_time=1)


def thumbnail_img(img):
    max_size = 512
    (h, w, _) = img.shape

    if (w <= max_size and h <= max_size) and (w == max_size or h == max_size):
        # no need to resize
        return img

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

    text = pytesseract.image_to_string(gray, lang='rus').strip()
    text.replace("\n", " ")
    regex = r"[^A-Za-zА-Яа-я]+"
    text = re.sub(regex, " ", text)
    text = re.sub(r'\s\s+', ' ', text)
    return text


def main():
    try:
        executor.start_polling(dp, skip_updates=True)
    except KeyboardInterrupt:
        print("Received exit, exiting")


if __name__ == '__main__':
    main()

