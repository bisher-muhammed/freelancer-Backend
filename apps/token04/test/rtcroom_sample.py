#!/usr/bin/env python -u
# coding:utf-8

#
# Permission authentication token generation example.
#

import json
import os
import sys

# Add the root path to the system path to access the required modules
cur_path = os.path.abspath(os.path.dirname(__file__))
root_path = os.path.split(cur_path)[0]
sys.path.append(root_path)
from src import token04

if __name__ == '__main__':

    # Modify app_id to your appId, appID is a number, obtained from the ZEGO console
    # Example: 1234567890
    app_id = 

    # Modify server_secret to your serverSecret, serverSecret is a string, obtained from the ZEGO console
    # Example: "fa94dd0f974cf2e293728a526b028271"
    server_secret = 

    # Modify user_id to the user's user_id, user_id is a string
    # Example: "user1"
    user_id = "user1"

    # Token expiration time, unit: seconds
    effective_time_in_seconds = 3600

    # The permission control information of the permission authentication token is controlled by the payload
    payload = {
        "room_id": "room1", # Room ID
        "privilege": {
            1 : 1, # key 1 represents room permission, value 1 represents allowed, so here means allowing room login; if the value is 0, it means not allowed
            2 : 1  # key 2 represents push permission, value 1 represents allowed, so here means allowing push; if the value is 0, it means not allowed
        }, 
        "stream_id_list": None # Passing None means that all streams can be pushed. If a streamID list is passed in, only the streamIDs in the list can be pushed
    }

    # 3600 is the token expiration time, unit: seconds
    token_info = token04.generate_token04(app_id=app_id, user_id=user_id, secret=server_secret,
                                          effective_time_in_seconds=effective_time_in_seconds, payload=json.dumps(payload))
    print([token_info.token, token_info.error_code, token_info.error_message])
