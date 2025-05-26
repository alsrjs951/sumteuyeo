from googletrans import Translator
from asgiref.sync import sync_to_async

translator = Translator()

@sync_to_async
def translate_to_korean(text):
    return translator.translate(text, dest="ko").text

@sync_to_async
def translate_to_original(text, dest):
    return translator.translate(text, dest=dest).text
