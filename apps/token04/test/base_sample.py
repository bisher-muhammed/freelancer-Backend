#!/usr/bin/env python -u
# coding:utf-8

#
# Basic authentication token generation example
#

import sys
import os

# Add the root path to the system path to access the required modules
cur_path = os.path.abspath(os.path.dirname(__file__))
root_path = os.path.split(cur_path)[0]
sys.path.append(root_path)
from src import token04

if __name__ == '__main__':

    # Modify app_id to your appID, appID is a number, obtained from the ZEGO console
    # Example: 1234567890
    app_id = 

    # Modify server_secret to your serverSecret, serverSecret is a string, obtained from the ZEGO console
    # Example: "fa94dd0f974cf2e293728a526b028271"
    server_secret = 

    # Modify user_id to the user's user_id, user_id is a string
    # Example: "user1"
    user_id = "user1"

    # Token expiration time, in seconds
    effective_time_in_seconds = 3600

    # Additional configuration information
    payload = {
        "demoPayload": "" # When generating a basic authentication token, the payload should be set to an empty string
    }

    # Call the function to generate the token
    token_info = token04.generate_token04(app_id, user_id, server_secret, effective_time_in_seconds, json.dumps(payload))
    print([token_info.token, token_info.error_code, token_info.error_message])
