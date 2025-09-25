#!/bin/bash
# Set audio device to use DAC on card 3 by default
export AUDIO_DEVICE="alsa/sysdefault:CARD=3"
sudo -E .venv/bin/python srsserver.py --production
