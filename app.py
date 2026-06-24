from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from google.protobuf.message import DecodeError
import os
import sys

app = Flask(__name__)

# 🔥 Fix: Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# OB54 Configuration
RELEASE_VERSION = "OB54"
UNITY_VERSION = "2018.4.11f1"
USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)"
AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

def load_tokens(server_name):
    try:
        # 🔥 Fix: Use absolute path for Vercel
        base_path = "/tmp" if os.path.exists("/tmp") else "."
        
        if server_name == "IND":
            file_path = os.path.join(base_path, "token_ind.json")
        elif server_name in {"BR", "US", "SAC", "NA"}:
            file_path = os.path.join(base_path, "token_br.json")
        else:
            file_path = os.path.join(base_path, "token_bd.json")
            
        if not os.path.exists(file_path):
            # 🔥 Fallback: Try current directory
            file_path = file_path.replace("/tmp/", "")
            
        with open(file_path, "r") as f:
            tokens = json.load(f)
        return tokens
    except Exception as e:
        app.logger.error(f"Error loading tokens: {e}")
        return None

def encrypt_message(plaintext):
    try:
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Encryption error: {e}")
        return None

def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Protobuf create error: {e}")
        return None

async def send_request(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': USER_AGENT,
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-Unity-Version': UNITY_VERSION,
            'X-GA': "v1 1",
            'ReleaseVersion': RELEASE_VERSION
        }
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=edata, headers=headers, ssl=False) as response:
                if response.status != 200:
                    return None
                return await response.text()
    except Exception as e:
        app.logger.error(f"send_request error: {e}")
        return None

async def send_multiple_requests(uid, server_name, url):
    try:
        protobuf_message = create_protobuf_message(uid, server_name)
        if protobuf_message is None:
            return None
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            return None
            
        tokens = load_tokens(server_name)
        if tokens is None:
            return None
            
        tasks = []
        for i in range(50):  # 🔥 Reduced from 100 to 50 for Vercel timeout
            token = tokens[i % len(tokens)]["token"]
            tasks.append(send_request(encrypted_uid, token, url))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    except Exception as e:
        app.logger.error(f"send_multiple_requests error: {e}")
        return None

def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"create_protobuf error: {e}")
        return None

def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    return encrypt_message(protobuf_data)

def make_request(encrypt, server_name, token):
    try:
        if server_name == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
            
        edata = bytes.fromhex(encrypt)
        headers = {
            'User-Agent': USER_AGENT,
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-Unity-Version': UNITY_VERSION,
            'X-GA': "v1 1",
            'ReleaseVersion': RELEASE_VERSION
        }
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=30)
        
        if response.status_code != 200:
            return None
            
        binary = response.content
        return decode_protobuf(binary)
    except Exception as e:
        app.logger.error(f"make_request error: {e}")
        return None

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except Exception as e:
        app.logger.error(f"Protobuf decode error: {e}")
        return None

@app.route('/like', methods=['GET'])
def handle_requests():
    try:
        uid = request.args.get("uid")
        server_name = request.args.get("server_name", "").upper()

        if not uid or not server_name:
            return jsonify({"error": "UID and server_name are required"}), 400

        # 🔥 Fix: Run async in a safe way
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            tokens = load_tokens(server_name)
            if tokens is None:
                return jsonify({"error": "Failed to load tokens"}), 500
                
            token = tokens[0]['token']
            encrypted_uid = enc(uid)
            if encrypted_uid is None:
                return jsonify({"error": "Encryption failed"}), 500

            # Get before data
            before = make_request(encrypted_uid, server_name, token)
            if before is None:
                return jsonify({"error": "Failed to get player info"}), 500
                
            try:
                jsone = MessageToJson(before)
                data_before = json.loads(jsone)
                before_like = int(data_before.get('AccountInfo', {}).get('Likes', 0))
                before_level = int(data_before.get('AccountInfo', {}).get('Level', 0))
            except Exception as e:
                app.logger.error(f"Parse before error: {e}")
                before_like = 0
                before_level = 0

            # Get Like URL
            if server_name == "IND":
                url = "https://client.ind.freefiremobile.com/LikeProfile"
            elif server_name in {"BR", "US", "SAC", "NA"}:
                url = "https://client.us.freefiremobile.com/LikeProfile"
            else:
                url = "https://clientbp.ggpolarbear.com/LikeProfile"

            # Send likes
            loop.run_until_complete(send_multiple_requests(uid, server_name, url))

            # Get after data
            after = make_request(encrypted_uid, server_name, token)
            if after is None:
                return jsonify({"error": "Failed to get after info"}), 500
                
            try:
                jsone_after = MessageToJson(after)
                data_after = json.loads(jsone_after)
                after_like = int(data_after.get('AccountInfo', {}).get('Likes', 0))
                after_level = int(data_after.get('AccountInfo', {}).get('Level', 0))
                player_uid = int(data_after.get('AccountInfo', {}).get('UID', 0))
                player_name = str(data_after.get('AccountInfo', {}).get('PlayerNickname', ''))
            except Exception as e:
                app.logger.error(f"Parse after error: {e}")
                return jsonify({"error": "Failed to parse response"}), 500

            like_given = after_like - before_like
            status = 1 if like_given != 0 else 2

            result = {
                "LikesGivenByAPI": like_given,
                "LikesafterCommand": after_like,
                "LikesbeforeCommand": before_like,
                "Level": after_level,
                "PlayerNickname": player_name,
                "UID": player_uid,
                "status": status,
                "ReleaseVersion": RELEASE_VERSION
            }
            
            loop.close()
            return jsonify(result)
            
        except Exception as e:
            app.logger.error(f"Process error: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            try:
                loop.close()
            except:
                pass

    except Exception as e:
        app.logger.error(f"Handler error: {e}")
        return jsonify({"error": str(e)}), 500

# 🔥 For Vercel
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "FreeFire Like API is running!", "version": RELEASE_VERSION})

# Vercel handler
def handler(request, context):
    return app(request, context)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
