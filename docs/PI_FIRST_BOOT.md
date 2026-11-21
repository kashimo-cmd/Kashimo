# Pi first boot (K00)

Do these once, in order. Paste the output of step 7 into the chat.

1. **Flash.** Raspberry Pi Imager, device Pi 5, OS: Raspberry Pi OS Lite (64-bit), card: the 16 GB one. Click the gear (OS customisation): hostname `kashimo`, user `pi` and a password, your Wi-Fi name and password, country TN, time zone Africa/Tunis, enable SSH.
2. **Hardware.** Fit the active cooler. Plug the camera into a **USB 2.0 port** (black). Use the 5 V / 5 A supply. Insert the card, power on, wait 2 minutes.
3. **Connect.** CMD on the PC: `ssh pi@kashimo.local` (if it fails, find the Pi's IP on the router page and use `ssh pi@<ip>`).
4. **Update.** `sudo apt update && sudo apt full-upgrade -y && sudo reboot`, then reconnect with ssh.
5. **Tools for the probe.** `sudo apt install -y git v4l-utils i2c-tools ffmpeg`
6. **Get the probe.** Either (a) after the K00 pull request is merged: `git clone https://github.com/kashimo-cmd/Kashimo.git ~/kashimo`, or (b) now, from CMD on the PC in the Kashimo folder: `scp tools\pi_probe.sh pi@kashimo.local:~/` (then the script is `~/pi_probe.sh`).
7. **Probe.** On the Pi: `bash ~/kashimo/tools/pi_probe.sh | tee ~/probe.txt` (or `bash ~/pi_probe.sh | tee ~/probe.txt` for option b). Copy everything it prints into the chat.
8. **Fixed IP.** On the router, reserve one IP for the Pi (DHCP reservation). Write it down: it becomes `pi_ip` in `config/config.yaml`.

If the probe says `not installed` or `(command failed)` for a line, that is fine, paste it anyway.
Do not run `setup.sh` yet. K10 comes next.
