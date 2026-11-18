OS8088 SDK INCLUDE
==================
MAKE.BAT uses tools\get_sdk.ps1 to download the pinned OS8088 format-10
os88api.inc file when it is missing. The file is saved at:
  sdk\apps\os88api.inc

Python is not used for this. The SDK is checked for compatible API
addresses before assembly. For an offline build, place the compatible
include file at that location before running MAKE.BAT.

The OS8088 SDK is MIT licensed. See THIRD-PARTY-NOTICES.TXT.
