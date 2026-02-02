#!/usr/bin/env python -u
# coding:utf-8
import json
import random
import time
import struct
import binascii
from Crypto.Cipher import AES

ERROR_CODE_SUCCESS = 0
ERROR_CODE_APP_ID_INVALID = 1
ERROR_CODE_USER_ID_INVALID = 3
ERROR_CODE_SECRET_INVALID = 5
ERROR_CODE_EFFECTIVE_TIME_IN_SECONDS_INVALID = 6

class TokenInfo:
    def __init__(self, token, error_code, error_message):
        self.token = token
        self.error_code = error_code
        self.error_message = error_message

def __make_nonce():
    return random.getrandbits(31)

def __make_random_iv():
    chars = '0123456789abcdefghijklmnopqrstuvwxyz'
    return ''.join(chars[random.randint(0, 15)] for _ in range(16))

def __aes_pkcs5_padding(text, block_size):
    padding = block_size - len(text.encode('utf-8')) % block_size
    return text + chr(padding) * padding

def __aes_encrypt(plain_text, key, iv):
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    padded = __aes_pkcs5_padding(plain_text, 16)
    return cipher.encrypt(padded.encode('utf-8'))

def generate_token04(app_id, user_id, secret, effective_time_in_seconds, payload):
    if not isinstance(app_id, int) or app_id == 0:
        return TokenInfo("", ERROR_CODE_APP_ID_INVALID, "appID invalid")
    if not isinstance(user_id, str) or not user_id:
        return TokenInfo("", ERROR_CODE_USER_ID_INVALID, "userID invalid")
    if not isinstance(secret, str) or len(secret) != 32:
        return TokenInfo("", ERROR_CODE_SECRET_INVALID, "secret must be 32 bytes")
    if not isinstance(effective_time_in_seconds, int) or effective_time_in_seconds <= 0:
        return TokenInfo("", ERROR_CODE_EFFECTIVE_TIME_IN_SECONDS_INVALID, "invalid effective_time_in_seconds")

    now = int(time.time())
    expire = now + effective_time_in_seconds
    nonce = __make_nonce()

    _token = {"app_id": app_id, "user_id": user_id, "nonce": nonce,
              "ctime": now, "expire": expire, "payload": payload}
    plain_text = json.dumps(_token, separators=(',', ':'), ensure_ascii=False)
    iv = __make_random_iv()
    encrypt_buf = __aes_encrypt(plain_text, secret, iv)

    result_size = len(encrypt_buf) + 28
    result = bytearray(result_size)

    result[0:8] = struct.pack("!q", expire)
    result[8:10] = struct.pack("!h", len(iv))
    result[10:26] = iv.encode('utf-8')
    result[26:28] = struct.pack("!h", len(encrypt_buf))
    result[28:] = encrypt_buf

    token = "04" + binascii.b2a_base64(result, newline=False).decode()
    return TokenInfo(token, ERROR_CODE_SUCCESS, "success")
