# Pi 5 pin map (BCM) [CHECK on the real Pi]

Copy of [design.md](../docs/design.md) 4.4. This is a frozen contract: code reads it from `common/constants.py`. Change it only through an issue and a pull request that updates both.

| Function | GPIO |
|---|---|
| Servo pan / tilt (hardware PWM) | 12 / 13 |
| Servo rod fold | 19 [CHECK PWM on Pi 5, else software PWM] |
| Motor L fwd / rev (BTS7960 RPWM / LPWM) | 17 / 27 |
| Motor R fwd / rev | 22 / 23 |
| Motor enable (all R_EN, L_EN), 10 k pull-down | 24 |
| HC-SR04 left trig / echo | 5 / 6 |
| HC-SR04 front trig / echo | 16 / 20 |
| HC-SR04 right trig / echo | 21 / 26 |
| Encoder left / right | 4 / 25 |
| LED gate (MOSFET) | 18 |
| I2C SDA / SCL (MPU6050 0x68) | 2 / 3 |

Echo pins go through a divider (1 k series, 2 k to ground). Encoders on 3.3 V. Libraries: gpiozero + lgpio (RPi.GPIO and pigpio do not work on Pi 5).
Wiring has not been checked against a built robot.
