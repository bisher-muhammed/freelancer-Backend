from rest_framework.throttling import UserRateThrottle

class ZegoTokenRateThrottle(UserRateThrottle):
    scope = "zego_token"
