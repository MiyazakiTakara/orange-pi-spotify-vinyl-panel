# Orange Pi audio notes

The original target device used the analog jack through ALSA:

```text
plughw:0,0
```

Useful checks:

```bash
aplay -l
aplay -L
speaker-test -D plughw:0,0 -t wav -c 2
amixer -c 0 scontrols
```

If the jack is muted, open:

```bash
alsamixer
```

Choose the `ac200-audio` card and unmute or lower channels such as `DAC`, `Line Out` and `DAC I2S`.

Save mixer settings:

```bash
sudo alsactl store
```

If the board LEDs are annoying in a transparent case, disable them with a small systemd oneshot service:

```bash
for led in /sys/class/leds/*; do echo none | sudo tee "$led/trigger"; echo 0 | sudo tee "$led/brightness"; done
```
